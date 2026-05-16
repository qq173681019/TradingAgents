"""
统一LLM客户端 - 支持多Provider fallback

优先级: 千问(通义) → 智谱 → DeepSeek
全部使用 OpenAI 兼容接口，统一调用方式。
"""

import json
import os
import sys
import re
import time
import logging
import warnings
from typing import Optional, Dict, Any

warnings.filterwarnings('ignore', message='Unverified HTTPS request')

import requests

logger = logging.getLogger(__name__)

# 从 config 加载
_SHARED_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'TradingShared'))
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)


def _load_config():
    """延迟加载config，避免循环导入"""
    try:
        from config import (
            BAILIAN_API_KEY,
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_URL,
        )
        return {
            'qwen_key': BAILIAN_API_KEY,
            'zhipu_key': DEEPSEEK_API_KEY,
            'zhipu_url': DEEPSEEK_API_URL,
        }
    except ImportError:
        return {
            'qwen_key': '',
            'zhipu_key': '',
            'zhipu_url': '',
        }


# Provider 配置
PROVIDERS = None  # 延迟初始化


def _get_providers():
    global PROVIDERS
    if PROVIDERS is not None:
        return PROVIDERS

    cfg = _load_config()
    providers = []

    # 0. 自部署聚合网关 DeepSeek-V4-Flash (最快，内部网络) - 主力
    gateway_key = 'sk-zNz0yqnsr6JcoD5jkmfa4sc7fr9G1eEWphkv9oiGx2MnhRjv'
    gateway_url = 'https://hczqai.hczq.com:8442/v1/chat/completions'
    if gateway_key:
        providers.append({
            'name': 'Gateway-DeepSeek-V4',
            'api_key': gateway_key,
            'api_url': gateway_url,
            'model': 'DeepSeek-V4-Flash',
            'type': 'openai',
            'verify_ssl': False,
        })

    # 1. 智谱 GLM-4-Flash (免费，稳定) - 备用
    if cfg.get('zhipu_key'):
        providers.append({
            'name': 'ZhipuGLM',
            'api_key': cfg['zhipu_key'],
            'api_url': cfg['zhipu_url'] or 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            'model': 'glm-4-flash',
            'type': 'openai',
            'verify_ssl': True,
        })

    # 2. 千问/通义 (阿里百炼) - 备用
    if cfg.get('qwen_key'):
        providers.append({
            'name': 'Qwen',
            'api_key': cfg['qwen_key'],
            'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            'model': 'qwen-plus',
            'type': 'openai',
            'verify_ssl': True,
        })

    # 3. DeepSeek 官方 - 备用
    deepseek_key = 'sk-281898da205d4163a947f3af7bc5c942'
    if deepseek_key:
        providers.append({
            'name': 'DeepSeek',
            'api_key': deepseek_key,
            'api_url': 'https://api.deepseek.com/v1/chat/completions',
            'model': 'deepseek-chat',
            'type': 'openai',
            'verify_ssl': True,
        })

    PROVIDERS = providers
    return providers


class LLMClient:
    """统一LLM客户端，自动fallback"""

    def __init__(self, timeout: int = 30, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_provider = None

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.3, max_tokens: int = 2000) -> Optional[str]:
        """
        发送对话请求，自动 fallback

        Returns:
            LLM 响应文本，失败返回 None
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        providers = _get_providers()

        for provider in providers:
            for attempt in range(self.max_retries):
                try:
                    result = self._call_openai(provider, messages, temperature, max_tokens)
                    if result:
                        self._last_provider = provider['name']
                        return result
                except requests.exceptions.Timeout:
                    logger.warning(f"[{provider['name']}] 超时 (attempt {attempt+1})")
                except requests.exceptions.ConnectionError:
                    logger.warning(f"[{provider['name']}] 连接失败")
                    break  # 连接问题直接换provider
                except Exception as e:
                    err_msg = str(e)[:100]
                    logger.warning(f"[{provider['name']}] 错误: {err_msg}")
                    if '429' in err_msg:
                        time.sleep(2)
                        continue
                    break

        logger.error("所有LLM Provider均失败")
        return None

    def chat_json(self, system_prompt: str, user_prompt: str,
                  temperature: float = 0.2, max_tokens: int = 2000) -> Optional[Dict]:
        """
        发送对话并解析JSON响应

        Returns:
            解析后的dict，失败返回 None
        """
        text = self.chat(system_prompt, user_prompt, temperature, max_tokens)
        if not text:
            return None

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 提取最外层 { ... }
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        logger.warning(f"JSON解析失败，原始响应: {text[:200]}")
        return None

    def _call_openai(self, provider: dict, messages: list,
                     temperature: float, max_tokens: int) -> Optional[str]:
        """调用 OpenAI 兼容接口"""
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider['model'],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # 使用 trust_env=False 避免系统代理设置导致连接失败
        session = requests.Session()
        session.trust_env = False
        verify = provider.get('verify_ssl', True)
        resp = session.post(
            provider['api_url'],
            headers=headers,
            json=payload,
            timeout=self.timeout,
            verify=verify,
        )

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content.strip():
                return content
            raise Exception(f"空响应: {json.dumps(data)[:200]}")
        elif resp.status_code == 429:
            raise Exception(f"429 rate limited")
        else:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:150]}")

    @property
    def last_provider(self) -> Optional[str]:
        return self._last_provider


# 单例
_default_client = None

def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniMax CodingPlan Integration for Trading Agents
MiniMax API 集成模块，用于代码生成和智能分析
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class MiniMaxResponse:
    """MiniMax API 响应数据类"""
    content: str
    usage: Dict[str, int]
    model: str
    success: bool
    error: Optional[str] = None


class MiniMaxCodingPlan:
    """MiniMax CodingPlan API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 MiniMax 客户端
        
        Args:
            api_key: API 密钥，如果未提供则从环境变量加载
        """
        self.api_key = api_key or self._load_api_key()
        self.base_url = "https://api.minimax.chat"
        self.default_model = "abab6.5s-chat"
        self.session = requests.Session()
        
        if not self.api_key:
            raise ValueError("MiniMax API 密钥未找到，请设置环境变量或配置文件")
    
    def _load_api_key(self) -> Optional[str]:
        """从环境变量或配置文件加载 API 密钥"""
        # 1. 检查环境变量
        api_key = os.getenv('MINIMAX_API_KEY')
        if api_key and api_key != 'your-api-key-here':
            return api_key
        
        # 2. 检查配置文件
        config_files = ['.env.local', '.env', '.env.example']
        for config_file in config_files:
            try:
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if 'MINIMAX_API_KEY' in line and '=' in line:
                                key, value = line.split('=', 1)
                                value = value.strip().strip('"\'')
                                if value and value != 'your-api-key-here':
                                    return value
            except Exception as e:
                print(f"读取配置文件 {config_file} 失败: {e}")
        
        return None
    
    def _make_request(self, messages: List[Dict[str, str]], 
                     max_tokens: int = 1000,
                     temperature: float = 0.3,
                     model: Optional[str] = None) -> MiniMaxResponse:
        """发送请求到 MiniMax API"""
        model = model or self.default_model
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/v1/text/chatcompletion_v2",
                headers=headers,
                json=data,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and result['choices']:
                    content = result['choices'][0]['message']['content']
                    usage = result.get('usage', {})
                    
                    return MiniMaxResponse(
                        content=content,
                        usage=usage,
                        model=model,
                        success=True
                    )
                else:
                    error_msg = result.get('error', {}).get('message', '未知错误')
                    return MiniMaxResponse(
                        content="",
                        usage={},
                        model=model,
                        success=False,
                        error=error_msg
                    )
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return MiniMaxResponse(
                    content="",
                    usage={},
                    model=model,
                    success=False,
                    error=error_msg
                )
                
        except Exception as e:
            return MiniMaxResponse(
                content="",
                usage={},
                model=model,
                success=False,
                error=str(e)
            )
    
    def test_connection(self) -> bool:
        """测试 API 连接"""
        print("🔄 正在测试 MiniMax API 连接...")
        
        messages = [
            {
                "role": "user",
                "content": "你好，这是一个连接测试。请简单回复'连接成功'。"
            }
        ]
        
        response = self._make_request(messages, max_tokens=50, temperature=0.1)
        
        if response.success:
            print("[OK] MiniMax API 连接成功！")
            print(f"[WRITE] 回复内容: {response.content}")
            if response.usage:
                print(f"[CHART] 使用情况: {response.usage}")
            return True
        else:
            print(f"[FAIL] 连接失败: {response.error}")
            return False
    
    def generate_code(self, prompt: str, language: str = "python") -> MiniMaxResponse:
        """生成代码"""
        messages = [
            {
                "role": "user",
                "content": f"请生成{language}代码来实现以下需求：\n{prompt}\n\n请只返回代码，不要包含解释。"
            }
        ]
        
        return self._make_request(messages, max_tokens=2000, temperature=0.3)
    
    def analyze_code(self, code: str, language: str = "python") -> MiniMaxResponse:
        """分析代码"""
        messages = [
            {
                "role": "user",
                "content": f"请分析以下{language}代码，指出可能的问题和改进建议：\n\n```{language}\n{code}\n```"
            }
        ]
        
        return self._make_request(messages, max_tokens=1500, temperature=0.3)
    
    def optimize_code(self, code: str, language: str = "python") -> MiniMaxResponse:
        """优化代码"""
        messages = [
            {
                "role": "user",
                "content": f"请优化以下{language}代码，提高性能和可读性：\n\n```{language}\n{code}\n```\n\n请提供优化后的完整代码。"
            }
        ]
        
        return self._make_request(messages, max_tokens=2000, temperature=0.3)
    
    def explain_code(self, code: str, language: str = "python") -> MiniMaxResponse:
        """解释代码"""
        messages = [
            {
                "role": "user",
                "content": f"请解释以下{language}代码的功能和逻辑：\n\n```{language}\n{code}\n```"
            }
        ]
        
        return self._make_request(messages, max_tokens=1000, temperature=0.3)
    
    def debug_code(self, code: str, error_message: str, language: str = "python") -> MiniMaxResponse:
        """调试代码"""
        messages = [
            {
                "role": "user",
                "content": f"以下{language}代码出现了错误，请帮助调试并提供修复方案：\n\n代码：\n```{language}\n{code}\n```\n\n错误信息：\n{error_message}\n\n请提供修复后的代码。"
            }
        ]
        
        return self._make_request(messages, max_tokens=2000, temperature=0.3)
    
    def chat(self, message: str) -> MiniMaxResponse:
        """通用对话"""
        messages = [
            {
                "role": "user",
                "content": message
            }
        ]
        
        return self._make_request(messages)


def test_minimax_integration():
    """测试 MiniMax 集成功能"""
    print("🎉 MiniMax CodingPlan Python 集成测试")
    print("=" * 50)
    
    try:
        # 初始化客户端
        client = MiniMaxCodingPlan()
        
        # 测试连接
        if not client.test_connection():
            return False
        
        print("\n🔄 正在测试代码生成功能...")
        code_response = client.generate_code(
            "创建一个函数计算股票价格的移动平均线", 
            "python"
        )
        
        if code_response.success:
            print("[OK] 代码生成测试成功！")
            print(f"[WRITE] 生成的代码:\n{code_response.content}")
            if code_response.usage:
                print(f"[CHART] 使用情况: {code_response.usage}")
        else:
            print(f"[FAIL] 代码生成失败: {code_response.error}")
            return False
        
        print("\n🎉 所有测试通过！MiniMax 集成成功配置")
        return True
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        print("🔧 请检查:")
        print("   1. API 密钥是否正确")
        print("   2. 网络连接是否正常")
        print("   3. MiniMax 服务是否可用")
        return False


if __name__ == "__main__":
    test_minimax_integration()
#!/usr/bin/env python3
"""
解决地区限制问题 - 查找可用的免费模型
"""
import os
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def find_available_models():
    """查找在你的地区可用的免费模型"""
    print("=== 查找地区可用的免费模型 ===\n")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
            "X-Title": "TradingAgents"
        }
        
        print("正在获取模型列表...")
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get("data", [])
            
            # 查找免费且可能在你地区可用的模型
            available_models = []
            
            # 优先选择这些通常全球可用的模型
            preferred_providers = [
                "openai",
                "anthropic", 
                "google",
                "deepseek",
                "qwen",
                "mistral"
            ]
            
            for model in models:
                model_id = model.get("id", "")
                pricing = model.get("pricing", {})
                
                # 检查是否免费
                is_free = (
                    ":free" in model_id or 
                    pricing.get("prompt", "0") == "0" or
                    pricing.get("prompt", 0) == 0
                )
                
                if is_free:
                    # 检查是否来自首选提供商
                    provider = model_id.split("/")[0] if "/" in model_id else ""
                    if provider in preferred_providers:
                        available_models.append({
                            "id": model_id,
                            "provider": provider,
                            "name": model.get("name", ""),
                            "context_length": model.get("context_length", 0)
                        })
            
            # 按提供商排序
            available_models.sort(key=lambda x: (x["provider"], x["id"]))
            
            print(f"\n找到 {len(available_models)} 个推荐的免费模型:\n")
            
            current_provider = None
            for model in available_models:
                if model["provider"] != current_provider:
                    current_provider = model["provider"]
                    print(f"\n=== {current_provider.upper()} ===")
                
                print(f"  - {model['id']}")
                if model['context_length']:
                    print(f"    上下文长度: {model['context_length']:,}")
            
            # 推荐具体模型
            print(f"\n=== 推荐配置 ===")
            
            # 查找最佳选择
            best_models = {
                "openai": None,
                "google": None, 
                "deepseek": None,
                "anthropic": None
            }
            
            for model in available_models:
                provider = model["provider"]
                if provider in best_models and best_models[provider] is None:
                    best_models[provider] = model["id"]
            
            # 输出推荐配置
            if best_models["deepseek"]:
                print(f"\n选项1 - DeepSeek (推荐):")
                print(f'  deep_think_llm: "{best_models["deepseek"]}"')
                print(f'  quick_think_llm: "{best_models["deepseek"]}"')
                
            if best_models["google"]:
                print(f"\n选项2 - Google:")
                print(f'  deep_think_llm: "{best_models["google"]}"')
                print(f'  quick_think_llm: "{best_models["google"]}"')
                
            if best_models["openai"]:
                print(f"\n选项3 - OpenAI:")
                print(f'  deep_think_llm: "{best_models["openai"]}"')
                print(f'  quick_think_llm: "{best_models["openai"]}"')
            
            return available_models
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        return []

def test_model(model_id):
    """测试特定模型是否可用"""
    print(f"\n测试模型: {model_id}")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
            "X-Title": "TradingAgents"
        }
        
        data = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": "Hello, respond with 'Success'"}
            ],
            "max_tokens": 10
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and result["choices"]:
                content = result["choices"][0]["message"]["content"]
                print(f"  ✅ 成功: {content}")
                return True
        else:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            print(f"  ❌ 失败 ({response.status_code}): {error_data}")
            return False
            
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return False

if __name__ == "__main__":
    print("解决地区限制问题\n")
    
    models = find_available_models()
    
    if models:
        print(f"\n=== 测试推荐模型 ===")
        
        # 测试几个最有希望的模型
        test_candidates = []
        for model in models:
            if "deepseek" in model["id"].lower():
                test_candidates.append(model["id"])
            elif "google" in model["id"].lower() and "gemini" in model["id"].lower():
                test_candidates.append(model["id"])
            elif "qwen" in model["id"].lower():
                test_candidates.append(model["id"])
        
        # 限制测试数量
        for model_id in test_candidates[:3]:
            if test_model(model_id):
                print(f"\n🎉 找到可用模型: {model_id}")
                print(f"请更新配置文件使用此模型!")
                break
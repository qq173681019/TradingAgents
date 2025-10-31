#!/usr/bin/env python3
"""
详细的 OpenRouter API 诊断工具
"""
import os
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def diagnose_openrouter_key():
    """诊断 OpenRouter API 密钥"""
    print("=== OpenRouter API 密钥诊断 ===\n")
    
    # 获取 API 密钥
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到 OPENAI_API_KEY 环境变量")
        return False
    
    print(f"✓ API 密钥已找到")
    print(f"  完整密钥: {api_key}")
    print(f"  密钥长度: {len(api_key)} 字符")
    print(f"  前缀: {api_key[:15]}...")
    
    # 检查密钥格式
    if not api_key.startswith("sk-or-v1-"):
        print("⚠️  警告: API 密钥不是标准的 OpenRouter 格式")
        print("   OpenRouter 密钥通常以 'sk-or-v1-' 开头")
    else:
        print("✓ API 密钥格式看起来正确")
    
    # 检查密钥长度
    if len(api_key) < 80:
        print("⚠️  警告: API 密钥可能过短")
        print(f"   当前长度: {len(api_key)}, 通常应该 > 80 字符")
    else:
        print("✓ API 密钥长度正常")
    
    return True

def test_openrouter_models():
    """测试 OpenRouter 模型可用性"""
    print("\n=== 测试 OpenRouter 模型可用性 ===\n")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    # 测试获取模型列表
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
            "X-Title": "TradingAgents"
        }
        
        print("正在获取可用模型列表...")
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30
        )
        
        print(f"HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            models_data = response.json()
            if "data" in models_data:
                models = models_data["data"]
                print(f"✓ 成功获取 {len(models)} 个模型")
                
                # 查找我们需要的免费模型
                target_models = [
                    "meta-llama/llama-3.3-8b-instruct:free",
                    "deepseek/deepseek-chat-v3-0324:free",
                    "google/gemini-2.0-flash-exp:free"
                ]
                
                available_free_models = []
                for model in models:
                    model_id = model.get("id", "")
                    if ":free" in model_id or model.get("pricing", {}).get("prompt", "0") == "0":
                        available_free_models.append(model_id)
                
                print(f"\n找到 {len(available_free_models)} 个免费模型:")
                for model in available_free_models[:10]:  # 显示前10个
                    print(f"  - {model}")
                
                print(f"\n检查目标模型可用性:")
                for target in target_models:
                    if any(target in model.get("id", "") for model in models):
                        print(f"  ✓ {target}")
                    else:
                        print(f"  ❌ {target} - 不可用")
                        
                return True
            else:
                print("❌ 响应格式错误")
                return False
        else:
            print(f"❌ HTTP 错误: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_simple_chat():
    """测试简单的聊天请求"""
    print("\n=== 测试简单聊天请求 ===\n")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    # 使用一个通用的免费模型
    test_models = [
        "openai/gpt-3.5-turbo",  # 通常可用
        "meta-llama/llama-3.1-8b-instruct:free",
        "microsoft/wizardlm-2-8x22b"
    ]
    
    for model in test_models:
        print(f"测试模型: {model}")
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
            
            data = {
                "model": model,
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
                    print(f"  ✓ 成功: {content}")
                    return True
                else:
                    print(f"  ❌ 响应格式错误: {result}")
            else:
                print(f"  ❌ HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            
    return False

if __name__ == "__main__":
    print("OpenRouter API 完整诊断\n")
    
    # 步骤 1: 诊断密钥
    key_ok = diagnose_openrouter_key()
    
    if not key_ok:
        print("\n❌ API 密钥问题，请检查 .env 文件")
        exit(1)
    
    # 步骤 2: 测试模型列表
    models_ok = test_openrouter_models()
    
    # 步骤 3: 测试聊天
    chat_ok = test_simple_chat()
    
    print(f"\n=== 最终诊断结果 ===")
    print(f"API 密钥: {'✓' if key_ok else '❌'}")
    print(f"模型列表: {'✓' if models_ok else '❌'}")
    print(f"聊天测试: {'✓' if chat_ok else '❌'}")
    
    if key_ok and models_ok and chat_ok:
        print("\n🎉 OpenRouter 配置完全正常！")
    else:
        print("\n⚠️  存在配置问题，请检查:")
        print("1. API 密钥是否正确")
        print("2. 网络连接是否正常")
        print("3. OpenRouter 账户状态")
#!/usr/bin/env python3
"""
测试 OpenRouter API 连接
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

def test_openrouter_chat():
    """测试 OpenRouter 聊天功能"""
    print("测试 OpenRouter 聊天 API...")
    
    # 获取 API 密钥
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到 OPENAI_API_KEY 环境变量")
        return False
    
    print(f"✓ API 密钥已找到: {api_key[:20]}...")
    
    try:
        # 创建客户端 - OpenRouter 需要特定的头部
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
        )
        
        # 测试可用的免费模型
        test_models = [
            "meta-llama/llama-3.3-8b-instruct:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "google/gemini-2.0-flash-exp:free"
        ]
        
        for model in test_models:
            print(f"\n测试模型: {model}")
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": "Hello! Please respond with 'Success' if you receive this message."}
                    ],
                    max_tokens=50
                )
                
                if response.choices and response.choices[0].message:
                    print(f"✓ {model} 工作正常")
                    print(f"  响应: {response.choices[0].message.content}")
                    return True
                else:
                    print(f"❌ {model} 响应格式错误")
                    
            except Exception as e:
                print(f"❌ {model} 错误: {e}")
                continue
                
        return False
        
    except Exception as e:
        print(f"❌ OpenRouter 连接错误: {e}")
        return False

def test_openrouter_embeddings():
    """测试 OpenRouter 嵌入功能"""
    print("\n测试 OpenRouter 嵌入 API...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
                "X-Title": "TradingAgents"
            }
        )
        
        # 测试嵌入模型
        embedding_models = [
            "text-embedding-3-small",
            "text-embedding-ada-002"
        ]
        
        for model in embedding_models:
            print(f"测试嵌入模型: {model}")
            try:
                response = client.embeddings.create(
                    model=model,
                    input="This is a test sentence for embedding."
                )
                
                if response.data and response.data[0].embedding:
                    print(f"✓ {model} 嵌入成功，维度: {len(response.data[0].embedding)}")
                    return True
                else:
                    print(f"❌ {model} 嵌入失败")
                    
            except Exception as e:
                print(f"❌ {model} 错误: {e}")
                continue
                
        return False
        
    except Exception as e:
        print(f"❌ 嵌入 API 错误: {e}")
        return False

if __name__ == "__main__":
    print("=== OpenRouter API 测试 ===\n")
    
    chat_success = test_openrouter_chat()
    embed_success = test_openrouter_embeddings()
    
    print(f"\n=== 测试结果 ===")
    print(f"聊天 API: {'✓ 成功' if chat_success else '❌ 失败'}")
    print(f"嵌入 API: {'✓ 成功' if embed_success else '❌ 失败'}")
    
    if chat_success and embed_success:
        print("\n🎉 OpenRouter 配置成功！可以运行 TradingAgents。")
    else:
        print("\n⚠️  OpenRouter 配置存在问题，请检查 API 密钥和模型名称。")
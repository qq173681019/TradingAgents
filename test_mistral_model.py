import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_mistral_model():
    api_key = os.getenv("OPENAI_API_KEY")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "TradingAgents",
        "Content-Type": "application/json"
    }
    
    # 测试基本聊天
    payload = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [{"role": "user", "content": "Hello, how are you?"}],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    print("测试基本聊天...")
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应头: {response.headers}")
    
    if response.status_code == 200:
        try:
            result = response.json()
            print("✅ 基本聊天成功")
            print(f"响应: {result['choices'][0]['message']['content']}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析错误: {e}")
            print(f"原始响应内容: {response.text[:500]}")
    else:
        print(f"❌ 请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")

    # 测试工具调用
    print("\n测试工具调用...")
    tool_payload = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [{"role": "user", "content": "What's the weather like?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ],
        "max_tokens": 100
    }
    
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=tool_payload,
        timeout=30
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        try:
            result = response.json()
            print("✅ 工具调用成功")
            print(f"响应: {json.dumps(result, indent=2)}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析错误: {e}")
            print(f"原始响应内容: {response.text[:500]}")
    else:
        print(f"❌ 工具调用失败: {response.status_code}")
        print(f"错误信息: {response.text}")

if __name__ == "__main__":
    test_mistral_model()
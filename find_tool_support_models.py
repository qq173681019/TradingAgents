import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def check_models_with_tool_support():
    api_key = os.getenv("OPENAI_API_KEY")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "TradingAgents"
    }
    
    response = requests.get("https://openrouter.ai/api/v1/models", headers=headers)
    
    if response.status_code == 200:
        models = response.json()['data']
        
        # 过滤支持工具调用且免费或低成本的模型
        tool_models = []
        
        for model in models:
            model_id = model.get('id', '')
            pricing = model.get('pricing', {})
            context_length = model.get('context_length', 0)
            
            # 检查是否免费或低成本
            prompt_cost = float(pricing.get('prompt', '999'))
            completion_cost = float(pricing.get('completion', '999'))
            
            # 免费模型或者非常便宜的模型
            if prompt_cost == 0 or (prompt_cost < 0.001 and completion_cost < 0.001):
                # 测试是否支持工具调用
                test_payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "test_function",
                                "description": "A test function",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        }
                    ],
                    "max_tokens": 10
                }
                
                try:
                    test_response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=test_payload,
                        timeout=30
                    )
                    
                    if test_response.status_code == 200:
                        tool_models.append({
                            'id': model_id,
                            'prompt_cost': prompt_cost,
                            'completion_cost': completion_cost,
                            'context_length': context_length,
                            'status': 'supports_tools'
                        })
                        print(f"✅ {model_id} - 支持工具调用")
                    else:
                        print(f"❌ {model_id} - 不支持工具调用 ({test_response.status_code})")
                        
                except Exception as e:
                    print(f"⚠️ {model_id} - 测试失败: {str(e)}")
        
        print(f"\n找到 {len(tool_models)} 个支持工具调用的免费/低成本模型：")
        for model in tool_models:
            print(f"- {model['id']} (上下文长度: {model['context_length']})")
            
        return tool_models
    
    else:
        print(f"获取模型列表失败: {response.status_code}")
        return []

if __name__ == "__main__":
    models = check_models_with_tool_support()
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def check_openrouter_quota():
    api_key = os.getenv("OPENAI_API_KEY")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "TradingAgents"
    }
    
    # 获取账户信息
    try:
        response = requests.get("https://openrouter.ai/api/v1/auth/key", headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("🔑 OpenRouter 账户信息:")
            print(f"   用户ID: {data.get('data', {}).get('label', 'N/A')}")
            print(f"   剩余积分: ${data.get('data', {}).get('usage', 0)}")
            print(f"   速率限制: {data.get('data', {}).get('rate_limit', {})}")
        else:
            print(f"❌ 获取账户信息失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    
    # 解析配额重置时间
    reset_timestamp = 1761868800000  # 从错误信息中获取
    reset_time = datetime.fromtimestamp(reset_timestamp / 1000)
    current_time = datetime.now()
    
    print(f"\n⏰ 配额重置信息:")
    print(f"   重置时间: {reset_time}")
    print(f"   当前时间: {current_time}")
    
    if reset_time > current_time:
        time_diff = reset_time - current_time
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)
        print(f"   剩余等待: {hours}小时{minutes}分钟")
    else:
        print("   ✅ 配额应该已经重置！")

if __name__ == "__main__":
    check_openrouter_quota()
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def test_deepseek_api():
    """测试DeepSeek API连接"""
    
    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "your_deepseek_api_key_here":
        print("❌ DeepSeek API密钥未设置")
        print("📝 请按以下步骤获取DeepSeek API密钥：")
        print("   1. 访问 https://platform.deepseek.com/")
        print("   2. 注册账户并登录")
        print("   3. 在控制台创建API密钥")
        print("   4. 将密钥填入 .env 文件的 DEEPSEEK_API_KEY=")
        return False
    
    print(f"🔑 DeepSeek API密钥已设置: {api_key[:20]}...")
    
    try:
        # 创建DeepSeek客户端
        client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key
        )
        
        print("🔗 正在测试DeepSeek API连接...")
        
        # 测试简单的聊天完成
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的金融分析师。"},
                {"role": "user", "content": "请简单介绍一下股票技术分析。"}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        print("✅ DeepSeek API连接成功！")
        print("📊 测试响应:")
        print(f"   模型: {response.model}")
        print(f"   用量: {response.usage.total_tokens} tokens")
        print(f"   内容: {response.choices[0].message.content[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ DeepSeek API连接失败: {e}")
        print("🔧 可能的解决方案:")
        print("   1. 检查API密钥是否正确")
        print("   2. 确认网络连接正常")
        print("   3. 检查DeepSeek账户余额")
        return False

def test_deepseek_tools():
    """测试DeepSeek的工具调用功能"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "your_deepseek_api_key_here":
        print("❌ 请先设置DeepSeek API密钥")
        return False
    
    try:
        client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key
        )
        
        print("🛠️ 测试DeepSeek工具调用功能...")
        
        # 定义一个简单的工具
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_stock_price",
                    "description": "获取股票价格信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "股票代码，如AAPL"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            }
        ]
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "我想查询苹果公司(AAPL)的股票价格"}
            ],
            tools=tools,
            tool_choice="auto",
            max_tokens=100
        )
        
        if response.choices[0].message.tool_calls:
            print("✅ DeepSeek支持工具调用功能！")
            tool_call = response.choices[0].message.tool_calls[0]
            print(f"   调用工具: {tool_call.function.name}")
            print(f"   参数: {tool_call.function.arguments}")
        else:
            print("⚠️ DeepSeek可能不完全支持工具调用，但基本对话功能正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 工具调用测试失败: {e}")
        return False

if __name__ == "__main__":
    print("🚀 DeepSeek API 测试开始\n")
    
    # 测试基本连接
    if test_deepseek_api():
        print("\n" + "="*50)
        # 测试工具调用
        test_deepseek_tools()
    
    print("\n" + "="*50)
    print("📋 DeepSeek API使用说明:")
    print("1. DeepSeek提供GPT兼容的API接口")
    print("2. 支持多种模型：deepseek-chat, deepseek-coder等")
    print("3. 中国用户友好，支持人民币充值")
    print("4. 价格相对便宜，性能优秀")
    print("5. 官网：https://platform.deepseek.com/")
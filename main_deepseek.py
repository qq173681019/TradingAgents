from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config for DeepSeek
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"
config["backend_url"] = "https://api.deepseek.com/v1"
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance and alpha_vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
}

print("🚀 使用DeepSeek API初始化TradingAgents...")
print(f"   LLM提供商: {config['llm_provider']}")
print(f"   模型: {config['deep_think_llm']}")
print(f"   API端点: {config['backend_url']}")

# Initialize with custom config
try:
    ta = TradingAgentsGraph(debug=True, config=config)
    print("✅ TradingAgents初始化成功！")
    
    # forward propagate
    print("\n📊 开始分析股票: AAPL")
    print("⏳ 正在进行多智能体分析...")
    
    _, decision = ta.propagate("AAPL", "2024-05-10")
    
    print("\n🎯 分析完成！")
    print("="*60)
    print("📝 投资决策结果:")
    print("="*60)
    print(decision)
    print("="*60)
    
except Exception as e:
    print(f"❌ 运行过程中出现错误: {e}")
    print("\n🔧 故障排除建议:")
    print("1. 确保DeepSeek API密钥已正确设置在.env文件中")
    print("2. 检查网络连接是否正常")
    print("3. 确认DeepSeek账户有足够余额")
    print("4. 运行 'python test_deepseek_api.py' 测试API连接")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
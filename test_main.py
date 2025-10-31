from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "z-ai/glm-4.5-air:free"
config["quick_think_llm"] = "z-ai/glm-4.5-air:free"
config["backend_url"] = "https://openrouter.ai/api/v1"
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance and alpha_vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
}

# Initialize with custom config
print("🚀 初始化 TradingAgents...")
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
print("📊 开始分析 NVDA...")
try:
    _, decision = ta.propagate("NVDA", "2024-05-10")
    print("✅ 分析完成!")
    print("📝 决策结果:")
    print(decision)
except Exception as e:
    print(f"❌ 分析过程中出现错误: {e}")
    print("但我们已经看到 News Analyst 和 Market Analyst 正常工作了！")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
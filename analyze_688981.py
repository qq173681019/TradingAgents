from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import datetime

# Load environment variables from .env file
load_dotenv()

# Create a custom config for DeepSeek
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"
config["backend_url"] = "https://api.deepseek.com/v1"
config["max_debate_rounds"] = 2  # 增加辩论轮次以获得更深入的分析

# Configure data vendors
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
}

print("🚀 使用DeepSeek API分析股票 688981...")
print(f"   LLM提供商: {config['llm_provider']}")
print(f"   模型: {config['deep_think_llm']}")
print(f"   API端点: {config['backend_url']}")
print(f"   辩论轮次: {config['max_debate_rounds']}")

# Initialize with custom config
try:
    ta = TradingAgentsGraph(debug=True, config=config)
    print("✅ TradingAgents初始化成功！")
    
    # Get current date for analysis
    current_date = datetime.date.today().strftime("%Y-%m-%d")
    
    # forward propagate for 688981 (中芯国际)
    print(f"\n📊 开始分析股票: 688981 (分析日期: {current_date})")
    print("⏳ 正在进行多智能体分析...")
    print("📈 包含：市场分析、技术指标、基本面分析、新闻分析等")
    
    _, decision = ta.propagate("688981.SS", current_date)  # 添加.SS后缀表示上海科创板
    
    print("\n🎯 688981 股票分析完成！")
    print("="*80)
    print("📝 688981 投资决策结果:")
    print("="*80)
    print(decision)
    print("="*80)
    
    # 额外信息
    print("\n💡 股票基本信息:")
    print("   股票代码: 688981")
    print("   股票名称: 中芯国际 (SMIC)")
    print("   交易所: 上海证券交易所科创板")
    print("   行业: 半导体制造")
    print("   主营业务: 集成电路晶圆代工制造")
    
except Exception as e:
    print(f"❌ 运行过程中出现错误: {e}")
    print("\n🔧 故障排除建议:")
    print("1. 确保DeepSeek API密钥已正确设置在.env文件中")
    print("2. 检查网络连接是否正常")
    print("3. 确认DeepSeek账户有足够余额")
    print("4. 对于A股，请确保使用正确的股票代码格式")
    print("5. 运行 'python test_deepseek_api.py' 测试API连接")
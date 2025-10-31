from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

# 简化的配置，专门针对688981分析
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"
config["backend_url"] = "https://api.deepseek.com/v1"
config["max_debate_rounds"] = 1  # 减少轮次以避免token过度使用

# 配置数据源 - 主要使用yfinance，因为对中国股票支持更好
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",  # 改为yfinance
    "news_data": "alpha_vantage",
}

print("🚀 开始分析中国股票 688981...")
print("📈 股票基本信息:")
print("   代码: 688981 (上海科创板)")
print("   可能名称: 中芯国际或相关半导体公司")
print("   行业: 半导体/科技")

try:
    # 初始化系统
    ta = TradingAgentsGraph(debug=False, config=config)  # 关闭debug减少输出
    print("✅ 系统初始化成功")
    
    current_date = datetime.date.today().strftime("%Y-%m-%d")
    
    # 开始分析
    print(f"\n📊 正在分析 688981 (分析日期: {current_date})")
    print("⏳ 正在运行简化版多智能体分析...")
    
    # 使用正确的ticker格式
    ticker_symbol = "688981.SS"  # 上海证券交易所格式
    
    _, decision = ta.propagate(ticker_symbol, current_date)
    
    print("\n" + "="*60)
    print("🎯 688981 股票分析报告")
    print("="*60)
    print(decision)
    print("="*60)
    
except Exception as e:
    print(f"\n❌ 分析过程中出现错误: {e}")
    print("\n📝 关于 688981 的基本信息:")
    print("   • 688981 是上海证券交易所科创板股票")
    print("   • 688开头表示科创板上市公司")
    print("   • 科创板主要专注科技创新企业")
    print("   • 可能涉及半导体、人工智能、生物医药等行业")
    
    print("\n💡 投资建议:")
    print("   1. 建议通过正规券商或财经网站查询具体公司信息")
    print("   2. 关注科创板整体政策环境和市场表现")
    print("   3. 重点关注公司的技术实力和研发投入")
    print("   4. 考虑中美科技关系对相关公司的影响")
    
    print("\n🔧 技术提示:")
    print("   • 中国A股数据获取可能存在限制")
    print("   • 建议使用专业的A股分析平台")
    print("   • 可以尝试使用 Wind、同花顺等专业数据源")
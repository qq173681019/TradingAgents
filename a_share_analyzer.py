from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

# A股专用配置
def create_a_share_config():
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "deepseek"
    config["deep_think_llm"] = "deepseek-chat"
    config["quick_think_llm"] = "deepseek-chat"
    config["backend_url"] = "https://api.deepseek.com/v1"
    config["max_debate_rounds"] = 1
    
    # A股数据源配置 - 针对中国市场优化
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",      # Yahoo Finance对A股支持较好
        "technical_indicators": "yfinance",  # 技术指标
        "fundamental_data": "openai",       # 使用AI进行基本面分析
        "news_data": "openai",              # 使用AI分析中文新闻
    }
    
    return config

# A股专用分析提示词
A_SHARE_ANALYSIS_PROMPTS = {
    "market_context": """
    分析中国A股市场时，请特别考虑以下因素：
    1. 政策导向性强 - 国家政策对行业和个股影响巨大
    2. 散户投资者为主 - 市场情绪波动较大
    3. T+1交易制度 - 当日买入次日才能卖出
    4. 涨跌停板限制 - 主板±10%，科创板/创业板±20%
    5. 监管环境 - 证监会监管政策变化
    """,
    
    "industry_analysis": """
    分析A股行业时，重点关注：
    1. 国家产业政策支持方向
    2. 供给侧结构性改革影响
    3. 双碳政策对传统行业冲击
    4. 科技自立自强政策支持
    5. 消费升级和内循环政策
    """,
    
    "valuation_methods": """
    A股估值分析请使用：
    1. PE估值 - 考虑行业平均PE
    2. PB估值 - 适用于银行、地产等
    3. PEG估值 - 成长股估值
    4. 政策溢价 - 政策支持行业的估值溢价
    5. 稀缺性溢价 - 行业龙头的稀缺性
    """,
    
    "risk_assessment": """
    A股投资风险评估：
    1. 政策风险 - 行业政策变化风险
    2. 流动性风险 - 市场流动性变化
    3. 退市风险 - ST、*ST股票风险
    4. 汇率风险 - 人民币汇率波动
    5. 系统性风险 - 整体市场风险
    """
}

def analyze_a_share_stock(ticker, company_name="", industry=""):
    """
    A股专用分析函数
    """
    print("🇨🇳 A股智能分析系统")
    print("="*50)
    print(f"股票代码: {ticker}")
    if company_name:
        print(f"公司名称: {company_name}")
    if industry:
        print(f"所属行业: {industry}")
    
    # 股票代码格式处理
    if len(ticker) == 6 and ticker.isdigit():
        if ticker.startswith('60') or ticker.startswith('68'):
            ticker_formatted = f"{ticker}.SS"  # 上海交易所
            exchange = "上海证券交易所"
        elif ticker.startswith('00') or ticker.startswith('30'):
            ticker_formatted = f"{ticker}.SZ"  # 深圳交易所
            exchange = "深圳证券交易所"
        else:
            ticker_formatted = f"{ticker}.SS"  # 默认上海
            exchange = "上海证券交易所"
    else:
        ticker_formatted = ticker
        exchange = "未知交易所"
    
    print(f"交易所: {exchange}")
    print(f"完整代码: {ticker_formatted}")
    
    # 板块识别
    board = ""
    if ticker.startswith('688'):
        board = "科创板"
    elif ticker.startswith('300'):
        board = "创业板"
    elif ticker.startswith('60'):
        board = "主板"
    elif ticker.startswith('00'):
        board = "深市主板"
    
    if board:
        print(f"板块: {board}")
    
    print("="*50)
    
    try:
        # 初始化A股专用配置
        config = create_a_share_config()
        ta = TradingAgentsGraph(debug=False, config=config)
        print("✅ A股分析系统初始化成功")
        
        current_date = datetime.date.today().strftime("%Y-%m-%d")
        print(f"📅 分析日期: {current_date}")
        print("🔄 正在进行A股专业分析...")
        print("   • 技术面分析")
        print("   • 基本面分析")
        print("   • 政策影响分析")
        print("   • 市场情绪分析")
        
        # 执行分析
        _, decision = ta.propagate(ticker_formatted, current_date)
        
        print("\n" + "="*60)
        print("📊 A股专业分析报告")
        print("="*60)
        print(decision)
        print("="*60)
        
        # A股特色风险提示
        print("\n⚠️  A股投资风险提示:")
        print("• 股市有风险，投资需谨慎")
        print("• 注意政策变化对股价的影响")
        print("• 关注公司基本面变化")
        print("• 合理控制仓位和风险")
        
    except Exception as e:
        print(f"\n❌ 分析过程中遇到问题: {e}")
        
        # 提供A股分析的替代建议
        print(f"\n📋 {ticker} A股分析建议:")
        print("="*40)
        
        # 基于代码提供基本信息
        if ticker.startswith('688'):
            print("🔬 科创板股票特点:")
            print("   • 科技创新企业，成长性较高")
            print("   • 估值相对较高，波动性大")
            print("   • 投资门槛50万，机构投资者较多")
            print("   • 关注技术实力和研发投入")
            
        elif ticker.startswith('300'):
            print("🚀 创业板股票特点:")
            print("   • 成长型中小企业")
            print("   • 注册制改革，市场化程度高")
            print("   • 波动性较大，适合风险承受能力强的投资者")
            
        elif ticker.startswith('60'):
            print("🏢 主板股票特点:")
            print("   • 大型成熟企业为主")
            print("   • 相对稳定，适合稳健投资")
            print("   • 分红较为稳定")
            
        print(f"\n💡 {ticker} 投资建议:")
        print("1. 📈 技术分析:")
        print("   • 关注均线系统和成交量")
        print("   • 观察是否突破重要技术位")
        print("   • 注意涨跌停板和换手率")
        
        print("2. 📊 基本面分析:")
        print("   • 查看最新财报和业绩预告")
        print("   • 关注ROE、营收增长率等指标")
        print("   • 分析行业地位和竞争优势")
        
        print("3. 🏛️ 政策面分析:")
        print("   • 关注相关行业政策支持")
        print("   • 注意监管政策变化")
        print("   • 观察国家战略规划影响")
        
        print("4. 💰 资金面分析:")
        print("   • 观察北上资金流向")
        print("   • 关注机构调研和持仓")
        print("   • 分析龙虎榜资金动向")

if __name__ == "__main__":
    # 示例：分析688981
    print("🚀 启动A股智能分析系统")
    
    # 可以添加更多股票信息
    stock_info = {
        "688981": {"name": "中芯国际", "industry": "半导体制造"},
        "600036": {"name": "招商银行", "industry": "银行"},
        "000002": {"name": "万科A", "industry": "房地产"},
        "300750": {"name": "宁德时代", "industry": "新能源电池"},
    }
    
    target_stock = "688981"
    
    if target_stock in stock_info:
        analyze_a_share_stock(
            target_stock, 
            stock_info[target_stock]["name"],
            stock_info[target_stock]["industry"]
        )
    else:
        analyze_a_share_stock(target_stock)
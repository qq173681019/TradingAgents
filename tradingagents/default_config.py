import os

# A股市场专用配置
A_SHARE_CONFIG = {
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat", 
    "backend_url": "https://api.deepseek.com/v1",
    "max_debate_rounds": 1,
    "enable_memory": False,
    
    # A股数据源配置
    "data_vendors": {
        "core_stock_apis": "yfinance",      # Yahoo Finance对A股支持较好
        "technical_indicators": "yfinance",  # 技术指标使用yfinance
        "fundamental_data": "local",        # 基本面使用本地分析
        "news_data": "local",               # 新闻使用本地分析
    },
    
    # A股特色分析提示词
    "analysis_prompts": {
        "market_context": "请考虑中国A股市场特殊性：政策导向、散户为主、T+1制度、涨跌停限制",
        "valuation_method": "使用适合A股的估值方法：PE/PB/PEG，考虑政策溢价和稀缺性",
        "risk_assessment": "分析A股特有风险：政策风险、流动性风险、退市风险、系统性风险"
    }
}

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat",
    "backend_url": "https://api.deepseek.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "alpha_vantage",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}

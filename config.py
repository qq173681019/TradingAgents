"""
配置文件 - 统一管理所有API Keys和配置项
使用方法: 
    from config import DEEPSEEK_API_KEY, MINIMAX_API_KEY, GEMINI_API_KEY, etc.
"""

# ==================== API Keys 配置 ====================

# DeepSeek API Key
# 获取地址: https://platform.deepseek.com/
DEEPSEEK_API_KEY = "sk-bdd85ba18ab54a699617d8b25fbecfea"

# MiniMax API Secret Key
# 获取方式：登录 https://platform.minimaxi.com/ -> API管理 -> API keys 页面的 Secret key 列
# 注意：MiniMax的Secret Key格式是 eyJhbG... 开头的长字符串
MINIMAX_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiIxNzM2ODEwMTkiLCJVc2VyTmFtZSI6IkplcmljbyIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTkzMDY5NDY4MjAwMjEwNTkxIiwiUGhvbmUiOiIiLCJHcm91cElEIjoiMTk5MzA2OTQ2ODE5NjAyMDM4MyIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6IjE3MzY4MTAxOUBxcS5jb20iLCJDcmVhdGVUaW1lIjoiMjAyNS0xMS0yNSAwNTo1NTowNyIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.XuMeLOiQygaANBagGyJ6GXPjjW2sUuaZJqVerZ-j5hIO-bUR9_4qxQuoMw0b6kqu3IPiaucU4MGouv8vvPjp-uNi1gY0pbeyL0F7ID5OIYd1tefqOrW_k_ZwA619yH7yEowBgFmAGpp0amUM-QK7KWajML5XPBKGhdqy2YY4ZW2pWalcU9zQ5mx4G6-NH3iQ3MPn6-37odvdPVtvxfwwP6zURRNNd5_8CLNmyuMDi9xHkqDcYcn6eE76z4uUUli7iPRFIFL6RKIx2M3mt2-y3jDgXvFIgMSGbxv5YN4E7KPdB7QXEhaqiXTnBVWmsWOxfV_tpJ7dzCRrqYhyZaiRwQ"

# MiniMax Group ID (从JWT payload中的GroupID字段获取)
MINIMAX_GROUP_ID = "1993069468196020383"

# Google Gemini API Key
# 获取地址: https://makersuite.google.com/app/apikey
GEMINI_API_KEY = "AIzaSyAkNFSx_OiKA9VVdUcXFU64GCPc1seXxvQ"

# OpenRouter API Key
# 获取地址: https://openrouter.ai/keys
OPENROUTER_API_KEY = "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"

# Choice金融终端账号密码
# 东方财富Choice专业金融数据终端
# 获取地址: https://choice.eastmoney.com/
CHOICE_USERNAME = "hczq2048"
CHOICE_PASSWORD = "yo336999"
ENABLE_CHOICE = True  # 设置为True启用Choice数据源

# Alpha Vantage API Key (股票数据API)
# 获取地址: https://www.alphavantage.co/
ALPHA_VANTAGE_API_KEY = "52N6YLT15MUAA46B"

# Polygon.io API Key (股票数据API)
# 获取地址: https://polygon.io/
POLYGON_API_KEY = "yb5xBES96DRleQzip9kKgCWbkc3E6N58"

# Tushare Token (A股数据API)
# 获取地址: https://tushare.pro/
TUSHARE_TOKEN = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"

# ==================== 功能开关配置 ====================

# ETF功能开关：设置为True显示ETF按钮，False则隐藏
ENABLE_ETF_BUTTONS = False

# ==================== AI模型配置 ====================

# 可用的AI模型列表
LLM_MODEL_OPTIONS = ["none", "deepseek", "minimax", "openrouter", "gemini"]

# 默认AI模型
DEFAULT_LLM_MODEL = "none"

# ==================== API端点配置 ====================

# DeepSeek API 端点
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"

# MiniMax API 端点
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
MINIMAX_MODEL_NAME = "abab6.5s-chat"

# Google Gemini API 端点
# Gemini 2.0 (Gemini 3.0的内部版本号) 使用gemini-2.0-flash-exp实验模型
# 也可以尝试: gemini-exp-1206 (最新实验版本)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
GEMINI_MODEL_NAME = "gemini-2.0-flash-exp"

# OpenRouter API 端点
# OpenRouter支持多种模型，可以通过模型名称切换
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_NAME = "openai/gpt-3.5-turbo"  # 可选: anthropic/claude-3-opus, meta-llama/llama-3-70b等

# ==================== 其他配置 ====================

# 数据文件配置
CACHE_FILE = "stock_analysis_cache.json"
BATCH_SCORE_FILE = "batch_stock_scores.json"
BATCH_SCORE_FILE_DEEPSEEK = "batch_stock_scores_deepseek.json"
BATCH_SCORE_FILE_MINIMAX = "batch_stock_scores_minimax.json"
BATCH_SCORE_FILE_OPENROUTER = "batch_stock_scores_openrouter.json"
BATCH_SCORE_FILE_GEMINI = "batch_stock_scores_gemini.json"
COMPREHENSIVE_DATA_FILE = "comprehensive_stock_data.json"
STOCK_INFO_FALLBACK_FILE = "stock_info_fallback.json"

# API超时设置（秒）
API_TIMEOUT = 30

# AI生成参数
AI_TEMPERATURE = 0.7
AI_MAX_TOKENS = 1000
AI_TOP_P = 0.95

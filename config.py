"""
配置文件 - 统一管理所有API Keys和配置项
使用方法: 
    from config import DEEPSEEK_API_KEY, MINIMAX_API_KEY, etc.
"""

# ==================== API Keys 配置 ====================

# DeepSeek API Key
# 获取地址: https://platform.deepseek.com/
DEEPSEEK_API_KEY = "sk-bdd85ba18ab54a699617d8b25fbecfea"

# MiniMax API Key (JWT Token)
# 获取地址: https://www.minimaxi.com/
MINIMAX_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiIxNzM2ODEwMTkiLCJVc2VyTmFtZSI6IkplcmljbyIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTkzMDY5NDY4MjAwMjEwNTkxIiwiUGhvbmUiOiIiLCJHcm91cElEIjoiMTk5MzA2OTQ2ODE5NjAyMDM4MyIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6IjE3MzY4MTAxOUBxcS5jb20iLCJDcmVhdGVUaW1lIjoiMjAyNS0xMS0yNSAwNTo1MToxNSIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.EsvLbXRHGF5F9nsmM2VtYmBXAtvgLZ2MjSg-NtezaB56XVHHRoJ2MU8HA0nYZDLFEigprqxSX5yLehC_lqJ-JixlSPl5TriWlvRWWwRp36QdyU4Aa5_5pxxikvDv23AsfxeFDRnPUfkUycwphDNNjqjNsoaI5GQemjPKXJOQ455MFZZMHZSuDdQkzFCoBHnsyOJ63NH1CPDQYhWqLkVo4jefwLV-_CEWS1vviloPPxInisAVK1gFcQm3yZ5GWFIny5-fPeMmqGnCsM0j1ZovDlRKVwxCAYIwvSfgkWWbGS3GnnXoJEmJTzrgIe_LwDQftoCHgMV4oTlk0uKQXqASDg"

# MiniMax Group ID (从 JWT Token 中提取)
MINIMAX_GROUP_ID = "1993069468196020383"

# Alpha Vantage API Key (股票数据API)
# 获取地址: https://www.alphavantage.co/
ALPHA_VANTAGE_API_KEY = "52N6YLT15MUAA46B"  # 如果使用，请填写

# Polygon.io API Key (股票数据API)
# 获取地址: https://polygon.io/
POLYGON_API_KEY = "yb5xBES96DRleQzip9kKgCWbkc3E6N58"  # 如果使用，请填写

# Tushare Token (A股数据API)
# 获取地址: https://tushare.pro/
TUSHARE_TOKEN = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"  # 如果使用，请填写

# ==================== 功能开关配置 ====================

# ETF功能开关：设置为True显示ETF按钮，False则隐藏
ENABLE_ETF_BUTTONS = False

# ==================== AI模型配置 ====================

# 可用的AI模型列表
LLM_MODEL_OPTIONS = ["none", "deepseek", "minimax"]

# 默认AI模型
DEFAULT_LLM_MODEL = "none"

# ==================== API端点配置 ====================

# DeepSeek API 端点
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"

# MiniMax API 端点
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
MINIMAX_MODEL_NAME = "abab6.5s-chat"

# ==================== 其他配置 ====================

# 数据文件配置
CACHE_FILE = "stock_analysis_cache.json"
BATCH_SCORE_FILE = "batch_stock_scores.json"
BATCH_SCORE_FILE_DEEPSEEK = "batch_stock_scores_deepseek.json"
BATCH_SCORE_FILE_MINIMAX = "batch_stock_scores_minimax.json"
COMPREHENSIVE_DATA_FILE = "comprehensive_stock_data.json"
STOCK_INFO_FALLBACK_FILE = "stock_info_fallback.json"

# API超时设置（秒）
API_TIMEOUT = 30

# AI生成参数
AI_TEMPERATURE = 0.7
AI_MAX_TOKENS = 1000
AI_TOP_P = 0.95

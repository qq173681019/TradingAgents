"""
配置文件 - 统一管理所有API Keys和配置项
使用方法: 
    from config import DEEPSEEK_API_KEY, MINIMAX_API_KEY, etc.
"""

# ==================== API Keys 配置 ====================

# DeepSeek API Key
# 获取地址: https://platform.deepseek.com/
DEEPSEEK_API_KEY = "sk-bdd85ba18ab54a699617d8b25fbecfea"

# MiniMax API Secret Key
# 获取方式：登录 https://platform.minimaxi.com/ -> API管理 -> API keys 页面的 Secret key 列
# 注意：MiniMax的Secret Key格式是 eyJhbG... 开头的长字符串，不是 sk- 开头
MINIMAX_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJKZXJpY28iLCJVc2VyTmFtZSI6IkplcmljbyIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTkyODU0OTE1OTQ4NDgzMDMxIiwiUGhvbmUiOiIxNzcwMTMyNzc1MyIsIkdyb3VwSUQiOiIxOTkyODU0OTE1OTQwMDk0NzAxIiwiUGFnZU5hbWUiOiIiLCJNYWlsIjoiIiwiQ3JlYXRlVGltZSI6IjIwMjUtMTEtMjUgMTc6Mjk6MzgiLCJUb2tlblR5cGUiOjQsImlzcyI6Im1pbmltYXgifQ.D9jrYdx3EQoCko9fhJb37cvjo9icHRFDNxLhSg5eskBGEO-clgo7ugjjEKuO4q8DiVXkI_sQheWT2gKTZKwRoLVrnr_j6jYTQIZIt2gZXybRbELtSCalOs6ux3w4r4s00R4D4u_RzOAHrFfITT-44A8q2cSgoVSjU88ybschl6mK03Kv6W3rBgSULFvMdZEHQqmYXYrXPGBMsdGRIKRw1ridSN9tYkEw1OuwTJJINC6jb4MmGi_gFpZWkLZUzL5stfQ2j3iNGL6tThCDzseXyTnSkfvc4-kYRhqMFGAjYDLBWxIdYwLMj4PiK43RiWbdRN8zn_zh-60GlPjAz3GdjQ"

# MiniMax Group ID (从JWT payload中的GroupID字段获取)
MINIMAX_GROUP_ID = "1992854915940094701"

# OpenAI API Key
# 获取地址: https://platform.openai.com/api-keys
# 注意：OpenAI的API Key格式是 sk- 开头
# 国内用户如遇地区限制，可考虑使用代理服务或第三方API服务
OPENAI_API_KEY = "sk-AzpYpTOIRyuWsU7XE3VGO3KMlHNYsqmkBl8bFtoeZvBs3efm"

# OpenRouter API Key
# 获取地址: https://openrouter.ai/keys
# OpenRouter提供多种AI模型的统一API接口，支持GPT、Claude、Llama等
OPENROUTER_API_KEY = "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"
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
LLM_MODEL_OPTIONS = ["none", "deepseek", "minimax", "openai", "openrouter"]

# 默认AI模型
DEFAULT_LLM_MODEL = "none"

# ==================== API端点配置 ====================

# DeepSeek API 端点
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"

# MiniMax API 端点
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
MINIMAX_MODEL_NAME = "abab6.5s-chat"

# OpenAI API 端点
# 默认官方端点（可能在某些地区受限）
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
# 备用端点示例（如使用代理服务，请修改为对应的端点）
# OPENAI_API_URL = "https://your-proxy-service.com/v1/chat/completions"
OPENAI_MODEL_NAME = "gpt-3.5-turbo"

# OpenRouter API 端点
# OpenRouter 提供统一的API接口访问多种AI模型
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_NAME = "openai/gpt-3.5-turbo"  # 可选: anthropic/claude-3-haiku, meta-llama/llama-2-70b-chat 等

# OpenAI 代理配置（可选）
# 如果需要使用HTTP代理访问OpenAI API，请配置以下选项
OPENAI_PROXY = None  # 示例: "http://127.0.0.1:7890" 或 "socks5://127.0.0.1:7890"

# ==================== 其他配置 ====================

# 数据文件配置
CACHE_FILE = "stock_analysis_cache.json"
BATCH_SCORE_FILE = "batch_stock_scores.json"
BATCH_SCORE_FILE_DEEPSEEK = "batch_stock_scores_deepseek.json"
BATCH_SCORE_FILE_MINIMAX = "batch_stock_scores_minimax.json"
BATCH_SCORE_FILE_OPENAI = "batch_stock_scores_openai.json"
BATCH_SCORE_FILE_OPENROUTER = "batch_stock_scores_openrouter.json"
COMPREHENSIVE_DATA_FILE = "comprehensive_stock_data.json"
STOCK_INFO_FALLBACK_FILE = "stock_info_fallback.json"

# API超时设置（秒）
API_TIMEOUT = 30

# AI生成参数
AI_TEMPERATURE = 0.7
AI_MAX_TOKENS = 1000
AI_TOP_P = 0.95

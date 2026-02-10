"""
TradingShared 共享配置文件
包含所有API密钥和全局配置
"""

# ==================== API密钥配置 ====================

# DeepSeek API
DEEPSEEK_API_KEY = ""
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"

# MiniMax API
MINIMAX_API_KEY = ""
MINIMAX_GROUP_ID = ""
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
MINIMAX_MODEL_NAME = "abab6.5s-chat"

# OpenAI API
OPENAI_API_KEY = "sk-AzpYpTOIRyuWsU7XE3VGO3KMlHNYsqmkBl8bFtoeZvBs3efm"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_NAME = "gpt-3.5-turbo"

# OpenRouter API
OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_NAME = "openai/gpt-3.5-turbo"

# Google Gemini API
GEMINI_API_KEY = "AIzaSyAkNFSx_OiKA9VVdUcXFU64GCPc1seXxvQ"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
GEMINI_MODEL_NAME = "gemini-2.0-flash-exp"

# GOOGLE API
GOOGLE_API_KEY="77802de1555ea0e29ef1c9b7a9f2a0a5467608c8fb081cfd54876d03e4ddadff"

# Alpha Vantage API
ALPHA_VANTAGE_API_KEY = ""


# 阿里百炼（Qwen）
BAILIAN_API_KEY = "sk-7ad9f69c693e4284a2384a920591113d"
BAILIAN_ID = "3314360"
BAILIAN_ACCOUNT = "1778470174535081"

# ==================== 数据源配置 ====================
FINNHUB_API_KEY="d3s9411r01qs1apro6ugd3s9411r01qs1apro6v0"
ALPHA_VANTAGE_API_KEY="52N6YLT15MUAA46B"

# Choice金融终端
ENABLE_CHOICE = True  # 后台数据收集器是否使用Choice（GUI复选框独立控制）
CHOICE_USERNAME = "hczq2048"  # Choice用户名
CHOICE_USER = "hczq2048"  # 兼容性别名（旧代码使用）
CHOICE_PASSWORD = "yo336999"  # Choice密码
CHOICE_PASS = "yo336999"  # 兼容性别名（旧代码使用）

# Tushare
TUSHARE_TOKEN = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"

# ==================== 应用配置 ====================

# LLM模型选项
LLM_MODEL_OPTIONS = ["none", "deepseek", "minimax", "openrouter", "gemini"]
DEFAULT_LLM_MODEL = "none"

# API超时和参数
API_TIMEOUT = 300
AI_TEMPERATURE = 0.7
AI_MAX_TOKENS = 1000
AI_TOP_P = 0.95

# 功能开关
ENABLE_ETF_BUTTONS = False

# ==================== 路径配置 ====================
import os

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# 确保数据目录存在
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ==================== 使用说明 ====================
"""
使用方法：

1. 直接导入：
   from config import DEEPSEEK_API_KEY, CHOICE_USER

2. 使用环境变量覆盖（推荐）：
   创建 .env.local 文件，添加：
   DEEPSEEK_API_KEY=your_key_here
   
3. 在其他项目中使用：
   import sys
   sys.path.insert(0, r"D:\TradingShared")
   from config import CHOICE_USER, TUSHARE_TOKEN

注意：
- 不要将包含真实密钥的config.py提交到Git
- 建议使用 .env.local 存储敏感信息
- .env.local 已在 .gitignore 中排除
"""

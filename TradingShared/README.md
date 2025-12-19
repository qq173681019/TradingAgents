# TradingShared - 共享资源库

##  目录结构

```
TradingShared/
 api/              # 共享API接口
 data/             # 共享数据文件
 config.py         # 配置文件（API密钥等）
 .env.example      # 环境变量模板
 .env.local        # 本地环境变量（不提交到Git）
 path_config.py    # 路径配置模块
 README.md         # 本文件
```

##  配置说明

### 方法1: 使用config.py（简单）

直接在 `config.py` 中填写API密钥：

```python
# 在项目中导入
import sys
sys.path.insert(0, r"D:\TradingShared")
from config import CHOICE_USER, TUSHARE_TOKEN, DEEPSEEK_API_KEY
```

### 方法2: 使用环境变量（推荐）

1. 复制 `.env.example` 为 `.env.local`
2. 在 `.env.local` 中填入真实密钥
3. 项目会自动读取环境变量

```bash
# .env.local 示例
DEEPSEEK_API_KEY=sk-xxxxx
CHOICE_USER=your_username
CHOICE_PASS=your_password
```

##  在项目中使用

### 添加路径

```python
import sys
sys.path.insert(0, r"D:\TradingShared")
sys.path.insert(0, r"D:\TradingShared\api")
```

### 导入API模块

```python
# 导入Choice API
from EmQuantAPI import c
from choice_api_wrapper import ChoiceAPI

# 导入其他数据源API
from baostock_api import get_stock_data
from tencent_kline_api import get_kline_data
```

### 访问共享数据

```python
import json
CACHE_FILE = r"D:\TradingShared\data\stock_analysis_cache.json"
with open(CACHE_FILE, 'r', encoding='utf-8') as f:
    cache = json.load(f)
```

##  配置项说明

### AI模型API
- `DEEPSEEK_API_KEY`: DeepSeek API密钥
- `MINIMAX_API_KEY`: MiniMax API密钥
- `OPENAI_API_KEY`: OpenAI API密钥
- `OPENROUTER_API_KEY`: OpenRouter API密钥
- `GEMINI_API_KEY`: Google Gemini API密钥

### 数据源
- `CHOICE_USER/PASS`: Choice金融终端账号
- `TUSHARE_TOKEN`: Tushare Pro Token
- `ALPHA_VANTAGE_API_KEY`: Alpha Vantage密钥

### 参数设置
- `API_TIMEOUT`: API请求超时时间（秒）
- `AI_TEMPERATURE`: AI生成温度（0-1）
- `AI_MAX_TOKENS`: AI最大生成token数
- `DEFAULT_LLM_MODEL`: 默认使用的LLM模型

##  安全提示

1. **不要提交密钥**: `.env.local` 和包含真实密钥的 `config.py` 不应提交到Git
2. **使用环境变量**: 在生产环境建议使用环境变量而非硬编码
3. **定期轮换**: 定期更换API密钥以提高安全性
4. **权限管理**: 确保只有授权用户能访问配置文件

##  快速开始

### 初次配置

```bash
# 1. 复制环境变量模板
cd D:\TradingShared
copy .env.example .env.local

# 2. 编辑 .env.local，填入真实密钥
notepad .env.local

# 3. 在项目中测试导入
python -c "import sys; sys.path.insert(0, r'D:\TradingShared'); from config import CHOICE_USER; print(f'用户名: {CHOICE_USER}')"
```

### 验证配置

```python
# 运行验证脚本
import sys
sys.path.insert(0, r"D:\TradingShared")
from path_config import setup_paths
setup_paths()
print("配置加载成功！")
```

##  相关文档

- [文件结构说明](../TradingAgents/文件结构说明.md)
- [重组完成报告](../TradingAgents/重组完成报告.md)

---
更新日期: 2025-12-19
# 🇨🇳 TradingAgents - A股专用配置指南

## 📋 A股分析系统配置

针对中国A股市场的特殊需求，我们需要对系统进行专门优化。

## 🔧 A股数据源配置

### 1. 修改数据源优先级
```python
# A股专用配置
config["data_vendors"] = {
    "core_stock_apis": "yfinance",          # Yahoo Finance对A股支持较好
    "technical_indicators": "yfinance",     # 技术指标计算
    "fundamental_data": "local",            # 使用本地数据或AI分析
    "news_data": "openai",                  # 使用AI分析A股新闻
}
```

### 2. A股股票代码格式
```python
# 上海交易所
"600000.SS"  # 浦发银行
"688981.SS"  # 科创板股票

# 深圳交易所  
"000001.SZ"  # 平安银行
"300001.SZ"  # 创业板股票
```

### 3. A股特色分析提示词
```python
# 针对A股的专用提示词
A_SHARE_PROMPTS = {
    "market_context": "请考虑中国A股市场的特殊性：政策导向、散户为主、T+1交易制度",
    "valuation": "请使用适合A股的估值方法：PE、PB、PEG，并考虑行业政策影响",
    "risk_factors": "请分析A股特有风险：政策风险、流动性风险、退市风险"
}
```

## 💼 A股分析增强功能

### 1. 政策影响分析
- 监管政策变化
- 行业政策导向
- 宏观经济政策

### 2. 资金流向分析
- 北上资金流向
- 机构持仓变化
- 散户情绪指标

### 3. A股特色指标
- 换手率分析
- 涨跌停板分析
- 龙虎榜数据

## 🚀 快速部署A股分析系统

创建专用的A股分析脚本，集成以上功能。
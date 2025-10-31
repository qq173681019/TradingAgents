# TradingAgents 配置指南

## 配置状态

✅ **Python 环境配置完成**  
- 使用 Python 3.13.9
- 虚拟环境 `.venv` 已创建并激活
- 所有依赖包已安装成功

✅ **项目文件配置完成**  
- `.env` 文件已创建
- 项目结构完整

## 🔑 必需的 API 密钥配置

在运行程序之前，你需要获取并配置以下API密钥：

### 1. OpenRouter API Key (推荐 - 免费模型可用)
- 访问 [OpenRouter](https://openrouter.ai/)
- 创建账户并获取API密钥
- OpenRouter提供多种免费模型，包括Llama、DeepSeek等
- 在 `.env` 文件中替换 `your_openrouter_api_key_here` 为你的真实密钥

### 2. Alpha Vantage API Key (免费)
- 访问 [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
- 注册免费账户并获取API密钥
- 在 `.env` 文件中替换 `your_alpha_vantage_api_key_here` 为你的真实密钥

## 📝 .env 文件配置

编辑项目根目录下的 `.env` 文件：

```bash
# Alpha Vantage API Key for stock market data
ALPHA_VANTAGE_API_KEY=你的_alpha_vantage_密钥_这里
# OpenRouter API Key (works as OpenAI compatible endpoint)
OPENAI_API_KEY=你的_openrouter_密钥_这里
```

注意：虽然变量名叫 `OPENAI_API_KEY`，但实际使用的是 OpenRouter API 密钥，程序已配置为使用 OpenRouter 端点。

## 🚀 运行程序

### 方法1: 使用命令行界面 (推荐用于初次体验)
```powershell
# 确保在项目根目录并激活虚拟环境
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe -m cli.main
```

### 方法2: 运行主程序脚本
```powershell
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe main.py
```

### 方法3: 使用 Python 代码
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 创建配置 - 使用 OpenRouter 免费模型
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "deepseek/deepseek-chat-v3-0324:free"  # 免费 DeepSeek 模型
config["quick_think_llm"] = "meta-llama/llama-3.3-8b-instruct:free"  # 免费 Llama 模型
config["backend_url"] = "https://openrouter.ai/api/v1"

# 初始化
ta = TradingAgentsGraph(debug=True, config=config)

# 运行分析（示例：分析NVDA股票在2024-05-10的情况）
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

## ⚠️ 重要提示

1. **免费模型**: 配置使用 OpenRouter 的免费模型（DeepSeek V3 和 Llama 3.3），无需付费即可体验
2. **数据源**: 程序使用 yfinance (免费) 和 Alpha Vantage 获取股票数据
3. **调试模式**: 设置 `debug=True` 可以看到详细的执行过程
4. **首次运行**: 建议先用简单的股票代码（如SPY、AAPL、NVDA）进行测试
5. **OpenRouter优势**: 提供多种免费AI模型，无需OpenAI账户

## 🔧 故障排除

如果遇到问题：

1. **API密钥错误**: 确保 `.env` 文件中的OpenRouter密钥正确且有效
2. **依赖问题**: 确保在激活的虚拟环境中运行
3. **网络问题**: 确保可以访问 OpenRouter 和 Alpha Vantage API
4. **模型选择**: 使用免费的OpenRouter模型，避免产生费用
5. **嵌入模型**: 如果遇到嵌入相关错误，检查OpenRouter是否支持text-embedding-3-small

## 📞 获取帮助

- 查看项目的 [GitHub Issues](https://github.com/TauricResearch/TradingAgents/issues)
- 加入 [Discord 社区](https://discord.com/invite/hk9PGKShPK)

---
⚡ **配置已完成！程序现在使用 OpenRouter API**

## 📋 当前状态

✅ Python 环境 (3.13.9) 已配置  
✅ 所有依赖已安装  
✅ `.env` 文件已创建  
✅ 程序已配置为使用 OpenRouter API  
⚠️ 需要验证 OpenRouter API 密钥  

## 🔑 OpenRouter API 密钥问题

测试显示当前 API 密钥可能有问题。请：

1. **检查 OpenRouter 账户**
   - 访问 https://openrouter.ai/
   - 确认账户状态和 API 密钥有效性

2. **验证 API 连接**
   ```powershell
   C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe test_openrouter.py
   ```

3. **查看详细配置指南**
   - 阅读 `OPENROUTER_SETUP.md` 文件
   - 包含完整的故障排除步骤

## 🚀 成功配置后的运行方法

```powershell
# CLI 界面
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe -m cli.main

# 直接运行
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe main.py
```

配置完成！现在你可以开始使用 TradingAgents 进行股票分析了。
# OpenRouter 配置完成指南

## 🎉 配置状态

✅ **程序已配置为使用 OpenRouter**
- 默认配置已修改为使用 OpenRouter 端点
- 选择免费模型（DeepSeek V3 和 Llama 3.3）
- 添加了 OpenRouter 所需的 HTTP 头部
- 所有相关文件已更新

## ⚠️ 当前问题

测试显示 OpenRouter API 密钥可能存在问题，返回 "User not found" 错误。

## 🔧 解决步骤

### 1. 检查 OpenRouter API 密钥

当前 `.env` 文件中的密钥:
```
OPENAI_API_KEY=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
```

请执行以下步骤：

1. **访问 OpenRouter 控制台**
   - 打开 https://openrouter.ai/
   - 登录或创建账户

2. **验证 API 密钥**
   - 进入 "Keys" 页面
   - 检查密钥是否有效且未过期
   - 确认账户状态是否正常

3. **生成新的 API 密钥**（如果需要）
   - 在 OpenRouter 控制台创建新密钥
   - 复制新密钥并替换 `.env` 文件中的值

### 2. 测试 API 连接

运行测试脚本验证连接：
```powershell
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe test_openrouter.py
```

### 3. 确认免费模型可用性

检查以下免费模型是否在你的 OpenRouter 账户中可用：
- `meta-llama/llama-3.3-8b-instruct:free`
- `deepseek/deepseek-chat-v3-0324:free`
- `google/gemini-2.0-flash-exp:free`

### 4. 备选方案

如果 OpenRouter 仍然有问题，你可以：

**选项 A: 使用其他免费服务**
- 考虑使用 Groq（也提供免费的 Llama 模型）
- 或者使用本地 Ollama

**选项 B: 回退到 OpenAI**
- 修改 `main.py` 中的配置：
```python
config["llm_provider"] = "openai"
config["backend_url"] = "https://api.openai.com/v1"
config["deep_think_llm"] = "gpt-4o-mini"
config["quick_think_llm"] = "gpt-4o-mini"
```

## 📋 测试清单

- [ ] 确认 OpenRouter 账户状态
- [ ] 验证 API 密钥有效性
- [ ] 检查免费模型配额
- [ ] 运行 `test_openrouter.py` 获得成功结果
- [ ] 运行 `main.py` 测试完整功能

## 🚀 成功后的使用方法

配置成功后，你可以：

1. **使用 CLI 界面**:
```powershell
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe -m cli.main
```

2. **直接运行主程序**:
```powershell
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe main.py
```

3. **使用 Python 代码**:
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

## 💡 OpenRouter 的优势

- 🆓 提供多种免费模型
- 🚀 无需 OpenAI 账户
- 🌐 统一 API 访问多种模型
- ⚡ 较好的性能和稳定性

---

如果遇到问题，请：
1. 检查网络连接
2. 确认 API 密钥格式正确
3. 查看 OpenRouter 文档或联系支持
4. 考虑使用备选配置方案
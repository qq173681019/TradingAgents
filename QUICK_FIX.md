# OpenRouter API 密钥问题解决指南

## 🚨 当前问题
- 错误: `AuthenticationError: Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}`
- 原因: OpenRouter 无法识别当前 API 密钥关联的用户

## 🔧 解决步骤

### 立即行动 - 重新生成 API 密钥

1. **访问 OpenRouter 控制台**
   ```
   https://openrouter.ai/keys
   ```

2. **删除当前密钥**
   - 找到当前使用的密钥
   - 点击删除/撤销

3. **创建新密钥**
   - 点击 "Create New Key"
   - 给密钥起个名字（如 "TradingAgents"）
   - 复制新生成的完整密钥

4. **更新 .env 文件**
   ```bash
   # 替换这一行中的密钥
   OPENAI_API_KEY=新的完整密钥
   ```

### 替代方案 - 使用其他服务

如果 OpenRouter 问题持续，可以切换到其他免费服务：

#### 选项A: Groq (推荐)
```python
# 修改 main.py 配置
config["llm_provider"] = "openai"
config["backend_url"] = "https://api.groq.com/openai/v1"
config["deep_think_llm"] = "llama3-8b-8192"
config["quick_think_llm"] = "llama3-8b-8192"
```

#### 选项B: 本地 Ollama
```python
# 修改 main.py 配置
config["llm_provider"] = "ollama" 
config["backend_url"] = "http://localhost:11434/v1"
config["deep_think_llm"] = "llama3.1"
config["quick_think_llm"] = "llama3.1"
```

## 🧪 验证步骤

更新密钥后运行：
```powershell
C:/Users/ext.jgu/.pyenv/pyenv-win/versions/3.13.9/python.exe diagnose_openrouter.py
```

## 📞 如果问题持续

1. 检查 OpenRouter 账户状态
2. 联系 OpenRouter 支持
3. 使用备选方案（Groq 或 Ollama）
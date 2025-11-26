# 🎉 MiniMax CodingPlan VSCode 集成配置指南

## 🚀 快速设置（3分钟完成）

### 第一步：获取 MiniMax API 密钥
1. 访问 [MiniMax 开发者控制台](https://www.minimax.chat/)
2. 注册/登录账户
3. 获取您的 API 密钥

### 第二步：配置 API 密钥

选择以下任一方式配置您的 API 密钥：

#### 方式1：编辑 .env.local 文件（推荐）
```bash
# 编辑 .env.local 文件
ALPHA_VANTAGE_API_KEY=alpha_vantage_api_key_placeholder
OPENAI_API_KEY=openai_api_key_placeholder
MINIMAX_API_KEY=您的实际MiniMax_API密钥
```

#### 方式2：设置环境变量
```powershell
# Windows PowerShell
$env:MINIMAX_API_KEY="您的实际MiniMax_API密钥"

# 或者添加到系统环境变量中
```

#### 方式3：直接修改示例文件
编辑 `.env.example` 文件，将 `your-api-key-here` 替换为您的实际密钥。

### 第三步：运行测试

#### Node.js 测试
```bash
node test-codingplan.js
```

#### Python 测试
```bash
python minimax_integration.py
```

## 🔧 功能特性

### Node.js 集成
- ✅ API 连接测试
- ✅ 代码生成测试
- ✅ 彩色控制台输出
- ✅ 详细错误诊断

### Python 集成
- ✅ 代码生成 (`generate_code`)
- ✅ 代码分析 (`analyze_code`)
- ✅ 代码优化 (`optimize_code`)
- ✅ 代码解释 (`explain_code`)
- ✅ 代码调试 (`debug_code`)
- ✅ 通用对话 (`chat`)

### VSCode 集成
- ✅ 调试配置
- ✅ Python 环境设置
- ✅ 格式化和代码检查
- ✅ 环境变量自动加载

## 🎯 使用示例

### Python 代码生成示例
```python
from minimax_integration import MiniMaxCodingPlan

# 初始化客户端
client = MiniMaxCodingPlan()

# 生成股票分析代码
response = client.generate_code(
    "创建一个函数计算股票价格的布林带指标",
    "python"
)

if response.success:
    print(response.content)
```

### 代码优化示例
```python
# 优化现有代码
old_code = '''
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)
'''

response = client.optimize_code(old_code, "python")
print(response.content)
```

## 🚨 安全注意事项

1. **不要将 API 密钥提交到版本控制系统**
   - `.env.local` 已在 `.gitignore` 中
   - 请确保不要提交包含真实密钥的文件

2. **定期轮换 API 密钥**
   - 建议定期更新您的 API 密钥

3. **监控 API 使用量**
   - 注意控制台输出的使用统计信息

## 🐛 故障排除

### 常见问题
1. **"未找到有效的 MiniMax API 密钥"**
   - 检查 `.env.local` 文件是否存在且格式正确
   - 确认 API 密钥没有多余的空格或引号

2. **"网络连接失败"**
   - 检查网络连接
   - 确认防火墙设置

3. **"API 响应异常"**
   - 验证 API 密钥是否有效
   - 检查 MiniMax 服务状态

### 调试模式
运行测试脚本时会显示详细的错误信息和调试输出。

## 📁 文件说明

- `test-codingplan.js` - Node.js 测试脚本
- `minimax_integration.py` - Python 集成模块
- `package.json` - Node.js 项目配置
- `.env.local` - 本地环境变量（需手动配置）
- `.env.example` - 环境变量示例
- `.vscode/` - VSCode 配置文件

## 🎊 集成完成后

一旦配置成功，您就可以在股票分析系统中使用 MiniMax 的强大功能：

1. **智能代码生成** - 自动生成交易策略代码
2. **代码优化建议** - 改进现有算法性能
3. **错误调试** - 快速定位和修复问题
4. **代码解释** - 理解复杂的金融算法逻辑

立即开始体验 AI 辅助的股票分析开发吧！🚀
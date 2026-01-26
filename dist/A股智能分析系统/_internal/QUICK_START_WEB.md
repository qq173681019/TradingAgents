# 🚀 Web版快速启动指南

## ⚡ 5分钟快速开始

### 步骤1: 安装依赖

```bash
# 如果还没安装
pip install flask flask-cors
```

### 步骤2: 启动系统

#### 方式A: Windows用户 (推荐)
```bash
# 直接双击运行
启动Web版系统.bat
```
**这个脚本会自动：**
- ✅ 启动Flask后端
- ✅ 打开Web前端
- ✅ 显示系统信息

#### 方式B: 手动启动

**终端1 - 启动Flask后端：**
```bash
python flask_backend.py
```

**终端2 - 打开Web前端：**
```bash
# Windows
start web_interface.html

# Mac
open web_interface.html

# Linux
xdg-open web_interface.html
```

### 步骤3: 开始使用

1. **单股分析**: 输入股票代码 (如 600519)
2. **批量评分**: 输入多个股票代码，快速评分
3. **查看推荐**: 根据评分自动生成投资推荐

---

## 📱 功能速览

### 单股分析
```
输入: 600519
输出: 贵州茅台的完整分析报告
      ├─ 技术评分: 7.5/10
      ├─ 基本面评分: 8.2/10
      ├─ 综合评分: 7.9/10 ⭐ 推荐买入
      ├─ 当前价格: ¥1250.50
      ├─ 技术指标 (RSI, MACD等)
      ├─ 基本面指标 (PE, PB, ROE等)
      └─ AI投资建议
```

### 批量评分
```
输入: 
600519
600036
000002
300750
600887

输出: 快速评分结果 (5秒内)
排序: 按综合评分从高到低
显示: 代码、技术评分、基本面评分、综合评分、价格
```

### 投资推荐
```
参数: 最低评分(默认6.0) + 股票类型(全部/主板/创业板/科创板)
输出: 推荐的股票列表和理由
```

---

## 🔗 API端点速查

### 所有API调用示例

```bash
# 1. 健康检查
curl http://localhost:5000/api/health

# 2. 分析单只股票
curl http://localhost:5000/api/analyze/600519

# 3. 批量评分
curl -X POST http://localhost:5000/api/batch-score \
  -H "Content-Type: application/json" \
  -d '{"stocks": ["600519", "600036"], "use_llm": false}'

# 4. 获取推荐
curl "http://localhost:5000/api/recommendations?min_score=6.0&type=all"
```

---

## ⚙️ 常见配置

### 启用LLM分析

编辑 `a_share_gui_compatible.py` 第~555行：

```python
# 设置默认LLM模型
self.llm_var = tk.StringVar(value="deepseek")  # 可选: deepseek, minimax, openrouter, gemini

# 设置API密钥 (在config.py中)
DEEPSEEK_API_KEY = "your_key_here"
MINIMAX_API_KEY = "your_key_here"
```

### 调整评分权重

编辑 `a_share_gui_compatible.py` 第~10727行：

```python
# 修改权重
tech_weight = 0.4    # 技术面权重 (可改为0.3-0.5)
fund_weight = 0.6    # 基本面权重 (可改为0.5-0.7)
```

### 修改Flask端口

编辑 `flask_backend.py` 最后一行：

```python
app.run(
    host='127.0.0.1',
    port=5000,  # 改为其他端口，如8080
    debug=True,
    use_reloader=False,
    threaded=True
)
```

---

## 🧪 测试功能

### 运行自动测试

```bash
# 确保Flask后端正在运行
python test_web_version.py
```

**输出示例：**
```
✅ 后端服务状态: online
✅ 测试股票 600519 (贵州茅台)
  技术评分: 7.5
  基本面评分: 8.2
  综合评分: 7.9
  价格: ¥1250.50
...
✅ 所有测试完成
```

---

## 🎯 典型使用场景

### 场景1: 快速评估一只股票

```
1. 打开Web界面
2. 点击"单股分析"标签页
3. 输入股票代码 (如 000002)
4. 点击"分析"按钮
5. 查看结果 (技术面+基本面+建议)
```

**耗时**: 5-10秒

### 场景2: 快速筛选优质股票

```
1. 打开Web界面
2. 点击"批量评分"标签页
3. 输入10-20只股票代码
4. 点击"开始批量评分"
5. 等待完成 (通常1-2分钟)
6. 查看排名结果
```

**效果**: 快速排序，找到综合评分最高的股票

### 场景3: 获取AI投资建议

```
1. 单股分析某只股票
2. 查看"投资建议"部分
3. 阅读AI生成的建议
4. 参考建议做投资决策
```

**优势**: AI分析速度快，综合多个指标

---

## ⚠️ 常见问题

### Q: 后端启动失败？

```
可能原因:
1. Python环境错误
2. 依赖未安装
3. 端口被占用

解决方案:
# 检查Python
python --version

# 检查Flask
python -c "import flask; print(flask.__version__)"

# 安装依赖
pip install flask flask-cors

# 检查端口占用
netstat -ano | findstr :5000  (Windows)
lsof -i :5000                 (Mac/Linux)
```

### Q: Web无法连接后端？

```
可能原因:
1. 防火墙阻止
2. localhost解析问题
3. 后端未启动

解决方案:
# 检查后端是否运行
curl http://localhost:5000/api/health

# 尝试IP地址
http://127.0.0.1:5000 (而非localhost)

# 检查浏览器控制台 (F12)
查看Network标签中的请求错误
```

### Q: 分析很慢？

```
可能原因:
1. 网络连接慢
2. 数据源API响应慢
3. 正在进行LLM分析

解决方案:
1. 关闭LLM分析 (不勾选Use LLM)
2. 检查网络连接
3. 用更少的股票测试
4. 查看后端控制台日志
```

### Q: 某些股票无法分析？

```
可能原因:
1. 股票代码错误
2. 股票停牌/退市
3. 数据源暂时不可用
4. 网络连接问题

解决方案:
1. 确认股票代码正确
2. 验证该股票是否活跃
3. 稍后重试或联系数据源
4. 检查网络连接
```

---

## 📊 评分说明

### 评分区间

| 评分范围 | 评价 | 建议 |
|---------|------|------|
| 8.0-10 | ⭐⭐⭐ 优秀 | 强烈推荐买入 |
| 7.0-8.0 | ⭐⭐ 很好 | 推荐买入 |
| 6.0-7.0 | ⭐ 良好 | 可考虑买入 |
| 5.0-6.0 | 一般 | 观望 |
| 0-5.0 | 较差 | 不推荐 |

### 评分组成

```
综合评分 = 技术评分 × 40% + 基本面评分 × 60%

技术评分 (0-10):
  ├─ RSI (相对强弱指数)
  ├─ MACD (趋势)
  ├─ 均线系统 (MA5, MA10, MA20, MA60)
  ├─ 成交量
  └─ 动量

基本面评分 (0-10):
  ├─ PE比率 (市盈率)
  ├─ PB比率 (市净率)
  ├─ ROE (净资产收益率)
  ├─ 营收增长
  └─ 利润增长
```

---

## 🔄 原GUI vs Web版

### 功能对比

| 功能 | 原GUI | Web版 | 说明 |
|------|------|-----|----|
| 单股分析 | ✅ | ✅ | 完全相同 |
| 批量评分 | ✅ | ✅ | 完全相同 |
| 推荐系统 | ✅ | ✅ | 完全相同 |
| 技术分析 | ✅ | ✅ | 完全相同 |
| 基本面分析 | ✅ | ✅ | 完全相同 |
| LLM建议 | ✅ | ✅ | 完全相同 |
| 筹码分析 | ✅ | ✅ | 完全相同 |

### 体验对比

| 方面 | 原GUI | Web版 |
|------|------|-----|----|
| 启动速度 | 快 | 稍慢(需启动后端) |
| 界面现代度 | 传统 | 现代 |
| 易用性 | 需学习 | 直观 |
| 跨平台 | 仅Windows | 全平台 |
| 响应速度 | 快 | 稍慢(网络延迟) |
| 远程使用 | ✗ | ✓ |

---

## 📚 进一步了解

详细文档：
- `WEB_VERSION_README.md` - 完整使用指南
- `WEB_IMPLEMENTATION_SUMMARY.md` - 技术实现细节
- `README.md` - 原有GUI文档

---

## 🎉 开始使用

```bash
# 一行命令启动 (Windows)
启动Web版系统.bat

# 或手动启动 (所有平台)
python flask_backend.py  # 终端1
# 然后用浏览器打开 web_interface.html
```

**就这么简单！** 🚀

---

最后更新: 2026-01-26  
版本: 1.0

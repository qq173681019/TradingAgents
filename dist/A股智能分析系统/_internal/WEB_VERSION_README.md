# A股智能分析系统 - Web版使用指南

## 📋 项目概述

这是原有A股智能分析系统的**完整Web版本**，保留了所有核心功能，但以Web界面替代Tkinter GUI。

### ✨ 核心功能

| 功能 | Tkinter GUI | Web版 | 说明 |
|------|-----------|--------|------|
| **单股分析** | ✅ | ✅ | 深度分析单只股票，包括技术面+基本面+LLM建议 |
| **批量评分** | ✅ | ✅ | 评分4396只股票，返回排名列表 |
| **推荐系统** | ✅ | ✅ | 生成投资推荐和买卖信号 |
| **技术分析** | ✅ | ✅ | 计算技术指标(RSI, MACD, MA等) |
| **基本面分析** | ✅ | ✅ | 计算PE, PB, ROE等指标 |
| **LLM分析** | ✅ | ✅ | 支持Deepseek, Minimax等模型 |
| **筹码分析** | ✅ | ✅ | 分析主力筹码分布 |
| **数据更新** | ✅ | ✅ | 实时更新K线和选手数据 |
| **多数据源** | ✅ | ✅ | Tencent, Sina, Yahoo, Baostock, Choice |

## 🚀 快速开始

### 1️⃣ 安装依赖

```bash
pip install flask flask-cors
```

### 2️⃣ 启动系统

#### 方式A: 使用启动脚本 (推荐Windows用户)

```bash
# 双击运行
启动Web版系统.bat
```

该脚本会:
- ✅ 自动启动Flask后端
- ✅ 自动打开Web前端
- ✅ 自动检查依赖

#### 方式B: 手动启动

```bash
# 终端1: 启动Flask后端
python flask_backend.py

# 终端2: 打开Web前端
# 用浏览器打开当前目录的 web_interface.html
# 或运行: start web_interface.html
```

### 3️⃣ 访问系统

- **Web前端**: `web_interface.html` (自动打开)
- **后端API**: `http://localhost:5000`
- **API文档**: 见下方

## 📱 Web界面说明

### 标签页1: 单股分析

分析单只股票的完整信息：

```
输入: 股票代码 (如 600519)
输出:
  ├─ 技术评分 (0-10)
  ├─ 基本面评分 (0-10)
  ├─ 综合评分 (0-10) ⭐ 关键指标
  ├─ 价格信息
  ├─ 技术指标 (RSI, MACD, MA等)
  ├─ 基本面指标 (PE, PB, ROE等)
  └─ 投资建议 (AI生成)
```

**例子:**
```
输入: 600519
输出:
  - 技术评分: 7.5
  - 基本面评分: 8.2
  - 综合评分: 7.9 ✨ 推荐买入
  - 当前价格: ¥1250.50
  - RSI: 65 (超买)
  - PE: 25.3
  - 投资建议: 该股票基本面良好，技术面显示超买...
```

### 标签页2: 批量评分

快速评分多只股票：

```
输入: 股票代码列表 (每行一个)
输出: 排序后的评分表
  ├─ 代码
  ├─ 技术评分
  ├─ 基本面评分
  ├─ 综合评分 ⭐ 排序依据
  └─ 当前价格
```

**例子:**
```
输入:
600519
600036
000002
300750
600887

输出:
600519   7.5   8.2   7.9  ¥1250.50
300750   8.1   7.8   7.95 ¥850.25
000002   6.8   7.5   7.15 ¥18.50
...
```

### 标签页3: 投资推荐

基于评分生成推荐：

```
参数:
  ├─ 最低评分 (如 6.0, 推荐 7.0+)
  └─ 股票类型 (全部, 主板, 创业板, 科创板)

输出: 推荐股票列表
  ├─ 代码
  ├─ 名称
  ├─ 评分
  └─ 推荐理由
```

## 🔌 API 文档

所有功能都通过REST API暴露，可直接调用。

### 1. 单股分析

```http
GET /api/analyze/<ticker>

示例: GET /api/analyze/600519

响应:
{
    "success": true,
    "code": "600519",
    "name": "贵州茅台",
    "data": {
        "stock_info": {...},
        "price": 1250.50,
        "scores": {
            "technical": 7.5,
            "fundamental": 8.2,
            "comprehensive": 7.9
        },
        "tech_data": {...},
        "fund_data": {...},
        "tech_analysis": "...",
        "fund_analysis": "...",
        "advice": "...",
        "timestamp": "2026-01-26T10:30:00"
    }
}
```

### 2. 批量评分

```http
POST /api/batch-score

请求体:
{
    "stocks": ["600519", "600036", "000002"],
    "use_llm": false
}

响应:
{
    "success": true,
    "total": 3,
    "scored": 3,
    "results": {
        "600519": {
            "technical_score": 7.5,
            "fundamental_score": 8.2,
            "comprehensive_score": 7.9,
            "price": 1250.50
        },
        ...
    }
}
```

### 3. 获取推荐

```http
GET /api/recommendations?min_score=6.0&type=mainboard

响应:
{
    "success": true,
    "min_score": 6.0,
    "stock_type": "mainboard",
    "recommendations": [...]
}
```

### 4. 健康检查

```http
GET /api/health

响应:
{
    "status": "online",
    "timestamp": "2026-01-26T10:30:00",
    "gui_ready": true
}
```

## 🛠️ 配置说明

### 修改LLM模型

编辑 `a_share_gui_compatible.py` 中的 LLM 配置：

```python
# 行 ~555: 设置默认LLM
self.llm_var = tk.StringVar(value="deepseek")  # 可选: deepseek, minimax, openrouter, gemini

# 或在GUI中选择：
# 在Web版中通过单股分析时自动使用配置的模型
```

### 启用Choice数据源

编辑 `config.py`:

```python
CHOICE_USERNAME = "your_username"
CHOICE_PASSWORD = "your_password"
```

然后在使用时会自动调用Choice API获取实时数据。

### 修改评分权重

编辑 `a_share_gui_compatible.py` 中的评分计算函数:

```python
# 行 ~10727: calculate_comprehensive_score
tech_weight = 0.4  # 技术面权重
fund_weight = 0.6  # 基本面权重
```

## 📊 分析逻辑说明

### 评分体系 (0-10分)

#### 技术面评分 (calculate_technical_score)

```
基于:
  ├─ RSI (30-70为正常, <30超卖, >70超买)
  ├─ MACD (金叉看多, 死叉看空)
  ├─ 均线系统 (MA5, MA10, MA20, MA60)
  ├─ 成交量 (量能是否配合)
  └─ 动量 (上升, 震荡, 下降)

权重: 40% (默认)
```

#### 基本面评分 (calculate_fundamental_score)

```
基于:
  ├─ PE比率 (越低越好，但要合理)
  ├─ PB比率 (越低越好)
  ├─ ROE (越高越好，>15%优秀)
  ├─ 营收增长 (越高越好)
  └─ 利润增长 (越高越好)

权重: 60% (默认)
```

#### 综合评分 (calculate_comprehensive_score)

```
= 技术评分 × 40% + 基本面评分 × 60%

评分区间:
  8.0-10.0: ⭐⭐⭐ 强烈推荐 (买入)
  7.0-8.0:  ⭐⭐   推荐 (买入)
  6.0-7.0:  ⭐    可考虑 (观望)
  5.0-6.0:  -    一般 (持有)
  0-5.0:    ❌   不推荐 (卖出)
```

### LLM分析

支持多个LLM模型生成投资建议：

```
模型选择:
  ├─ deepseek (推荐，免费)
  ├─ minimax (备选)
  ├─ openrouter (多模型)
  └─ gemini (Google)

输出:
  - 短期建议 (1-3个月)
  - 中期建议 (3-6个月)
  - 长期建议 (6-12个月)
  - 风险提示
```

## ⚡ 性能优化

### 缓存策略

系统自动缓存：

```
├─ 股票信息 (长期缓存)
├─ K线数据 (每日更新)
├─ 技术指标 (实时计算)
├─ 基本面数据 (定期更新)
└─ 推荐结果 (分析时生成)
```

### 批量评分优化

- 启用异步处理
- 自动分批请求
- 并发控制 (防止超时)

## 🐛 常见问题

### Q: Web界面无法连接后端？

A: 
```
1. 检查Flask是否运行 (应有 "Running on http://127.0.0.1:5000" 信息)
2. 检查防火墙是否允许 5000 端口
3. 尝试在浏览器访问 http://localhost:5000/api/health
4. 检查浏览器控制台错误信息 (F12 -> Console)
```

### Q: 分析很慢，怎么优化？

A:
```
1. 检查网络连接
2. 关闭LLM分析 (不勾选Use LLM)
3. 使用更少的股票进行批量评分
4. 检查API调用限流情况
```

### Q: 某些股票无法分析？

A:
```
1. 股票代码是否正确 (如 600519, 不要加 .SH)
2. 是否是停牌或退市股票
3. 检查网络连接
4. 查看后端控制台错误信息
```

### Q: 能否同时运行GUI版和Web版？

A:
```
✅ 可以！两个版本完全独立
- GUI版使用Tkinter (进程1)
- Web版使用Flask (进程2)
- 两者共享相同的分析逻辑
- 可以同时运行，互不影响
```

## 📚 文件清单

```
TradingAgent/
├─ flask_backend.py              # Flask后端应用 (新增)
├─ web_interface.html            # Web前端界面 (新增)
├─ 启动Web版系统.bat            # 启动脚本 (新增)
├─ WEB_VERSION_README.md         # 本文件
├─ a_share_gui_compatible.py     # 原有GUI (保持不变)
├─ chip_health_analyzer.py       # 筹码分析 (保持不变)
├─ minimax_integration.py        # LLM集成 (保持不变)
└─ requirements.txt              # 依赖列表 (更新)
```

## 🔄 原GUI vs Web版对比

| 方面 | 原GUI | Web版 | 更好的选择 |
|------|------|-----|----|
| **功能** | 100% | 100% | 相同 |
| **界面** | Tkinter (传统) | 现代Web设计 | Web版 |
| **易用性** | 需学习按钮位置 | 直观明确 | Web版 |
| **跨平台** | 仅Windows | 所有平台 | Web版 |
| **性能** | 本地 | 网络延迟 | GUI版 |
| **自定义** | 代码修改 | CSS修改 | Web版 |
| **远程访问** | 不支持 | 支持 | Web版 |

## 🎯 推荐使用场景

### 使用Web版的场景:
- 📱 想要现代化UI
- 🌐 需要跨平台使用
- 🔄 经常远程访问
- 📊 需要快速入门
- 🚀 想要扩展功能 (API)

### 使用原GUI的场景:
- ⚡ 追求最快响应速度
- 🔧 经常自定义分析参数
- 📊 需要深度功能定制
- 🖥️ 只在Windows上使用

## 📞 技术支持

遇到问题？

1. **检查错误日志**: 查看Flask控制台输出
2. **查看浏览器控制台**: F12 -> Console
3. **测试API**: 访问 http://localhost:5000/api/health
4. **查看README**: 原有GUI的 README.md

## 🎉 总结

Web版保留了原有系统的**所有功能**，只是提供了：
- ✨ 更现代的用户界面
- 🌐 更好的跨平台支持
- 🚀 更容易扩展的API
- 📱 更好的用户体验

**您可以放心使用Web版，所有原有功能都完整保留！**

---

最后更新: 2026-01-26  
版本: 1.0  
兼容: Python 3.7+

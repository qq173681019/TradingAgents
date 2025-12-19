# PE和PB数据获取说明

## 📊 核心发现

**PE（市盈率）和PB（市净率）不是计算的，而是从数据源直接获取的！**

但当所有数据源失败时，会使用**估算的默认值**。

---

## 🔍 两种数据源的PE/PB获取方式

### 1️⃣ **常规数据源（不使用Choice）**

**数据获取流程**（按优先级）：

#### **第1优先：Tushare Pro**
```python
# 需要2000积分
pro = ts.pro_api(TUSHARE_TOKEN)
basic_info = pro.stock_basic(ts_code=f"{ticker}.SH")
# 获取：pe_ratio, pb_ratio, roe 等
```

#### **第2优先：Baostock**
```python
rs = bs.query_stock_basic(code=f"sh.{ticker}")
# 返回基本面数据
```

#### **第3优先：yfinance**
```python
stock = yf.Ticker(f"{ticker}.SS")
info = stock.info
pe_ratio = info.get('trailingPE')
pb_ratio = info.get('priceToBook')
```

#### **第4优先：akshare**
```python
import akshare as ak
stock_individual_info = ak.stock_individual_info_em(symbol=ticker)
# 提取：市盈率-动态、市净率
```

#### **第5兜底：价格估算（使用默认值）⚠️**
```python
# 位置：a_share_gui_compatible.py 第8476行
return {
    'pe_ratio': 15.0,   # ⚠️ 固定默认值 - 市场平均PE
    'pb_ratio': 1.8,    # ⚠️ 固定默认值 - 市场平均PB
    'roe': 10.0,        # 统一为百分比形式
}
```

**说明**：
- 600036使用的是**第5兜底方案**（所有数据源都失败了）
- PE=15.0, PB=1.8 **不是真实数据，是估算的固定值**

---

### 2️⃣ **Choice数据源**

**数据获取方式**：

#### **直接从Choice API获取真实数据**
```python
# 位置：a_share_gui_compatible.py 第18774-18785行
from EmQuantAPI import c

# 分别获取PE, PB, ROE
pe_data = c.css(stock_code, "PE", "")
pb_data = c.css(stock_code, "PB", "")
roe_data = c.css(stock_code, "ROE", "")

# 提取真实值
pe = float(pe_data.Data[stock_code][0])  # 真实PE
pb = float(pb_data.Data[stock_code][0])  # 真实PB
roe = float(roe_data.Data[stock_code][0]) if success else 10.0
```

**说明**：
- Choice从金融终端API获取**真实的实时数据**
- PE=7.09, PB=1.01 是**当前市场真实值**

---

## 📈 实际案例对比（600036 招商银行）

### **不使用Choice（常规数据源）**

从你的日志可以看到：
```
600036 尝试Tushare基础数据...
ℹ 600036 Tushare积分不足(需2000分获取基本面)，自动切换备用源

600036 尝试Baostock基础数据...
⚠ 600036 Baostock基础数据为空

600036 尝试yfinance基础数据...
yfinance获取 600036 基础数据失败: [SSL证书错误]

600036 尝试akshare基础数据接口...
600036 akshare基础数据接口失败: [代理连接失败]

600036 尝试价格估算基础数据...  ⚠️ 启用兜底方案
✅ 步骤3完成: 基本面数据获取成功 - PE15.0 [实时数据源]
```

**结果**：
- PE = **15.0** ❌ 估算值（固定）
- PB = **1.8** ❌ 估算值（固定）
- ROE = **10.0** ❌ 估算值（固定）

---

### **使用Choice数据源**

从你的日志可以看到：
```
📡 正在从Choice API实时获取 600036 基本面数据...
[DEBUG] PE解析: 7.093937
[DEBUG] PB解析: 1.006799
[DEBUG] ROE解析（使用默认值）: 10.0 (ErrorCode=10000013)
✅ 步骤3完成: Choice API基本面获取成功 - PE7.1 [Choice实时API]
```

**结果**：
- PE = **7.09** ✅ 真实值（从Choice API）
- PB = **1.01** ✅ 真实值（从Choice API）
- ROE = **10.0** ⚠️ 估算值（Choice ROE接口失败）

---

## 📊 差异原因分析

### **PE差异：15.0 vs 7.09 (相差7.91)**

| 项目 | 常规数据源 | Choice数据源 | 差异 |
|------|-----------|-------------|------|
| **PE** | 15.0 | 7.09 | **-52.7%** |
| **数据来源** | 兜底估算值 | Choice API真实值 | - |
| **是否准确** | ❌ 不准确 | ✅ 准确 | - |

**说明**：
- 15.0 是固定的市场平均值，不是招商银行的真实PE
- 7.09 是招商银行当前的真实市盈率
- 差异巨大是因为一个是估算，一个是真实数据

---

### **PB差异：1.8 vs 1.01 (相差0.79)**

| 项目 | 常规数据源 | Choice数据源 | 差异 |
|------|-----------|-------------|------|
| **PB** | 1.8 | 1.01 | **-43.9%** |
| **数据来源** | 兜底估算值 | Choice API真实值 | - |
| **是否准确** | ❌ 不准确 | ✅ 准确 | - |

**说明**：
- 1.8 是固定的市场平均值，不是招商银行的真实PB
- 1.01 是招商银行当前的真实市净率
- 银行股PB通常较低（<1.5），估算值明显偏高

---

## 🔧 为什么常规数据源全部失败？

### **1. Tushare积分不足**
```
ℹ 600036 Tushare积分不足(需2000分获取基本面)
```
- 需要2000积分才能获取基本面数据
- 目前积分不足

### **2. Baostock数据为空**
```
⚠ 600036 Baostock基础数据为空
```
- Baostock可能不提供基本面数据
- 或该股票没有数据

### **3. yfinance SSL证书错误**
```
Failed to perform, curl: (77) error setting certificate verify locations
```
- SSL证书验证失败
- 网络配置问题

### **4. akshare代理连接失败**
```
HTTPSConnectionPool: Max retries exceeded
Caused by ProxyError: Remote end closed connection without response
```
- 代理服务器问题
- 网络连接异常

---

## 💡 解决方案

### **方案1：使用Choice数据源（推荐）✅**
- ✅ 直接从金融终端获取真实数据
- ✅ 准确可靠
- ✅ 已在你的系统中配置

### **方案2：升级Tushare积分**
- 需要2000积分
- 费用较高

### **方案3：修复网络配置**
- 解决SSL证书问题
- 解决代理连接问题
- 不保证成功

### **方案4：接受估算值（不推荐）❌**
- PE=15.0, PB=1.8 只是市场平均值
- 对于银行股等特殊行业误差极大
- 导致评分不准确

---

## 📌 总结

1. **PE和PB是从数据源获取的，不是计算的**
2. **常规数据源失败时会使用固定的估算值**：
   - PE = 15.0（市场平均）
   - PB = 1.8（市场平均）
3. **Choice数据源提供真实值**：
   - PE = 7.09（招商银行真实PE）
   - PB = 1.01（招商银行真实PB）
4. **差异巨大的原因**：
   - 估算值 vs 真实值
   - 市场平均 vs 个股实际
5. **建议**：
   - ✅ 优先使用Choice数据（准确）
   - ⚠️ 常规数据源需要修复网络配置
   - ❌ 不要依赖估算值做投资决策

---

## 🔗 相关代码位置

- 价格估算兜底方案: [a_share_gui_compatible.py#L8476-L8483](d:\TradingAgents\a_share_gui_compatible.py#L8476-L8483)
- Choice PE/PB获取: [a_share_gui_compatible.py#L18774-L18805](d:\TradingAgents\a_share_gui_compatible.py#L18774-L18805)
- 数据获取流程: [a_share_gui_compatible.py#L8350-L8520](d:\TradingAgents\a_share_gui_compatible.py#L8350-L8520)

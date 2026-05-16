# 评分映射 Gap 分析报告

## 问题概述
- **V19回测**: 86.2% beat_idx
- **实盘验证**: 25% 胜率（T+1）
- **根因**: 推荐器 `map_stock_to_subscores()` 用的是**估算映射**，不是真实K线特征

## 核心差异

### 1. 回测用的是**真实K线数据**
回测 `calc_features()` 从日K线计算33个真实特征：
- `r1/r3/r5/r10/r20`: 真实涨跌幅
- `close_ma5/ma10/ma20`: 真实MA偏离度
- `ma5_slope/ma10_slope`: 真实MA斜率
- `rsi`: 真实14日RSI
- `vol5/vol10`: 真实波动率
- `macd`: 真实MACD
- `consistency/streak`: 真实连涨天数
- `vol_ratio/vol_shrink/turn_spike`: 真实成交量指标

### 2. 推荐器用的是**粗略估算**
`map_stock_to_subscores()` 用 stock_screener 的 0-10 分数**反向估算**特征：

| 特征 | 回测真实计算 | 推荐器估算方式 | 偏差程度 |
|------|------------|--------------|---------|
| `momentum_s` | r1*0.3+r3*0.3+r5*0.4 | (technical-4.0)*1.2+recent_gain*0.05 | ⚠️ 大 |
| `trend_s` | MA排列+斜率 | technical*0.8 | ⚠️ 大 |
| `consistency_s` | 连涨天数*1.5 | chip*0.6 | ⚠️ 中 |
| `rsi_s` | RSI 40-60→3, 30-40→4 | technical映射区间 | ⚠️ 大 |
| `vol_s` | vol_ratio区间 | turnover映射 | ⚠️ 中 |
| `mr_s` | -r5*0.5-r3*0.3 | -recent_gain*0.15 | ⚠️ 大 |
| `rel_str` | 个股vs指数涨幅差 | recent_gain*0.3 | ⚠️ 大 |
| `close_ma5/20` | 真实偏离度 | (technical-5.0)/20 | ⚠️ 极大 |

### 3. 条件判断全部失真
回测的 boost/penalty 条件基于真实指标：
- `consistency >= 4` → 真实连涨4天 → 推荐器: `int(chip/2.0)` ≈ 随便猜
- `close_ma20 > 0` → 真实站上MA20 → 推荐器: `(technical-5.0)/20`
- `rsi > 70` → 真实超买 → 推荐器: `50 + (technical-5.0)*5`
- `vol5 > 3.5` → 真实高波 → 推荐器: `2.0 + (10-technical)*0.3`

## 根本原因
**推荐器没有获取K线数据来计算真实特征**，而是用 stock_screener 的打分结果反推。

stock_screener 的分数是综合打分(0-10)，而回测需要的是原始技术指标值。这两个维度的映射本质上是不可能的——你没法从"技术面9分"精确还原出RSI=55、MA5斜率=0.02、连涨3天这些信息。

## 解决方案

### 方案A：推荐器直接计算真实特征（推荐）
在推荐器中引入 K线数据，对每只候选股调用 `calc_features()` 计算真实特征，然后用V19参数评分。

**改动点：**
1. 在 `daily_recommender.py` 中导入 `calc_features` 从 `backtest_v19_sector.py`
2. 加载K线数据（或复用 stock_screener 已获取的数据）
3. 对每只候选股计算真实特征
4. 直接用真实特征 + V19参数评分

**优点：** 彻底消除映射偏差
**缺点：** 需要K线数据，增加数据获取时间

### 方案B：stock_screener 输出原始特征（轻量）
在 stock_screener 阶段就把 rsi、close_ma20、vol5 等真实值一起输出到 stock dict 中。

**改动点：**
1. 修改 `stock_screener.py`，在评分时保存中间特征值
2. `map_stock_to_subscores()` 优先使用真实值

**优点：** 改动较小
**缺点：** stock_screener 可能没有全部所需数据

### 建议：方案A
既然 V19 回测已经证明效果很好，最直接的做法就是让推荐器复用回测的评分逻辑，消除中间的映射损耗。

## 优先级
**高** — 这是回测 86.2% vs 实盘 25% 的核心原因，修复后预期实盘胜率大幅提升。

---
*Generated: 2026-05-09*

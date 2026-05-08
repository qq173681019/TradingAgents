# TradingAgent 算法演进史

> 本文档记录了 TradingAgent 股票推荐系统从 V1 到 V14 的完整演进过程，
> 包括每个版本的核心思路、回测结果、失败原因和关键发现。
> **供后续 AI Agent 接手时快速了解项目背景。**

---

## 项目概述

- **目标**: 每天推荐3只A股，次日涨幅跑赢沪深300指数的比例 ≥ 80%
- **数据源**: 东方财富API（首选）+ Tushare + AKShare + 腾讯API
- **K线数据**: `TradingShared/data/kline_cache/kline_full_latest.json`（全市场）
- **指数数据**: `TradingShared/data/kline_cache/index_full_latest.json`
- **评分数据**: `TradingShared/data/batch_stock_scores_*.json`
- **评估期**: 2026-03-01 ~ 2026-04-24（约40个交易日）
- **核心指标**: 
  - **win_rate**: 推荐的3只中跑赢指数的比例 > 50% 的天数占比
  - **beat_idx**: 推荐股平均涨幅 > 沪深300指数涨幅的天数占比
  - **ne_beat**: 排除 Risk 5（极端行情）后的 beat_idx

---

## 算法版本演进

### V1 (2026-04-08) — 初始版本
- **思路**: 基础技术指标 + 新闻情绪分析
- **结果**: 基线水平，未详细记录
- **文件**: 已删除（早期探索）

### V2 (2026-04-09) — 6个月 Walk-Forward
- **思路**: 6个月回测窗口 + 增强特征工程
- **改进**: 扩大选股池、追高过滤、均线多头排列、均值回归信号、XGBoost/ML模型
- **结果**: < 50% beat_idx
- **失败原因**: 特征太多噪声大，ML模型过拟合
- **文件**: `backtest_v2.py` → 已删除

### V3 / V3.1 (2026-04-10) — 机器学习尝试
- **思路**: XGBoost + LightGBM + Logistic 滚动训练
- **改进**: 899只股票池、换手率变化、板块热度、涨跌幅异常、市场环境分类
- **结果**: < 50% beat_idx
- **失败原因**: 未来数据泄露风险、模型不稳定
- **文件**: `backtest_v3.py`, `backtest_v31.py` → 已删除

### V4 (2026-04-11) — 熊市防御策略 ⭐
- **思路**: 市场状态精细检测 + 多策略自适应
- **改进**: 
  - VIX-like 波动率检测
  - 牛/熊/震荡市场分类
  - 熊市: 低Beta + 高基本面 + 均值回归
  - 自适应选股数量（极端行情减仓）
  - 板块防御偏好
- **结果**: **73.1% 天数跑赢指数**（R1-R4）
- **关键发现**: 市场状态检测是有效的，分散化选股有帮助
- **遗留问题**: K线缓存899只/评分池210只仅覆盖41只，无K线数据降权40%
- **文件**: `backtest_v4.py` → 已删除（逻辑已被 V8/V9 继承）

### V5 (2026-04-25) — 适配新数据格式
- **思路**: 迁移到 `kline_full_latest.json`（3192只）+ `index_full_latest.json`
- **改进**: 
  - 扩大到3192只股票
  - 50维特征、评估40天
  - 加强相对强度权重 + 反转加强
  - 涨停后回调回避、强势连涨加分
- **结果**: 约 56% beat_idx（`backtest_final_report.txt` 记录最佳配置 GB_d2_tw10_n3 = 56.1%）
- **失败原因**: 特征过多导致信号噪声
- **文件**: `backtest_v5.py` → 已删除

### V6 (2026-04-26) — 震荡市双策略
- **思路**: Risk 3 使用 resilient + reversal 双策略
- **改进**: 
  - resilient: 低波动 + 高相对强度 + 防御板块
  - reversal: RSI超卖 + 均值回归 + 支撑位
  - Risk 3 门槛 0.3 → 0.5
- **结果**: 约 55-58% beat_idx
- **失败原因**: 双策略分散了信号，reversal 在震荡市不生效
- **文件**: `backtest_v6.py` → 已删除

### V7 (2026-04-27) — 震荡市质量提升
- **思路**: 提升 Risk 3 选股门槛 + 加强惩罚
- **改进**: 
  - Risk 3 门槛 0.3 → 0.5
  - 近期涨过多惩罚 (r3 > 10%)
  - r5 < -3% 惩罚
  - r10 正向动量加权
  - blacklist: 前一天涨停股第二天回避
- **结果**: 约 58% beat_idx
- **失败原因**: 过滤太严导致选股池太小
- **文件**: `backtest_v7.py` → 已删除

### V8 (2026-04-28) — 震荡市板块轮动 ⭐
- **思路**: Risk 3 放弃防御低波动，改用板块轮动选股
- **改进**: 
  - 实时计算行业3日/5日相对强度
  - 选最热板块中动量最强的个股
  - 热板块加速引擎（动态权重替代静态 sector_avg）
  - Risk 3 选股 2→3只，Risk 5 选股 1→2只
- **结果**: **60% beat_idx**
- **关键发现**: 板块轮动在震荡市有效，但分散度不够
- **文件**: `backtest_v8.py` → 已删除（逻辑已被 V9 继承）

### V9 系列 (2026-04-28) — 分散化优化 ⭐⭐ 最佳版本

这是经过最多实验的版本，测试了多种变体：

| 变体 | 核心改动 | beat_idx |
|------|---------|----------|
| V9a | 稳健板块+全局过滤 | 47.5% ❌ |
| V9b | 分散化+过热过滤 | 60% ❌ |
| V9c | 超分散10只 | 55% ❌ |
| **V9d** | Ensemble rotation+defense | **65%** ✅ |
| V9e | R3均值回归 | 57.5% ❌ |
| **V9** | V8 + MAX_INDUSTRY=1 | **62.5%** ✅ |
| **V9_best** | 同V9 | **62.5%** ✅ |
| **V9_final** | 分散化改进版 | **62.5%** ✅ |

**V9 核心算法（保留版本）:**

```
市场状态检测:
  - 指数MA20 vs MA5 → 牛/熊/震荡
  - 连跌天数 → Risk Level 1-5
  - 波动率 → vol_state: high/normal/low

Risk 5 (极端): defense 策略
  - 高Beta惩罚 (×0.3-0.6)
  - 高Beta行业严厉惩罚 (×0.1)
  - 防御行业加分 (×1.3)
  - 相对强度为主 (18%)
  - 均值回归加强 (12%)
  - 选2只

Risk 4 (熊市): defense 策略  
  - 类似 Risk 5 但略宽松
  - 选3只

Risk 3 (震荡): rotation 策略 ⭐ 核心创新
  - 动态板块热度（每日计算行业近3日平均涨幅）
  - 热板块中的强势个股
  - 板块热度 > 3%: ×1.8 加成
  - 板块热度 < -2%: ×0.3 惩罚
  - RSI > 75: ×0.3 不追高
  - MA20 上方: ×1.2 安全加成
  - 选5只

Risk 1-2 (牛/正常): momentum 策略
  - 动量+趋势为主
  - 选5-6只

通用规则:
  - MAX_INDUSTRY = 1 (强制行业分散)
  - 涨跌停过滤 (pct_1d > ±9.5%)
  - Blacklist: 前一天大跌3%+、连续2天跌、Risk4+前一天涨6%+
  - 最低分数门槛 (Risk4/3: 0.3, Risk1/2: 0.5)
```

**V9d 额外改进:**
- Ensemble 方法：同时运行 rotation + defense 策略
- 两种策略的候选股合并后重新排名

**保留文件:**
- `backtest_v9.py` — V8基准 + MAX_INDUSTRY=1 (62.5%)
- `backtest_v9_best.py` — 同上 (62.5%)
- `backtest_v9_final.py` — 分散化改进版 (62.5%)
- `backtest_v9d.py` — Ensemble rotation+defense (65%)

### V10 (2026-04-28) — 两阶段选股
- **思路**: Stage1 V9评分 → Stage2 PE/PB/OBV/缩量上涨过滤
- **结果**: 未达 50%
- **失败原因**: 估值过滤在A股短线无效
- **文件**: `backtest_v10.py` → 已删除

### V11 (2026-04-28) — 行业中性化
- **思路**: 行业内排名而非全市场排名 + 涨幅已大回避
- **结果**: 未达 50%
- **失败原因**: 行业内排名池太小，信号不足
- **文件**: `backtest_v11.py` → 已删除

### V12 (2026-04-29) — 极致精选
- **思路**: 只在信号极强时出手，宁可空仓
- **结果**: 42.4% beat_idx
- **失败原因**: 太保守导致大量空仓天
- **文件**: `backtest_v12.py` → 已删除

### V13 (2026-04-29) — 趋势跟随+量价确认
- **思路**: 纯趋势跟随 + 量价背离检测
- **结果**: 未成功回测（依赖 LightGBM 安装）
- **文件**: `backtest_v13.py` → 已删除

### V14 (2026-04-29) — 精选动量+市场择时
- **思路**: Hermes AI 生成的简化版
- **结果**: 42.4% beat_idx
- **失败原因**: 过于简化，丢失了市场状态检测
- **文件**: `backtest_v14.py` → 已删除

---

## 关键发现与教训

### ✅ 有效的策略
1. **市场状态检测** — 牛/熊/震荡分类是基础，不同市场用不同策略
2. **板块轮动** — 震荡市选最热板块中的强势股有效
3. **行业分散** — MAX_INDUSTRY=1 是最有效的单一改进
4. **相对强度** — 个股 vs 指数的相对表现比绝对表现更有预测力
5. **Blacklist 机制** — 前一天大跌/连涨的股票第二天回避
6. **追高过滤** — RSI > 75、pct_1d > 9.5% 的不追

### ❌ 无效的策略
1. **XGBoost/LightGBM** — 过拟合严重，不稳定
2. **纯均值回归** — 超跌反弹不可靠
3. **估值过滤** — PE/PB 在短线预测中无效
4. **行业内排名** — 池太小信号不足
5. **过度保守** — 空仓太多错失行情
6. **过于分散** — 10只反而降低 beat_idx

### ⚠️ 已知问题
1. **80% 目标远未达到** — 当前最佳 65% (V9d)
2. **极端行情 (Risk 5)** — 仍然表现差，需要更好的避险策略
3. **K线数据覆盖** — 评分池和K线池覆盖不一致
4. **回测期偏短** — 仅40天，统计显著性不足

---

## 当前项目文件结构

```
TradingAgent/
├── backtest_v9.py          # V9基准 (62.5% beat_idx) — 主要参考
├── backtest_v9_best.py     # V9最佳 (62.5% beat_idx)
├── backtest_v9_final.py    # V9分散化改进 (62.5% beat_idx)  
├── backtest_v9d.py         # V9d Ensemble (65% beat_idx) — 当前最佳
├── daily_recommender.py    # 每日推荐主入口
├── quick_recommend.py      # 快速推荐（无API依赖）
├── stock_screener.py       # 股票筛选器
├── market_state.py         # 市场状态检测
├── blacklist.py            # 黑名单过滤
├── news_analyzer.py        # 新闻情绪分析
├── email_notifier.py       # 邮件推送
├── export_recommendations.py  # 导出推荐结果
├── generate_mainboard_scores.py  # 生成主板评分数据
├── data_loader.py          # 数据加载器
├── fetch_kline_data.py     # K线数据获取
├── update_kline_batch.py   # 批量更新K线
├── update_kline_cli.py     # K线更新CLI
├── chip_health_analyzer.py # 筹码健康分析器
├── minimax_integration.py  # AI模型集成
├── minimax_feature_extensions.py  # AI特征扩展
├── a_share_gui_compatible.py  # GUI工具
├── requirements.txt
├── README.md
├── EVOLUTION.md            # ← 本文档
├── *.bat                   # 各种启动脚本
├── chanlun/                # 缠论分析模块
│   ├── chanlun_core.py     # 缠论核心算法
│   ├── backtest_chanlun.py # 缠论回测
│   ├── backtest_akshare.py # AKShare数据源
│   ├── backtest_tushare_large.py
│   ├── aggressive_scanner.py
│   ├── hourly_fetcher.py
│   ├── kline_merge.py
│   └── test_chanlun.py
├── experts/                # 多专家系统
│   ├── technical_expert.py
│   ├── fundamental_expert.py
│   ├── chip_expert.py
│   ├── macro_expert.py
│   └── debate_judge.py     # 专家辩论裁决
├── backtest_results/       # 历史回测报告
├── recommendation_history/ # 历史推荐记录
└── data/                   # 本地数据缓存
```

---

## 下一步方向建议

1. **突破 65% → 80%**: 需要根本性的方法改进，而非调参
2. **缠论集成**: `chanlun/` 目录已有基础代码，可尝试与 V9 融合
3. **多专家辩论**: `experts/` 目录有5个专家模块，可尝试投票机制
4. **更长回测期**: 当前40天不够，需要至少6个月
5. **实时验证**: stock-pick-v2 的 Cron 闭环系统在做每日验证
6. **情绪因子**: NewsData 新闻情绪 + 社交媒体情绪
7. **资金流向**: 大单/北向资金/主力资金

---

*文档创建: 2026-05-04*
*最后更新: 2026-05-04*

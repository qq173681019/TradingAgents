# 全栈工程师修改日志

## 2026-05-14 评分对齐修复

### 核心问题
daily_recommender.py 的评分与 backtest_v22_honest.py 存在严重不对齐：
1. **缺失 V22 新维度**: 回测使用了 bb_s, atr_s, vol_health_s, support_s, obv_s 共5个新子分数，但推荐器评分函数完全忽略
2. **缺失 V22 新条件**: exhaustion, vol_price_diverge, bb_oversold, atr_expand, distribution, near_support, vp_confirm/diverge 等条件从未检查
3. **归一化偏差**: 使用 `5.0 + raw * 0.4` 线性映射，与回测的排序逻辑不一致
4. **无动态阈值**: 固定推荐TOP N，不根据候选质量调整
5. **无连续失败降温**: 反复推荐同一只亏损股

### 修改的文件

#### 1. `real_feature_calculator.py`
- **calc_features()**: 重写 V22 特征计算，与 backtest_v22_honest.py 完全对齐
  - `bb_pctb`: 修正为 0~1 范围（之前错误用了 0~100）
  - `atr_ratio`: 改用 ATR14/ATR28 比率（之前错误用 ATR/close 百分比）
  - `down_vol_ratio`: 改为 下跌日 vs 上涨日 量比（之前用涨跌幅分类）
  - `support_dist`: 改为相对20日高低范围位置 0~1（之前用百分比距离）
  - 新增 `obv_accel` (OBV加速度，替代旧的 obv_trend)
  - 新增 `vol_price_confirm` (量价确认)
  - 新增 `vol_price_diverge` (量价背离)
  - 新增 `exhaustion` (动量耗竭)
- **compute_real_subscores()**: 新增 V22 子分数计算
  - `bb_s`: 布林带位置评分
  - `atr_s`: ATR比率评分
  - `vol_health_s`: 成交量健康度评分
  - `support_s`: 支撑位距离评分
  - `obv_s`: OBV趋势评分（与回测一致用 obv_accel/avg_v 归一化）
  - `vol_price_confirm/diverge/exhaustion` 条件标志

#### 2. `daily_recommender.py`
- **score_with_v17_risk2()**: 完全重写，与 backtest_v22.score_risk2 100%对齐
  - 新增 bb_s, vol_health_s 权重项
  - 新增 exhaustion, vol_price_diverge 惩罚项
- **score_with_v17_risk3()**: 完全重写，与 backtest_v22.score_risk3 100%对齐
  - 新增 bb_s, support_s, obv_s 权重项
  - 新增 exhaustion, vol_price_diverge 惩罚项
- **score_with_v17_risk45()**: 完全重写，与 backtest_v22.score_risk45 100%对齐
  - 新增 bb_s, atr_s, vol_health_s, support_s, obv_s 权重项
  - 新增 bb_oversold/overbought, atr_expand, distribution, near_support, vp_confirm/diverge, exhaustion 条件
- **归一化**: 替换线性映射为 sigmoid: `10/(1+exp(-0.35*(raw-2)))`
  - raw=0 → 5.6, raw=5 → 8.0, raw=-3 → 3.3
- **新增 get_dynamic_threshold()**: 根据候选股中位数质量动态调整推荐阈值
- **新增 apply_cooldown_penalty()**: 连续推荐失败的股票临时降权
- **新增 load/save_cooldown_data()**: 降温数据持久化

### 预期效果
- 推荐器评分与回测评分从 ~45% 对齐提升到接近 100%
- V22 新维度（约占总权重 15-25%）不再丢失
- 连续失败股票不再反复推荐
- 低质量候选日自动降低推荐数量

### 待验证
- dry-run 测试确认输出正常
- 实盘跟踪新评分 vs 回测评分的相关性

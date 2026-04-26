# TradingAgents 回测优化任务

## 目标
将 beat_index（跑赢指数的天数占比）从 66.7% 提升到 85%+

## 当前状态
- 数据已就绪：3192只A股日线K线（2025-10-01 ~ 2026-04-25）
- K线缓存：`TradingShared/data/kline_cache/kline_full_latest.json`
- 指数数据：`TradingShared/data/kline_cache/index_full_latest.json`（上证指数，73天）
- 之前的Claude Code会话因上下文爆满已废弃，你需要从头分析

## 约束
- **只用真实K线数据**，禁止模拟
- 避免过拟合（walk-forward验证不能崩）
- 每次改动记录到 `backtest_results/`
- 改核心文件前先备份
- 回测区间用数据覆盖的评估期

## 关键文件
- 当前最佳版本：`TradingAgent/backtest_v4.py`（V4 熊市防御版）
- 分析报告：`TradingAgent/backtest_results/V5_ANALYSIS_REPORT.md`
- 配置：`TradingShared/config.py`
- Tushare token 在 config.py 里

## 之前实验结果
- V4=66.7%, V5-c=69.7%, V5-a=69.2%, V5-d=57.6%, V5-b=51.5%, ML=22.2%
- ML方案严重过拟合，不要再用
- 899只股票池已接近天花板，现在有3192只数据

## 任务
1. 先读取现有代码理解算法
2. 用 3192 只股票的新数据跑 V4 baseline 回测，看扩充数据后 beat_index 有没有提升
3. 分析结果，找出改进方向
4. 实验改进方案，每次改动都记录结果
5. 目标：beat_index >= 85%，且 walk-forward 不崩

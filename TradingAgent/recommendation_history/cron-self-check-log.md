## 2026-06-13 15:30 周六盘中 explicit-check (hour=15 weekday=6, weekend guard 5th override)

**判定**：explicit-check (prompt 含 "检查并汇报") 完全解耦 hour/weekday 守卫。Weekday=6 周六守卫第 5 次 override（累计 9 次 override 总数）。

**Phase 0 - P0 维度 mtime-delta**：
- backtest_v23_v4.log: 30.64d (5-14 00:13, 幻影日志 — 实为 V22 结果)
- verification_summary_v3.json: 16.92d (5-27 17:31, T+3 验证积压 17d)
- kline_cache: 11.80d (6-01 20:12, 已滞 12 天)
- backtest_v28.json: 29.61d (5-15 00:56, 幻影)
- latest rec (6-12 15:01): 1.02d

**Phase 1 - 后台进程**：0 个相关进程

**Phase 2 - 6-12 推荐回顾**：
- date=2026-06-12, action=RECOMMEND, regime=strong_bull, risk=1
- total_scored=65, 候选池严重缩量（vs 6-11 的 243）
- 3 只推荐：002578(62.9) / 603466(58.7) / 002378(53.8)
- **0/3 ≥70 门槛**（决策树规则 1 触发）
- **3/3 资金分 <10**（决策树规则 7 触发）
- **3/3 final_score <65**（决策树规则 8 触发）

**Phase 3 - 累计 buy_price 重算 (Pattern H, v1 first-match)**：
- 58 样本 / 有效 46 / OK=17 / STALE=4 / STALE2=11 / CRIT=14
- **v1 异常率 = 63.0%** | CRIT 率 = 30.4% (vs 基线一致)
- Pattern H 累计重算 **17 次稳定**

**Phase 4 - 强牛市 Day 数**：
- 当前 = **Day 16** (5/22~6/12 工作日累计)
- **6-15 周一开盘后 = Day 17** = V28 训练纪录(14d) 破 3 天

**Phase 5 - 守卫统计**：
- 累计 explicit-check override = 9 次 (6-10 23:30 / 6-11 08:30 / 6-12 20:30 / 6-12 22:30 / 6-13 01:00 / 6-13 05:01 / 6-13 05:30 / 6-13 06:30 / **6-13 15:30**)
- 周末守卫 override 累计 5 次 (6-13 01:00 / 05:01 / 05:30 / 06:30 / 15:30)

**Phase 6 - 6-15 开盘前 P0 必跑清单**：
1. **K线 cache 刷新** — 已滞 12 天，6-15 推荐 cron 必须先跑 `update_kline_choice_v3.py` (Windows 端或 WSL)
2. **T+3 验证补跑** — verification_summary_v3.json 已积压 17d，6-15 收盘后跑 `verify_recommendation_v3.py`
3. **LLM 凭据修复** — 4 个 LLM 全部失败 (Gateway-DeepSeek-V4 / ZhipuGLM / Qwen / DeepSeek)
4. **buy_price 排查** — 14 CRIT 样本 (30.4%) 是 stock_cache 残留 + 推荐器选错基准日双重 bug，6-15 前重点 fix
5. **新增回测** — backtest_v28.json 29.61d 幻影，建议 6-15 周末重跑 V28 walkforward 验证强牛市泛化

**经济成本**：本次 tick 约 0.8s (Pattern H 累计重算 + 6 维度 stat)

# Bug修复报告

**日期**: 2026-05-14 23:15  
**修复人**: Bug修复工程师 (Subagent)

---

## Bug 1: 行业全部显示"未知"

### 原因
评分文件 `batch_stock_scores_optimized_主板_*.json` 中只有极少数股票(25/2462)包含 `industry` 字段，绝大多数股票没有行业信息。

### 修复内容 (`stock_screener.py`)
1. 添加了多层行业信息查找链：
   - 第一优先级：评分文件中的 `industry` 字段
   - 第二优先级：本地行业缓存 `industry_cache.json`
   - 第三优先级：评分文件中的 `matched_sector` 字段
   - 兜底：显示"未知"
2. 新增 `_load_industry_cache()` / `_save_industry_cache()` 方法，支持行业信息本地持久化
3. 新增 `_batch_fetch_industry()` 方法，支持在线批量获取行业信息并缓存
4. 修复了 `load_stock_data()` 中旧格式评分文件的元数据过滤问题（旧文件有 `date`, `scores` 等非股票字段）

### 状态: ✅ 已修复（在线时行业信息会自动获取并缓存）

---

## Bug 2: 20日涨幅全是0.0%

### 原因
`get_recent_gain()` 方法首先查找 `kline_{stock_code}.json` 单独文件，但实际的K线数据存储在 `kline_full_latest.json` 合并文件中，且key格式为 `sh600000`（带前缀），而代码用 `600000`（无前缀）查找，永远找不到。

### 修复内容 (`stock_screener.py`)
1. 修改查找优先级：先查 `kline_full_latest.json`，再查单独文件，最后查 akshare
2. 新增 `_kline_key()` 方法，自动处理 `sh`/`sz` 前缀的key映射
3. 新增 `_load_kline_full()` 方法，带缓存的合并文件加载
4. 验证结果：000001 → -1.07%, 600000 → -10.25%, 000002 → -3.73%

### 状态: ✅ 已修复并验证

---

## Bug 3: fund_flow_score 全是20.0（异常）

### 原因
`new_factors.py` 中 `score_fund_flow()` 返回0-100范围评分，但 `daily_recommender.py` 按0-10范围使用（阈值7.5、2.5等）。由于mock数据 `total_flow=0`，走 `else` 分支返回20.0（100分制），实际应该是5.0左右（10分制）。

### 修复内容 (`new_factors.py`)
1. 评分范围从0-100改为0-10
2. 无数据时返回5.0（中性）而非0.0
3. 增加更细粒度的评分档位（区分流入/流出程度）
4. 验证结果：
   - `score_fund_flow({})` → 5.0 ✅
   - `score_fund_flow({'total_flow':0})` → 4.5 ✅
   - `score_fund_flow({'total_flow':200000000})` → 9.0 ✅

### 状态: ✅ 已修复并验证

---

## Bug 4: lhb_score 全是20.0（异常）

### 原因
同Bug 3，`score_lhb()` 返回0-100范围，mock数据下返回10+5+5=20.0。

### 修复内容 (`new_factors.py`)
1. 评分范围从0-100改为0-10
2. 无数据/全0数据时返回5.0（中性）
3. 三个维度（成交额、机构净买、上榜次数）各占0-4、0-3、0-3分
4. 验证结果：
   - `score_lhb({})` → 5.0 ✅
   - `score_lhb({'total_amount':0,...})` → 5.0 ✅
   - `score_lhb({'total_amount':200M,...})` → 10.0 ✅

### 状态: ✅ 已修复并验证

---

## Bug 5: 离线模式市值硬编码50亿

### 原因
`screen()` 方法在离线模式（无实时行情数据）下，所有股票市值硬编码为 `50e8`（50亿），导致筛选无法区分大小盘股。

### 修复内容 (`stock_screener.py`)
1. 优先从评分文件获取 `market_cap` 字段
2. 如无，从 `kline_full_latest.json` 的最近收盘价推算估算市值
3. 最终才使用50亿作为兜底默认值
4. 添加了 `_kline_key()` 调用以正确查找K线数据

### 状态: ✅ 已修复（推算精度有限，但比硬编码好）

---

## 额外修复

### `load_stock_data()` 元数据过滤
旧版评分文件格式包含 `date`, `timestamp`, `model`, `scores` 等元数据字段作为顶级key。`screen()` 遍历时会把字符串值当作字典处理导致报错。新增过滤逻辑，只保留包含评分数据的股票条目。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `TradingAgent/stock_screener.py` | Bug 1, 2, 5 + 元数据过滤 |
| `TradingAgent/new_factors.py` | Bug 3, 4 |

## 注意事项

- **Bug 1（行业信息）**：当前绝大多数股票仍显示"未知"，因为评分文件中缺少行业数据。修复后的代码已支持在线获取并缓存行业信息，下次在线运行时会自动填充 `industry_cache.json`。建议在 `generate_mainboard_scores.py` 中也加入行业信息的生成。
- **网络环境**：本次修复期间网络不可用（代理问题），未能在线验证行业获取功能。

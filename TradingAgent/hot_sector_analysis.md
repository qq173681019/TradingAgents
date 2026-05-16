# A股热点板块追踪系统 — 诊断与设计方案

> 分析师：新闻热点分析师  
> 日期：2026-05-14  

---

## 一、当前系统问题诊断

### 1. 新闻分析模块 (`news_analyzer.py`)

**现状：** 逐股获取个股新闻 → LLM 情绪打分 → 0-10 分

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ❌ **只分析个股，不分析宏观/板块新闻** | 高 | 完全缺失板块级别的新闻热度聚合，无法发现"某个板块突然被新闻引爆"的信号 |
| ❌ **无新闻量统计** | 高 | 只判断单条新闻情绪，不统计新闻数量变化。某股突然被大量报道本身就是重要信号 |
| ⚠️ **LLM 依赖过重** | 中 | 每只股票都调 LLM 分析，批量分析 30 只股票需要 30+ 次 API 调用，耗时且费用高 |
| ⚠️ **quick_check 过于简单** | 中 | 仅匹配固定关键词列表，无法识别"高管被调查""业绩变脸"等隐晦利空 |
| ✅ 多 API fallback 链 | — | 设计合理，智谱→DeepSeek→Gemini 三层 fallback |

### 2. 板块热度模块 (`enhanced_data_fetcher.py` → `fetch_sector_heat`)

**现状：** 按板块名获取当日涨跌幅、资金净流入

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ❌ **只取快照，无趋势** | 高 | `fetch_sector_heat()` 只返回当前值，无5日/10日/20日趋势对比 |
| ❌ **不区分概念板块 vs 行业板块** | 高 | A股热点往往在概念板块（如"机器人""低空经济"），而非申万行业分类 |
| ⚠️ **无个股粒度排名** | 中 | 只返回板块涨幅前3名，无法知道板块内哪些个股最强势 |
| ⚠️ **模糊匹配不可靠** | 中 | 板块名称包含关系匹配容易错配（如"石油"可能匹配到"石油石化"或"石油加工"） |

### 3. 板块轮动模块 (`sector_rotation.py`)

**现状：** 本地缓存优先 → 新浪/AKShare 在线补充 → K线兜底，输出排名和评分

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ❌ **缓存严重过期** | 高 | 本地缓存 `sector_ranking_cache.json` 最后更新于 **2026-05-06**，距今天已有 8 天！而 TTL 检查阈值为 48 小时，理论上应该触发在线刷新 |
| ❌ **缺失关键维度** | 高 | 无资金流向趋势、无新闻热度维度、无板块成交额/换手率变化 |
| ❌ **评分算法偏简单** | 中 | `_compute_score()` 仅基于涨幅+连涨天数，基础分50，完全不考虑资金面 |
| ⚠️ **新浪接口不稳定** | 中 | `stock_sector_spot(indicator="行业资金流")` 频繁失效，且返回字段名不确定 |
| ⚠️ **无概念板块覆盖** | 中 | 只跟踪行业板块，概念板块（A股热点的核心载体）完全缺失 |

### 4. 系统整体架构问题

| 问题 | 说明 |
|------|------|
| 🔴 **三大模块相互独立** | news_analyzer、enhanced_data_fetcher、sector_rotation 各自为战，没有统一的热点信号聚合层 |
| 🔴 **无实时盘面监控** | 所有数据获取都是"拉取"模式，无盘中实时信号推送机制 |
| 🟡 **板块-个股关联弱** | 从热点板块到具体个股的筛选缺乏系统化流程 |

---

## 二、热点板块追踪系统设计方案

### 架构总览

```
┌─────────────────────────────────────────────────────┐
│                  HotSectorTracker                    │
│              (每日热点追踪核心引擎)                    │
├──────────┬──────────┬──────────┬────────────────────┤
│ 数据采集层 │ 信号分析层 │ 评分排序层 │     输出层        │
├──────────┼──────────┼──────────┼────────────────────┤
│东财板块行情│ 涨幅异动  │          │ TOP5热门板块       │
│东财概念板块│ 资金异动  │ 综合评分  │ 板块内个股排名     │
│东财资金流向│ 新闻爆量  │ 多维排序  │ 启动/衰退信号      │
│个股新闻   │ 量价配合  │          │ 轮动预判           │
└──────────┴──────────┴──────────┴────────────────────┘
```

### 2.1 数据源设计

#### 数据源 A：东方财富行业板块（已有 akshare 接口）

```python
# 行业板块列表 + 涨跌幅 + 资金流向
import akshare as ak

# 行业板块行情
df = ak.stock_board_industry_name_em()
# 返回字段: 板块名称, 最新价, 涨跌幅, 总市值, 换手率, 主力净流入等

# 行业板块成分股
cons_df = ak.stock_board_industry_cons_em(symbol="半导体")
# 返回字段: 代码, 名称, 涨跌幅, 最新价, 涨跌额, 成交量, 成交额, 换手率等
```

#### 数据源 B：东方财富概念板块（关键补充）

```python
# 概念板块列表 — A股热点的核心！
df = ak.stock_board_concept_name_em()
# 返回: 概念名称, 涨跌幅, 总市值, 换手率等

# 概念板块成分股
cons_df = ak.stock_board_concept_cons_em(symbol="机器人")
```

#### 数据源 C：板块资金流向

```python
# 行业板块资金流（5日/10日）
df_5 = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
df_10 = ak.stock_sector_fund_flow_rank(indicator="5日", sector_type="行业资金流")

# 概念板块资金流
df_concept = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")
```

#### 数据源 D：板块新闻热度（新增）

```python
# 东方财富板块新闻（非 akshare 标准接口，需自行爬取）
import requests

def fetch_sector_news(sector_name: str, count: int = 20) -> list:
    """获取板块相关新闻（东财搜索API）"""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "jQuery",
        "param": json.dumps({
            "uid": "",
            "keyword": sector_name,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": count,
                    "preTag": "",
                    "postTag": ""
                }
            }
        })
    }
    # ... 解析JSONP返回，已在 news_analyzer.py 中实现
```

### 2.2 综合评分算法

```python
def compute_sector_score(sector_data: dict) -> float:
    """
    热点板块综合评分算法 (0-100)
    
    维度及权重:
    ┌──────────────────┬──────┬───────────────────────────┐
    │ 维度              │ 权重  │ 数据源                    │
    ├──────────────────┼──────┼───────────────────────────┤
    │ 短期涨幅(1日/5日)  │ 25%  │ 东财板块行情              │
    │ 资金净流入        │ 20%  │ 东财资金流向              │
    │ 新闻热度          │ 15%  │ 东财搜索API              │
    │ 量能变化(换手率)   │ 15%  │ 东财板块行情              │
    │ 动量(5日vs20日)   │ 10%  │ 涨幅对比                 │
    │ 板块内涨停股数量   │ 10%  │ 成分股筛选               │
    │ 机构研报数量变化   │  5%  │ 东财研报API              │
    └──────────────────┴──────┴───────────────────────────┘
    """
    
    score = 0.0
    
    # ── 1. 短期涨幅 (25%) ──
    change_1d = sector_data.get('change_pct', 0)
    change_5d = sector_data.get('change_5d', 0)
    # 用5日涨幅为主，1日涨幅辅助
    price_score = (change_5d * 1.5 + change_1d * 1.0) / 2.5
    score += _normalize(price_score, -10, 10) * 25  # 映射到0-25
    
    # ── 2. 资金净流入 (20%) ──
    net_inflow = sector_data.get('net_inflow', 0)  # 亿元
    inflow_score = min(net_inflow / 20.0, 1.0)  # 20亿封顶
    score += max(0, inflow_score) * 20
    
    # ── 3. 新闻热度 (15%) ──
    news_count = sector_data.get('news_count_7d', 0)
    news_score = min(news_count / 50.0, 1.0)  # 50条封顶
    score += news_score * 15
    
    # ── 4. 量能变化 (15%) ──
    turnover = sector_data.get('turnover_rate', 0)
    turnover_score = min(turnover / 8.0, 1.0)  # 8%换手率封顶
    score += turnover_score * 15
    
    # ── 5. 动量 (10%) ──
    change_20d = sector_data.get('change_20d', 0)
    momentum = change_5d - change_20d * 0.25  # 5日涨幅超越20日均值
    momentum_score = _normalize(momentum, -5, 5)
    score += momentum_score * 10
    
    # ── 6. 涨停股数量 (10%) ──
    limit_up_count = sector_data.get('limit_up_count', 0)
    limit_score = min(limit_up_count / 5.0, 1.0)  # 5只封顶
    score += limit_score * 10
    
    # ── 7. 研报数量 (5%) ──
    report_count = sector_data.get('research_count_30d', 0)
    report_score = min(report_count / 20.0, 1.0)  # 20篇封顶
    score += report_score * 5
    
    return round(max(0, min(100, score)), 1)


def _normalize(value, low, high):
    """将值归一化到 0-1"""
    return max(0, min(1, (value - low) / (high - low)))
```

### 2.3 信号检测算法

```python
# ─── 板块启动信号 ───
def detect_launch_signal(sector: dict, history: list) -> dict:
    """
    板块启动信号检测
    
    触发条件（满足3/5即发出信号）:
    1. 当日涨幅 > 2%
    2. 资金净流入 > 5亿
    3. 换手率较5日均值提升 > 50%
    4. 板块内出现 >= 2 只涨停股
    5. 新闻数量较前5日均值增长 > 100%
    
    返回: {
        'signal': True/False,
        'strength': 'strong'/'medium'/'weak',
        'triggers': ['涨幅突破', '资金涌入', ...],
        'score': 0-100
    }
    """
    triggers = []
    
    if sector.get('change_pct', 0) > 2.0:
        triggers.append('涨幅突破2%')
    if sector.get('net_inflow', 0) > 5:
        triggers.append('资金涌入超5亿')
    if _turnover_surge(sector, history):
        triggers.append('换手率飙升')
    if sector.get('limit_up_count', 0) >= 2:
        triggers.append(f"涨停股{sector['limit_up_count']}只")
    if _news_surge(sector, history):
        triggers.append('新闻量激增')
    
    signal = len(triggers) >= 3
    strength = 'strong' if len(triggers) >= 4 else ('medium' if len(triggers) == 3 else 'weak')
    
    return {
        'signal': signal,
        'strength': strength,
        'triggers': triggers,
        'score': len(triggers) * 20
    }


# ─── 板块衰退信号 ───
def detect_decay_signal(sector: dict, history: list) -> dict:
    """
    板块衰退信号检测
    
    触发条件（满足3/5即发出信号）:
    1. 5日涨幅 > 10% 后当日跌幅 > 1% （高位回落）
    2. 资金连续3日净流出
    3. 龙头股开板/炸板
    4. 涨停股数量从5+降至0-1
    5. 板块内个股涨跌比 < 0.3（大部分在跌）
    """
    triggers = []
    
    hist_5d = [h.get('change_pct', 0) for h in history[-5:]] if history else []
    if sum(hist_5d) > 10 and sector.get('change_pct', 0) < -1:
        triggers.append('高位回落')
    
    recent_inflow = [h.get('net_inflow', 0) for h in history[-3:]] if len(history) >= 3 else []
    if all(v < 0 for v in recent_inflow):
        triggers.append('资金连续3日流出')
    
    if sector.get('limit_up_count', 0) <= 1 and any(
        h.get('limit_up_count', 0) >= 5 for h in (history[-5:] if len(history) >= 5 else history)
    ):
        triggers.append('涨停股锐减')
    
    advance_decline = sector.get('advance_count', 0) / max(sector.get('stock_count', 1), 1)
    if advance_decline < 0.3:
        triggers.append('个股普跌')
    
    leader = sector.get('leader_change', 0)
    if leader < -3:
        triggers.append('龙头股大跌')
    
    signal = len(triggers) >= 3
    return {
        'signal': signal,
        'strength': 'strong' if len(triggers) >= 4 else 'medium',
        'triggers': triggers
    }


# ─── 板块轮动预判 ───
def predict_rotation(hot_sectors: list, all_sectors: list) -> list:
    """
    板块轮动预判
    
    逻辑:
    1. 找到当前热点板块（TOP5）
    2. 查找历史上与这些热点板块联动性高的板块
    3. 找到资金开始流入但尚未大涨的板块（"蓄势板块"）
    4. 找到调整到位的前期热点（"超跌反弹"板块）
    
    输出: 推荐关注的下一个可能轮动到的板块列表
    """
    candidates = []
    
    for sector in all_sectors:
        # 蓄势信号: 资金流入 + 涨幅不大 + 量能放大
        if (sector.get('net_inflow', 0) > 3 
            and 0 < sector.get('change_5d', 0) < 3
            and sector.get('turnover_rate', 0) > sector.get('turnover_avg_20d', 0) * 1.3):
            candidates.append({
                'sector': sector['name'],
                'type': '蓄势待发',
                'reason': '资金悄然流入，涨幅不大，量能放大',
                'confidence': 0.6
            })
        
        # 超跌反弹信号: 前期强势，近期调整10%+，开始企稳
        if (sector.get('change_20d', 0) > 5 
            and sector.get('change_5d', 0) < -5
            and sector.get('change_pct', 0) > 0):  # 当日翻红
            candidates.append({
                'sector': sector['name'],
                'type': '超跌反弹',
                'reason': '前期强势股调整后企稳翻红',
                'confidence': 0.5
            })
    
    # 按置信度排序
    candidates.sort(key=lambda x: x['confidence'], reverse=True)
    return candidates[:5]
```

### 2.4 完整实现类（伪代码/框架）

```python
class HotSectorTracker:
    """A股热点板块追踪器"""
    
    def __init__(self):
        self.sector_cache_ttl = 1800  # 30分钟
        self.history_days = 20         # 历史数据天数
    
    # ─── 数据采集 ───
    
    def fetch_industry_sectors(self) -> list:
        """获取所有行业板块数据"""
        # ak.stock_board_industry_name_em()
        pass
    
    def fetch_concept_sectors(self) -> list:
        """获取所有概念板块数据（关键！）"""
        # ak.stock_board_concept_name_em()
        pass
    
    def fetch_sector_fund_flow(self, sector_type='industry') -> list:
        """获取板块资金流向"""
        # ak.stock_sector_fund_flow_rank()
        pass
    
    def fetch_sector_constituents(self, sector_name: str, sector_type='industry') -> list:
        """获取板块成分股详情"""
        # ak.stock_board_industry_cons_em() / ak.stock_board_concept_cons_em()
        pass
    
    def count_sector_news(self, sector_name: str, days: int = 7) -> int:
        """统计板块近N天新闻数量"""
        # 复用 news_analyzer.py 的 _fetch_news_eastmoney()
        pass
    
    # ─── 综合分析 ───
    
    def daily_scan(self) -> dict:
        """
        每日热点扫描（核心入口）
        
        返回:
        {
            'date': '2026-05-14',
            'hot_sectors': [...],       # TOP5 热门板块 + 个股排名
            'cold_sectors': [...],      # TOP5 冷门板块
            'launch_signals': [...],    # 启动信号
            'decay_signals': [...],     # 衰退信号
            'rotation_candidates': [...], # 轮动预判
            'concept_hot': [...],       # 热门概念板块
        }
        """
        # 1. 采集数据
        industry = self.fetch_industry_sectors()
        concept = self.fetch_concept_sectors()
        fund_flow = self.fetch_sector_fund_flow()
        
        # 2. 合并计算综合评分
        all_sectors = self._merge_and_score(industry, concept, fund_flow)
        
        # 3. 信号检测
        launch_signals = [self.detect_launch_signal(s) for s in all_sectors]
        decay_signals = [self.detect_decay_signal(s) for s in all_sectors]
        
        # 4. 轮动预判
        hot_names = [s['name'] for s in all_sectors[:5]]
        rotation = self.predict_rotation(hot_names, all_sectors)
        
        # 5. TOP5 热门板块 + 板块内个股排名
        hot_5 = []
        for sector in all_sectors[:5]:
            constituents = self.fetch_sector_constituents(sector['name'])
            constituents.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
            hot_5.append({
                **sector,
                'top_stocks': constituents[:10]
            })
        
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'hot_sectors': hot_5,
            'cold_sectors': all_sectors[-5:],
            'launch_signals': [s for s in launch_signals if s['signal']],
            'decay_signals': [s for s in decay_signals if s['signal']],
            'rotation_candidates': rotation,
            'concept_hot': [s for s in all_sectors if s.get('type') == 'concept'][:5],
        }
    
    # ─── 板块内个股排名 ───
    
    def rank_stocks_in_sector(self, sector_name: str, top_n: int = 10) -> list:
        """
        板块内个股综合排名
        
        排名维度:
        - 涨跌幅 (30%)
        - 资金净流入 (20%)
        - 换手率 (15%)
        - 量比 (15%)
        - 流通市值偏好 (10%) — 偏好50-500亿
        - 技术形态 (10%)
        """
        constituents = self.fetch_sector_constituents(sector_name)
        # ... 多维打分排序
        return sorted_constituents[:top_n]
```

### 2.5 具体可用的 AKShare API 调用清单

```python
import akshare as ak

# ═══ 行业板块 ═══
# 1. 行业板块列表（含涨跌幅、换手率、市值）
df = ak.stock_board_industry_name_em()
# 关键列: 板块名称, 涨跌幅, 总市值, 换手率, 上涨家数, 下跌家数

# 2. 行业板块成分股
df = ak.stock_board_industry_cons_em(symbol="小金属")
# 关键列: 代码, 名称, 涨跌幅, 最新价, 成交额, 换手率, 涨跌额

# ═══ 概念板块（极其重要！） ═══
# 3. 概念板块列表
df = ak.stock_board_concept_name_em()
# 关键列同上

# 4. 概念板块成分股
df = ak.stock_board_concept_cons_em(symbol="机器人")

# ═══ 资金流向 ═══
# 5. 板块资金流向排名
df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
# indicator: "今日"/"5日"/"10日"
# sector_type: "行业资金流"/"概念资金流"/"地域资金流"

# 6. 个股资金流向
df = ak.stock_individual_fund_flow(stock="600519", market="sh")
# 关键列: 日期, 主力净流入, 小单净流入, 中单净流入, 大单净流入

# ═══ 涨停板 ═══
# 7. 今日涨停股
df = ak.stock_zt_pool_em(date="20260514")
# 关键列: 代码, 名称, 涨幅, 封板资金, 首次封板时间, 最后封板时间, 连板数, 所属行业

# 8. 连板股（龙头股追踪）
df = ak.stock_zt_pool_strong_em(date="20260514")

# ═══ 新闻 ═══  
# 9. 个股新闻（已有）
df = ak.stock_news_em(symbol="贵州茅台")

# 10. 财经新闻热搜（概念热点发现）
# 无直接 akshare 接口，可用东财搜索 API
```

---

## 三、修复建议优先级

### P0 — 立即修复

1. **修复板块缓存过期问题**
   - `sector_rotation.py` 的缓存 TTL=1800s (30分钟)，但实际本地文件8天没更新
   - 原因：可能是在线 API 也失败了，导致 fallback 到旧缓存
   - 建议：缓存超过 48h 强制标记为 stale，不使用旧数据做决策

2. **增加概念板块数据源**
   - 当前完全缺失概念板块（`stock_board_concept_name_em`）
   - A股热点 80% 出现在概念板块，这是最大的数据盲区

### P1 — 一周内

3. **实现 `HotSectorTracker` 核心类**
   - 按上述设计实现 `daily_scan()` 入口
   - 输出 TOP5 热门板块 + 板块内个股排名

4. **增加板块级新闻热度**
   - 不是逐只股票分析新闻，而是按板块聚合新闻数量
   - 用新闻数量变化（而非 LLM 情绪）作为板块热度指标

### P2 — 持续优化

5. **增加历史趋势对比**
   - 保存每日板块评分快照，用于趋势分析和轮动预判
   - 建议存储格式：`sector_history/YYYY-MM-DD.json`

6. **接入涨停板数据**
   - `stock_zt_pool_em` 提供当日涨停股及其所属行业
   - 板块内涨停股数量是判断板块强度的最直接指标

7. **减少 LLM 依赖**
   - 新闻分析先用关键词统计（数量+情绪关键词），LLM 只用于关键节点
   - 可减少 90% 的 API 调用

---

## 四、总结

当前系统在个股新闻情绪分析方面做得不错，但在**板块级热点追踪**上存在明显短板：

1. **缺概念板块** — A股热点的核心载体
2. **缺新闻量统计** — 只做情绪不做量
3. **缺资金面分析** — 板块资金流向数据有但没用好
4. **缺信号机制** — 无启动/衰退/轮动信号
5. **缓存过期** — 实际数据已8天未更新

核心改造方向：**从"个股驱动"升级为"板块驱动"**，先发现热点板块，再在板块内选个股。这才是 A股市场最有效的选股逻辑。

---

*报告完成于 2026-05-14 23:07*

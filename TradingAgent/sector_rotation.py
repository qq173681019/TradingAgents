#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
板块轮动检测模块 v3
==================
优先使用本地板块缓存，在线API作为补充。

数据源优先级：
  1. 本地 sector_ranking_cache.json（已包含210个板块的5/10/20日涨幅、动量等）
  2. AKShare 新浪板块接口 ak.stock_sector_spot()（补充在线数据）
  3. K线缓存按行业分组计算涨幅（兜底）

功能：
  - fetch_sector_ranking()   — 获取板块5/10/20日涨幅排名
  - get_hot_sectors(n=5)     — TOP N 热点板块
  - get_cold_sectors(n=5)    — TOP N 冷门板块
  - score_sector_rotation()  — 单板块评分 0-10

作者：TradingAgent 算法工程师
日期：2026-05-06
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── 禁用代理 ──
for k in list(os.environ):
    if k.upper().endswith('PROXY') or k.upper() == 'ALL_PROXY':
        os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'

logger = logging.getLogger(__name__)

# ── 路径 ──
DATA_DIR = Path(r"D:\GitHub\TradingAgents\TradingShared\data")
SECTOR_CACHE_DIR = DATA_DIR / "sector_cache"
RANKING_CACHE = SECTOR_CACHE_DIR / "sector_ranking_cache.json"
MAPPING_CACHE = SECTOR_CACHE_DIR / "sector_mapping.json"
KLINE_CACHE_DIR = DATA_DIR / "kline_cache"

# ── 内存缓存 ──
_cache = {
    'ranking': None,      # List[Dict] 排名数据
    'loaded_at': None,    # timestamp
}
_CACHE_TTL = 1800  # 30 分钟


# =========================================================================
# 1. 本地缓存读取
# =========================================================================

def _load_local_cache() -> Optional[List[Dict]]:
    """从 sector_ranking_cache.json 加载板块排名数据"""
    if not RANKING_CACHE.exists():
        logger.warning(f"[sector_rotation] 本地缓存不存在: {RANKING_CACHE}")
        return None

    try:
        text = RANKING_CACHE.read_text(encoding='utf-8')
        data = json.loads(text)
        ranking = data.get('ranking', [])
        ts = data.get('timestamp', '')

        # 检查缓存新鲜度（不超过2天）
        if ts:
            try:
                cached_dt = datetime.fromisoformat(ts)
                age_hours = (datetime.now() - cached_dt).total_seconds() / 3600
                if age_hours > 48:
                    logger.warning(f"[sector_rotation] 本地缓存已过期 {age_hours:.0f}h，尝试在线刷新")
                else:
                    logger.info(f"[sector_rotation] 本地缓存 {age_hours:.1f}h 前，{len(ranking)} 个板块")
            except ValueError:
                pass

        if not ranking:
            return None

        return ranking

    except Exception as e:
        logger.error(f"[sector_rotation] 读取本地缓存失败: {e}")
        return None


def _save_local_cache(ranking: List[Dict]):
    """保存板块排名到本地缓存"""
    try:
        SECTOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'timestamp': datetime.now().isoformat(),
            'ranking': ranking,
        }
        RANKING_CACHE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        logger.info(f"[sector_rotation] 已保存 {len(ranking)} 个板块到本地缓存")
    except Exception as e:
        logger.error(f"[sector_rotation] 保存本地缓存失败: {e}")


# =========================================================================
# 2. 在线数据获取（新浪板块）
# =========================================================================

def _fetch_sina_sector_spot() -> Optional[pd.DataFrame]:
    """通过 AKShare 新浪板块接口获取板块行情"""
    try:
        import akshare as ak
        # 新浪板块接口，非东方财富源
        df = ak.stock_sector_spot(indicator="行业资金流")
        if df is None or df.empty:
            logger.warning("[sector_rotation] 新浪板块接口返回空数据")
            return None
        logger.info(f"[sector_rotation] 新浪板块接口获取 {len(df)} 个板块")
        return df
    except Exception as e:
        logger.warning(f"[sector_rotation] 新浪板块接口失败: {e}")
        return None


def _fetch_ak_board_industry() -> Optional[pd.DataFrame]:
    """AKShare 东方财富行业板块列表（备选，可能被限流）"""
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return None
        logger.info(f"[sector_rotation] AKShare行业板块获取 {len(df)} 个板块")
        return df
    except Exception as e:
        logger.warning(f"[sector_rotation] AKShare行业板块接口失败: {e}")
        return None


# =========================================================================
# 3. K线缓存兜底计算
# =========================================================================

def _calc_from_kline_cache() -> Optional[List[Dict]]:
    """
    从K线缓存按行业分组计算板块涨幅。
    使用 sector_mapping.json 将股票映射到板块。
    """
    if not KLINE_CACHE_DIR.exists() or not MAPPING_CACHE.exists():
        logger.warning("[sector_rotation] K线缓存或板块映射不存在，无法兜底计算")
        return None

    try:
        mapping = json.loads(MAPPING_CACHE.read_text(encoding='utf-8'))
        stock_to_sector = mapping.get('stock_to_sector', {})
        if not stock_to_sector:
            return None

        # 找到最新的K线文件
        kline_files = sorted(KLINE_CACHE_DIR.glob("kline_full_latest.json"))
        if not kline_files:
            kline_files = sorted(KLINE_CACHE_DIR.glob("kline_full_*.json"))
        if not kline_files:
            return None

        kline_data = json.loads(kline_files[-1].read_text(encoding='utf-8'))
        logger.info(f"[sector_rotation] 从K线缓存计算板块涨幅，共 {len(stock_to_sector)} 只股票映射")

        # 按板块分组
        sector_stocks: Dict[str, List] = {}
        for code, sector in stock_to_sector.items():
            if code in kline_data:
                sector_stocks.setdefault(sector, []).append(kline_data[code])

        # 计算每个板块的平均涨幅
        ranking = []
        for sector, stocks in sector_stocks.items():
            rets_5d, rets_10d, rets_20d = [], [], []
            for s in stocks:
                closes = s.get('closes', s.get('close', []))
                if isinstance(closes, list) and len(closes) >= 6:
                    rets_5d.append((closes[-1] - closes[-6]) / closes[-6] * 100 if closes[-6] > 0 else 0)
                if isinstance(closes, list) and len(closes) >= 11:
                    rets_10d.append((closes[-1] - closes[-11]) / closes[-11] * 100 if closes[-11] > 0 else 0)
                if isinstance(closes, list) and len(closes) >= 21:
                    rets_20d.append((closes[-1] - closes[-21]) / closes[-21] * 100 if closes[-21] > 0 else 0)

            if rets_5d:
                ranking.append({
                    'sector': sector,
                    'ret_5d': round(sum(rets_5d) / len(rets_5d), 2),
                    'ret_10d': round(sum(rets_10d) / len(rets_10d), 2) if rets_10d else None,
                    'ret_20d': round(sum(rets_20d) / len(rets_20d), 2) if rets_20d else None,
                    'stock_count': len(stocks),
                    'data_source': 'kline_cache',
                })

        # 排序
        ranking.sort(key=lambda x: x.get('ret_5d', -999), reverse=True)
        for i, item in enumerate(ranking):
            item['rank'] = i + 1
            # 简单评分
            score = _compute_score(item)
            item['score'] = round(score, 1)
            item['category'] = 'hot' if score >= 60 else ('cold' if score <= 35 else 'neutral')

        logger.info(f"[sector_rotation] K线兜底计算完成，{len(ranking)} 个板块")
        return ranking if ranking else None

    except Exception as e:
        logger.error(f"[sector_rotation] K线兜底计算失败: {e}")
        return None


def _compute_score(item: Dict) -> float:
    """根据涨幅数据计算综合评分 (0-100)"""
    score = 50.0  # 基础分

    # 5日涨幅贡献 (权重 40%)
    r5 = item.get('ret_5d')
    if r5 is not None:
        score += r5 * 2.5  # +10%涨幅 = +25分

    # 10日涨幅贡献 (权重 30%)
    r10 = item.get('ret_10d')
    if r10 is not None:
        score += r10 * 1.2

    # 20日涨幅贡献 (权重 20%)
    r20 = item.get('ret_20d')
    if r20 is not None:
        score += r20 * 0.6

    # 连涨天数加分
    streak_up = item.get('streak_up', 0)
    score += streak_up * 0.5

    # 动量加分
    momentum = item.get('momentum')
    if momentum is not None:
        score += momentum * 1.5

    return max(0, min(100, score))


# =========================================================================
# 4. 数据获取（多源 fallback）
# =========================================================================

def _get_ranking() -> List[Dict]:
    """
    获取板块排名数据，多源 fallback：
      1. 内存缓存
      2. 本地 JSON 文件
      3. 在线 API（新浪）
      4. K线缓存兜底
    """
    # 1. 内存缓存
    if _cache['ranking'] is not None and _cache['loaded_at'] is not None:
        if (time.time() - _cache['loaded_at']) < _CACHE_TTL:
            return _cache['ranking']

    # 2. 本地缓存文件
    ranking = _load_local_cache()
    if ranking is not None:
        _cache['ranking'] = ranking
        _cache['loaded_at'] = time.time()
        return ranking

    # 3. 在线 API
    logger.info("[sector_rotation] 本地缓存不可用，尝试在线API...")

    # 3a. 新浪板块
    df = _fetch_sina_sector_spot()
    if df is not None:
        ranking = _parse_sina_data(df)
        if ranking:
            _save_local_cache(ranking)
            _cache['ranking'] = ranking
            _cache['loaded_at'] = time.time()
            return ranking

    # 3b. AKShare 行业板块
    df2 = _fetch_ak_board_industry()
    if df2 is not None:
        ranking = _parse_ak_data(df2)
        if ranking:
            _save_local_cache(ranking)
            _cache['ranking'] = ranking
            _cache['loaded_at'] = time.time()
            return ranking

    # 4. K线兜底
    ranking = _calc_from_kline_cache()
    if ranking:
        _save_local_cache(ranking)
        _cache['ranking'] = ranking
        _cache['loaded_at'] = time.time()
        return ranking

    logger.error("[sector_rotation] 所有数据源均不可用!")
    return []


def _parse_sina_data(df: pd.DataFrame) -> List[Dict]:
    """解析新浪板块数据为标准格式"""
    try:
        ranking = []
        for i, row in df.iterrows():
            item = {
                'sector': str(row.get('板块名称', row.iloc[0] if len(row) > 0 else '')),
                'ret_5d': None,
                'ret_10d': None,
                'ret_20d': None,
                'data_source': 'sina',
                'rank': 0,
            }
            # 尝试提取涨跌幅
            for col in df.columns:
                if '涨' in col and '幅' in col:
                    try:
                        val = float(str(row[col]).replace('%', ''))
                        if '今日' in col or '最新' in col:
                            item['ret_5d'] = val  # 至少有当日数据
                        elif '5' in col:
                            item['ret_5d'] = val
                        elif '10' in col:
                            item['ret_10d'] = val
                    except (ValueError, TypeError):
                        pass

            ranking.append(item)

        if ranking:
            ranking.sort(key=lambda x: x.get('ret_5d') or -999, reverse=True)
            for i, item in enumerate(ranking):
                item['rank'] = i + 1
                score = _compute_score(item)
                item['score'] = round(score, 1)
                item['category'] = 'hot' if score >= 60 else ('cold' if score <= 35 else 'neutral')

        return ranking
    except Exception as e:
        logger.error(f"[sector_rotation] 解析新浪数据失败: {e}")
        return []


def _parse_ak_data(df: pd.DataFrame) -> List[Dict]:
    """解析AKShare行业板块数据"""
    try:
        ranking = []
        for i, row in df.iterrows():
            item = {
                'sector': str(row.get('板块名称', '')),
                'ret_5d': None,
                'ret_10d': None,
                'ret_20d': None,
                'data_source': 'akshare',
                'rank': 0,
            }
            # 提取涨跌幅
            for col in df.columns:
                val = row.get(col)
                if val is None:
                    continue
                try:
                    if isinstance(val, str):
                        val = float(val.replace('%', ''))
                    if '5日' in col:
                        item['ret_5d'] = round(float(val), 2)
                    elif '10日' in col:
                        item['ret_10d'] = round(float(val), 2)
                    elif '20日' in col:
                        item['ret_20d'] = round(float(val), 2)
                    elif '今日' in col or '涨跌幅' in col:
                        item['ret_5d'] = item['ret_5d'] or round(float(val), 2)
                except (ValueError, TypeError):
                    pass

            ranking.append(item)

        if ranking:
            ranking.sort(key=lambda x: x.get('ret_5d') or -999, reverse=True)
            for i, item in enumerate(ranking):
                item['rank'] = i + 1
                score = _compute_score(item)
                item['score'] = round(score, 1)
                item['category'] = 'hot' if score >= 60 else ('cold' if score <= 35 else 'neutral')

        return ranking
    except Exception as e:
        logger.error(f"[sector_rotation] 解析AKShare数据失败: {e}")
        return []


# =========================================================================
# 公开接口
# =========================================================================

def fetch_sector_ranking(days: int = 5) -> List[Dict]:
    """
    获取所有行业板块按近N日涨幅排名

    参数:
        days: 5 / 10 / 20

    返回:
        List[Dict]，按涨幅降序，每项包含:
        rank, sector, score, ret_5d, ret_10d, ret_20d, category, ...
    """
    ranking = _get_ranking()
    if not ranking:
        return []

    # 按指定天数排序
    key = f'ret_{days}d'
    valid = [x for x in ranking if x.get(key) is not None]
    invalid = [x for x in ranking if x.get(key) is None]

    valid.sort(key=lambda x: x[key], reverse=True)
    result = valid + invalid
    for i, item in enumerate(result):
        item['rank'] = i + 1

    return result


def get_hot_sectors(n: int = 5, days: int = 5) -> List[Dict]:
    """
    获取 TOP N 热点板块

    参数:
        n: 返回数量
        days: 排名依据天数 (5/10/20)

    返回:
        List[Dict]
    """
    return fetch_sector_ranking(days=days)[:n]


def get_cold_sectors(n: int = 5, days: int = 5) -> List[Dict]:
    """
    获取 TOP N 冷门板块

    参数:
        n: 返回数量
        days: 排名依据天数 (5/10/20)

    返回:
        List[Dict]，从最冷到较冷
    """
    ranking = fetch_sector_ranking(days=days)
    return ranking[-n:][::-1]


def score_sector_rotation(industry_name: str) -> float:
    """
    单板块评分 (0-10)

    评分逻辑:
      - 查找该板块在排名中的位置
      - score 字段为 0-100，映射到 0-10
      - 涨幅排名前10%: 8-10分
      - 涨幅排名10%-30%: 6-8分
      - 涨幅排名30%-50%: 5-6分（中性）
      - 涨幅排名50%-70%: 4-5分
      - 涨幅排名后30%: 0-4分
      - 额外加分: 5日涨幅>3% +0.5，10日涨幅>5% +0.5
      - 额外扣分: 5日跌幅>5% -1.0
      - 未找到 / API失败: 返回 5.0 中性分

    参数:
        industry_name: 行业板块名称（如 "小金属", "半导体"）

    返回:
        float, 0-10
    """
    try:
        ranking = _get_ranking()
        if not ranking:
            return 5.0

        total = len(ranking)
        if total == 0:
            return 5.0

        # 空字符串直接返回中性分
        if not industry_name or not industry_name.strip():
            return 5.0

        # 模糊匹配
        target = None
        target_rank = None
        for item in ranking:
            name = item.get('sector', '')
            if (name == industry_name
                    or industry_name in name
                    or name in industry_name):
                target = item
                target_rank = item.get('rank', 0)
                break

        if target is None:
            return 5.0

        # 基于 rank 的百分位评分
        pct = target_rank / total  # 0=最好, 1=最差

        if pct <= 0.10:
            base = 8.0 + (0.10 - pct) / 0.10 * 2.0   # 8-10
        elif pct <= 0.30:
            base = 6.0 + (0.30 - pct) / 0.20 * 2.0   # 6-8
        elif pct <= 0.50:
            base = 5.0 + (0.50 - pct) / 0.20 * 1.0   # 5-6
        elif pct <= 0.70:
            base = 4.0 + (0.70 - pct) / 0.20 * 1.0   # 4-5
        else:
            base = max(0.0, 4.0 - (pct - 0.70) / 0.30 * 4.0)  # 0-4

        # 涨幅额外加分/扣分
        bonus = 0.0
        r5 = target.get('ret_5d')
        r10 = target.get('ret_10d')

        if r5 is not None and r5 > 3:
            bonus += 0.5
        if r10 is not None and r10 > 5:
            bonus += 0.5
        if r5 is not None and r5 < -5:
            bonus -= 1.0

        # 连涨天数加分（如果缓存有此字段）
        streak_up = target.get('streak_up', 0)
        if isinstance(streak_up, (int, float)) and streak_up >= 5:
            bonus += 0.3

        score = max(0.0, min(10.0, base + bonus))
        return round(score, 2)

    except Exception as e:
        logger.warning(f"[sector_rotation] score_sector_rotation({industry_name}) failed: {e}")
        return 5.0


def get_sector_info(industry_name: str) -> Optional[Dict]:
    """获取单个板块的详细信息"""
    try:
        if not industry_name or not industry_name.strip():
            return None
        ranking = _get_ranking()
        for item in ranking:
            name = item.get('sector', '')
            if (name == industry_name
                    or industry_name in name
                    or name in industry_name):
                return item
        return None
    except Exception:
        return None


def refresh_cache(force: bool = False) -> bool:
    """
    强制刷新缓存

    参数:
        force: 是否跳过TTL检查

    返回:
        bool, 是否成功刷新
    """
    if force:
        _cache['ranking'] = None
        _cache['loaded_at'] = None

    ranking = _get_ranking()
    return len(ranking) > 0


# =========================================================================
# 集成说明
# =========================================================================

INTEGRATION_GUIDE = """
## 集成到 enhanced_scorer.py 的说明

### 方式1: 替换现有板块热度评分
在 calculate_enhanced_total_score() 中:
```python
from sector_rotation import score_sector_rotation
sector_rotation_score = score_sector_rotation(industry)
```

### 方式2: 作为额外维度叠加（推荐）
在 enrich_stock_data() 中:
```python
from sector_rotation import score_sector_rotation
stock['sector_rotation_score'] = score_sector_rotation(stock.get('industry', ''))
```

### 推荐乘数方式:
  score *= (0.85 + sector_rotation_score * 0.03)
  # 7分→1.06x, 5分→1.00x, 3分→0.94x
"""


# =========================================================================
# 测试
# =========================================================================

if __name__ == '__main__':
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        stream=sys.stdout,
    )

    print("=" * 76)
    print("板块轮动检测模块 v3 — 测试")
    print("=" * 76)

    # 测试 1: 热点板块 TOP 10
    print("\n>> 1. 热点板块 TOP 10（按5日涨幅）")
    print(f"  {'排名':>4}  {'板块':<12}  {'评分':>5}  {'5日':>7}  {'10日':>7}  {'20日':>7}  {'连涨':>4}  {'类别'}")
    print("  " + "-" * 66)
    hot10 = get_hot_sectors(n=10, days=5)
    for item in hot10:
        r5 = item.get('ret_5d')
        r10 = item.get('ret_10d')
        r20 = item.get('ret_20d')
        streak = item.get('streak_up', '-')
        r5s = f"{r5:+.1f}%" if r5 is not None else "N/A"
        r10s = f"{r10:+.1f}%" if r10 is not None else "N/A"
        r20s = f"{r20:+.1f}%" if r20 is not None else "N/A"
        cat = item.get('category', '?')
        print(f"  {item['rank']:>4}  {item['sector']:<12}  {item['score']:>5.1f}  {r5s:>7}  {r10s:>7}  {r20s:>7}  {streak!s:>4}  {cat}")

    # 测试 2: 冷门板块 TOP 10
    print("\n>> 2. 冷门板块 TOP 10（按5日涨幅）")
    print(f"  {'排名':>4}  {'板块':<12}  {'评分':>5}  {'5日':>7}  {'10日':>7}  {'20日':>7}  {'类别'}")
    print("  " + "-" * 58)
    cold10 = get_cold_sectors(n=10, days=5)
    for item in cold10:
        r5 = item.get('ret_5d')
        r10 = item.get('ret_10d')
        r20 = item.get('ret_20d')
        r5s = f"{r5:+.1f}%" if r5 is not None else "N/A"
        r10s = f"{r10:+.1f}%" if r10 is not None else "N/A"
        r20s = f"{r20:+.1f}%" if r20 is not None else "N/A"
        cat = item.get('category', '?')
        print(f"  {item['rank']:>4}  {item['sector']:<12}  {item['score']:>5.1f}  {r5s:>7}  {r10s:>7}  {r20s:>7}  {cat}")

    # 测试 3: 板块评分
    print("\n>> 3. 板块评分测试")
    test_names = ['小金属', '半导体', '白酒', '银行', '房地产', '医药', '电子', '锂电池']
    print(f"  {'板块':<10}  {'评分':>5}  {'排名':>5}  {'5日涨幅':>8}  {'说明'}")
    print("  " + "-" * 50)
    for name in test_names:
        score = score_sector_rotation(name)
        info = get_sector_info(name)
        if info:
            rank = info.get('rank', '?')
            r5 = info.get('ret_5d')
            r5s = f"{r5:+.1f}%" if r5 is not None else "N/A"
            desc = '热点' if score >= 7 else ('冷门' if score <= 4 else '中性')
        else:
            rank = '?'
            r5s = 'N/A'
            desc = '未找到'
        print(f"  {name:<10}  {score:>5.1f}  {rank!s:>5}  {r5s:>8}  {desc}")

    # 测试 4: 异常
    print("\n>> 4. 异常测试")
    print(f"  不存在的板块: {score_sector_rotation('不存在的行业板块')}")
    print(f"  空字符串: {score_sector_rotation('')}")

    print("\n" + "=" * 76)
    print("[OK] 测试完成")
    print("=" * 76)

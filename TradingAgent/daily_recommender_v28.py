#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V28 每日潜力股推荐引擎
====================
基于V28回测验证的87.5% beat_idx策略，集成到日常推荐流程。

核心差异（vs daily_recommender.py）:
1. 使用 detect_no_trade_signals() 判断是否交易
2. 使用V28的6维评分（趋势/资金/板块/相对强度/量价/风险）
3. 使用V25 Optuna优化权重
4. 行业数据从kline_full_latest.json获取
5. 多样化过滤（同行业最多1只，冷却期3天）

使用方法:
    python daily_recommender_v28.py              # 完整推荐（含邮件发送）
    python daily_recommender_v28.py --dry-run    # 仅运行不发送邮件
    python daily_recommender_v28.py --debug      # 调试模式，输出详细评分
"""

import json, os, sys, time, gc, warnings, functools, argparse, logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger('V28')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
SHARED_DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))
sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingAgent'))

# LLM 分析模块
try:
    from llm.hot_sector_analyzer import HotSectorAnalyzer
    LLM_AVAILABLE = True
except ImportError as e:
    print(f"  [WARN] LLM模块不可用: {e}")
    LLM_AVAILABLE = False

# V2 筛选器集成
try:
    from stock_screener_v2 import StockScreenerV2, SectorRotator, MoneyFlowFilter
    V2_AVAILABLE = True
except ImportError as e:
    print(f"  [WARN] V2筛选器不可用: {e}")
    V2_AVAILABLE = False

# ============================================================================
# Config
# ============================================================================
MIN_KLINE_DAYS = 30
V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True

COOLDOWN_DAYS = 5  # V28.1: 冷却期从3天增加到5天，防止连续推荐
LIMIT_UP_THRESHOLD = 15.0
IPO_MIN_DAYS = 30
PT_ST_KEYWORDS = ['PT', 'ST', '*ST', '退']
BLOCKED_CODE_PREFIXES = ['2', '9', '4']

DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']

MAX_SAME_INDUSTRY = 1  # V28: 同行业最多1只
RECOMMEND_COUNT = 3

# V28.1: 验证反馈惩罚配置
VERIFICATION_FEEDBACK_FILE = os.path.join(BASE_DIR, 'v28_verification_feedback.json')
FEEDBACK_PENALTY_PER_LOSS = 3.0   # 每次亏损惩罚分数
FEEDBACK_PENALTY_DECAY_DAYS = 10  # 惩罚衰减天数
FEEDBACK_BONUS_PER_WIN = 1.0     # 每次盈利奖励分数


# ============================================================================
# Helper functions (from backtest_v28)
# ============================================================================
def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)

def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)

def normalize_code(code):
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code

def is_tradeable(code, name=''):
    if len(code) >= 1 and code[0] in BLOCKED_CODE_PREFIXES:
        return False
    for kw in PT_ST_KEYWORDS:
        if kw in name:
            return False
    return True


# ============================================================================
# Data Loading (from backtest_v28)
# ============================================================================
def load_merged_kline():
    """加载K线数据"""
    print("[1/3] 加载K线数据...")
    v19_pool = None
    if V19_USE_POOL and os.path.exists(V19_POOL_FILE):
        with open(V19_POOL_FILE, 'r', encoding='utf-8') as f:
            v19_pool = set(json.load(f))
        print(f"  V19股票池: {len(v19_pool)} 只")

    new_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}

    print(f"  加载: {os.path.basename(new_file)} ({os.path.getsize(new_file)/1024/1024:.1f}MB)")
    with open(new_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    merged = {}
    skipped_pool = 0
    skipped_days = 0

    for code, records in raw_data.items():
        clean = normalize_code(code)
        if v19_pool is not None and clean not in v19_pool:
            skipped_pool += 1
            continue
        if not records:
            continue
        combined = []
        seen_dates = set()
        for r in records:
            d = r.get('date', '')
            if d and d not in seen_dates:
                seen_dates.add(d)
                combined.append({k: v for k, v in r.items() if k in NEED_COLS})
        if len(combined) < MIN_KLINE_DAYS:
            skipped_days += 1
            continue

        df = pd.DataFrame(combined)
        df['date'] = pd.to_datetime(df['date'], format='mixed').dt.tz_localize(None)
        df = df.sort_values('date').drop_duplicates(subset='date', keep='last')
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        merged[clean] = df

    del raw_data
    gc.collect()

    all_max_dates = [df['date'].max() for df in merged.values()]
    print(f"  已加载: {len(merged)} 只 (跳过 {skipped_pool} 池外, {skipped_days} 太短)")
    if all_max_dates:
        print(f"  最新日期: {max(all_max_dates).date()}")
    return merged


def _parse_index_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    records = []
    if 'date' in raw and isinstance(raw['date'], dict):
        n = len(raw['date'])
        for i in range(n):
            try:
                ts = raw['date'].get(str(i))
                cl = float(raw['close'].get(str(i), 0))
                if ts is None or cl <= 0:
                    continue
                if isinstance(ts, (int, float)):
                    ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d')
                else:
                    ds = str(ts)
                records.append({'date': ds, 'close': cl})
            except:
                continue
    del raw
    return records


def load_index_extended():
    """加载指数数据"""
    print("[2/3] 加载指数数据...")
    old_idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    new_idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')

    old_records = []
    if os.path.exists(old_idx_file):
        old_records = _parse_index_file(old_idx_file)
    new_records = []
    if os.path.exists(new_idx_file):
        new_records = _parse_index_file(new_idx_file)

    seen_dates = set()
    all_records = []
    for r in old_records + new_records:
        if r['date'] not in seen_dates:
            seen_dates.add(r['date'])
            all_records.append(r)
    gc.collect()

    index_df = pd.DataFrame(all_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date').drop_duplicates(
        subset='date', keep='last')
    index_df['close'] = index_df['close'].astype('float32')
    print(f"  指数: {len(index_df)} 天, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    return index_df


def _load_sector_mapping():
    """从 sector_mapping.json 构建代码->行业映射"""
    mapping_file = os.path.join(DATA_DIR, 'sector_cache', 'sector_mapping.json')
    if not os.path.exists(mapping_file):
        return {}
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        code_to_industry = {}

        # 优先使用 stock_to_sector 格式
        s2s = data.get('stock_to_sector', {})
        if s2s and isinstance(s2s, dict):
            for code, sector in s2s.items():
                c = normalize_code(str(code))
                code_to_industry[c] = sector
        elif isinstance(data, dict):
            # Fallback: sector_to_stocks 格式
            s2ss = data.get('sector_to_stocks', data.get('sectors', {}))
            if isinstance(s2ss, dict):
                for sector_name, codes in s2ss.items():
                    if isinstance(codes, list):
                        for code in codes:
                            c = normalize_code(str(code))
                            if c not in code_to_industry:
                                code_to_industry[c] = sector_name

        print(f"  行业映射: {len(code_to_industry)} 只 (来自 sector_mapping.json)")
        return code_to_industry
    except Exception as e:
        print(f"  行业映射加载失败: {e}")
        return {}


def load_scores():
    """加载评分数据"""
    print("[3/3] 加载评分数据...")
    import glob
    opt_pattern = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
    opt_files = sorted(glob.glob(opt_pattern),
                       key=lambda x: os.path.getmtime(x), reverse=True)

    scores = {}
    loaded_from = None

    for score_file in opt_files:
        if os.path.getsize(score_file) < 100000:
            continue
        try:
            with open(score_file, 'r', encoding='utf-8') as f:
                sd = json.load(f)
            for code, s in sd.items():
                if not isinstance(s, dict):
                    continue
                clean = normalize_code(code)
                scores[clean] = {
                    'tech': float(s.get('short_term_score', 5.0)),
                    'fund': float(s.get('long_term_score', 5.0)),
                    'chip': float(s.get('chip_score', 5.0)),
                    'sector': float(s.get('hot_sector_score', 5.0)),
                    'name': s.get('name', ''),
                    'industry': s.get('industry', s.get('matched_sector', 'unknown')),
                    'sector_change': float(s.get('sector_change', 0.0)),
                }
            loaded_from = os.path.basename(score_file)
            break
        except:
            continue

    # 补充行业数据：从 sector_mapping.json 反查
    code_to_industry = _load_sector_mapping()
    if code_to_industry:
        fixed = 0
        for code, static in scores.items():
            raw_ind = static.get('industry', 'unknown')
            if raw_ind in ('unknown', '未知', '', None) and code in code_to_industry:
                static['industry'] = code_to_industry[code]
                fixed += 1
        print(f"  行业补充: {fixed} 只从sector_mapping获取行业")

    if scores:
        print(f"  评分: {len(scores)} 只 (来自 {loaded_from})")
    else:
        print(f"  评分: 0 只 (警告!)")
    return scores


# ============================================================================
# No-Trade Signal Detection (from backtest_v28)
# ============================================================================
def detect_no_trade_signals(index_df, date):
    """检测不交易信号。Returns (should_skip, signals_list, total_risk)"""
    hist = index_df[index_df['date'] < date]
    closes = hist['close'].values
    n = len(closes)
    if n < 6:
        return False, [], 0

    signals = []

    # Signal 1: 冲高回落
    if n >= 2:
        prev_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if prev_ret > 3.0:
            signals.append(('冲高回落风险', 2))

    # Signal 2: 连涨疲劳
    consec_up = 0
    for i in range(n - 1, max(0, n - 8), -1):
        if closes[i] > closes[i - 1]:
            consec_up += 1
        else:
            break
    if consec_up >= 4:
        signals.append(('连涨疲劳(4天+)', 3))
    elif consec_up >= 3:
        signals.append(('连涨注意(3天)', 2))

    # Signal 3: 波动率急升
    if n >= 25:
        daily_rets_5 = np.diff(closes[-6:]) / closes[-6:-1] * 100
        daily_rets_20 = np.diff(closes[-21:]) / closes[-21:-1] * 100
        vol_5 = np.std(daily_rets_5)
        vol_20 = np.std(daily_rets_20)
        if vol_20 > 0.001 and vol_5 / vol_20 > 2.0:
            signals.append(('波动率急升', 2))

    # Signal 4: 累计跌幅
    if n >= 3:
        cum_ret_2d = (closes[-1] - closes[-3]) / closes[-3] * 100
        if cum_ret_2d < -2.0:
            signals.append(('累计跌幅>2%', 2))

    # Signal 5: 连跌
    consec_down = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
            consec_down += 1
        else:
            break
    if consec_down >= 3:
        signals.append(('连跌(3天+)', 2))

    # Signal 6: 大阴线
    if n >= 2:
        yesterday_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if yesterday_ret < -1.5:
            signals.append(('大阴线', 1))

    # Signal 7: 连跌2天
    if n >= 3:
        if closes[-1] < closes[-2] and closes[-2] < closes[-3]:
            signals.append(('连跌2天', 1))

    # Signal 8: 昨日小跌
    if n >= 2:
        yest_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if -1.5 < yest_ret < -0.1:
            signals.append(('昨日小跌', 1))

    total_risk = sum(r for _, r in signals)
    should_skip = total_risk >= 2

    return should_skip, signals, total_risk


# ============================================================================
# Market Regime Detection (from backtest_v28)
# ============================================================================
def detect_market_regime(index_df, date):
    """检测市场状态。Returns (regime, confidence, risk)"""
    hist = index_df[index_df['date'] < date]
    if len(hist) < 20:
        return 'range', 0.5, 3

    closes = hist['close'].values
    n = len(closes)

    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if n >= 60 else ma20

    trend_score = 0
    if closes[-1] > ma5: trend_score += 1
    if ma5 > ma10: trend_score += 1
    if ma10 > ma20: trend_score += 1
    if ma20 > ma60: trend_score += 1

    ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    ret60 = (closes[-1] - closes[-61]) / closes[-61] * 100 if n >= 61 else 0
    momentum = ret5 * 0.5 + ret20 * 0.3 + ret60 * 0.2

    if n >= 21:
        daily_rets = (closes[-20:] - closes[-21:-1]) / closes[-21:-1] * 100
        volatility = np.std(daily_rets)
    else:
        volatility = 0.8

    if trend_score >= 3 and momentum > 2:
        regime = 'strong_bull'; risk = 1
    elif trend_score >= 2 and momentum > 0:
        regime = 'bull'; risk = 2
    elif trend_score <= 1 and momentum < -2:
        regime = 'bear'; risk = 4
    elif trend_score == 0 and momentum < -3:
        regime = 'crisis'; risk = 5
    else:
        regime = 'range'; risk = 3

    if volatility > 1.5:
        risk = min(risk + 1, 5)

    consec_decline = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
            consec_decline += 1
        else:
            break
    if consec_decline >= 4:
        risk = min(risk + 1, 5)

    confidence = abs(trend_score - 2) / 2.0
    confidence = min(confidence + abs(momentum) / 5.0, 1.0)

    return regime, confidence, risk


def should_trade(regime, confidence, risk):
    """判断是否应该交易"""
    if risk >= 5:
        return False, 0
    if risk == 4 and confidence > 0.6:
        return True, 1
    if risk == 3 and confidence < 0.3:
        return False, 0
    if risk <= 2:
        return True, 3 if risk == 1 else 2
    return True, 2


# ============================================================================
# Sub-score modules (from backtest_v28)
# ============================================================================
def multi_timeframe_trend_score(hist_closes):
    c = hist_closes
    n = len(c)
    if n < 20:
        return 50, 'neutral'

    score = 0
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:])
    ma20 = np.mean(c[-20:])

    daily_score = 0
    if c[-1] > ma5 > ma10 > ma20:     daily_score += 40
    elif c[-1] > ma5 > ma10:          daily_score += 30
    elif c[-1] > ma5:                 daily_score += 15
    elif c[-1] < ma5 < ma10 < ma20:   daily_score -= 40
    elif c[-1] < ma5 < ma10:          daily_score -= 30
    elif c[-1] < ma5:                 daily_score -= 15

    if n >= 6:
        ma5_slope = (ma5 - np.mean(c[-6:-1])) / max(np.mean(c[-6:-1]), 0.01) * 100
        if ma5_slope > 1:     daily_score += 15
        elif ma5_slope > 0:   daily_score += 8
        elif ma5_slope < -1:  daily_score -= 15
        elif ma5_slope < 0:   daily_score -= 8
    score += daily_score * 0.4

    weekly_score = 0
    if n >= 60:
        weekly_closes = c[::5]
        if len(weekly_closes) >= 12:
            wma5 = np.mean(weekly_closes[-5:])
            wma10 = np.mean(weekly_closes[-10:])
            if weekly_closes[-1] > wma5 > wma10:      weekly_score += 40
            elif weekly_closes[-1] > wma5:             weekly_score += 20
            elif weekly_closes[-1] < wma5 < wma10:    weekly_score -= 40
            elif weekly_closes[-1] < wma5:             weekly_score -= 20
    score += weekly_score * 0.4

    monthly_score = 0
    if n >= 120:
        monthly_closes = c[::20]
        if len(monthly_closes) >= 6:
            mma5 = np.mean(monthly_closes[-5:])
            if monthly_closes[-1] > mma5:   monthly_score += 30
            else:                            monthly_score -= 30
    score += monthly_score * 0.2

    score = max(0, min(100, (score + 100) / 2))

    if score >= 75:    direction = 'strong_up'
    elif score >= 55:  direction = 'up'
    elif score >= 45:  direction = 'neutral'
    elif score >= 25:  direction = 'down'
    else:              direction = 'strong_down'

    return score, direction


def money_flow_score(hist_closes, hist_volumes, hist_highs, hist_lows, hist_turn):
    c, v, hi, lo, turn = hist_closes, hist_volumes, hist_highs, hist_lows, hist_turn
    n = len(c)
    if n < 10:
        return 5.0

    score = 5.0
    up_vols = [v[i] for i in range(-10, 0) if c[i] > c[i - 1]]
    dn_vols = [v[i] for i in range(-10, 0) if c[i] <= c[i - 1]]
    avg_up = np.mean(up_vols) if up_vols else 1
    avg_dn = np.mean(dn_vols) if dn_vols else 1
    vol_ratio = avg_up / max(avg_dn, 1)

    if vol_ratio > 2.0:     score += 2.0
    elif vol_ratio > 1.5:   score += 1.0
    elif vol_ratio < 0.7:   score -= 1.5
    elif vol_ratio < 0.5:   score -= 2.5

    obv_series = [0]
    start = max(-20, -n)
    for i in range(start, 0):
        if i - 1 < start:
            obv_series.append(obv_series[-1])
        elif c[i] > c[i - 1]:     obv_series.append(obv_series[-1] + v[i])
        elif c[i] < c[i - 1]:   obv_series.append(obv_series[-1] - v[i])
        else:                    obv_series.append(obv_series[-1])

    if obv_series[-1] == max(obv_series): score += 1.5
    if len(obv_series) >= 5 and obv_series[-1] < obv_series[-5]: score -= 1.0

    for i in range(-3, 0):
        body = abs(c[i] - c[i - 1])
        upper_wick = hi[i] - max(c[i], c[i - 1])
        lower_wick = min(c[i], c[i - 1]) - lo[i]
        total_range = max(hi[i] - lo[i], 0.01)
        if c[i] > c[i - 1]:
            if (body + lower_wick) / total_range > 0.7: score += 0.3
        else:
            if (body + upper_wick) / total_range > 0.7: score -= 0.3

    if n >= 10 and not np.all(turn == 1):
        turn_today = turn[-1]
        turn_avg5 = np.mean(turn[-6:-1])
        turn_ratio = turn_today / max(turn_avg5, 0.1)
        if turn_ratio > 2.0 and c[-1] > c[-2]:        score += 1.5
        elif turn_ratio > 1.5 and c[-1] > c[-2]:      score += 0.5
        elif turn_ratio > 2.0 and c[-1] < c[-2]:      score -= 2.0
        elif turn_ratio < 0.5:                          score -= 0.5

    return max(0, min(10, score))


def relative_strength_rank(code, hist_closes, industry, peer_data):
    if len(hist_closes) < 6:
        return 50
    my_return = (hist_closes[-1] - hist_closes[-6]) / hist_closes[-6] * 100
    peer_returns = [p_ret for pcode, p_ret in peer_data if pcode != code]
    if len(peer_returns) < 2:
        return 50
    percentile = sum(1 for r in peer_returns if r < my_return) / len(peer_returns) * 100
    return percentile


def calc_volume_health(hist_closes, hist_volumes):
    c, v = hist_closes, hist_volumes
    n = len(c)
    if n < 10:
        return 50
    score = 50
    for i in range(-5, 0):
        if c[i] > c[i - 1] and v[i] > v[i - 1]:      score += 3
        elif c[i] < c[i - 1] and v[i] < v[i - 1]:     score += 2
        elif c[i] > c[i - 1] and v[i] < v[i - 1]:     score -= 1
        elif c[i] < c[i - 1] and v[i] > v[i - 1]:     score -= 3
    vol_cv = np.std(v[-10:]) / max(np.mean(v[-10:]), 1)
    if vol_cv < 0.3:    score += 5
    elif vol_cv > 0.8:  score -= 5
    return max(0, min(100, score))


def detect_divergence(hist_closes, hist_volumes, lookback=20):
    c, v = hist_closes, hist_volumes
    n = len(c)
    if n < lookback:
        return {'bullish': False, 'bearish': False, 'strength': 0}

    obv = [0]
    for i in range(1, n):
        if c[i] > c[i - 1]:     obv.append(obv[-1] + v[i])
        elif c[i] < c[i - 1]:   obv.append(obv[-1] - v[i])
        else:                    obv.append(obv[-1])
    obv = np.array(obv)

    recent = min(lookback, n)
    result = {'bullish': False, 'bearish': False, 'strength': 0}

    price_min_idx = np.argmin(c[-recent:])
    if price_min_idx >= recent - 5:
        obv_at_min = obv[-(recent - price_min_idx)] if price_min_idx < recent else obv[-1]
        obv_min = np.min(obv[-recent:])
        if obv_at_min > obv_min * 1.1:
            result['bullish'] = True
            result['strength'] = min(1.0, (obv_at_min - obv_min) / max(abs(obv_min), 1))

    price_max_idx = np.argmax(c[-recent:])
    if price_max_idx >= recent - 5:
        obv_at_max = obv[-(recent - price_max_idx)] if price_max_idx < recent else obv[-1]
        obv_max = np.max(obv[-recent:])
        if obv_at_max < obv_max * 0.9:
            result['bearish'] = True
            result['strength'] = min(1.0, (obv_max - obv_at_max) / max(abs(obv_max), 1))

    return result


def identify_hot_sectors(kline_dict, scores_dict, date, lookback=5):
    """识别热点板块"""
    sector_returns = defaultdict(list)
    sector_volumes = defaultdict(list)

    for code, df in kline_dict.items():
        static = scores_dict.get(code)
        if not static:
            continue
        industry = static.get('industry', 'unknown')
        if industry in ('unknown', '未知', ''):
            continue
        hist = df[df['date'] < date]
        if len(hist) < lookback + 1:
            continue

        c = hist['close'].values
        v = hist['volume'].values
        ret = (c[-1] - c[-lookback - 1]) / c[-lookback - 1] * 100
        sector_returns[industry].append(ret)
        if len(v) >= 15:
            vol_ratio = np.mean(v[-5:]) / max(np.mean(v[-15:-5]), 1)
            sector_volumes[industry].append(vol_ratio)

    sector_avg_ret = {}
    for ind, rets in sector_returns.items():
        if len(rets) >= 3:
            sector_avg_ret[ind] = {
                'avg_ret': float(np.mean(rets)),
                'positive_rate': sum(1 for r in rets if r > 0) / len(rets),
                'count': len(rets),
            }

    sector_vol_ratio = {}
    for ind, vrs in sector_volumes.items():
        if len(vrs) >= 2:
            sector_vol_ratio[ind] = float(np.mean(vrs))

    sector_heat = {}
    for ind, stats in sector_avg_ret.items():
        vr = sector_vol_ratio.get(ind, 1.0)
        heat = (stats['avg_ret'] * 0.4
                + stats['positive_rate'] * 5 * 0.3
                + (vr - 1.0) * 3 * 0.3)
        sector_heat[ind] = heat

    sorted_sectors = sorted(sector_heat.items(), key=lambda x: x[1], reverse=True)
    return {
        'hot': sorted_sectors[:8],
        'all_heat': sector_heat,
    }


# ============================================================================
# V25 Optuna Params
# ============================================================================
def load_v25_params():
    """加载V25 Optuna参数"""
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v25_best_params.json')
    if not os.path.exists(params_path):
        print(f"  [错误] V25参数不存在: {params_path}")
        sys.exit(1)

    with open(params_path, 'r', encoding='utf-8') as f:
        v25_params = json.load(f)

    weights_config = {
        'weights_bull': v25_params['params']['weights_bull'],
        'weights_range': v25_params['params']['weights_range'],
        'weights_bear': v25_params['params']['weights_bear'],
        'min_score_threshold': v25_params['params']['min_score_threshold'],
        'cooldown_penalty_weight': 5.0,
        'w_extra': 0.0,
        'n_rec_low_risk': 3,
        'n_rec_med_risk': 2,
    }

    print(f"  V25参数加载成功")
    print(f"  min_score: {weights_config['min_score_threshold']:.1f}")
    print(f"  weights_bull: {[f'{w:.3f}' for w in weights_config['weights_bull']]}")
    return weights_config


# ============================================================================
# V28.1: Verification Feedback Tracker
# ============================================================================
class VerificationFeedback:
    """追踪每只股票的T+3验证结果，对亏损股施加惩罚"""
    def __init__(self):
        self.records = {}  # code -> [{'date': str, 'win': bool, 'actual_return': float}]

    def load(self):
        if os.path.exists(VERIFICATION_FEEDBACK_FILE):
            try:
                with open(VERIFICATION_FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.records = data.get('records', {})
            except:
                self.records = {}
        return self

    def save(self):
        data = {
            'records': self.records,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        with open(VERIFICATION_FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def record_result(self, code, date_str, win, actual_return=0.0):
        """记录验证结果"""
        if code not in self.records:
            self.records[code] = []
        # 避免重复记录
        for r in self.records[code]:
            if r['date'] == date_str:
                return
        self.records[code].append({
            'date': date_str,
            'win': win,
            'actual_return': round(actual_return, 4),
        })

    def get_penalty(self, code, current_date_str):
        """计算惩罚分数（亏损越多，惩罚越大，但会随时间衰减）"""
        if code not in self.records:
            return 0.0
        current = pd.Timestamp(current_date_str)
        penalty = 0.0
        for r in self.records[code]:
            days_ago = (current - pd.Timestamp(r['date'])).days
            if days_ago < 0:
                continue
            decay = max(0, 1 - days_ago / FEEDBACK_PENALTY_DECAY_DAYS)
            if r['win']:
                penalty -= FEEDBACK_BONUS_PER_WIN * decay  # bonus (negative penalty)
            else:
                penalty += FEEDBACK_PENALTY_PER_LOSS * decay
        return penalty

    def get_record_summary(self, code):
        """获取某只股票的验证摘要"""
        if code not in self.records:
            return None
        results = self.records[code]
        wins = sum(1 for r in results if r['win'])
        return {'total': len(results), 'wins': wins, 'win_rate': wins/len(results) if results else 0}

    def import_from_verification_summary(self, summary_path):
        """从验证汇总文件导入历史记录"""
        if not os.path.exists(summary_path):
            return 0
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            return 0
        imported = 0
        for day in data.get('daily_results', []):
            date_str = day.get('date', '')
            for stock in day.get('results', day.get('stocks', [])):
                code = stock.get('code', '')
                win = stock.get('win', stock.get('t1_win', False))
                actual_ret = stock.get('actual_return', stock.get('best_return', 0))
                if code:
                    self.record_result(code, date_str, win, actual_ret)
                    imported += 1
        return imported


# ============================================================================
# Cooldown Tracker
# ============================================================================
class CooldownTracker:
    def __init__(self, cooldown_days=COOLDOWN_DAYS):
        self.cooldown_days = cooldown_days
        self.last_rec_date = {}

    def is_cooled_down(self, code, current_date):
        if code not in self.last_rec_date:
            return True
        days_since = (current_date - self.last_rec_date[code]).days
        return days_since >= self.cooldown_days

    def mark_recommended(self, code, date):
        self.last_rec_date[code] = date

    def get_freshness_penalty(self, code, current_date):
        if code not in self.last_rec_date:
            return 0
        days_since = (current_date - self.last_rec_date[code]).days
        if days_since >= self.cooldown_days:
            return 0
        return (self.cooldown_days - days_since) / self.cooldown_days * 10


# ============================================================================
# ★★★ V28 Scoring Engine ★★★
# ============================================================================
def score_all_stocks(kline, index_df, scores, date, risk, weights_config, debug=False, sector_mapping=None):
    """对全部股票计算V28评分，返回排序后的候选列表
    
    Args:
        sector_mapping: 可选的股票->行业映射字典
    """
    print(f"\n  正在计算V28评分 (risk={risk})...")
    
    # 加载行业映射（如果未提供）
    if sector_mapping is None:
        sector_mapping = _load_sector_mapping()

    regime, confidence, risk_detected = detect_market_regime(index_df, date)
    should, n_rec = should_trade(regime, confidence, risk_detected)
    print(f"  市场状态: {regime}, confidence={confidence:.2f}, risk={risk_detected}, "
          f"should_trade={should}, n_rec={n_rec}")

    # 使用检测到的risk，不是传入的（传入的可能是旧的）
    risk = risk_detected

    sector_info = identify_hot_sectors(kline, scores, date)

    # 选择权重
    if risk <= 2:
        w = weights_config['weights_bull']
    elif risk >= 4:
        w = weights_config['weights_bear']
    else:
        w = weights_config['weights_range']

    min_score = weights_config.get('min_score_threshold', 55)

    # Precompute industry peer returns
    industry_peers = defaultdict(list)

    # Phase 1: Filter tradeable stocks & compute industry returns
    stock_cache = {}
    skip_stats = defaultdict(int)

    for code, df in kline.items():
        static = scores.get(code)
        name = static.get('name', '') if static else ''

        if not is_tradeable(code, name):
            skip_stats['pt_st'] += 1
            continue

        hist = df[df['date'] < date]
        c = hist['close'].values
        total_days = len(df)

        if len(c) < 20:
            skip_stats['short_hist'] += 1
            continue

        if total_days < IPO_MIN_DAYS:
            skip_stats['ipo'] += 1
            continue

        # 涨停过滤
        if len(c) >= 2:
            last_pct = (c[-1] - c[-2]) / c[-2] * 100
            if last_pct > LIMIT_UP_THRESHOLD:
                skip_stats['limit_up'] += 1
                continue
        else:
            last_pct = 0

        # 行业信息：优先从评分文件获取，补充sector_mapping
        industry = 'unknown'
        if static:
            raw_ind = static.get('industry', '')
            if raw_ind and raw_ind not in ('unknown', '未知', '', None):
                industry = raw_ind
        
        # 从sector_mapping补充缺失的行业信息
        if industry == 'unknown' and sector_mapping:
            industry = sector_mapping.get(code, 'unknown')

        # 从kline计算20日涨幅（不再依赖评分文件）
        ret20 = (c[-1] - c[-21]) / c[-21] * 100 if len(c) >= 21 else 0

        # 计算5日涨幅用于行业peer比较
        ret5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
        industry_peers[industry].append((code, ret5))

        v = hist['volume'].values
        hi = hist['high'].values if 'high' in hist.columns else c
        lo = hist['low'].values if 'low' in hist.columns else c
        turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))

        # 市值估算：用最近收盘价和换手率推算
        # 最新成交额 / 换手率 ≈ 流通市值
        if len(turn) > 0 and turn[-1] > 0 and len(v) > 0:
            turnover_amount = c[-1] * v[-1]  # 当日成交额（元）
            market_cap_est = turnover_amount / (turn[-1] / 100.0)  # 流通市值
            market_cap_yi = market_cap_est / 1e8  # 转为亿元
        else:
            market_cap_yi = 50.0  # fallback

        # Extra score from static data
        extra_score = 50
        if static:
            extra_score = (static.get('tech', 5.0) * 5 + static.get('fund', 5.0) * 3 +
                           static.get('chip', 5.0) * 2 + static.get('sector', 5.0) * 3) / 13 * 10

        stock_cache[code] = {
            'c': c, 'v': v, 'hi': hi, 'lo': lo, 'turn': turn,
            'industry': industry, 'name': name,
            'last_pct': last_pct,
            'extra_score': extra_score,
            'ret20': ret20,
            'market_cap': market_cap_yi,
            'close': c[-1],  # 收盘价
        }

    # Phase 2: Compute sub-scores
    results = []
    for code, cache in stock_cache.items():
        industry = cache['industry']
        c, v, hi, lo, turn = cache['c'], cache['v'], cache['hi'], cache['lo'], cache['turn']

        trend_s, trend_dir = multi_timeframe_trend_score(c)
        mf_s = money_flow_score(c, v, hi, lo, turn)
        money_s = mf_s * 10

        sector_heat_val = sector_info['all_heat'].get(industry, 0)
        sector_s = max(0, min(100, (sector_heat_val + 5) * 10))

        peer_data = industry_peers.get(industry, [])
        rs_s = relative_strength_rank(code, c, industry, peer_data)

        vol_s = calc_volume_health(c, v)

        is_def = is_defensive_industry(industry)
        is_hb = is_high_beta_industry(industry)
        if risk >= 4:
            risk_adj = 80 if is_def else (20 if is_hb else 40)
        elif risk <= 2:
            risk_adj = 70 if is_hb else (40 if is_def else 55)
        else:
            risk_adj = 55

        div = detect_divergence(c, v)
        extra_s = cache['extra_score']

        # 计算最终分数
        final = (trend_s * w[0] + money_s * w[1] + sector_s * w[2]
                 + rs_s * w[3] + vol_s * w[4] + risk_adj * w[5])
        total_w = sum(w)
        if total_w > 0:
            final /= total_w

        # Divergence adjustment
        if div['bullish']:
            final += 5 * div['strength']
        if div['bearish']:
            final -= 8 * div['strength']

        results.append({
            'code': code,
            'name': cache['name'],
            'industry': industry,
            'final_score': final,
            'close': cache['close'],  # 收盘价
            'trend_s': trend_s,
            'trend_dir': trend_dir,
            'money_s': mf_s,  # 0-10范围
            'sector_s': sector_s,
            'rs_s': rs_s,
            'vol_s': vol_s,
            'risk_adj': risk_adj,
            'extra_s': extra_s,
            'div_bullish': div['bullish'],
            'div_bearish': div['bearish'],
            'div_strength': div['strength'],
            'ret20': cache['ret20'],
            'market_cap': cache['market_cap'],
        })

    # Sort by score
    results.sort(key=lambda x: x['final_score'], reverse=True)

    skip_str = ', '.join(f'{k}={v}' for k, v in sorted(skip_stats.items()) if v > 0)
    print(f"  评分完成: {len(results)} 只 (跳过: {skip_str})")

    if debug and results:
        print(f"\n  === Top 10 调试信息 ===")
        for i, r in enumerate(results[:10], 1):
            print(f"  {i:2}. {r['code']} {r['name'][:6]:6} 行业:{r['industry'][:6]:6} "
                  f"得分:{r['final_score']:.1f} "
                  f"趋势:{r['trend_s']:.0f} 资金:{r['money_s']:.1f} "
                  f"板块:{r['sector_s']:.0f} RS:{r['rs_s']:.0f} "
                  f"量价:{r['vol_s']:.0f} 风险:{r['risk_adj']:.0f} "
                  f"20日涨幅:{r['ret20']:+.1f}% 市值:{r['market_cap']:.1f}亿")

    return results, risk, regime, sector_info, stock_cache


# ============================================================================
# Selection with diversification
# ============================================================================
def select_recommendations(scored_stocks, weights_config, risk, cooldown_tracker, date, debug=False, feedback_tracker=None):
    """从评分后的股票中选择推荐，应用多样化过滤 + 验证反馈惩罚"""
    min_score = weights_config.get('min_score_threshold', 55)
    n_rec = RECOMMEND_COUNT

    # V28.1: 应用验证反馈惩罚
    if feedback_tracker:
        date_str = str(date.date()) if hasattr(date, 'date') else str(date)[:10]
        for s in scored_stocks:
            penalty = feedback_tracker.get_penalty(s['code'], date_str)
            if penalty != 0:
                s['final_score'] -= penalty
                s['feedback_penalty'] = penalty
                if debug:
                    summary = feedback_tracker.get_record_summary(s['code'])
                    print(f"    [FEEDBACK] {s['code']} {s['name']}: penalty={penalty:.1f} (hist: {summary})")
        # 重新排序
        scored_stocks.sort(key=lambda x: x['final_score'], reverse=True)

    selected = []
    ind_count = defaultdict(int)
    skipped_reasons = defaultdict(int)

    for s in scored_stocks:
        if len(selected) >= n_rec:
            break

        code = s['code']
        score = s['final_score']
        industry = s['industry']

        # V28.1: 硬过滤 - 历史胜率极低的股票直接跳过
        if feedback_tracker:
            summary = feedback_tracker.get_record_summary(code)
            if summary and summary['total'] >= 3 and summary['win_rate'] < 0.2:
                skipped_reasons['low_win_rate'] += 1
                continue

        # 过滤条件
        if score < min_score:
            skipped_reasons['below_threshold'] += 1
            continue
        if s['trend_dir'] == 'strong_down':
            skipped_reasons['strong_down'] += 1
            continue
        if s.get('div_bearish') and s.get('div_strength', 0) > 0.5:
            skipped_reasons['bearish_div'] += 1
            continue
        if not cooldown_tracker.is_cooled_down(code, date):
            skipped_reasons['cooldown'] += 1
            continue
        if ind_count[industry] >= MAX_SAME_INDUSTRY:
            skipped_reasons['same_industry'] += 1
            continue

        selected.append(s)
        ind_count[industry] += 1

    # Fallback: 放宽条件
    if len(selected) < n_rec:
        for s in scored_stocks:
            if len(selected) >= n_rec:
                break
            if any(x['code'] == s['code'] for x in selected):
                continue
            if s['final_score'] < min_score - 10:
                break
            if s['trend_dir'] == 'strong_down':
                continue
            if not cooldown_tracker.is_cooled_down(s['code'], date):
                continue
            if ind_count[s['industry']] >= MAX_SAME_INDUSTRY:
                continue
            selected.append(s)
            ind_count[s['industry']] += 1

    # Mark cooldown
    for s in selected:
        cooldown_tracker.mark_recommended(s['code'], date)

    if skipped_reasons:
        skip_str = ', '.join(f'{k}={v}' for k, v in sorted(skipped_reasons.items()))
        print(f"  过滤统计: {skip_str}")

    return selected


# ============================================================================
# V2 预过滤集成
# ============================================================================
V2_FILTER_THRESHOLD = 0.5  # 只在置信度>=0.5时启用V2预过滤

def apply_v2_prefilter(kline_dict, scores_dict, date_pd, risk, regime, confidence):
    """
    应用V2预过滤：用板块轮动筛选候选池
    
    流程：
    1. 获取热点板块（使用SectorRotator）
    2. 过滤出在热点板块中的股票
    3. 返回过滤后的候选代码集合
    
    Returns:
        (v2_filtered_codes: set, hot_sectors: list, v2_stats: dict)
    """
    import time as time_module
    t0 = time_module.time()
    
    stats = {
        'total_in_kline': len(kline_dict),
        'total_in_scores': len(scores_dict),
        'v2_filtered_count': 0,
        'hot_sectors_used': [],
        'v2_enabled': False,
    }
    
    # 置信度太低时不启用V2过滤（避免误判热点板块）
    if confidence < V2_FILTER_THRESHOLD and regime in ('bear', 'crisis'):
        print(f"  [V2] 置信度={confidence:.2f} 或市场{risk}，跳过V2预过滤")
        return set(kline_dict.keys()), [], stats
    
    if not V2_AVAILABLE:
        print(f"  [V2] V2筛选器未加载，使用全量候选池")
        return set(kline_dict.keys()), [], stats
    
    print(f"\n{'=' * 70}")
    print(f"  步骤1.5: V2 预过滤（板块轮动筛选）")
    print(f"{'=' * 70}")
    
    try:
        # 初始化板块轮动识别器
        sector_rotator = SectorRotator()
        
        # 获取热点板块
        hot_sectors = sector_rotator.get_hot_sectors(top_n=10)
        
        if not hot_sectors:
            print(f"  [V2] 未获取到热点板块，使用全量候选池")
            return set(kline_dict.keys()), [], stats
        
        stats['hot_sectors_used'] = [s[0] for s in hot_sectors]
        stats['v2_enabled'] = True
        
        print(f"  热点板块(Top 10): {[s[0] for s in hot_sectors[:5]]}...")
        
        # 加载行业映射（使用V28自带的函数）
        sector_mapping = _load_sector_mapping()
        
        # 过滤候选池
        v2_filtered = set()
        skip_no_match = 0
        skip_no_sector = 0
        
        for code in kline_dict.keys():
            # 优先从评分数据获取行业信息
            static = scores_dict.get(code)
            
            if static:
                industry = static.get('industry', static.get('matched_sector', ''))
                if not industry or industry in ('unknown', '未知', ''):
                    # 从sector_mapping补充
                    industry = sector_mapping.get(code, '未知')
                name = static.get('name', '')
            else:
                # 没有评分数据，从sector_mapping获取
                industry = sector_mapping.get(code, '未知')
                name = ''
            
            if not industry or industry == '未知':
                skip_no_sector += 1
            
            stock_info = {
                'code': code,
                'name': name,
                'industry': industry,
                'matched_sector': industry,
            }
            
            # 用V2的is_in_hot_sector判断
            if sector_rotator.is_in_hot_sector(stock_info, hot_sectors):
                v2_filtered.add(code)
            else:
                skip_no_match += 1
        
        stats['v2_filtered_count'] = len(v2_filtered)
        stats['filtered_out'] = skip_no_match
        stats['no_sector_data'] = skip_no_sector
        
        print(f"  V2预过滤: {len(v2_filtered)}/{len(kline_dict)} 只通过板块筛选")
        print(f"  (过滤掉 {skip_no_match} 只不在热点板块, {skip_no_sector} 只无行业数据)")
        
        elapsed = time_module.time() - t0
        print(f"  V2预过滤耗时: {elapsed:.1f}s")
        
        return v2_filtered, hot_sectors, stats
        
    except Exception as e:
        print(f"  [V2] V2预过滤失败: {e}，使用全量候选池")
        import traceback
        traceback.print_exc()
        return set(kline_dict.keys()), [], stats


# ============================================================================
# Main Entry Point
# ============================================================================
def run_v28_recommendation(dry_run=False, debug=False, use_v2_prefilter=True,
                         enable_agent_debate=False, debate_top_n=3,
                         debate_rounds=3, risk_rounds=2):
    """执行V28推荐
    
    Args:
        dry_run: 不发送邮件
        debug: 输出详细调试信息
        use_v2_prefilter: 是否启用V2预过滤（默认True）
        enable_agent_debate: 启用 Agent 多空辩论
        debate_top_n: 辩论前N只股票
        debate_rounds: 多空辩论轮数
        risk_rounds: 风险辩论轮数
    """
    t0 = time.time()
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    today_pd = pd.Timestamp(today_str)

    print("=" * 70)
    print(f"V28 每日推荐引擎 | {today_str}")
    print("=" * 70)

    # Load data
    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = load_scores()
    weights_config = load_v25_params()

    print(f"\n{'=' * 70}")
    print(f"  步骤1: 不交易信号检测")
    print(f"{'=' * 70}")

    # No-trade signal check
    skip_day, no_trade_signals, no_trade_risk = detect_no_trade_signals(index_df, today_pd)

    if no_trade_signals:
        signal_names = ', '.join(f"{s[0]}({s[1]})" for s in no_trade_signals)
        print(f"  检测到风险信号: {signal_names}")
        print(f"  总风险分: {no_trade_risk}")

    if skip_day:
        print(f"\n  [WARN] 今日不推荐交易！")
        print(f"  原因: {', '.join(s[0] for s in no_trade_signals)}")
        print(f"  建议空仓观望")
        print("=" * 70)
        result = {
            'date': today_str,
            'action': 'NO_TRADE',
            'reason': ', '.join(s[0] for s in no_trade_signals),
            'no_trade_risk': no_trade_risk,
            'signals': [{'name': s[0], 'risk': s[1]} for s in no_trade_signals],
        }
        # Save result
        _save_result(result, dry_run)
        elapsed = time.time() - t0
        print(f"\n  耗时: {elapsed:.0f}s")
        return result

    # Market regime
    regime, confidence, risk = detect_market_regime(index_df, today_pd)
    should, n_rec = should_trade(regime, confidence, risk)
    print(f"  市场状态: {regime}, confidence={confidence:.2f}, risk={risk}")
    print(f"  应该交易: {should}, 推荐数: {n_rec}")

    if not should:
        print(f"\n  [WARN] 市场风险过高，今日不推荐交易！")
        print(f"  regime={regime}, risk={risk}")
        print("=" * 70)
        result = {
            'date': today_str,
            'action': 'NO_TRADE',
            'reason': f'市场风险过高(regime={regime}, risk={risk})',
            'no_trade_risk': 0,
            'signals': [],
        }
        _save_result(result, dry_run)
        elapsed = time.time() - t0
        print(f"\n  耗时: {elapsed:.0f}s")
        return result

    # ===== V2 预过滤（核心集成）=====
    v2_stats = {}
    hot_sectors = []
    if use_v2_prefilter:
        v2_filtered_codes, hot_sectors, v2_stats = apply_v2_prefilter(
            kline, scores, today_pd, risk, regime, confidence)
        
        # 如果V2过滤后候选池太小，放宽条件
        if len(v2_filtered_codes) < 5:
            print(f"  [V2] 过滤后候选池过小({len(v2_filtered_codes)}只)，放宽条件")
            v2_filtered_codes = set(kline.keys())
            v2_stats['v2_enabled'] = False
        
        # 创建过滤后的kline子集
        kline_filtered = {code: df for code, df in kline.items() if code in v2_filtered_codes}
        kline_size = len(kline)
        kline = kline_filtered
        print(f"  进入V28评分的候选池: {len(kline)}/{kline_size} 只")
    else:
        v2_filtered_codes = set(kline.keys())

    # 加载行业映射（供V28评分使用）
    sector_mapping = _load_sector_mapping()
    print(f"  行业映射已加载: {len(sector_mapping)} 只")

    print(f"\n{'=' * 70}")
    print(f"  步骤2: V28 6维评分")
    print(f"{'=' * 70}")

    # Score all stocks
    scored_stocks, actual_risk, actual_regime, sector_info, stock_cache = score_all_stocks(
        kline, index_df, scores, today_pd, risk, weights_config, debug=debug,
        sector_mapping=sector_mapping)

    # ===== 新增: LLM 板块语义分析 =====
    llm_analysis = None
    llm_analyzer = None
    if LLM_AVAILABLE:
        print(f"\n{'=' * 70}")
        print(f"  步骤2.5: LLM 板块语义分析")
        print(f"{'=' * 70}")
        try:
            llm_analyzer = HotSectorAnalyzer()
            internal_hot = sector_info.get('hot', []) if sector_info else []
            llm_analysis = llm_analyzer.analyze(
                internal_hot_sectors=internal_hot,
                fetch_news=True,
            )

            # 打印 LLM 分析报告
            report = llm_analyzer.format_report()
            for line in report.split('\n'):
                print(f"  {line}")

            # 用 sector_boost 调整评分
            boost_applied = 0
            for s in scored_stocks:
                industry = s['industry']
                boost = llm_analyzer.get_sector_boost(industry)
                if boost != 0:
                    s['final_score'] += boost
                    s['llm_boost'] = boost
                    boost_applied += 1

            # 重新排序
            scored_stocks.sort(key=lambda x: x['final_score'], reverse=True)
            print(f"\n  LLM板块加分已应用: {boost_applied} 只股票")
            print(f"  LLM Provider: {llm_analysis.get('provider', '?')}")

            # 风险警告检查
            risk_warnings = llm_analysis.get('risk_warnings', [])
            if risk_warnings:
                print(f"  ⚠️ LLM风险警告: {'; '.join(risk_warnings)}")

        except Exception as e:
            print(f"  [WARN] LLM分析失败: {e}")
            llm_analysis = None
    else:
        print(f"\n  [INFO] LLM模块未启用，跳过语义分析")

    print(f"\n{'=' * 70}")
    print(f"  步骤3: 多样化选择")
    print(f"{'=' * 70}")

    # Load cooldown history
    cooldown_tracker = _load_cooldown_tracker()

    # Select recommendations
    # V28.1: Load verification feedback
    feedback_tracker = VerificationFeedback().load()

    selected = select_recommendations(
        scored_stocks, weights_config, actual_risk, cooldown_tracker, today_pd, debug=debug,
        feedback_tracker=feedback_tracker)

    # Save cooldown
    _save_cooldown_tracker(cooldown_tracker)

    print(f"\n{'=' * 70}")
    print(f"  步骤4: 推荐结果")
    print(f"{'=' * 70}")

    if not selected:
        print("  今日无满足条件的推荐")
        result = {
            'date': today_str,
            'action': 'NO_RECOMMENDATION',
            'reason': '无满足条件的股票',
            'recommendations': [],
        }
        _save_result(result, dry_run)
        elapsed = time.time() - t0
        print(f"\n  耗时: {elapsed:.0f}s")
        return result

    # Build recommendation output
    recommendations = []
    for i, s in enumerate(selected, 1):
        rec = {
            'rank': i,
            'code': s['code'],
            'name': s['name'],
            'industry': s['industry'],
            'final_score': round(s['final_score'], 1),
            'scores': {
                'trend': round(s['trend_s'], 1),
                'money_flow': round(s['money_s'], 1),  # 0-10范围
                'sector': round(s['sector_s'], 1),
                'relative_strength': round(s['rs_s'], 1),
                'volume_health': round(s['vol_s'], 1),
                'risk_adjustment': round(s['risk_adj'], 1),
            },
            'trend_direction': s['trend_dir'],
            'ret_20d': round(s['ret20'], 2),
            'market_cap_yi': round(s['market_cap'], 1),
            'divergence': {
                'bullish': s['div_bullish'],
                'bearish': s['div_bearish'],
            },
            'buy_price': round(s.get('close', 0), 2),  # 收盘价作为建议买入价
        }
        recommendations.append(rec)

        print(f"  {i}. {s['code']} {s['name'][:8]:8} 行业:{s['industry'][:8]:8} "
              f"得分:{s['final_score']:.1f} "
              f"趋势:{s['trend_s']:.0f} 资金:{s['money_s']:.1f} "
              f"板块:{s['sector_s']:.0f} RS:{s['rs_s']:.0f} "
              f"20日涨幅:{s['ret20']:+.1f}% 市值:{s['market_cap']:.1f}亿")

    result = {
        'date': today_str,
        'action': 'RECOMMEND',
        'market': {
            'regime': actual_regime,
            'risk': actual_risk,
            'confidence': round(confidence, 2),
        },
        'no_trade_signals': [{'name': s[0], 'risk': s[1]} for s in no_trade_signals],
        'no_trade_risk_total': no_trade_risk,
        'llm_analysis': {
            'provider': llm_analysis.get('provider', 'none') if llm_analysis else 'none',
            'market_summary': llm_analysis.get('market_summary', '') if llm_analysis else '',
            'hot_sectors_analysis': llm_analysis.get('hot_sectors_analysis', []) if llm_analysis else [],
            'sector_boost': llm_analysis.get('sector_boost', {}) if llm_analysis else {},
            'risk_warnings': llm_analysis.get('risk_warnings', []) if llm_analysis else [],
            'tomorrow_focus': llm_analysis.get('tomorrow_focus', []) if llm_analysis else [],
        } if llm_analysis else {
            'provider': 'none',
            'market_summary': '',
            'hot_sectors_analysis': [],
            'sector_boost': {},
            'risk_warnings': [],
            'tomorrow_focus': [],
        },
        'recommendations': recommendations,
        'total_scored': len(scored_stocks),
        'v2_prefilter': {
            'enabled': v2_stats.get('v2_enabled', False),
            'candidate_pool_size': v2_stats.get('v2_filtered_count', len(kline)),
            'hot_sectors': v2_stats.get('hot_sectors_used', [])[:10],
            'filtered_out': v2_stats.get('filtered_out', 0),
        },
        'top_10_debug': [
            {
                'code': s['code'],
                'name': s['name'][:8],
                'industry': s['industry'][:8],
                'score': round(s['final_score'], 1),
                'ret20': round(s['ret20'], 2),
                'market_cap': round(s['market_cap'], 1),
                'money_s': round(s['money_s'], 1),
            }
            for s in scored_stocks[:10]
        ] if debug else [],
    }

    # Agent 多空辩论
    if enable_agent_debate and recommendations:
        try:
            from agent_debate import integrate_with_v28
            print(f"\n{'=' * 70}")
            print(f"  步骤5: Agent 多空辩论")
            print(f"{'=' * 70}")
            result = integrate_with_v28(
                result, top_n=debate_top_n,
                debate_rounds=debate_rounds,
                risk_rounds=risk_rounds,
                verbose=True,
            )
            # 打印辩论报告
            if 'agent_debate' in result and 'report' in result['agent_debate']:
                print(result['agent_debate']['report'])
        except Exception as e:
            print(f"  [WARN] Agent 辩论失败: {e}")
            result['agent_debate'] = {'status': 'failed', 'error': str(e)}

    # Save result
    _save_result(result, dry_run)

    # Send email (unless dry-run)
    if not dry_run:
        _send_email(result)

    elapsed = time.time() - t0
    print(f"\n  耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("=" * 70)

    return result


# ============================================================================
# Cooldown persistence
# ============================================================================
COOLDOWN_FILE = os.path.join(BASE_DIR, 'v28_cooldown.json')

def _load_cooldown_tracker():
    tracker = CooldownTracker(COOLDOWN_DAYS)
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for code, date_str in data.get('last_rec_date', {}).items():
                tracker.last_rec_date[code] = pd.Timestamp(date_str)
        except:
            pass
    return tracker

def _save_cooldown_tracker(tracker):
    data = {
        'last_rec_date': {code: str(d.date()) for code, d in tracker.last_rec_date.items()},
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================
# Result persistence
# ============================================================================
RESULT_HISTORY_DIR = os.path.join(BASE_DIR, 'recommendation_history')

def _save_result(result, dry_run=False):
    os.makedirs(RESULT_HISTORY_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    suffix = '_dryrun' if dry_run else ''
    filepath = os.path.join(RESULT_HISTORY_DIR, f'v28_recommendation_{today}{suffix}.json')

    # Convert numpy types
    def convert(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj

    result = convert(result)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存: {filepath}")


# ============================================================================
# Email notification
# ============================================================================
def _send_email(result):
    """发送推荐邮件"""
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))
        from email_notifier import EmailNotifier
        notifier = EmailNotifier()

        if result['action'] == 'NO_TRADE':
            # Send no-trade notification
            subject = f"V28推荐 {result['date']}: 今日不交易"
            html = f"""
            <h2>V28推荐引擎 - 不交易通知</h2>
            <p><b>日期:</b> {result['date']}</p>
            <p><b>原因:</b> {result.get('reason', '风险信号触发')}</p>
            <p><b>风险分:</b> {result.get('no_trade_risk', 'N/A')}</p>
            <p><b>信号:</b></p>
            <ul>
            {''.join(f'<li>{s["name"]} (风险:{s["risk"]})</li>' for s in result.get('signals', []))}
            </ul>
            <p>建议空仓观望。</p>
            """
            notifier.send_custom_email(subject, html)
        elif result['action'] == 'RECOMMEND':
            # Send recommendation email
            recs = result.get('recommendations', [])
            subject = f"V28推荐 {result['date']}: {len(recs)}只"
            market = result.get('market', {})
            llm = result.get('llm_analysis', {})
            rows = ''
            for rec in recs:
                scores = rec.get('scores', {})
                llm_boost = rec.get('llm_boost', 0)
                boost_str = f" (+{llm_boost:.1f}LLM)" if llm_boost else ""
                rows += f"""
                <tr>
                    <td>{rec['rank']}</td>
                    <td>{rec['code']}</td>
                    <td>{rec['name']}</td>
                    <td>{rec['industry']}</td>
                    <td><b>{rec['final_score']}{boost_str}</b></td>
                    <td>{scores.get('trend', 'N/A')}</td>
                    <td>{scores.get('money_flow', 'N/A')}</td>
                    <td>{scores.get('sector', 'N/A')}</td>
                    <td>{scores.get('relative_strength', 'N/A')}</td>
                    <td>{rec.get('ret_20d', 'N/A')}%</td>
                    <td>{rec.get('market_cap_yi', 'N/A')}亿</td>
                </tr>"""

            # LLM analysis section
            llm_section = ''
            if llm and llm.get('provider', 'none') != 'none':
                llm_section = f"""
            <h3>🤖 LLM板块分析 ({llm.get('provider', '?')})</h3>
            <p><b>市场判断:</b> {llm.get('market_summary', '-')}</p>
            <ul>
            {''.join(f'<li>🔥 {s.get("name", "?")} | 热度:{s.get("hotness", "?")} | 持续性:{s.get("sustainability", "?")} | {s.get("summary", "")}</li>' for s in llm.get('hot_sectors_analysis', []))}
            </ul>
            {''.join(f'<p>⚠️ {w}</p>' for w in llm.get('risk_warnings', []))}
            {''.join(f'<p>👁 明日关注: {f}</p>' for f in llm.get('tomorrow_focus', []))}
            """

            html = f"""
            <h2>V28推荐引擎 - 每日推荐</h2>
            <p><b>日期:</b> {result['date']}</p>
            <p><b>市场状态:</b> {market.get('regime', 'N/A')} (风险={market.get('risk', 'N/A')})</p>
            <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>#</th><th>代码</th><th>名称</th><th>行业</th><th>得分</th>
                <th>趋势</th><th>资金</th><th>板块</th><th>RS</th><th>20日涨幅</th><th>市值</th></tr>
            {rows}
            </table>
            {llm_section}
            <p>共评分 {result.get('total_scored', 'N/A')} 只股票。</p>
            """
            notifier.send_custom_email(subject, html)
    except Exception as e:
        print(f"  邮件发送失败: {e}")


# ============================================================================
# QA Validation
# ============================================================================
def run_qa_validation():
    """运行QA验证，检查V28推荐器的各项输出"""
    print("=" * 70)
    print("V28 推荐器 QA 验证")
    print("=" * 70)

    t0 = time.time()
    today_pd = pd.Timestamp(datetime.now().strftime('%Y-%m-%d'))

    qa_results = {
        'industry_not_unknown': False,
        'ret20_not_zero': False,
        'fund_flow_score_range': False,
        'lhb_check': True,  # V28没有lhb_score，跳过
        'market_cap_diverse': False,
        'no_pt_st': False,
        'same_industry_max1': False,
        'no_trade_signal_works': False,
    }

    # Load data
    print("\n[QA] 加载数据...")
    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = load_scores()
    weights_config = load_v25_params()

    # ===== Test 1: No-trade signal detection =====
    print("\n[QA-1] 不交易信号检测...")
    # 用历史日期测试
    test_date = pd.Timestamp('2026-05-12')
    skip_day, signals, risk_total = detect_no_trade_signals(index_df, test_date)
    print(f"  2026-05-12: skip={skip_day}, risk={risk_total}, signals={[(s[0],s[1]) for s in signals]}")

    test_date2 = pd.Timestamp('2026-05-13')
    skip_day2, signals2, risk_total2 = detect_no_trade_signals(index_df, test_date2)
    print(f"  2026-05-13: skip={skip_day2}, risk={risk_total2}, signals={[(s[0],s[1]) for s in signals2]}")

    # 至少有一种情况能检测到信号
    qa_results['no_trade_signal_works'] = skip_day or skip_day2 or len(signals) > 0 or len(signals2) > 0
    print(f"  [OK] 不交易信号检测: {'PASS' if qa_results['no_trade_signal_works'] else 'FAIL'}")

    # ===== Test 2: Score stocks with recent date =====
    print("\n[QA-2] 评分测试 (使用最近交易日)...")
    # 找到最近的一个交易日
    recent_dates = index_df[index_df['date'] < today_pd].sort_values('date', ascending=False)
    if len(recent_dates) == 0:
        print("  [错误] 无可用交易日")
        return qa_results

    test_date_qa = recent_dates.iloc[0]['date']
    print(f"  使用交易日: {test_date_qa.date()}")

    scored_stocks, risk, regime, sector_info_qa, stock_cache_qa = score_all_stocks(
        kline, index_df, scores, test_date_qa, 3, weights_config, debug=True)

    if not scored_stocks:
        print("  [错误] 评分为空")
        return qa_results

    # ===== Test 3: Industry not unknown =====
    print("\n[QA-3] 行业数据检查...")
    unknown_count = sum(1 for s in scored_stocks[:50] if s['industry'] in ('unknown', '未知', ''))
    total_top50 = min(50, len(scored_stocks))
    unknown_ratio = unknown_count / total_top50 if total_top50 > 0 else 1
    qa_results['industry_not_unknown'] = unknown_ratio < 0.3  # 最多30%未知
    print(f"  Top 50中未知行业: {unknown_count}/{total_top50} ({unknown_ratio*100:.1f}%)")
    print(f"  {'[OK]' if qa_results['industry_not_unknown'] else '[X]'} 行业检查: "
          f"{'PASS' if qa_results['industry_not_unknown'] else 'FAIL'}")

    # Show industry distribution
    ind_dist = defaultdict(int)
    for s in scored_stocks[:50]:
        ind_dist[s['industry']] += 1
    print(f"  行业分布(Top50): {dict(sorted(ind_dist.items(), key=lambda x: -x[1])[:10])}")

    # ===== Test 4: 20日涨幅不是0 =====
    print("\n[QA-4] 20日涨幅检查...")
    zero_ret_count = sum(1 for s in scored_stocks[:50] if abs(s['ret20']) < 0.01)
    qa_results['ret20_not_zero'] = zero_ret_count < 5
    avg_ret20 = np.mean([s['ret20'] for s in scored_stocks[:50]])
    print(f"  Top 50中20日涨幅=0: {zero_ret_count}/{total_top50}")
    print(f"  平均20日涨幅: {avg_ret20:+.2f}%")
    print(f"  {'[OK]' if qa_results['ret20_not_zero'] else '[X]'} 涨幅检查: "
          f"{'PASS' if qa_results['ret20_not_zero'] else 'FAIL'}")

    # ===== Test 5: money_flow_score in 0-10 =====
    print("\n[QA-5] 资金流向分数范围检查...")
    out_of_range = sum(1 for s in scored_stocks[:50] if s['money_s'] < 0 or s['money_s'] > 10)
    qa_results['fund_flow_score_range'] = out_of_range == 0
    money_range = [s['money_s'] for s in scored_stocks[:50]]
    print(f"  资金分范围: [{min(money_range):.1f}, {max(money_range):.1f}]")
    print(f"  超出[0,10]的: {out_of_range}")
    print(f"  {'[OK]' if qa_results['fund_flow_score_range'] else '[X]'} 资金分范围: "
          f"{'PASS' if qa_results['fund_flow_score_range'] else 'FAIL'}")

    # ===== Test 6: 市值数据合理性 =====
    print("\n[QA-6] 市值数据检查...")
    caps = [s['market_cap'] for s in scored_stocks[:50]]
    all_50 = sum(1 for c in caps if abs(c - 50.0) < 1.0)
    qa_results['market_cap_diverse'] = all_50 < 10  # 最多20%是50亿
    print(f"  市值范围: [{min(caps):.1f}, {max(caps):.1f}] 亿")
    print(f"  市值=50亿的: {all_50}/{len(caps)}")
    print(f"  {'[OK]' if qa_results['market_cap_diverse'] else '[X]'} 市值多样性: "
          f"{'PASS' if qa_results['market_cap_diverse'] else 'FAIL'}")

    # ===== Test 7: 无PT/ST =====
    print("\n[QA-7] PT/ST过滤检查...")
    pt_st_in_top = []
    for s in scored_stocks[:50]:
        name = s['name']
        for kw in PT_ST_KEYWORDS:
            if kw in name:
                pt_st_in_top.append(f"{s['code']} {name}")
                break
    qa_results['no_pt_st'] = len(pt_st_in_top) == 0
    if pt_st_in_top:
        print(f"  发现PT/ST: {pt_st_in_top}")
    print(f"  {'[OK]' if qa_results['no_pt_st'] else '[X]'} PT/ST过滤: "
          f"{'PASS' if qa_results['no_pt_st'] else 'FAIL'}")

    # ===== Test 8: 同行业最多1只 =====
    print("\n[QA-8] 多样化选择检查...")
    cooldown_tracker = CooldownTracker(COOLDOWN_DAYS)
    selected = select_recommendations(
        scored_stocks, weights_config, risk, cooldown_tracker, test_date_qa)

    if selected:
        sel_industries = [s['industry'] for s in selected]
        from collections import Counter
        ind_counter = Counter(sel_industries)
        max_same = max(ind_counter.values())
        qa_results['same_industry_max1'] = max_same <= MAX_SAME_INDUSTRY
        print(f"  推荐行业: {dict(ind_counter)}")
        print(f"  最大同行业数: {max_same} (限制: {MAX_SAME_INDUSTRY})")
        print(f"  {'[OK]' if qa_results['same_industry_max1'] else '[X]'} 多样化: "
              f"{'PASS' if qa_results['same_industry_max1'] else 'FAIL'}")
    else:
        print("  无推荐结果，跳过")
        qa_results['same_industry_max1'] = True

    # ===== Summary =====
    print(f"\n{'=' * 70}")
    print(f"  QA 验证总结")
    print(f"{'=' * 70}")

    all_pass = True
    for check, passed in qa_results.items():
        status = "[PASS] PASS" if passed else "[FAIL] FAIL"
        print(f"  {check:30s} {status}")
        if not passed:
            all_pass = False

    print(f"\n  总计: {'全部通过 [PASS]' if all_pass else '存在失败项 [FAIL]'}")

    elapsed = time.time() - t0
    print(f"  QA耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("=" * 70)

    # Save QA results
    qa_file = os.path.join(RESULT_HISTORY_DIR, f'v28_qa_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    os.makedirs(RESULT_HISTORY_DIR, exist_ok=True)

    def convert(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj

    with open(qa_file, 'w', encoding='utf-8') as f:
        json.dump(convert(qa_results), f, ensure_ascii=False, indent=2)
    print(f"  QA结果已保存: {qa_file}")

    return qa_results


# ============================================================================
# CLI
# ============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='V28 每日推荐引擎')
    parser.add_argument('--dry-run', action='store_true', help='不发送邮件')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    parser.add_argument('--qa', action='store_true', help='运行QA验证')
    parser.add_argument('--no-v2', action='store_true', help='禁用V2预过滤')
    parser.add_argument('--debate', action='store_true', help='启用Agent多空辩论')
    parser.add_argument('--debate-n', type=int, default=3, help='辩论股票数')
    parser.add_argument('--debate-rounds', type=int, default=3, help='多空辩论轮数')
    parser.add_argument('--risk-rounds', type=int, default=2, help='风险辩论轮数')
    args = parser.parse_args()

    if args.qa:
        run_qa_validation()
    else:
        run_v28_recommendation(
            dry_run=args.dry_run, debug=args.debug,
            use_v2_prefilter=not args.no_v2,
            enable_agent_debate=args.debate,
            debate_top_n=args.debate_n,
            debate_rounds=args.debate_rounds,
            risk_rounds=args.risk_rounds,
        )

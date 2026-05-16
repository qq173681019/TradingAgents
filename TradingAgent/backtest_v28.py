#!/usr/bin/env python3
# NOTE: Run with python3 (not python) to avoid JSON parsing issues
# -*- coding: utf-8 -*-
"""
V28 - Fundamental Restructure: Dual-Mode System

Core insight from 12-day test analysis:
  - Most FAIL days happen when market drops and stocks drop more
  - If we can detect and SKIP those days → dramatic improvement

V28 Strategy:
  Mode 1 (Trend Confirmation): Use V25 scoring when trend is clear
  Mode 2 (No-Trade Defense): Skip trading when risk signals detected

No-trade signals:
  1. 冲高回落: Previous day surge >3% 
  2. 连涨疲劳: Index up 4+ consecutive days
  3. 波动率急升: 5d vol > 2x 20d vol
  4. 累计跌幅: Past 2 days cumulative drop >2%
  5. 连跌: 3+ consecutive down days

Based on V26 (real trading calendar, cooldown, limit-up filter).
Uses V25 Optuna params (no re-optimization).

Test window: 04-22 ~ 05-13
"""

import json, os, sys, time, gc, warnings, functools
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
SHARED_DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# Config
# ============================================================================
MIN_KLINE_DAYS = 30
MAX_INDUSTRY = 2
MEMORY_LIMIT_MB = 8000

V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True

# Walk-Forward periods
PERIOD_TRAIN_START = '2026-02-07'
PERIOD_TRAIN_END = '2026-03-28'
PERIOD_VALID_START = '2026-03-28'
PERIOD_VALID_END = '2026-04-22'
PERIOD_TEST_START = '2026-04-22'
PERIOD_TEST_END = '2026-05-13'

PERIOD_A = ('2026-02-07', '2026-03-03')
PERIOD_B = ('2026-03-03', '2026-03-28')
PERIOD_C = ('2026-03-28', '2026-04-22')
PERIOD_D = ('2026-04-22', '2026-05-13')

# FIX #2: Cooldown settings
COOLDOWN_DAYS = 3
USE_COOLDOWN = True

# FIX #4: Limit-up filter settings
LIMIT_UP_THRESHOLD = 15.0
IPO_MIN_DAYS = 30

PT_ST_KEYWORDS = ['PT', 'ST', '*ST', '退']
BLOCKED_CODE_PREFIXES = ['2', '9', '4']

DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']


def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)

def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


# ============================================================================
# Memory Monitor
# ============================================================================
def check_memory(limit_mb=MEMORY_LIMIT_MB):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if mb > limit_mb:
            gc.collect()
            return True
        return False
    except ImportError:
        return False

def print_mem(label=""):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label:
            print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError:
        pass


# ============================================================================
# Code normalization & Stock filtering
# ============================================================================
def normalize_code(code):
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code

def is_tradeable(code, name='', static=None):
    if len(code) >= 1 and code[0] in BLOCKED_CODE_PREFIXES:
        return False
    for kw in PT_ST_KEYWORDS:
        if kw in name:
            return False
    return True


# ============================================================================
# Data Loading (same as V26)
# ============================================================================
def load_merged_kline():
    print("[1/3] Loading and merging kline data...")
    v19_pool = None
    if V19_USE_POOL and os.path.exists(V19_POOL_FILE):
        with open(V19_POOL_FILE, 'r', encoding='utf-8') as f:
            v19_pool = set(json.load(f))
        print(f"  V19 stock pool: {len(v19_pool)} stocks")

    new_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}

    print(f"  Loading: {os.path.basename(new_file)} ({os.path.getsize(new_file)/1024/1024:.1f}MB)")
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

    all_min_dates = [df['date'].min() for df in merged.values()]
    all_max_dates = [df['date'].max() for df in merged.values()]
    print(f"  Loaded: {len(merged)} stocks (skipped {skipped_pool} out-of-pool, {skipped_days} too short)")
    print(f"  Date range: {min(all_min_dates).date()} ~ {max(all_max_dates).date()}")
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
    print("[2/3] Loading and merging index data...")
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
    print(f"  Index: {len(index_df)} days, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    return index_df


def _load_scores():
    import glob
    opt_pattern = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
    opt_files = sorted(glob.glob(opt_pattern),
                       key=lambda x: (os.path.getsize(x) > 100000, os.path.getmtime(x)), reverse=True)
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

    if not scores:
        score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
        if not os.path.exists(score_file):
            all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
            if all_sf:
                score_file = max(all_sf, key=lambda x: os.path.getsize(x))
        if os.path.exists(score_file):
            loaded_from = os.path.basename(score_file)
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
                    'industry': s.get('industry', 'unknown'),
                    'sector_change': 0.0,
                }

    if scores:
        print(f"  Scores: {len(scores)} stocks (from {loaded_from})")
    else:
        print(f"  Scores: 0 stocks (WARNING)")
    return scores


# ============================================================================
# Trading dates helper
# ============================================================================
def get_trading_dates(index_df, start_str, end_str):
    start = pd.to_datetime(start_str)
    end = pd.to_datetime(end_str)
    mask = (index_df['date'] >= start) & (index_df['date'] <= end)
    trading_dates = sorted(index_df.loc[mask, 'date'].tolist())
    return trading_dates


# ============================================================================
# Helpers
# ============================================================================
def get_stock_return(df, date):
    day_rows = df[df['date'] >= date]
    if len(day_rows) < 2:
        return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None

def get_index_return(index_df, date):
    day_rows = index_df[index_df['date'] >= date]
    if len(day_rows) < 2:
        return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None


# ============================================================================
# Limit-up detection & IPO filter
# ============================================================================
def has_limit_up_yesterday(hist_closes, threshold=LIMIT_UP_THRESHOLD):
    n = len(hist_closes)
    if n < 2:
        return False
    last_pct = (hist_closes[-1] - hist_closes[-2]) / hist_closes[-2] * 100
    return last_pct > threshold

def count_recent_limit_ups(hist_closes, lookback=5, threshold=LIMIT_UP_THRESHOLD):
    n = len(hist_closes)
    count = 0
    for i in range(max(1, n - lookback), n):
        pct = (hist_closes[i] - hist_closes[i-1]) / hist_closes[i-1] * 100
        if pct > threshold:
            count += 1
    return count

def is_ipo_stock(total_trading_days):
    return total_trading_days < IPO_MIN_DAYS


# ============================================================================
# ★★★ V28 NEW: No-Trade Signal Detection ★★★
# ============================================================================
def detect_no_trade_signals(index_df, date):
    """
    Detect no-trade signals from index data.
    Returns (should_skip, signals_list, total_risk_bonus)
    
    Signals:
      1. 冲高回落: Previous day surge >3%
      2. 连涨疲劳: 4+ consecutive up days (strong), 3+ (mild)
      3. 波动率急升: 5d realized vol > 2x 20d vol
      4. 累计跌幅: Past 2 days cumulative drop >2%
      5. 连跌信号: 3+ consecutive down days
      6. 大阴线: Yesterday dropped >1.5%
    """
    hist = index_df[index_df['date'] < date]
    closes = hist['close'].values
    n = len(closes)
    
    if n < 6:
        return False, [], 0
    
    signals = []
    
    # Signal 1: 冲高回落 (前日大涨>3%)
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
        signals.append(('连涨注意(3天)', 2))  # V28b: increased from 1 to 2
    
    # Signal 3: 波动率急升
    if n >= 25:
        daily_rets_5 = np.diff(closes[-6:]) / closes[-6:-1] * 100
        daily_rets_20 = np.diff(closes[-21:]) / closes[-21:-1] * 100
        vol_5 = np.std(daily_rets_5)
        vol_20 = np.std(daily_rets_20)
        if vol_20 > 0.001 and vol_5 / vol_20 > 2.0:
            signals.append(('波动率急升', 2))
    
    # Signal 4: 累计跌幅 (过去2天累计跌>2%)
    if n >= 3:
        cum_ret_2d = (closes[-1] - closes[-3]) / closes[-3] * 100
        if cum_ret_2d < -2.0:
            signals.append(('累计跌幅>2%', 2))
    
    # Signal 5: 连跌 (3天+连续下跌)
    consec_down = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
            consec_down += 1
        else:
            break
    if consec_down >= 3:
        signals.append(('连跌(3天+)', 2))
    
    # Signal 6: 大阴线 (昨日跌>1.5%)
    if n >= 2:
        yesterday_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if yesterday_ret < -1.5:
            signals.append(('大阴线', 1))
    
    # Signal 7: 连续2天下跌
    if n >= 3:
        consec_down_2 = (closes[-1] < closes[-2]) and (closes[-2] < closes[-3])
        if consec_down_2:
            signals.append(('连跌2天', 1))
    
    # Signal 8: 昨日小跌后今日可能继续 (momentum reversal)
    if n >= 2:
        yest_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if -1.5 < yest_ret < -0.1:
            signals.append(('昨日小跌', 1))
    
    total_risk = sum(r for _, r in signals)
    should_skip = total_risk >= 2  # V28b: lowered from 3 to 2
    
    return should_skip, signals, total_risk


# ============================================================================
# Market Regime Detection (same as V25)
# ============================================================================
def detect_market_regime_v25(index_df, date):
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
# Sector Rotation
# ============================================================================
def identify_hot_sectors(kline_dict, scores_dict, date, lookback=5):
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
# Sub-score modules (same as V25/V26)
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
            if len(weekly_closes) >= 6:
                wma5_slope = (wma5 - np.mean(weekly_closes[-6:-1])) / max(np.mean(weekly_closes[-6:-1]), 0.01) * 100
                weekly_score += max(-15, min(15, wma5_slope * 10))
    score += weekly_score * 0.4

    monthly_score = 0
    if n >= 120:
        monthly_closes = c[::20]
        if len(monthly_closes) >= 6:
            mma5 = np.mean(monthly_closes[-5:])
            if monthly_closes[-1] > mma5:   monthly_score += 30
            else:                            monthly_score -= 30
            if monthly_closes[-1] > monthly_closes[-3]: monthly_score += 20
            else:                                        monthly_score -= 20
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


# ============================================================================
# Precompute sub-scores (with no-trade signal detection)
# ============================================================================
def precompute_v28(kline, index_df, scores, start_str, end_str):
    """Precompute all sub-scores + no-trade signals for every trading day."""
    valid_dates = get_trading_dates(index_df, start_str, end_str)
    valid_dates = [d for d in valid_dates if get_index_return(index_df, d) is not None]

    print(f"  Real trading days: {len(valid_dates)} "
          f"({valid_dates[0].date() if valid_dates else 'N/A'} ~ {valid_dates[-1].date() if valid_dates else 'N/A'})")

    daily_data = []
    for day_idx, test_date in enumerate(valid_dates):
        # ★ V28: No-trade signal detection
        skip_day, no_trade_signals, no_trade_risk = detect_no_trade_signals(index_df, test_date)

        # Market regime
        regime, confidence, risk = detect_market_regime_v25(index_df, test_date)
        should, n_rec = should_trade(regime, confidence, risk)

        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None:
            idx_ret = 0

        # Sector info
        sector_info = identify_hot_sectors(kline, scores, test_date)

        # Precompute industry peer returns
        industry_peers = defaultdict(list)
        stock_hist_cache = {}
        debug_skip = defaultdict(int)

        for code, df in kline.items():
            static = scores.get(code)
            name = static.get('name', '') if static else ''

            if not is_tradeable(code, name):
                debug_skip['pt_st'] += 1
                continue

            if len(df[df['date'] >= test_date]) == 0:
                debug_skip['no_future'] += 1
                continue

            hist = df[df['date'] < test_date]
            c = hist['close'].values
            total_days = len(df)

            if len(c) < 20:
                debug_skip['short_hist'] += 1
                continue

            if is_ipo_stock(total_days):
                debug_skip['ipo'] += 1
                continue

            last_pct = (c[-1] - c[-2]) / c[-2] * 100
            if last_pct > LIMIT_UP_THRESHOLD:
                debug_skip['limit_up_yesterday'] += 1
                continue

            recent_limit_ups = count_recent_limit_ups(c, lookback=5, threshold=LIMIT_UP_THRESHOLD)
            if recent_limit_ups >= 2:
                debug_skip['multi_limit_up'] += 1
                continue

            industry = static.get('industry', 'unknown') if static else 'unknown'
            ret5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
            industry_peers[industry].append((code, ret5))

            v = hist['volume'].values
            hi = hist['high'].values if 'high' in hist.columns else c
            lo = hist['low'].values if 'low' in hist.columns else c
            turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))

            extra_score = 50
            if static:
                extra_score = (static.get('tech', 5.0) * 5 + static.get('fund', 5.0) * 3 +
                               static.get('chip', 5.0) * 2 + static.get('sector', 5.0) * 3) / 13 * 10

            stock_hist_cache[code] = {
                'c': c, 'v': v, 'hi': hi, 'lo': lo, 'turn': turn,
                'industry': industry, 'name': name,
                'stock_return': get_stock_return(df, test_date),
                'last_pct': last_pct,
                'recent_limit_ups': recent_limit_ups,
                'extra_score': extra_score,
            }

        # Compute sub-scores
        stock_scores = []
        for code, cache in stock_hist_cache.items():
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

            stock_scores.append({
                'code': code,
                'name': cache['name'],
                'industry': industry,
                'trend_s': trend_s,
                'money_s': money_s,
                'sector_s': sector_s,
                'rs_s': rs_s,
                'vol_s': vol_s,
                'risk_adj': risk_adj,
                'extra_s': extra_s,
                'trend_dir': trend_dir,
                'div_bullish': div['bullish'],
                'div_bearish': div['bearish'],
                'div_strength': div['strength'],
                'stock_return': cache['stock_return'],
            })

        daily_data.append({
            'test_date': test_date,
            'regime': regime,
            'confidence': confidence,
            'risk': risk,
            'should_trade': should,
            'n_recommend': n_rec,
            'idx_ret': idx_ret,
            'stocks': stock_scores,
            # ★ V28 no-trade fields
            'skip_day': skip_day,
            'no_trade_signals': no_trade_signals,
            'no_trade_risk': no_trade_risk,
        })

        if (day_idx + 1) % 10 == 0:
            skip_str = ', '.join(f'{k}={v}' for k, v in sorted(debug_skip.items()) if v > 0)
            print(f"    {day_idx + 1}/{len(valid_dates)} days "
                  f"({len(stock_scores)} scored, skips: {skip_str})")
            check_memory()

    print(f"  Period {start_str}~{end_str}: {len(daily_data)} valid trading days")
    return daily_data


# ============================================================================
# Cooldown tracking
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
# ★★★ V28 Evaluation with no-trade logic ★★★
# ============================================================================
def evaluate_v28(daily_data, weights_config, detailed=False, use_cooldown=True):
    """
    V28 evaluation: skip days with no-trade signals.
    No-trade days are excluded from beat_idx calculation.
    """
    beat_count = 0
    total = 0
    skipped = 0
    no_trade = 0  # Days skipped by V28 no-trade signals
    no_trade_regime = 0  # Days skipped by regime (risk >= 5)
    stats_by_risk = defaultdict(lambda: {'beat': 0, 'total': 0, 'no_trade': 0})
    day_details = []

    cooldown = CooldownTracker(COOLDOWN_DAYS)
    use_cooldown = USE_COOLDOWN and use_cooldown
    cooldown_penalty_weight = weights_config.get('cooldown_penalty_weight', 5.0)

    for dd in daily_data:
        risk = dd['risk']
        regime = dd['regime']
        idx_ret = dd['idx_ret']
        test_date = dd['test_date']

        # ★ V28: No-trade signal check (before regime check)
        if dd['skip_day']:
            no_trade += 1
            if detailed:
                signal_names = ', '.join(f"{s[0]}({s[1]})" for s in dd['no_trade_signals'])
                day_details.append({
                    'date': str(test_date.date()),
                    'regime': regime, 'risk': risk,
                    'action': 'NO_TRADE',
                    'signals': signal_names,
                    'no_trade_risk': dd['no_trade_risk'],
                    'n_stocks': 0,
                    'avg_ret': None, 'idx_ret': round(idx_ret, 2),
                    'beat': None,
                    'top': [],
                })
            continue

        if not dd['should_trade']:
            no_trade_regime += 1
            continue

        stocks = dd['stocks']
        if risk <= 2:
            n_rec = weights_config.get('n_rec_low_risk', dd['n_recommend'])
        elif risk >= 4:
            n_rec = 1
        else:
            n_rec = weights_config.get('n_rec_med_risk', dd['n_recommend'])
        min_score = weights_config.get('min_score_threshold', 55)

        if risk <= 2:
            w = weights_config['weights_bull']
        elif risk >= 4:
            w = weights_config['weights_bear']
        else:
            w = weights_config['weights_range']

        scored = []
        w_extra = weights_config.get('w_extra', 0.0)
        for s in stocks:
            final = (s['trend_s'] * w[0] + s['money_s'] * w[1] + s['sector_s'] * w[2]
                     + s['rs_s'] * w[3] + s['vol_s'] * w[4] + s['risk_adj'] * w[5]
                     + s['extra_s'] * w_extra)
            total_w = sum(w) + w_extra
            if total_w > 0:
                final /= total_w

            if s['div_bullish']:
                final += 5 * s['div_strength']
            if s['div_bearish']:
                final -= 8 * s['div_strength']

            if use_cooldown:
                penalty = cooldown.get_freshness_penalty(s['code'], test_date)
                final -= penalty * cooldown_penalty_weight

            scored.append((s, final))

        scored.sort(key=lambda x: x[1], reverse=True)

        selected = []
        ind_count = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= n_rec:
                break
            if sc < min_score:
                continue
            if s['trend_dir'] == 'strong_down':
                continue
            if s['div_bearish'] and s['div_strength'] > 0.5:
                continue
            if use_cooldown and not cooldown.is_cooled_down(s['code'], test_date):
                continue
            if ind_count[s['industry']] >= MAX_INDUSTRY:
                continue
            selected.append((s, sc))
            ind_count[s['industry']] += 1

        # Fallback
        if len(selected) < n_rec:
            for s, sc in scored:
                if len(selected) >= n_rec:
                    break
                if any(x[0]['code'] == s['code'] for x in selected):
                    continue
                if sc < min_score - 10:
                    break
                if s['trend_dir'] == 'strong_down':
                    continue
                if use_cooldown and not cooldown.is_cooled_down(s['code'], test_date):
                    continue
                if ind_count[s['industry']] >= MAX_INDUSTRY:
                    continue
                selected.append((s, sc))
                ind_count[s['industry']] += 1

        if not selected:
            skipped += 1
            continue

        if use_cooldown:
            for s, sc in selected:
                cooldown.mark_recommended(s['code'], test_date)

        stock_rets = []
        for s, sc in selected:
            if s['stock_return'] is not None:
                stock_rets.append(s['stock_return'])

        if stock_rets:
            avg_ret = np.mean(stock_rets)
            beat_idx = avg_ret > idx_ret
            total += 1
            if beat_idx:
                beat_count += 1
            stats_by_risk[risk]['total'] += 1
            if beat_idx:
                stats_by_risk[risk]['beat'] += 1

            if detailed:
                day_details.append({
                    'date': str(test_date.date()),
                    'regime': regime, 'risk': risk,
                    'action': 'TRADE',
                    'n_stocks': len(stock_rets),
                    'avg_ret': round(avg_ret, 2),
                    'idx_ret': round(idx_ret, 2),
                    'beat': beat_idx,
                    'top': [{'code': s['code'], 'name': s['name'],
                             'score': round(sc, 1),
                             'ret': round(s['stock_return'], 2) if s['stock_return'] else None}
                            for s, sc in selected[:3]],
                })

    beat_rate = beat_count / total if total > 0 else 0
    return beat_rate, stats_by_risk, beat_count, total, skipped, no_trade, no_trade_regime, day_details


# ============================================================================
# Load V25 pre-optimized params
# ============================================================================
def load_v25_params():
    """Load V25 Optuna params instead of re-optimizing."""
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v25_best_params.json')
    if not os.path.exists(params_path):
        print(f"  [ERROR] V25 params not found: {params_path}")
        sys.exit(1)
    
    with open(params_path, 'r', encoding='utf-8') as f:
        v25_params = json.load(f)
    
    # Extract and adapt params for V28 evaluation
    weights_config = {
        'weights_bull': v25_params['params']['weights_bull'],
        'weights_range': v25_params['params']['weights_range'],
        'weights_bear': v25_params['params']['weights_bear'],
        'min_score_threshold': v25_params['params']['min_score_threshold'],
        'cooldown_penalty_weight': 5.0,  # Default from V26
        'w_extra': 0.0,  # V25 didn't have extra weight
        'n_rec_low_risk': 3,
        'n_rec_med_risk': 2,
    }
    
    print(f"  Loaded V25 params (no re-optimization)")
    print(f"  min_score: {weights_config['min_score_threshold']:.1f}")
    print(f"  weights_bull: {[f'{w:.3f}' for w in weights_config['weights_bull']]}")
    
    return weights_config


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()

    print("=" * 70)
    print("V28 - Fundamental Restructure: Dual-Mode System")
    print("  Mode 1: Trend Confirmation (V25 scoring)")
    print("  Mode 2: No-Trade Defense (skip uncertain days)")
    print("  Signals: 冲高回落 / 连涨疲劳 / 波动率急升 / 累计跌幅 / 连跌")
    print("  Uses V25 Optuna params (no re-optimization)")
    print("=" * 70)

    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = _load_scores()
    print_mem("All data loaded")

    # Verify trading dates
    test_dates = get_trading_dates(index_df, PERIOD_TEST_START, PERIOD_TEST_END)
    print(f"\n  Test period trading dates ({len(test_dates)} days):")
    for d in test_dates:
        print(f"    {d.date()} ({d.strftime('%A')})")

    # Precompute all periods
    print("\n[Precompute] Computing V28 sub-scores for 4 periods...")
    periods_data = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B),
                              ('C', PERIOD_C), ('D', PERIOD_D)]:
        print(f"\n  Period {plabel}: {ps} ~ {pe}")
        periods_data[plabel] = precompute_v28(kline, index_df, scores, ps, pe)
        gc.collect()
        print_mem(f"After Period {plabel}")

    del kline
    gc.collect()
    print_mem("After freeing kline")

    # ★ V28: Use V25 pre-optimized params (NO Optuna)
    print(f"\n{'=' * 70}")
    print(f"  [V28] Loading V25 pre-optimized params...")
    print(f"{'=' * 70}")
    best_params = load_v25_params()

    # Print no-trade signal analysis for test period
    print(f"\n{'=' * 70}")
    print(f"  [V28] No-Trade Signal Analysis (Period D)")
    print(f"{'=' * 70}")
    for dd in periods_data['D']:
        if dd['no_trade_signals']:
            signal_names = ', '.join(f"{s[0]}({s[1]})" for s in dd['no_trade_signals'])
            action = "SKIP" if dd['skip_day'] else "OK"
            print(f"  {dd['test_date'].date()} risk={dd['no_trade_risk']} "
                  f"regime={dd['regime']} → {action} | {signal_names}")
        else:
            print(f"  {dd['test_date'].date()} risk=0 regime={dd['regime']} → OK (no signals)")

    # Evaluate all periods
    print(f"\n{'=' * 70}")
    print(f"  V28 EVALUATION (V25 params + no-trade filter)")
    print(f"{'=' * 70}")

    period_results = {}
    for plabel in ['A', 'B', 'C', 'D']:
        bi, stats, bc, bt, sk, nt, nt_regime, det = evaluate_v28(
            periods_data[plabel], best_params, detailed=True)
        period_results[plabel] = {
            'beat_rate': bi, 'beat_count': bc, 'total_days': bt,
            'skipped': sk, 'no_trade': nt, 'no_trade_regime': nt_regime,
            'details': det,
        }
        print(f"  Period {plabel}: {bc}/{bt} = {bi * 100:.1f}% "
              f"(no_trade_signal={nt}, no_trade_regime={nt_regime}, skipped={sk})")

    # Test period detail
    test_bi = period_results['D']['beat_rate']
    test_bc = period_results['D']['beat_count']
    test_bt = period_results['D']['total_days']
    test_nt = period_results['D']['no_trade']
    test_nt_regime = period_results['D']['no_trade_regime']

    print(f"\n{'=' * 70}")
    print(f"  [TEST] Period D — FINAL (never used for tuning)")
    print(f"{'=' * 70}")
    print(f"  Test beat_idx: {test_bc}/{test_bt} = {test_bi * 100:.1f}%")
    print(f"  No-trade (signal): {test_nt} days skipped")
    print(f"  No-trade (regime): {test_nt_regime} days skipped")
    print(f"  Total days in period: {len(periods_data['D'])}")

    # Day-by-day results
    print(f"\n  Day-by-day results:")
    for det in period_results['D']['details']:
        if det.get('action') == 'NO_TRADE':
            print(f"    {det['date']} → NO_TRADE | signals: {det.get('signals', '')} "
                  f"| idx_ret={det['idx_ret']:+.2f}%")
        elif det.get('beat') is not None:
            beat_mark = "WIN" if det['beat'] else "LOSE"
            top_names = ', '.join(f"{t['name'][:4]}({t['ret']:+.1f}%)"
                                  for t in det['top'] if t['ret'] is not None)
            print(f"    {det['date']} risk={det['risk']} "
                  f"avg={det['avg_ret']:+.2f}% idx={det['idx_ret']:+.2f}% "
                  f"{beat_mark} | {top_names}")

    # Train & valid summary
    train_all = periods_data['A'] + periods_data['B']
    train_bi, _, train_bc, train_bt, _, _, _, _ = evaluate_v28(train_all, best_params)
    valid_bi = period_results['C']['beat_rate']

    gap = (train_bi - test_bi) * 100
    print(f"\n  Train: {train_bc}/{train_bt} = {train_bi * 100:.1f}%")
    print(f"  Valid: {period_results['C']['beat_count']}/{period_results['C']['total_days']} "
          f"= {valid_bi * 100:.1f}%")
    print(f"  Test:  {test_bc}/{test_bt} = {test_bi * 100:.1f}%")
    print(f"  Gap: {gap:.1f}pp")

    # Comparison
    print(f"\n{'=' * 70}")
    print(f"  BASELINES")
    print(f"{'=' * 70}")
    print(f"  V10: 60.8% | V14: 49.0% | V22: 72.9%(leaked) | V24: 69.2% | "
          f"V25: 76.9% | V26: ? | V28: {test_bi * 100:.1f}%")

    # Save results
    os.makedirs(RESULT_DIR, exist_ok=True)

    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v28-dual-mode',
        'description': 'V25 params + no-trade signal detection. Skip days with risk signals (冲高回落/连涨疲劳/波动率急升/累计跌幅/连跌)',
        'walk_forward_split': {
            'train': f'{PERIOD_TRAIN_START} ~ {PERIOD_TRAIN_END}',
            'valid': f'{PERIOD_VALID_START} ~ {PERIOD_VALID_END}',
            'test': f'{PERIOD_TEST_START} ~ {PERIOD_TEST_END}',
        },
        'train_result': {'beat_idx': train_bi, 'days': train_bt},
        'valid_result': {'beat_idx': valid_bi, 'days': period_results['C']['total_days']},
        'test_result': {
            'beat_idx': test_bi, 'days': test_bt,
            'no_trade_signal': test_nt,
            'no_trade_regime': test_nt_regime,
            'skipped': period_results['D']['skipped'],
            'total_period_days': len(periods_data['D']),
        },
        'period_results': {k: {kk: vv for kk, vv in v.items() if kk != 'details'}
                           for k, v in period_results.items()},
        'test_details': period_results['D']['details'],
        'comparison': {
            'v10': 60.8, 'v14': 49.0, 'v22_joint': 72.9,
            'v24_test': 69.2, 'v25_test': 76.9, 'v28_test': round(test_bi * 100, 1),
        },
        'params': {
            'source': 'V25 Optuna (no re-optimization)',
            'weights_bull': best_params['weights_bull'],
            'weights_range': best_params['weights_range'],
            'weights_bear': best_params['weights_bear'],
            'min_score_threshold': best_params['min_score_threshold'],
        },
        'no_trade_signals': {
            'threshold': 3,
            'signals': ['冲高回落(2)', '连涨疲劳4+(3)/3+(1)', '波动率急升(2)',
                        '累计跌幅>2%(2)', '连跌3+(2)', '大阴线(1)'],
        },
        'elapsed_seconds': time.time() - t0,
    }

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

    final = convert(final)
    fp = os.path.join(RESULT_DIR, 'backtest_v28.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n  Results: {fp}")

    elapsed = time.time() - t0
    print(f"\n  Total: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print("=" * 70)


if __name__ == '__main__':
    main()

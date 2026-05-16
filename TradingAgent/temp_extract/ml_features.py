#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Feature Engineering for TradingAgent
========================================
Build training dataset from kline + index + new_factors for ML model.

V10 manual scoring beat_idx=58.8% (4.5 months).
Goal: Replace manual scoring with ML model.

Dataset splits:
  Train:      2025-11-01 ~ 2026-02-28
  Validation: 2026-03-01 ~ 2026-03-15
  Test:       2026-03-16 ~ 2026-04-24

Output: ml_train_dataset.npz
"""

import json, os, sys, time, gc, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = r'D:\GitHub\TradingAgents\TradingAgent'
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
OUTPUT_FILE = os.path.join(DATA_DIR, 'ml_train_dataset.npz')

# ============================================================================
# Date ranges
# ============================================================================
TRAIN_START = '2025-11-01'
TRAIN_END = '2026-02-28'
VAL_START = '2026-03-01'
VAL_END = '2026-03-15'
TEST_START = '2026-03-16'
TEST_END = '2026-04-24'

FEATURE_MIN_DAYS = 30

# Industry classification keywords (from V10)
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]


def is_defensive_industry(industry):
    return 1 if any(kw in industry for kw in DEFENSIVE_KEYWORDS) else 0


def is_high_beta_industry(industry):
    return 1 if any(kw in industry for kw in HIGH_BETA_KEYWORDS) else 0


# ============================================================================
# Memory utilities
# ============================================================================
def print_mem(label=""):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label:
            print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError:
        pass


# ============================================================================
# Data Loading
# ============================================================================
def normalize_code(code):
    """Remove sh/sz prefix"""
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code


def load_kline_data():
    """Load kline data for all stocks"""
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    print(f"  Loading kline: {os.path.basename(kline_file)} ({os.path.getsize(kline_file)/1024/1024:.1f}MB)")

    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    kline = {}
    skipped = 0

    for code, records in raw.items():
        clean = normalize_code(code)
        if len(records) < FEATURE_MIN_DAYS:
            skipped += 1
            continue

        # Parse into arrays for fast access
        dates = []
        closes = np.empty(len(records), dtype=np.float32)
        opens = np.empty(len(records), dtype=np.float32)
        highs = np.empty(len(records), dtype=np.float32)
        lows = np.empty(len(records), dtype=np.float32)
        volumes = np.empty(len(records), dtype=np.float32)

        for i, r in enumerate(records):
            dates.append(r['date'])
            closes[i] = r['close']
            opens[i] = r['open']
            highs[i] = r['high']
            lows[i] = r['low']
            volumes[i] = r['volume']

        kline[clean] = {
            'dates': dates,  # list of str
            'close': closes,
            'open': opens,
            'high': highs,
            'low': lows,
            'volume': volumes,
        }

    del raw
    gc.collect()

    print(f"  Kline: {len(kline)} stocks ({skipped} skipped)")
    print(f"  Date range: {next(iter(kline.values()))['dates'][0]} ~ {next(iter(kline.values()))['dates'][-1]}")
    return kline


def load_index_data():
    """Load index (HS300) data"""
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')

    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)

    records = []
    if 'date' in raw_idx and isinstance(raw_idx['date'], dict):
        n = len(raw_idx['date'])
        for i in range(n):
            try:
                ds = str(raw_idx['date'].get(str(i), ''))
                cl = float(raw_idx['close'].get(str(i), 0))
                if ds and cl > 0:
                    records.append((ds, cl))
            except:
                continue

    del raw_idx
    gc.collect()

    # Build lookup: date -> close
    idx_close = {r[0]: np.float32(r[1]) for r in records}
    # Build lookup: date -> next day return
    idx_return = {}
    sorted_dates = sorted([r[0] for r in records])
    for i in range(len(sorted_dates) - 1):
        d = sorted_dates[i]
        d_next = sorted_dates[i + 1]
        idx_return[d] = np.float32((idx_close[d_next] - idx_close[d]) / idx_close[d] * 100)

    print(f"  Index: {len(records)} days, {sorted_dates[0]} ~ {sorted_dates[-1]}")
    return idx_close, idx_return


def load_scores():
    """Load stock scores for industry info"""
    score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    scores = {}

    if os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            if not isinstance(s, dict):
                continue
            clean = normalize_code(code)
            scores[clean] = {
                'industry': s.get('industry', 'unknown'),
                'name': s.get('name', ''),
                'hot_sector_detail': s.get('hot_sector_detail', ''),
            }

    print(f"  Scores: {len(scores)} stocks")
    return scores


def load_new_factors():
    """Load new factors cache"""
    factors_file = os.path.join(DATA_DIR, 'new_factors_cache.json')
    with open(factors_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {
        'north_flow': data.get('north_flow', {}),
        'lhb': data.get('lhb', {}),
        'limit_stats': data.get('limit_stats', {}),
        'margin_daily': data.get('margin_daily', {}),
    }

    # Pre-process margin_daily: aggregate total margin balance per date
    margin_totals = {}
    for date, etf_data in result['margin_daily'].items():
        total_balance = 0.0
        for etf_code, info in etf_data.items():
            total_balance += info.get('margin_balance', 0)
        margin_totals[date] = total_balance
    result['margin_totals'] = margin_totals

    # Build margin change (day-over-day)
    margin_dates = sorted(margin_totals.keys())
    margin_change = {}
    for i in range(1, len(margin_dates)):
        d = margin_dates[i]
        d_prev = margin_dates[i - 1]
        margin_change[d] = margin_totals[d] - margin_totals[d_prev]
    result['margin_change'] = margin_change

    # Pre-process LHB: per-stock net buy per date
    lhb_stock = {}  # date -> {code -> net_buy}
    for date, entries in result['lhb'].items():
        stock_map = {}
        for entry in entries:
            code = entry.get('code', '')
            if code:
                stock_map[code] = entry.get('net_buy', 0)
        lhb_stock[date] = stock_map
    result['lhb_stock'] = lhb_stock

    # Pre-process limit stats: extract counts per date
    limit_counts = {}
    for date, info in result['limit_stats'].items():
        # date field in limit_stats might be "2026-04-10 00:00:00"
        d = date[:10] if len(date) > 10 else date
        limit_counts[d] = {
            'limit_up': info.get('zt_count', 0),
            'limit_down': info.get('dt_count', 0),
        }
    result['limit_counts'] = limit_counts

    # Pre-compute north_flow market net inflow per date
    nf_market = {}
    for date, info in result['north_flow'].items():
        nf_market[date] = info.get('main_net_inflow', 0)
    result['nf_market'] = nf_market

    print(f"  New factors loaded:")
    print(f"    North flow: {len(result['north_flow'])} dates")
    print(f"    LHB: {len(result['lhb'])} dates")
    print(f"    Limit stats: {len(result['limit_stats'])} dates")
    print(f"    Margin: {len(result['margin_daily'])} dates")

    del data
    gc.collect()
    return result


# ============================================================================
# Industry Label Encoding
# ============================================================================
def build_industry_encoder(scores, kline_codes):
    """Build industry label encoder from scores data"""
    # Collect all industries
    industry_set = set()
    for code in kline_codes:
        s = scores.get(code)
        if s:
            industry_set.add(s.get('industry', 'unknown'))
    industry_set.add('unknown')

    sorted_industries = sorted(industry_set)
    encoder = {ind: i for i, ind in enumerate(sorted_industries)}
    return encoder


# ============================================================================
# Feature Calculation (adapted from V10 calc_features)
# ============================================================================
def calc_features_fast(close, open_, high, low, volume, n):
    """
    Calculate all technical features from numpy arrays.
    close/open/high/low/volume are arrays, n is the length to use.
    Returns dict of features or None if not enough data.
    """
    if n < 20:
        return None

    c = close[:n]
    o = open_[:n]
    h = high[:n]
    lo = low[:n]
    v = volume[:n]

    f = {}

    # Returns
    f['r1'] = float((c[-1] - c[-2]) / c[-2] * 100) if n >= 2 else 0.0
    f['r3'] = float((c[-1] - c[-4]) / c[-4] * 100) if n >= 4 else 0.0
    f['r5'] = float((c[-1] - c[-6]) / c[-6] * 100) if n >= 6 else 0.0
    f['r10'] = float((c[-1] - c[-11]) / c[-11] * 100) if n >= 11 else 0.0
    f['r20'] = float((c[-1] - c[-21]) / c[-21] * 100) if n >= 21 else 0.0

    # Moving averages
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10

    f['close_ma5'] = float(c[-1] / ma5 - 1)
    f['close_ma10'] = float(c[-1] / ma10 - 1)
    f['close_ma20'] = float(c[-1] / ma20 - 1)
    f['ma5_slope'] = float((ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1])) if n >= 6 else 0.0
    f['ma10_slope'] = float((ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1])) if n >= 11 else 0.0
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)

    # RSI 14
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i - 1]) / c[i - 1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = float(100 - 100 / (1 + ag / al))

    # MACD (simplified)
    if n >= 26:
        ema12 = ema26 = float(c[-1])
        for i in range(-26, 0):
            ema12 = float(c[i]) * (2 / 14) + ema12 * (1 - 2 / 14)
            ema26 = float(c[i]) * (2 / 27) + ema26 * (1 - 2 / 27)
        f['macd'] = float(ema12 - ema26)
    else:
        f['macd'] = 0.0

    # Volatility
    if n >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        f['vol5'] = float(np.std(rets) * 100)
    else:
        f['vol5'] = 0.0
    if n >= 11:
        rets10 = np.diff(c[-11:]) / c[-11:-1]
        f['vol10'] = float(np.std(rets10) * 100)
    else:
        f['vol10'] = f.get('vol5', 0.0)

    # Volume ratio
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = float(np.mean(v[-5:]) / np.mean(v[-10:]))
    else:
        f['vol_ratio'] = 1.0

    # Volume shrinkage
    if n >= 10:
        v5 = np.mean(v[-5:])
        v5_prev = np.mean(v[-10:-5])
        f['vol_shrink'] = float(v5 / max(v5_prev, 1))
    else:
        f['vol_shrink'] = 1.0

    # Turnover features - not available in kline data, use volume-based proxies
    # turn_ratio -> vol_ratio (already computed)
    # turn_avg -> avg volume ratio
    f['turn_ratio'] = f['vol_ratio']
    f['turn_avg'] = float(np.mean(v[-5:]) / max(np.mean(v), 1))
    f['turn_spike'] = float(v[-1] / max(np.mean(v[-5:]), 1)) if n >= 5 else 1.0

    # Price position
    w20 = min(20, n)
    f['price_pos'] = float((c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100)

    # ATR percentage
    if n >= 6:
        trs = []
        for i in range(-min(14, n - 1), 0):
            tr = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
            trs.append(tr)
        f['atr_pct'] = float(np.mean(trs) / c[-1] * 100)
    else:
        f['atr_pct'] = 0.0

    # Streak (consecutive up/down days)
    streak = 0
    for i in range(n - 1, 0, -1):
        if c[i] > c[i - 1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i - 1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak

    # Consistency (positive days in last 5)
    f['consistency'] = 0
    if n >= 5:
        for i in range(-4, 0):
            if c[i + 1] > c[i]:
                f['consistency'] += 1

    # Max drawdown in last 10 days
    if n >= 10:
        peak = float(c[-10])
        max_dd = 0.0
        for i in range(-9, 1):
            if c[i] > peak:
                peak = float(c[i])
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        f['max_dd_10d'] = float(max_dd)
    else:
        f['max_dd_10d'] = 0.0

    # Distance to support (min of last 20 days)
    f['dist_support'] = float((c[-1] - np.min(c[-w20:])) / c[-1] * 100)

    # Beta and relative strength (placeholder, will be computed with index data)
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0

    return f


# ============================================================================
# Market State Detection (from V10)
# ============================================================================
def detect_market_state(idx_close_sorted, date_idx):
    """
    Detect market state from index data.
    idx_close_sorted: list of (date_str, close_float) sorted by date
    date_idx: index into this list for the target date
    Returns: (risk_level, regime_onehot, momentum, vol_state_onehot)
    """
    if date_idx < 20:
        return 3, [0, 0, 1], 0.0, [0, 1, 0]

    closes = np.array([c for _, c in idx_close_sorted[:date_idx + 1]], dtype=np.float32)
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]

    if current > ma20 * 1.02 and ma5 > ma20:
        regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20:
        regime = 'bear'
    else:
        regime = 'range'

    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = float(ret5 * 0.6 + ret20 * 0.4)

    if n >= 10:
        idx_rets = np.diff(closes[-10:]) / closes[-10:-1] * 100
        idx_vol = np.std(idx_rets)
        if idx_vol > 1.5:
            vol_state = 'high'
        elif idx_vol > 0.8:
            vol_state = 'normal'
        else:
            vol_state = 'low'
    else:
        vol_state = 'normal'

    risk = 3
    consec_decline = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
            consec_decline += 1
        else:
            break

    if consec_decline >= 4:
        risk = 5
    elif consec_decline >= 3:
        risk = 4
    elif regime == 'bear' and vol_state == 'high':
        risk = 5
    elif regime == 'bear':
        risk = 4
    elif regime == 'bull' and vol_state == 'high':
        risk = 3
    elif regime == 'bull':
        risk = 2
    elif vol_state == 'high':
        risk = 4

    if n >= 2:
        last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if last_ret < -2:
            risk = min(risk + 1, 5)
        elif last_ret > 2:
            risk = max(risk - 1, 1)

    # One-hot encode
    regime_oh = [1, 0, 0] if regime == 'bull' else ([0, 1, 0] if regime == 'bear' else [0, 0, 1])
    vol_oh = [1, 0, 0] if vol_state == 'high' else ([0, 1, 0] if vol_state == 'normal' else [0, 0, 1])

    return risk, regime_oh, momentum, vol_oh


# ============================================================================
# Beta and Relative Strength Calculation
# ============================================================================
def calc_beta_relstrength(stock_close, idx_closes_array, n, n_beta=20, n_rel=5):
    """Calculate beta_20d and relative strength vs index"""
    beta = 1.0
    rs5 = 0.0
    rs3 = 0.0

    if n >= n_beta + 1:
        # Beta: correlation of stock returns with index returns
        s_rets = np.diff(stock_close[-(n_beta + 1):]) / stock_close[-(n_beta + 1):-1]
        i_rets = np.diff(idx_closes_array[-(n_beta + 1):]) / idx_closes_array[-(n_beta + 1):-1]
        if len(s_rets) == len(i_rets) and np.std(i_rets) > 0:
            cov = np.cov(s_rets, i_rets)
            if cov[0, 1] != 0 and cov[1, 1] > 0:
                beta = float(cov[0, 1] / cov[1, 1])

    if n >= n_rel + 1:
        s_ret5 = (stock_close[-1] - stock_close[-(n_rel + 1)]) / stock_close[-(n_rel + 1)]
        i_ret5 = (idx_closes_array[-1] - idx_closes_array[-(n_rel + 1)]) / idx_closes_array[-(n_rel + 1)]
        rs5 = float((s_ret5 - i_ret5) * 100)

    if n >= 4:
        s_ret3 = (stock_close[-1] - stock_close[-4]) / stock_close[-4]
        i_ret3 = (idx_closes_array[-1] - idx_closes_array[-4]) / idx_closes_array[-4]
        rs3 = float((s_ret3 - i_ret3) * 100)

    return beta, rs5, rs3


# ============================================================================
# Get new factor values for a stock on a date
# ============================================================================
def get_new_factors(code, date, new_factors):
    """Get new factor values for a stock on a specific date"""
    vals = {}

    # Market net inflow (from north_flow)
    nf = new_factors['nf_market']
    vals['market_net_inflow'] = float(nf.get(date, 0))

    # Stock main net inflow - not available per stock in current data
    # Use market-level north flow main_net_inflow as proxy
    north = new_factors['north_flow']
    if date in north:
        vals['stock_main_net_inflow'] = float(north[date].get('main_net_inflow', 0))
    else:
        vals['stock_main_net_inflow'] = 0.0

    # LHB (dragon-tiger list)
    lhb_stock = new_factors['lhb_stock']
    if date in lhb_stock and code in lhb_stock[date]:
        vals['on_lhb'] = 1
        vals['lhb_net_buy'] = float(lhb_stock[date][code])
    else:
        vals['on_lhb'] = 0
        vals['lhb_net_buy'] = 0.0

    # Margin balance (use total as proxy)
    margin_totals = new_factors['margin_totals']
    vals['margin_balance'] = float(margin_totals.get(date, 0))
    margin_change = new_factors['margin_change']
    vals['margin_change'] = float(margin_change.get(date, 0))

    # Limit up/down counts
    limit_counts = new_factors['limit_counts']
    if date in limit_counts:
        vals['limit_up_count'] = limit_counts[date]['limit_up']
        vals['limit_down_count'] = limit_counts[date]['limit_down']
    else:
        vals['limit_up_count'] = 0
        vals['limit_down_count'] = 0

    return vals


# ============================================================================
# Main: Build Dataset
# ============================================================================
def build_dataset():
    print("=" * 60)
    print("ML Feature Engineering - Building Training Dataset")
    print("=" * 60)
    t0 = time.time()

    # --- Load all data ---
    print("\n[1/4] Loading data...")
    kline = load_kline_data()
    idx_close, idx_return = load_index_data()
    scores = load_scores()
    new_factors = load_new_factors()
    print_mem("After loading")

    # --- Build industry encoder ---
    industry_encoder = build_industry_encoder(scores, kline.keys())
    print(f"\n  Industry encoder: {len(industry_encoder)} categories")

    # --- Prepare index data for market state + beta ---
    idx_dates_sorted = sorted(idx_close.keys())
    idx_close_list = [(d, float(idx_close[d])) for d in idx_dates_sorted]
    idx_close_array_dict = {}  # date -> cumulative close array up to that date
    # Build a mapping for fast lookup
    idx_date_to_pos = {d: i for i, d in enumerate(idx_dates_sorted)}

    # --- Define feature names ---
    TECH_FEATURES = [
        'r1', 'r3', 'r5', 'r10', 'r20',
        'close_ma5', 'close_ma10', 'close_ma20',
        'ma5_slope', 'ma10_slope',
        'ma_bull', 'ma_align',
        'rsi', 'macd',
        'vol5', 'vol10',
        'vol_ratio', 'vol_shrink',
        'turn_ratio', 'turn_avg', 'turn_spike',
        'price_pos', 'atr_pct',
        'streak', 'consistency',
        'max_dd_10d', 'dist_support',
        'beta_20d', 'rel_strength_5d', 'rel_strength_3d',
    ]

    NEW_FACTOR_FEATURES = [
        'market_net_inflow', 'stock_main_net_inflow',
        'on_lhb', 'lhb_net_buy',
        'margin_balance', 'margin_change',
        'limit_up_count', 'limit_down_count',
    ]

    MARKET_FEATURES = [
        'risk_level',
        'regime_bull', 'regime_bear', 'regime_range',
        'momentum',
        'vol_state_high', 'vol_state_normal', 'vol_state_low',
    ]

    INDUSTRY_FEATURES = [
        'industry_encoded',
        'sector_avg_change',  # will be 0 for now (no per-sector data per day)
        'is_defensive', 'is_high_beta',
    ]

    ALL_FEATURES = TECH_FEATURES + NEW_FACTOR_FEATURES + MARKET_FEATURES + INDUSTRY_FEATURES
    N_FEATURES = len(ALL_FEATURES)
    print(f"\n  Total features: {N_FEATURES}")
    print(f"    Technical: {len(TECH_FEATURES)}")
    print(f"    New factors: {len(NEW_FACTOR_FEATURES)}")
    print(f"    Market: {len(MARKET_FEATURES)}")
    print(f"    Industry: {len(INDUSTRY_FEATURES)}")

    # --- Get all trading dates from index ---
    all_dates = idx_dates_sorted
    print(f"\n  Trading dates: {len(all_dates)}, {all_dates[0]} ~ {all_dates[-1]}")

    # --- Determine date ranges ---
    train_dates = [d for d in all_dates if TRAIN_START <= d <= TRAIN_END]
    val_dates = [d for d in all_dates if VAL_START <= d <= VAL_END]
    test_dates = [d for d in all_dates if TEST_START <= d <= TEST_END]
    target_dates = train_dates + val_dates + test_dates

    print(f"  Train dates: {len(train_dates)} ({train_dates[0]} ~ {train_dates[-1]})")
    print(f"  Val dates: {len(val_dates)} ({val_dates[0]} ~ {val_dates[-1]})")
    print(f"  Test dates: {len(test_dates)} ({test_dates[0]} ~ {test_dates[-1]})")
    print(f"  Total target dates: {len(target_dates)}")

    # --- Build dataset ---
    print(f"\n[2/4] Building feature matrix...")

    # Pre-compute industry info for all stocks
    industry_info = {}
    for code in kline.keys():
        s = scores.get(code, {})
        ind = s.get('industry', 'unknown')
        industry_info[code] = {
            'encoded': industry_encoder.get(ind, 0),
            'name': ind,
            'is_defensive': is_defensive_industry(ind),
            'is_high_beta': is_high_beta_industry(ind),
        }

    # Collect all rows
    train_rows = []
    val_rows = []
    test_rows = []

    processed = 0
    skipped_no_features = 0
    skipped_no_nextday = 0

    stock_codes = sorted(kline.keys())
    total_stocks = len(stock_codes)

    for di, date in enumerate(target_dates):
        date_idx = idx_date_to_pos.get(date)
        if date_idx is None:
            continue

        # Market state for this date
        risk_level, regime_oh, momentum, vol_oh = detect_market_state(idx_close_list, date_idx)

        # Index close array up to this date (for beta/rel strength)
        idx_closes_up_to = np.array([float(idx_close[d]) for d in idx_dates_sorted[:date_idx + 1]], dtype=np.float32)

        # Check next-day index return
        idx_next_ret = idx_return.get(date)
        if idx_next_ret is None:
            continue

        batch_rows = []

        for code in stock_codes:
            kd = kline[code]
            dates = kd['dates']

            # Find the position of this date in the stock's kline
            try:
                pos = dates.index(date)
            except ValueError:
                continue

            # Need at least 20 bars before this date for features
            if pos < 20:
                continue

            # Need next-day data for label
            if pos + 1 >= len(dates):
                skipped_no_nextday += 1
                continue

            # Calculate technical features using data up to pos (inclusive)
            features = calc_features_fast(
                kd['close'][:pos + 1],
                kd['open'][:pos + 1],
                kd['high'][:pos + 1],
                kd['low'][:pos + 1],
                kd['volume'][:pos + 1],
                pos + 1,
            )
            if features is None:
                skipped_no_features += 1
                continue

            # Compute beta and relative strength
            stock_closes = kd['close'][:pos + 1]
            n_sc = pos + 1
            n_idx = min(n_sc, len(idx_closes_up_to))
            if n_idx >= 21:
                beta, rs5, rs3 = calc_beta_relstrength(
                    stock_closes, idx_closes_up_to[-n_idx:], n_idx
                )
                features['beta_20d'] = beta
                features['rel_strength_5d'] = rs5
                features['rel_strength_3d'] = rs3

            # Next-day return for label
            next_close = float(kd['close'][pos + 1])
            curr_close = float(kd['close'][pos])
            stock_next_ret = (next_close - curr_close) / curr_close * 100

            # Labels
            y = 1 if stock_next_ret > float(idx_next_ret) else 0
            y_continuous = stock_next_ret - float(idx_next_ret)

            # Build feature vector
            row = np.zeros(N_FEATURES + 2, dtype=np.float32)  # +2 for y, y_continuous

            # A. Technical features
            for i, fname in enumerate(TECH_FEATURES):
                row[i] = features.get(fname, 0.0)

            # B. New factors
            nf = get_new_factors(code, date, new_factors)
            offset = len(TECH_FEATURES)
            for i, fname in enumerate(NEW_FACTOR_FEATURES):
                row[offset + i] = nf.get(fname, 0.0)

            # C. Market state
            offset = len(TECH_FEATURES) + len(NEW_FACTOR_FEATURES)
            row[offset + 0] = risk_level
            row[offset + 1] = regime_oh[0]  # bull
            row[offset + 2] = regime_oh[1]  # bear
            row[offset + 3] = regime_oh[2]  # range
            row[offset + 4] = momentum
            row[offset + 5] = vol_oh[0]     # high
            row[offset + 6] = vol_oh[1]     # normal
            row[offset + 7] = vol_oh[2]     # low

            # D. Industry
            offset = len(TECH_FEATURES) + len(NEW_FACTOR_FEATURES) + len(MARKET_FEATURES)
            ind_info = industry_info.get(code, industry_info.get('unknown', {}))
            row[offset + 0] = ind_info.get('encoded', 0)
            row[offset + 1] = 0.0  # sector_avg_change (not available per day)
            row[offset + 2] = ind_info.get('is_defensive', 0)
            row[offset + 3] = ind_info.get('is_high_beta', 0)

            # Labels
            row[-2] = y
            row[-1] = y_continuous

            batch_rows.append(row)

        # Assign to split
        if date in train_dates or (train_dates and date <= train_dates[-1] and date >= train_dates[0]):
            split = 'train'
        elif val_dates and val_dates[0] <= date <= val_dates[-1]:
            split = 'val'
        else:
            split = 'test'

        if split == 'train':
            train_rows.extend(batch_rows)
        elif split == 'val':
            val_rows.extend(batch_rows)
        else:
            test_rows.extend(batch_rows)

        processed += len(batch_rows)

        if (di + 1) % 5 == 0 or di == len(target_dates) - 1:
            elapsed = time.time() - t0
            pct = (di + 1) / len(target_dates) * 100
            print(f"    Date {date} [{pct:.0f}%] - {processed} rows so far "
                  f"(train:{len(train_rows)} val:{len(val_rows)} test:{len(test_rows)}) "
                  f"[{elapsed:.0f}s]")

        # Periodic GC
        if (di + 1) % 10 == 0:
            gc.collect()

    print(f"\n  Total rows generated: {processed}")
    print(f"  Skipped (no features): {skipped_no_features}")
    print(f"  Skipped (no next day): {skipped_no_nextday}")
    print_mem("After building")

    # --- Convert to arrays ---
    print(f"\n[3/4] Converting to numpy arrays...")
    gc.collect()

    def rows_to_arrays(rows, n_feat):
        if not rows:
            return np.empty((0, n_feat), dtype=np.float32), np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32)
        data = np.array(rows, dtype=np.float32)
        X = data[:, :n_feat]
        y = data[:, -2]
        y_cont = data[:, -1]
        return X, y, y_cont

    X_train, y_train, y_train_cont = rows_to_arrays(train_rows, N_FEATURES)
    X_val, y_val, y_val_cont = rows_to_arrays(val_rows, N_FEATURES)
    X_test, y_test, y_test_cont = rows_to_arrays(test_rows, N_FEATURES)

    del train_rows, val_rows, test_rows
    gc.collect()

    # --- Statistics ---
    print(f"\n  Train: {X_train.shape[0]} samples, {X_train.shape[1]} features")
    if len(y_train) > 0:
        print(f"    Positive ratio: {np.mean(y_train):.4f}")
    print(f"  Val:   {X_val.shape[0]} samples")
    if len(y_val) > 0:
        print(f"    Positive ratio: {np.mean(y_val):.4f}")
    print(f"  Test:  {X_test.shape[0]} samples")
    if len(y_test) > 0:
        print(f"    Positive ratio: {np.mean(y_test):.4f}")

    # --- Save ---
    print(f"\n[4/4] Saving to {OUTPUT_FILE}...")
    np.savez_compressed(
        OUTPUT_FILE,
        X_train=X_train,
        y_train=y_train,
        y_train_cont=y_train_cont,
        X_val=X_val,
        y_val=y_val,
        y_val_cont=y_val_cont,
        X_test=X_test,
        y_test=y_test,
        y_test_cont=y_test_cont,
        feature_names=np.array(ALL_FEATURES, dtype=object),
    )

    file_size = os.path.getsize(OUTPUT_FILE) / 1024 / 1024
    print(f"  Saved: {file_size:.1f}MB")

    # --- Feature importance: correlation with y ---
    print(f"\n{'=' * 60}")
    print("Feature Correlation Analysis (vs y_continuous on train set)")
    print(f"{'=' * 60}")

    if len(X_train) > 0:
        corr_with_label = []
        for i, fname in enumerate(ALL_FEATURES):
            col = X_train[:, i]
            if np.std(col) > 0:
                corr = np.corrcoef(col, y_train_cont)[0, 1]
            else:
                corr = 0.0
            corr_with_label.append((fname, corr))

        corr_with_label.sort(key=lambda x: abs(x[1]), reverse=True)

        print(f"\n  Top 20 features by absolute correlation:")
        for fname, corr in corr_with_label[:20]:
            print(f"    {fname:30s}  corr={corr:+.4f}")

        print(f"\n  Bottom 10 features (least correlated):")
        for fname, corr in corr_with_label[-10:]:
            print(f"    {fname:30s}  corr={corr:+.4f}")

        # Feature value range stats
        print(f"\n  Feature value ranges (train set):")
        for fname in ALL_FEATURES[:10]:
            idx = ALL_FEATURES.index(fname)
            col = X_train[:, idx]
            print(f"    {fname:30s}  min={col.min():.4f}  max={col.max():.4f}  "
                  f"mean={col.mean():.4f}  std={col.std():.4f}")

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Done! Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    build_dataset()

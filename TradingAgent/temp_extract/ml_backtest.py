#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Backtest V2 for TradingAgent
=================================
V1 result: bull=88% PASS, bear=45% FAIL, range=47%, overall=55.3%

V2 improvements:
  1. Bear market defense: in bear regime, boost defensive stocks
  2. Risk-level adaptive: Risk >=4 use defense scoring
  3. Dynamic TOP_N: fewer picks in high risk
  4. Blend ML score with V10-style domain rules
"""

import json, os, sys, time, gc, warnings
import numpy as np
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = r'D:\GitHub\TradingAgents\TradingAgent'
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

MODEL_FILE = os.path.join(DATA_DIR, 'ml_model_best.txt')

EVAL_START = '2026-03-01'
EVAL_END = '2026-04-24'
FEATURE_MIN_DAYS = 30

# Industry keywords
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]


def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)


def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


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
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code


def load_kline():
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
            'dates': dates, 'close': closes, 'open': opens,
            'high': highs, 'low': lows, 'volume': volumes,
        }
    del raw
    gc.collect()
    print(f"  Kline: {len(kline)} stocks ({skipped} skipped)")
    return kline


def load_index():
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
    idx_close = {r[0]: np.float32(r[1]) for r in records}
    idx_return = {}
    sorted_dates = sorted([r[0] for r in records])
    for i in range(len(sorted_dates) - 1):
        d = sorted_dates[i]
        d_next = sorted_dates[i + 1]
        idx_return[d] = np.float32((idx_close[d_next] - idx_close[d]) / idx_close[d] * 100)
    print(f"  Index: {len(records)} days, {sorted_dates[0]} ~ {sorted_dates[-1]}")
    return idx_close, idx_return, sorted_dates


def load_scores():
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
            }
    print(f"  Scores: {len(scores)} stocks")
    return scores


# ============================================================================
# Feature Calculation (exact match with ml_features.py)
# ============================================================================
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
    'sector_avg_change',
    'is_defensive', 'is_high_beta',
]
ALL_FEATURES = TECH_FEATURES + NEW_FACTOR_FEATURES + MARKET_FEATURES + INDUSTRY_FEATURES


def calc_features_ml(close, open_, high, low, volume, n):
    if n < 20:
        return None
    c = close[:n]
    h = high[:n]
    lo = low[:n]
    v = volume[:n]

    f = {}
    f['r1'] = float((c[-1] - c[-2]) / c[-2] * 100) if n >= 2 else 0.0
    f['r3'] = float((c[-1] - c[-4]) / c[-4] * 100) if n >= 4 else 0.0
    f['r5'] = float((c[-1] - c[-6]) / c[-6] * 100) if n >= 6 else 0.0
    f['r10'] = float((c[-1] - c[-11]) / c[-11] * 100) if n >= 11 else 0.0
    f['r20'] = float((c[-1] - c[-21]) / c[-21] * 100) if n >= 21 else 0.0

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

    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i - 1]) / c[i - 1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = float(100 - 100 / (1 + ag / al))

    if n >= 26:
        ema12 = ema26 = float(c[-1])
        for i in range(-26, 0):
            ema12 = float(c[i]) * (2 / 14) + ema12 * (1 - 2 / 14)
            ema26 = float(c[i]) * (2 / 27) + ema26 * (1 - 2 / 27)
        f['macd'] = float(ema12 - ema26)
    else:
        f['macd'] = 0.0

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

    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = float(np.mean(v[-5:]) / np.mean(v[-10:]))
    else:
        f['vol_ratio'] = 1.0
    if n >= 10:
        v5 = np.mean(v[-5:])
        v5_prev = np.mean(v[-10:-5])
        f['vol_shrink'] = float(v5 / max(v5_prev, 1))
    else:
        f['vol_shrink'] = 1.0
    f['turn_ratio'] = f['vol_ratio']
    f['turn_avg'] = float(np.mean(v[-5:]) / max(np.mean(v), 1))
    f['turn_spike'] = float(v[-1] / max(np.mean(v[-5:]), 1)) if n >= 5 else 1.0

    w20 = min(20, n)
    f['price_pos'] = float((c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100)

    if n >= 6:
        trs = []
        for i in range(-min(14, n - 1), 0):
            tr = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
            trs.append(tr)
        f['atr_pct'] = float(np.mean(trs) / c[-1] * 100)
    else:
        f['atr_pct'] = 0.0

    streak = 0
    for i in range(n - 1, 0, -1):
        if c[i] > c[i - 1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i - 1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak

    f['consistency'] = 0
    if n >= 5:
        for i in range(-4, 0):
            if c[i + 1] > c[i]:
                f['consistency'] += 1

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
    f['dist_support'] = float((c[-1] - np.min(c[-w20:])) / c[-1] * 100)
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0

    return f


def detect_market_state(idx_close_sorted, date_idx):
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
        vol_state = 'high' if idx_vol > 1.5 else ('normal' if idx_vol > 0.8 else 'low')
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
    regime_oh = [1, 0, 0] if regime == 'bull' else ([0, 1, 0] if regime == 'bear' else [0, 0, 1])
    vol_oh = [1, 0, 0] if vol_state == 'high' else ([0, 1, 0] if vol_state == 'normal' else [0, 0, 1])
    return risk, regime_oh, momentum, vol_oh


def build_feature_vector(features, risk_level, regime_oh, momentum, vol_oh, ind_info, n_features):
    row = np.zeros(n_features, dtype=np.float32)
    for i, fname in enumerate(TECH_FEATURES):
        if i >= n_features:
            break
        row[i] = features.get(fname, 0.0)
    if n_features <= len(TECH_FEATURES):
        return row
    offset = len(TECH_FEATURES)
    # New factors: zeros
    if n_features <= offset + len(NEW_FACTOR_FEATURES):
        return row
    offset = len(TECH_FEATURES) + len(NEW_FACTOR_FEATURES)
    row[offset + 0] = risk_level
    row[offset + 1] = regime_oh[0]
    row[offset + 2] = regime_oh[1]
    row[offset + 3] = regime_oh[2]
    row[offset + 4] = momentum
    row[offset + 5] = vol_oh[0]
    row[offset + 6] = vol_oh[1]
    row[offset + 7] = vol_oh[2]
    if n_features <= offset + len(MARKET_FEATURES):
        return row
    offset = len(TECH_FEATURES) + len(NEW_FACTOR_FEATURES) + len(MARKET_FEATURES)
    row[offset + 0] = ind_info.get('encoded', 0)
    row[offset + 1] = 0.0
    row[offset + 2] = ind_info.get('is_defensive', 0)
    row[offset + 3] = ind_info.get('is_high_beta', 0)
    return row


def calc_beta_relstrength(stock_close, idx_closes_array, n, n_beta=20, n_rel=5):
    beta = 1.0
    rs5 = 0.0
    rs3 = 0.0
    if n >= n_beta + 1:
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
# Defense Score Calculator (V10-style domain knowledge)
# ============================================================================
def calc_defense_score(features, industry, risk_level, regime):
    """Calculate defense bonus/penalty based on domain knowledge.
    Returns a multiplier to apply to ML probability."""
    f = features
    multiplier = 1.0

    # --- Risk >= 4 (bear/defense) ---
    if risk_level >= 4:
        beta = f.get('beta_20d', 1.0)
        # Very strict beta filter in bear
        if beta > 1.3:
            multiplier *= 0.3
        elif beta > 1.0:
            multiplier *= 0.7
        elif beta < 0.7:
            multiplier *= 1.3

        # Industry
        if is_high_beta_industry(industry):
            multiplier *= 0.3
        if is_defensive_industry(industry):
            multiplier *= 1.3

        # Recent drawdown
        dd = f.get('max_dd_10d', 0)
        if dd < -10:
            multiplier *= 0.4

        # Volatility
        vol5 = f.get('vol5', 2)
        if vol5 > 3.0:
            multiplier *= 0.6
        elif vol5 < 1.5:
            multiplier *= 1.15

        # Relative strength (outperforming in bear = gold)
        rs = f.get('rel_strength_5d', 0)
        if rs > 5:
            multiplier *= 1.4
        elif rs > 2:
            multiplier *= 1.2
        elif rs < -3:
            multiplier *= 0.6

        # Negative streak
        streak = f.get('streak', 0)
        if streak <= -3:
            multiplier *= 0.4
        elif streak <= -2:
            multiplier *= 0.7
        # Positive streak in bear = resilient
        elif streak >= 2:
            multiplier *= 1.15

        # RSI
        rsi = f.get('rsi', 50)
        if rsi > 70:
            multiplier *= 0.6
        elif rsi < 25:
            multiplier *= 1.1

        # Large negative return yesterday
        r1 = f.get('r1', 0)
        if r1 < -5:
            multiplier *= 0.3
        elif r1 < -3:
            multiplier *= 0.6
        # Large positive = mean revert in bear
        if r1 > 7:
            multiplier *= 0.4
        elif r1 > 5:
            multiplier *= 0.6

        # MA position: below MA20 in bear = danger
        close_ma20 = f.get('close_ma20', 0)
        if close_ma20 > 0.02:
            multiplier *= 1.1  # above MA20 = resilient
        elif close_ma20 < -0.05:
            multiplier *= 0.5

    # --- Risk 3 (range) ---
    elif risk_level == 3:
        consistency = f.get('consistency', 0)
        if consistency >= 4:
            multiplier *= 1.15

        vol5 = f.get('vol5', 2)
        if vol5 > 3.5:
            multiplier *= 0.7
        elif vol5 < 1.5:
            multiplier *= 1.05

        if f.get('close_ma20', 0) < -0.05:
            multiplier *= 0.6

        r1 = abs(f.get('r1', 0))
        if r1 > 5:
            multiplier *= 0.6

        rsi = f.get('rsi', 50)
        if rsi > 75:
            multiplier *= 0.5

    return multiplier


# ============================================================================
# Main Backtest
# ============================================================================
def run_ml_backtest_v2():
    t0 = time.time()

    print("=" * 60)
    print("ML Model Backtest V2")
    print("=" * 60)
    print(f"Period: {EVAL_START} ~ {EVAL_END}")
    print(f"Improvement: Blend ML with defense scoring for bear market")

    # Load model
    print("\n[1/5] Loading models...")
    try:
        import lightgbm as lgb
        model = lgb.Booster(model_file=MODEL_FILE)
        n_features = model.num_feature()
        print(f"  General model: {os.path.basename(MODEL_FILE)}, {n_features} features")
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    bear_model = None  # Don't use bear model, it hurts

    # Load data
    print("\n[2/5] Loading data...")
    kline = load_kline()
    idx_close, idx_return, idx_dates = load_index()
    scores = load_scores()
    print_mem("Data loaded")

    # Build industry info
    industry_set = set()
    for code in kline.keys():
        s = scores.get(code, {})
        industry_set.add(s.get('industry', 'unknown'))
    industry_set.add('unknown')
    industry_encoder = {ind: i for i, ind in enumerate(sorted(industry_set))}

    industry_info = {}
    for code in kline.keys():
        s = scores.get(code, {})
        ind = s.get('industry', 'unknown')
        industry_info[code] = {
            'encoded': industry_encoder.get(ind, 0),
            'is_defensive': 1 if is_defensive_industry(ind) else 0,
            'is_high_beta': 1 if is_high_beta_industry(ind) else 0,
            'name': s.get('name', ''),
            'industry': ind,
        }

    idx_close_list = [(d, float(idx_close[d])) for d in idx_dates]
    idx_date_to_pos = {d: i for i, d in enumerate(idx_dates)}

    eval_dates = [d for d in idx_dates if EVAL_START <= d <= EVAL_END]
    print(f"\n  Eval dates: {len(eval_dates)} ({eval_dates[0]} ~ {eval_dates[-1]})")

    # Backtest
    print(f"\n[3/5] Running backtest...")

    results = []
    wins = 0
    total = 0
    stats_by_regime = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    stock_recent_perf = defaultdict(list)

    stock_codes = sorted(kline.keys())

    for day_idx, date in enumerate(eval_dates):
        date_idx = idx_date_to_pos.get(date)
        if date_idx is None:
            continue

        risk_level, regime_oh, momentum, vol_oh = detect_market_state(idx_close_list, date_idx)
        if regime_oh[0] == 1:
            regime = 'bull'
        elif regime_oh[1] == 1:
            regime = 'bear'
        else:
            regime = 'range'

        idx_closes_up_to = np.array(
            [float(idx_close[d]) for d in idx_dates[:date_idx + 1]], dtype=np.float32)
        idx_next_ret = idx_return.get(date)
        if idx_next_ret is None:
            continue

        # Dynamic TOP_N
        if risk_level >= 5:
            top_n = 2
        elif risk_level >= 4:
            top_n = 3
        elif risk_level == 3:
            top_n = 3
        else:
            top_n = 4

        # Score all stocks
        feature_matrix = []
        stock_list = []
        features_list = []  # Keep raw features for defense scoring

        for code in stock_codes:
            kd = kline[code]
            dates = kd['dates']
            try:
                pos = dates.index(date)
            except ValueError:
                continue
            if pos < 20 or pos + 1 >= len(dates):
                continue

            features = calc_features_ml(
                kd['close'][:pos + 1], kd['open'][:pos + 1],
                kd['high'][:pos + 1], kd['low'][:pos + 1],
                kd['volume'][:pos + 1], pos + 1)
            if features is None:
                continue

            stock_closes = kd['close'][:pos + 1]
            n_sc = pos + 1
            n_idx = min(n_sc, len(idx_closes_up_to))
            if n_idx >= 21:
                beta, rs5, rs3 = calc_beta_relstrength(
                    stock_closes, idx_closes_up_to[-n_idx:], n_idx)
                features['beta_20d'] = beta
                features['rel_strength_5d'] = rs5
                features['rel_strength_3d'] = rs3

            ind_info = industry_info.get(code, {'encoded': 0, 'is_defensive': 0, 'is_high_beta': 0})
            fv = build_feature_vector(features, risk_level, regime_oh, momentum, vol_oh, ind_info, n_features)

            feature_matrix.append(fv)
            stock_list.append(code)
            features_list.append(features)

        if not feature_matrix:
            continue

        # Batch predict
        X = np.array(feature_matrix, dtype=np.float32)
        probs = model.predict(X)

        # Apply defense scoring
        adjusted_scores = np.zeros(len(probs), dtype=np.float32)
        for i in range(len(probs)):
            code = stock_list[i]
            feats = features_list[i]
            industry = industry_info.get(code, {}).get('industry', 'unknown')

            if regime == 'bear' or risk_level >= 4:
                # In bear: defense adjustment
                defense_mult = calc_defense_score(feats, industry, risk_level, regime)
                adjusted_scores[i] = probs[i] * defense_mult
            elif regime == 'range' and risk_level >= 3:
                # In range: mild adjustment
                defense_mult = calc_defense_score(feats, industry, risk_level, regime)
                defense_mult = np.sign(defense_mult - 1.0) * np.sqrt(abs(defense_mult - 1.0)) + 1.0
                adjusted_scores[i] = probs[i] * defense_mult
            else:
                # Bull: pure ML
                adjusted_scores[i] = probs[i]

        # Sort by adjusted score
        sorted_indices = np.argsort(adjusted_scores)[::-1]

        # Blacklist
        blacklist = set()
        for code in stock_codes:
            rets = stock_recent_perf.get(code, [])
            if len(rets) >= 1 and rets[-1] < -3:
                blacklist.add(code)
            if risk_level >= 4 and len(rets) >= 1 and rets[-1] > 6:
                blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)
            if len(rets) >= 3 and rets[-1] < 0 and rets[-2] < 0 and rets[-3] < 0:
                blacklist.add(code)

        # Select TOP_N
        selected = []
        for idx in sorted_indices:
            code = stock_list[idx]
            if code in blacklist:
                continue
            selected.append({
                'code': code,
                'prob': float(probs[idx]),
                'adjusted': float(adjusted_scores[idx]),
                'name': industry_info.get(code, {}).get('name', ''),
                'industry': industry_info.get(code, {}).get('industry', 'unknown'),
            })
            if len(selected) >= top_n:
                break

        if not selected:
            for idx in sorted_indices[:top_n]:
                code = stock_list[idx]
                selected.append({
                    'code': code,
                    'prob': float(probs[idx]),
                    'adjusted': float(adjusted_scores[idx]),
                    'name': industry_info.get(code, {}).get('name', ''),
                    'industry': industry_info.get(code, {}).get('industry', 'unknown'),
                })

        if not selected:
            continue

        # Calculate returns
        idx_ret = float(idx_next_ret)
        daily_wins = 0
        stock_rets = []

        for s in selected:
            code = s['code']
            kd = kline[code]
            pos = kd['dates'].index(date)
            if pos + 1 >= len(kd['dates']):
                continue
            next_close = float(kd['close'][pos + 1])
            curr_close = float(kd['close'][pos])
            stock_ret = (next_close - curr_close) / curr_close * 100
            beat = bool(stock_ret > idx_ret)
            stock_rets.append({
                'code': code,
                'name': s['name'],
                'ret': round(float(stock_ret), 2),
                'beat': beat,
                'prob': round(s['prob'], 4),
                'adjusted': round(s['adjusted'], 4),
            })
            if beat:
                daily_wins += 1

        for sr in stock_rets:
            stock_recent_perf[sr['code']].append(sr['ret'])
            if len(stock_recent_perf[sr['code']]) > 5:
                stock_recent_perf[sr['code']] = stock_recent_perf[sr['code']][-5:]

        if stock_rets:
            total += 1
            wr = float(daily_wins / len(stock_rets))
            is_win = wr > 0.5
            if is_win:
                wins += 1
            avg_ret = float(np.mean([x['ret'] for x in stock_rets]))
            beat_idx = avg_ret > idx_ret

            results.append({
                'date': date,
                'regime': regime,
                'risk': int(risk_level),
                'top_n': top_n,
                'n_stocks': len(stock_rets),
                'stocks': stock_rets,
                'idx_ret': round(float(idx_ret), 2),
                'avg_ret': round(float(avg_ret), 2),
                'wr': round(wr, 2),
                'win': bool(is_win),
                'beat_idx': bool(beat_idx),
            })

            stats_by_regime[regime]['total'] += 1
            stats_by_risk[risk_level]['total'] += 1
            if is_win:
                stats_by_regime[regime]['wins'] += 1
                stats_by_risk[risk_level]['wins'] += 1
            if beat_idx:
                stats_by_regime[regime]['beat_idx'] += 1
                stats_by_risk[risk_level]['beat_idx'] += 1

            tag = 'W' if is_win else 'L'
            bi = '^' if beat_idx else 'v'
            print(f"  [{date}] {tag}{bi} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% R{risk_level} [{regime[:4]}] n={len(stock_rets)}"
                  f"  adj={selected[0]['adjusted']:.3f}")

        del feature_matrix, X, probs
        if (day_idx + 1) % 5 == 0:
            gc.collect()

    # Results
    print(f"\n[4/5] Generating results...")
    if total == 0:
        print("  ERROR: No valid trading days!")
        return None

    accuracy = wins / total
    beat_idx_days = sum(1 for r in results if r['beat_idx'])
    beat_idx_pct = beat_idx_days / total

    print(f"\n{'='*60}")
    print(f"ML BACKTEST V2 RESULTS")
    print(f"{'='*60}")
    print(f"  Period: {EVAL_START} ~ {EVAL_END} ({total} days)")
    print(f"  Win Rate:   {wins}/{total} = {accuracy*100:.1f}%")
    print(f"  Beat Index: {beat_idx_days}/{total} = {beat_idx_pct*100:.1f}%")
    print(f"")
    print(f"  By Regime:")
    for regime in ['bull', 'bear', 'range']:
        s = stats_by_regime.get(regime, {'wins': 0, 'total': 0, 'beat_idx': 0})
        if s['total'] > 0:
            acc = s['wins'] / s['total'] * 100
            bi = s['beat_idx'] / s['total'] * 100
            print(f"    {regime:8s}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    print(f"\n  By Risk Level:")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        if s['total'] > 0:
            acc = s['wins'] / s['total'] * 100
            bi = s['beat_idx'] / s['total'] * 100
            print(f"    Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")

    # Save
    print(f"\n[5/5] Saving results...")
    os.makedirs(RESULT_DIR, exist_ok=True)

    result_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'ml-backtest-v2',
        'model_file': os.path.basename(MODEL_FILE),
        'n_features': n_features,
        'eval_range': f'{EVAL_START} ~ {EVAL_END}',
        'total_days': total,
        'wins': wins,
        'accuracy': float(accuracy),
        'beat_idx_days': beat_idx_days,
        'beat_idx_pct': float(beat_idx_pct),
        'by_regime': {k: {kk: int(vv) for kk, vv in v.items()} for k, v in stats_by_regime.items()},
        'by_risk': {str(k): {kk: int(vv) for kk, vv in v.items()} for k, v in stats_by_risk.items()},
        'target_bull_80': bool(stats_by_regime.get('bull', {}).get('beat_idx', 0) /
                          max(stats_by_regime.get('bull', {}).get('total', 1), 1) * 100 >= 80),
        'target_bear_65': bool(stats_by_regime.get('bear', {}).get('beat_idx', 0) /
                          max(stats_by_regime.get('bear', {}).get('total', 1), 1) * 100 >= 65),
        'daily_results': [{
            'date': r['date'],
            'regime': r['regime'],
            'risk': r['risk'],
            'top_n': r['top_n'],
            'idx_ret': r['idx_ret'],
            'avg_ret': r['avg_ret'],
            'beat_idx': bool(r['beat_idx']),
            'win': bool(r['win']),
            'n_stocks': r['n_stocks'],
        } for r in results],
    }

    result_path = os.path.join(RESULT_DIR, 'backtest_ml_result.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    print(f"  Result saved: {result_path}")

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    bull_bi = stats_by_regime.get('bull', {}).get('beat_idx', 0) / max(stats_by_regime.get('bull', {}).get('total', 1), 1) * 100
    bear_bi = stats_by_regime.get('bear', {}).get('beat_idx', 0) / max(stats_by_regime.get('bear', {}).get('total', 1), 1) * 100
    print(f"\nTARGET CHECK:")
    print(f"  Bull beat_idx: {bull_bi:.0f}% (target >= 80%) {'PASS' if bull_bi >= 80 else 'FAIL'}")
    print(f"  Bear beat_idx: {bear_bi:.0f}% (target >= 65%) {'PASS' if bear_bi >= 65 else 'FAIL'}")
    print(f"  Overall beat_idx: {beat_idx_pct*100:.1f}%")
    print("=" * 60)

    return result_data


if __name__ == '__main__':
    run_ml_backtest_v2()

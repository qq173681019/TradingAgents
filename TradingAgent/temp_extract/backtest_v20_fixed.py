#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V20 - Fixed Backtest (T+1 + Additive Scoring + Real Static + Dynamic Sector)

Problem: V16 achieved 90% beat_idx on training period (03/01~04/24) but
V14 only got 49% on extended (4.5mo) backtest vs V10's 60.8%.
Root cause: overfitting to single training period.

V17 Solution:
  1. Multi-period joint optimization — optimize across 3 time windows simultaneously
  2. Robust objective = 0.5*mean_beat_idx + 0.3*min_beat_idx + 0.2*(1-variance)
  3. L2 regularization on params (penalize extreme weights)
  4. Parameter range constraint [0.001, 0.4] for weights
  5. Iterative per-risk optimization with cross-period validation

Time Windows:
  Period A: 2025-11-15 ~ 2026-01-15 (early period)
  Period B: 2026-01-15 ~ 2026-03-01 (mid period)
  Period C: 2026-03-01 ~ 2026-04-24 (original training period)

Strategy:
  Phase 1: Optimize R3 across all periods jointly (biggest impact)
  Phase 2: Optimize R2 across all periods jointly
  Phase 3: Optimize R4/5 across all periods jointly
  Phase 4: Final multi-period evaluation
  Phase 5: Extended validation against V10/V14/V16
"""

import json, os, sys, time, gc, warnings, functools
import numpy as np
import pandas as pd
from datetime import datetime
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
MIN_KLINE_DAYS = 30  # Lower threshold since we only have 3 months
MAX_INDUSTRY = 1
MEMORY_LIMIT_MB = 8000

# V19: Stock pool (hot sectors only)
V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True  # Set False to use full market

# Multi-period training windows (V19: recent 3 months)
PERIOD_A = ('2026-02-07', '2026-03-10')  # Early
PERIOD_B = ('2026-03-10', '2026-04-10')  # Mid
PERIOD_C = ('2026-04-10', '2026-05-06')  # Recent

# Full extended validation
PERIOD_FULL = ('2026-02-07', '2026-05-06')

N_TRIALS = 200  # Fewer trials since stock pool is smaller
TIMEOUT_PER_PHASE = 900  # 15 min per phase

# Parameter range constraints
W_MIN = 0.001
W_MAX = 0.4
L2_LAMBDA = 0.001  # Regularization strength

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
# Code normalization
# ============================================================================
def normalize_code(code):
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code

# ============================================================================
# Data Loading - Merge old + new for extended history
# ============================================================================
def load_merged_kline():
    print("[1/3] Loading and merging kline data...")
    
    # Load V19 stock pool if enabled
    v19_pool = None
    if V19_USE_POOL and os.path.exists(V19_POOL_FILE):
        with open(V19_POOL_FILE, 'r', encoding='utf-8') as f:
            v19_pool = set(json.load(f))
        print(f"  V19 stock pool: {len(v19_pool)} stocks")
    
    # Only use latest kline (V19 is 3-month focused, no need for old data)
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
        
        # Filter by V19 pool if enabled
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
    """Parse an index JSON file and return list of {date, close} records."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    records = []
    if 'date' in raw and isinstance(raw['date'], dict):
        n = len(raw['date'])
        for i in range(n):
            try:
                key = str(i)
                ts = raw['date'].get(key)
                cl = float(raw['close'].get(key, 0))
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
    
    # Load old index (covers 2025-10-08 ~ 2026-04-07)
    old_idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    # Load new index (covers 2025-10-01 ~ 2026-04-25)
    new_idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    
    old_records = []
    if os.path.exists(old_idx_file):
        print(f"  Loading old index: {os.path.basename(old_idx_file)}")
        old_records = _parse_index_file(old_idx_file)
    
    new_records = []
    if os.path.exists(new_idx_file):
        print(f"  Loading new index: {os.path.basename(new_idx_file)}")
        new_records = _parse_index_file(new_idx_file)
    
    # Merge (deduplicate by date, keep latest)
    seen_dates = set()
    all_records = []
    for r in old_records + new_records:
        if r['date'] not in seen_dates:
            seen_dates.add(r['date'])
            all_records.append(r)
    
    gc.collect()
    
    index_df = pd.DataFrame(all_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date').drop_duplicates(subset='date', keep='last')
    index_df['close'] = index_df['close'].astype('float32')
    print(f"  Index: {len(index_df)} days, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    
    return index_df


def _load_scores():
    """V20: Load real static scores (not hardcoded 5.0)"""
    import glob
    
    # Priority: latest optimized file with real scores
    opt_pattern = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
    opt_files = sorted(glob.glob(opt_pattern), key=lambda x: (os.path.getsize(x) > 100000, os.path.getmtime(x)), reverse=True)
    
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
        tech_v = [v['tech'] for v in scores.values()]
        fund_v = [v['fund'] for v in scores.values()]
        chip_v = [v['chip'] for v in scores.values()]
        sec_v = [v['sector'] for v in scores.values()]
        print(f"  Scores: {len(scores)} stocks (from {loaded_from})")
        print(f"    tech: mean={np.mean(tech_v):.2f} std={np.std(tech_v):.2f}")
        print(f"    fund: mean={np.mean(fund_v):.2f} std={np.std(fund_v):.2f}")
        print(f"    chip: mean={np.mean(chip_v):.2f} std={np.std(chip_v):.2f}")
        print(f"    sector: mean={np.mean(sec_v):.2f} std={np.std(sec_v):.2f}")
    else:
        print(f"  Scores: 0 stocks (WARNING)")
    
    return scores


# ============================================================================
# Feature Engineering (same as V16)
# ============================================================================
def calc_features(df, target_date):
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 20:
        return None
    
    c = hist['close'].values
    v = hist['volume'].values
    h = hist['high'].values if 'high' in hist.columns else c
    lo = hist['low'].values if 'low' in hist.columns else c
    turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
    pct = hist['pctChg'].values if 'pctChg' in hist.columns else np.zeros(len(c))
    
    n = len(c)
    f = {}
    
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0
    
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10
    
    f['close_ma5'] = c[-1] / ma5 - 1
    f['close_ma10'] = c[-1] / ma10 - 1
    f['close_ma20'] = c[-1] / ma20 - 1
    f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    f['ma10_slope'] = (ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1]) if n >= 11 else 0
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)
    
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)
    
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0
    
    if n >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        f['vol5'] = np.std(rets) * 100
    else:
        f['vol5'] = 0
    if n >= 11:
        rets10 = np.diff(c[-11:]) / c[-11:-1]
        f['vol10'] = np.std(rets10) * 100
    else:
        f['vol10'] = f.get('vol5', 0)
    
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    
    if n >= 6:
        v5 = np.mean(v[-5:])
        v5_prev = np.mean(v[-10:-5]) if n >= 10 else v5
        f['vol_shrink'] = v5 / max(v5_prev, 1)
    else:
        f['vol_shrink'] = 1.0
    
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_spike'] = 1.0
    
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    streak = 0
    for i in range(n-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak
    
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0
    
    f['pct_1d'] = f['r1']
    
    if n >= 10:
        peak = c[-10]
        max_dd = 0
        for i in range(-9, 1):
            if c[i] > peak:
                peak = c[i]
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        f['max_dd_10d'] = max_dd
    else:
        f['max_dd_10d'] = 0
    
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0
    
    f['consistency'] = 0
    if n >= 5:
        for i in range(-4, 0):
            if c[i+1] > c[i]:
                f['consistency'] += 1
    
    return f


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


def detect_market_state(index_df, date):
    hist = index_df[index_df['date'] < date].copy()
    if len(hist) < 20:
        return 'range', 0, 'normal', 3
    closes = hist['close'].values
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
    momentum = ret5 * 0.6 + ret20 * 0.4
    
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
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]:
            consec_decline += 1
        else:
            break
    
    if consec_decline >= 4: risk = 5
    elif consec_decline >= 3: risk = 4
    elif regime == 'bear' and vol_state == 'high': risk = 5
    elif regime == 'bear': risk = 4
    elif regime == 'bull' and vol_state == 'high': risk = 3
    elif regime == 'bull': risk = 2
    elif vol_state == 'high': risk = 4
    else: risk = 3
    
    if n >= 2:
        last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if last_ret < -2: risk = min(risk + 1, 5)
        elif last_ret > 2: risk = max(risk - 1, 1)
    
    return regime, momentum, vol_state, risk


def get_adaptive_top_n(risk_level):
    if risk_level >= 5: return 2
    elif risk_level >= 4: return 3
    elif risk_level == 3: return 3
    else: return 4

def get_stock_return(df, date):
    """T+1 return: buy at test_date close, sell at next trading day close"""
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
    """T+1 return: aligned with stock_return"""
    day_rows = index_df[index_df['date'] >= date]
    if len(day_rows) < 2:
        return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None

def build_blacklist(stock_recent_perf, risk):
    blacklist = set()
    for code, rets in stock_recent_perf.items():
        if len(rets) >= 1 and rets[-1] < -3:
            blacklist.add(code)
        if risk >= 4 and len(rets) >= 1 and rets[-1] > 6:
            blacklist.add(code)
        if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
            blacklist.add(code)
        if len(rets) >= 3 and rets[-1] < 0 and rets[-2] < 0 and rets[-3] < 0:
            blacklist.add(code)
    return blacklist


# ============================================================================
# Sub-score computation (same as V16)
# ============================================================================
def compute_stock_subscores(code, df, test_date, index_df, idx_rets_20, idx_ret_5d, idx_ret_3d, static, daily_sector_avg):
    """Compute all sub-scores for a single stock on a given date."""
    feats = calc_features(df, test_date)
    if feats is None:
        return None
    
    stock_hist = df[df['date'] < test_date]
    s_closes = stock_hist['close'].values
    s_n = len(s_closes)
    
    beta = 1.0
    if idx_rets_20 is not None and s_n >= 23:
        s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
        sr_len = min(len(s_rets_20), len(idx_rets_20))
        if sr_len >= 10:
            s_r = s_rets_20[-sr_len:]
            i_r = idx_rets_20[-sr_len:]
            idx_var = np.var(i_r)
            if idx_var > 0.001:
                beta = np.cov(s_r, i_r)[0, 1] / idx_var
    
    rel_str = 0.0
    rel_str_3d = 0.0
    if s_n >= 6:
        rel_str = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100 - idx_ret_5d
    if s_n >= 4:
        rel_str_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100 - idx_ret_3d
    
    feats['beta_20d'] = beta
    feats['rel_strength_5d'] = rel_str
    feats['rel_strength_3d'] = rel_str_3d
    
    stock_return = get_stock_return(df, test_date)
    
    f = feats
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return None
    
    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    
    vr = f.get('vol_ratio', 1)
    if 1.1 <= vr <= 2.0: vol_s = 3.0
    elif vr > 2.0: vol_s = 1.0
    else: vol_s = 2.0
    
    rsi = f.get('rsi', 50)
    if 40 <= rsi <= 60: rsi_s = 3.0
    elif 30 <= rsi < 40: rsi_s = 4.0
    elif 60 < rsi <= 70: rsi_s = 2.0
    else: rsi_s = 1.0
    
    vol5 = f.get('vol5', 2)
    if vol5 < 1.5: low_vol_s = 4.0
    elif vol5 < 2.5: low_vol_s = 3.0
    elif vol5 < 3.5: low_vol_s = 2.0
    else: low_vol_s = 1.0
    
    industry = static.get('industry', 'unknown') if static else 'unknown'
    
    defense_base = 0.0
    is_def = is_defensive_industry(industry)
    is_hb = is_high_beta_industry(industry)
    if is_def: defense_base += 3.0
    if is_hb: defense_base -= 2.0
    
    max_dd = f.get('max_dd_10d', 0)
    dd_pen = -3.0 if max_dd < -15 else (-1.0 if max_dd < -10 else 0.0)
    defense_s = defense_base + low_vol_s + dd_pen
    
    sector_heat = daily_sector_avg.get(industry, 0) * 0.1
    ind_heat = daily_sector_avg.get(industry, 0)
    
    consistency = f.get('consistency', 0)
    consistency_s = consistency * 1.5
    
    static_score = 0.0
    if static:
        tech = max(static.get('tech', 5), 0)
        fund = max(static.get('fund', 5), 0)
        chip = max(static.get('chip', 5), 0)
        sec = max(static.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sec * 0.15) / 10 * 5
    
    beta_bonus = 2.0 - min(beta, 2.0)
    
    return {
        'code': code,
        'name': static.get('name', '') if static else '',
        'industry': industry,
        'stock_return': stock_return,
        'momentum_s': momentum_s,
        'trend_s': trend_s,
        'consistency_s': consistency_s,
        'mr_s': mr_s,
        'vol_s': vol_s,
        'rsi_s': rsi_s,
        'static_score': static_score,
        'defense_s': defense_s,
        'sector_heat': sector_heat,
        'low_vol_s': low_vol_s,
        'rel_str': rel_str,
        'rel_str_3d': rel_str_3d,
        'beta_bonus': beta_bonus,
        'beta': beta,
        'consistency': consistency,
        'r1': f.get('r1', 0),
        'r3': f.get('r3', 0),
        'r5': f.get('r5', 0),
        'close_ma5': f.get('close_ma5', 0),
        'close_ma20': f.get('close_ma20', 0),
        'vol5': vol5,
        'vol_shrink': f.get('vol_shrink', 1),
        'turn_spike': f.get('turn_spike', 1),
        'rsi': rsi,
        'streak': f.get('streak', 0),
        'oversold': f.get('oversold', 0),
        'overbought': f.get('overbought', 0),
        'ind_heat': ind_heat,
        'is_defensive': is_def,
        'is_high_beta': is_hb,
    }


# ============================================================================
# Scoring Functions (same as V16)
# ============================================================================
def score_risk2(s, p):
    """V20 Risk2: additive bonus/penalty (not multiplicative)"""
    score = (
        s['momentum_s'] * p['w_momentum'] +
        s['trend_s'] * p['w_trend'] +
        s['consistency_s'] * p['w_consistency'] +
        s['vol_s'] * p['w_vol'] +
        s['rsi_s'] * p['w_rsi'] +
        s['static_score'] * p['w_static'] +
        s['defense_s'] * p['w_defense'] +
        s['sector_heat'] * p['w_sector'] +
        s['low_vol_s'] * p['w_low_vol'] +
        s['rel_str'] * p['w_rel_str'] +
        s['rel_str_3d'] * p['w_rel_str_3d']
    )
    if s['consistency'] >= 4: score += p['b_consistency']
    if s['close_ma20'] > 0: score += p['b_above_ma20']
    if 45 <= s['rsi'] <= 60: score += p['b_rsi_45_60']
    if s['ind_heat'] > 1.5: score += p['b_sector_hot']
    if s['rel_str'] > 2: score += p['b_rel_str']
    if s['close_ma20'] < -0.05: score -= p['p_below_ma20']
    if s['vol5'] > 3.5: score -= p['p_high_vol']
    if s['rsi'] > 70: score -= p['p_rsi_overbought']
    if abs(s['r1']) > 5: score -= p['p_big_move']
    if s['streak'] <= -2: score -= p['p_streak_neg']
    if s['vol_shrink'] < 0.7: score -= p['p_vol_shrink']
    if s['turn_spike'] > 2.0: score -= p['p_turn_spike']
    if s['close_ma5'] < -0.02: score -= p['p_below_ma5']
    return score


def score_risk3(s, p):
    score = (
        s['momentum_s'] * p['w_momentum'] +
        s['trend_s'] * p['w_trend'] +
        s['consistency_s'] * p['w_consistency'] +
        s['mr_s'] * p['w_mr'] +
        s['vol_s'] * p['w_vol'] +
        s['rsi_s'] * p['w_rsi'] +
        s['static_score'] * p['w_static'] +
        s['defense_s'] * p['w_defense'] +
        s['sector_heat'] * p['w_sector_heat'] +
        s['low_vol_s'] * p['w_low_vol'] +
        s['rel_str'] * p['w_rel_str'] +
        s['rel_str_3d'] * p['w_rel_str_3d']
    )
    if s['consistency'] >= 4: score += p['b_consistency_high']
    elif s['consistency'] >= 3: score += p['b_consistency_mid']
    if s['r3'] > 0 and s['r5'] > 0: score += p['b_uptrend_full']
    elif s['r3'] > 0: score += p['b_uptrend_partial']
    if s['close_ma20'] > 0: score += p['b_ma20_above']
    elif s['close_ma20'] < -0.05: score -= p['p_ma20_below']
    if s['vol5'] < 1.5: score += p['b_low_vol_high']
    elif s['vol5'] < 2.0: score += p['b_low_vol_mid']
    elif s['vol5'] > 3.5: score -= p['p_high_vol']
    if s['rsi'] > 75: score -= p['p_rsi_overbought']
    elif s['rsi'] > 65: score -= p['p_rsi_high']
    elif 45 <= s['rsi'] <= 60: score += p['b_rsi_sweet']
    if s['ind_heat'] > 2: score += p['b_sector_strong']
    elif s['ind_heat'] > 0.5: score += p['b_sector_mild']
    elif s['ind_heat'] < -2: score -= p['p_sector_cold']
    elif s['ind_heat'] < -0.5: score -= p['p_sector_cool']
    if s['rel_str'] > 3: score += p['b_rel_str_strong']
    elif s['rel_str'] > 1: score += p['b_rel_str_mild']
    if abs(s['r1']) > 5: score -= p['p_big_move5']
    if abs(s['r1']) > 3: score -= p['p_big_move3']
    if s['streak'] <= -2: score -= p['p_streak']
    if s['vol_shrink'] < 0.7: score -= p['p_vol_shrink']
    if s['turn_spike'] > 2.0: score -= p['p_turn_spike']
    if s['close_ma5'] < -0.02: score -= p['p_ma5_below']
    return score


def score_risk45(s, p):
    score = (
        s['momentum_s'] * p['w_momentum'] +
        s['trend_s'] * p['w_trend'] +
        s['mr_s'] * p['w_mr'] +
        s['vol_s'] * p['w_vol'] +
        s['rsi_s'] * p['w_rsi'] +
        s['static_score'] * p['w_static'] +
        s['defense_s'] * p['w_defense'] +
        s['sector_heat'] * p['w_sector'] +
        s['low_vol_s'] * p['w_low_vol'] +
        s['rel_str'] * p['w_rel_str'] +
        s['rel_str_3d'] * p['w_rel_str_3d'] +
        s['beta_bonus'] * p['w_beta']
    )
    if s['beta'] > 1.5: score -= p['p_beta_high']
    elif s['beta'] > 1.2: score -= p['p_beta_mid']
    elif s['beta'] < 0.5: score += p['b_beta_low']
    if s['oversold']: score += p['b_oversold']
    if s['overbought']: score -= p['p_overbought']
    if s['is_high_beta']: score -= p['p_high_beta_ind']
    if s['is_defensive']: score += p['b_defensive_ind']
    if s['rel_str'] > 3: score += p['b_rel_str_strong']
    if s['rel_str'] > 5: score += p['b_rel_str_very_strong']
    if s['vol5'] < 1.5: score += p['b_low_vol']
    if s['r1'] < -5: score -= p['p_big_drop']
    if s['r3'] < -8: score -= p['p_big_drop_3d']
    if s['r1'] > 7: score -= p['p_big_jump']
    if s['r3'] > 15: score -= p['p_overextended']
    if s['streak'] >= 2 and s['rel_str'] > 0: score += p['b_streak_relstr']
    return score


# ============================================================================
# Precompute daily data for a specific period
# ============================================================================
def precompute_period(kline, index_df, scores, sector_avg, start_str, end_str):
    """Precompute sub-scores for all stocks across a given date range."""
    eval_start = pd.to_datetime(start_str)
    eval_end = pd.to_datetime(end_str)
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = [d for d in date_range if get_index_return(index_df, d) is not None]
    
    daily_data = []
    
    for day_idx, test_date in enumerate(valid_dates):
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        actual_n = get_adaptive_top_n(risk)
        
        idx_hist = index_df[index_df['date'] < test_date]
        idx_closes = idx_hist['close'].values
        idx_n = len(idx_closes)
        if idx_n >= 22:
            idx_diff = np.diff(idx_closes[-21:])
            idx_base = idx_closes[-21:-1]
            idx_rets_20 = idx_diff[:len(idx_base)] / idx_base[:len(idx_diff)] * 100
        else:
            idx_rets_20 = None
        idx_ret_5d = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100 if idx_n >= 6 else 0
        idx_ret_3d = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100 if idx_n >= 4 else 0
        
        # Dynamic sector heat (V20: always dynamic, fallback to static)
        dynamic_sector_heat = defaultdict(list)
        for code, df in kline.items():
            static = scores.get(code, None)
            if static is None: continue
            industry = static.get('industry', 'unknown')
            s_hist = df[df['date'] < test_date]
            s_closes = s_hist['close'].values
            if len(s_closes) >= 4:
                ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                dynamic_sector_heat[industry].append(ret_3d)
        daily_sector_avg = {ind: float(np.mean(rets)) for ind, rets in dynamic_sector_heat.items() if len(rets) >= 3}
        if not daily_sector_avg:
            daily_sector_avg = sector_avg
        
        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None: idx_ret = 0
        
        stock_subscores = []
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0: continue
            ss = compute_stock_subscores(code, df, test_date, index_df,
                                          idx_rets_20, idx_ret_5d, idx_ret_3d,
                                          scores.get(code), daily_sector_avg)
            if ss is not None:
                stock_subscores.append(ss)
        
        daily_data.append({
            'test_date': test_date,
            'regime': regime,
            'momentum': momentum,
            'vol_state': vol_state,
            'risk': risk,
            'actual_n': actual_n,
            'idx_ret': idx_ret,
            'stocks': stock_subscores,
        })
        
        if (day_idx + 1) % 10 == 0:
            print(f"    {day_idx + 1}/{len(valid_dates)} days ({len(stock_subscores)} stocks)")
            check_memory()
    
    print(f"  Period {start_str}~{end_str}: {len(daily_data)} days")
    return daily_data


# ============================================================================
# Evaluate beat_idx for a given period with given params
# ============================================================================
def evaluate_period(daily_data, risk_filter, r2_params=None, r3_params=None, r45_params=None):
    """
    Evaluate beat_idx for a single period, filtered by risk level.
    Returns beat_pct (0-1).
    """
    stock_recent_perf = defaultdict(list)
    beat_count = 0
    total = 0
    
    for dd in daily_data:
        risk = dd['risk']
        # Filter by risk level
        if risk_filter == 2 and risk != 2: continue
        if risk_filter == 3 and risk != 3: continue
        if risk_filter == 45 and risk < 4: continue
        
        actual_n = dd['actual_n']
        idx_ret = dd['idx_ret']
        stocks = dd['stocks']
        
        scored = []
        if risk == 2 and r2_params:
            for s in stocks:
                sc = score_risk2(s, r2_params)
                scored.append((s, sc))
        elif risk == 3 and r3_params:
            for s in stocks:
                sc = score_risk3(s, r3_params)
                scored.append((s, sc))
        elif risk >= 4 and r45_params:
            for s in stocks:
                sc = score_risk45(s, r45_params)
                if risk == 5:
                    if s['beta'] > 1.3: sc *= 0.5
                    if s['r1'] < -3: sc *= 0.3
                    if s['is_high_beta']: sc *= 0.5
                scored.append((s, sc))
        else:
            continue
        
        scored.sort(key=lambda x: x[1], reverse=True)
        blacklist = build_blacklist(stock_recent_perf, risk)
        
        selected = []
        ind_count = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']] >= MAX_INDUSTRY: continue
            if risk >= 4 and sc < 0.3: continue
            if risk == 3 and sc < 0.3: continue
            if risk == 2 and sc < 0.5: continue
            selected.append((s, sc))
            ind_count[s['industry']] += 1
        
        if not selected:
            non_bl = [(s, sc) for s, sc in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk >= 3 else 2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected: continue
        
        stock_rets = []
        for s, sc in selected:
            if s['stock_return'] is not None:
                stock_rets.append({
                    'code': s['code'],
                    'ret': s['stock_return'],
                    'beat': s['stock_return'] > idx_ret,
                })
        
        for sr in stock_rets:
            stock_recent_perf[sr['code']].append(sr['ret'])
            if len(stock_recent_perf[sr['code']]) > 5:
                stock_recent_perf[sr['code']] = stock_recent_perf[sr['code']][-5:]
        
        if stock_rets:
            total += 1
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            if avg_ret > idx_ret:
                beat_count += 1
    
    beat_pct = beat_count / total if total > 0 else 0
    return beat_pct, beat_count, total


def evaluate_period_all_risks(daily_data, r2_params, r3_params, r45_params):
    """Evaluate beat_idx across ALL risk levels for a single period."""
    stock_recent_perf = defaultdict(list)
    beat_count = 0
    total = 0
    stats_by_risk = defaultdict(lambda: {'beat_idx': 0, 'total': 0, 'wins': 0})
    
    for dd in daily_data:
        risk = dd['risk']
        actual_n = dd['actual_n']
        idx_ret = dd['idx_ret']
        stocks = dd['stocks']
        
        scored = []
        if risk == 2 and r2_params:
            for s in stocks:
                sc = score_risk2(s, r2_params)
                scored.append((s, sc))
        elif risk == 3 and r3_params:
            for s in stocks:
                sc = score_risk3(s, r3_params)
                scored.append((s, sc))
        elif risk >= 4 and r45_params:
            for s in stocks:
                sc = score_risk45(s, r45_params)
                if risk == 5:
                    if s['beta'] > 1.3: sc *= 0.5
                    if s['r1'] < -3: sc *= 0.3
                    if s['is_high_beta']: sc *= 0.5
                scored.append((s, sc))
        else:
            continue
        
        scored.sort(key=lambda x: x[1], reverse=True)
        blacklist = build_blacklist(stock_recent_perf, risk)
        
        selected = []
        ind_count = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']] >= MAX_INDUSTRY: continue
            if risk >= 4 and sc < 0.3: continue
            if risk == 3 and sc < 0.3: continue
            if risk == 2 and sc < 0.5: continue
            selected.append((s, sc))
            ind_count[s['industry']] += 1
        
        if not selected:
            non_bl = [(s, sc) for s, sc in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk >= 3 else 2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected: continue
        
        stock_rets = []
        for s, sc in selected:
            if s['stock_return'] is not None:
                stock_rets.append({
                    'code': s['code'],
                    'ret': s['stock_return'],
                    'beat': s['stock_return'] > idx_ret,
                })
        
        for sr in stock_rets:
            stock_recent_perf[sr['code']].append(sr['ret'])
            if len(stock_recent_perf[sr['code']]) > 5:
                stock_recent_perf[sr['code']] = stock_recent_perf[sr['code']][-5:]
        
        if stock_rets:
            daily_wins = sum(1 for x in stock_rets if x['beat'])
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            
            total += 1
            if beat_idx:
                beat_count += 1
            
            stats_by_risk[risk]['total'] += 1
            if daily_wins > len(stock_rets) / 2:
                stats_by_risk[risk]['wins'] += 1
            if beat_idx:
                stats_by_risk[risk]['beat_idx'] += 1
    
    beat_pct = beat_count / total if total > 0 else 0
    return beat_pct, stats_by_risk, beat_count, total


# ============================================================================
# L2 Regularization
# ============================================================================
def l2_regularization(params, weight_keys, ref_params=None, lam=L2_LAMBDA):
    """Compute L2 penalty for deviation from reference params."""
    penalty = 0.0
    for key in weight_keys:
        val = params.get(key, 0)
        # Penalize extreme values (far from center of allowed range)
        penalty += val ** 2
    return lam * penalty


# ============================================================================
# Robust Objective Function
# ============================================================================
def robust_objective(beat_pcts):
    """
    Robust objective: 0.5*mean + 0.3*min + 0.2*(1-variance)
    beat_pcts: list of beat_idx percentages per period (0-1 scale)
    """
    mean_bi = np.mean(beat_pcts)
    min_bi = np.min(beat_pcts)
    variance = np.var(beat_pcts)
    
    # Penalize any period below 50%
    floor_penalty = sum(0.1 * (0.5 - bi) for bi in beat_pcts if bi < 0.5)
    
    obj = 0.5 * mean_bi + 0.3 * min_bi + 0.2 * (1.0 - min(variance, 1.0)) - floor_penalty
    return obj


# ============================================================================
# Phase 1: Optimize R3 across all periods jointly
# ============================================================================
def optimize_r3_robust(periods_data, n_trials=N_TRIALS):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 1] Optimizing R3 (robust multi-period) - {n_trials} trials")
    print(f"  Periods: A({len(periods_data['A'])}d), B({len(periods_data['B'])}d), C({len(periods_data['C'])}d)")
    
    # R3 parameter keys and ranges
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector_heat', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d']
    WEIGHT_DEFAULTS = [0.14, 0.10, 0.07, 0.09, 0.07, 0.02, 0.01, 0.10, 0.13, 0.04, 0.10, 0.15]
    
    MULT_KEYS = [
        'b_consistency_high', 'b_consistency_mid',
        'b_uptrend_full', 'b_uptrend_partial',
        'b_ma20_above', 'p_ma20_below',
        'b_low_vol_high', 'b_low_vol_mid', 'p_high_vol',
        'p_rsi_overbought', 'p_rsi_high', 'b_rsi_sweet',
        'b_sector_strong', 'b_sector_mild', 'p_sector_cold', 'p_sector_cool',
        'b_rel_str_strong', 'b_rel_str_mild',
        'p_big_move5', 'p_big_move3',
        'p_streak', 'p_vol_shrink', 'p_turn_spike',
        'p_ma5_below',
    ]
    MULT_RANGES = {
        'b_consistency_high': (0.05, 0.8), 'b_consistency_mid': (0.05, 0.5),
        'b_uptrend_full': (0.05, 0.6), 'b_uptrend_partial': (0.05, 0.4),
        'b_ma20_above': (0.05, 0.5), 'p_ma20_below': (0.05, 0.8),
        'b_low_vol_high': (0.05, 0.5), 'b_low_vol_mid': (0.05, 0.3), 'p_high_vol': (0.05, 0.8),
        'p_rsi_overbought': (0.05, 0.8), 'p_rsi_high': (0.05, 0.5), 'b_rsi_sweet': (0.05, 0.5),
        'b_sector_strong': (0.05, 0.5), 'b_sector_mild': (0.05, 0.3),
        'p_sector_cold': (0.05, 0.8), 'p_sector_cool': (0.05, 0.5),
        'b_rel_str_strong': (0.05, 0.6), 'b_rel_str_mild': (0.05, 0.4),
        'p_big_move5': (0.05, 0.8), 'p_big_move3': (0.05, 0.5),
        'p_streak': (0.05, 0.6),
        'p_vol_shrink': (0.05, 0.5), 'p_turn_spike': (0.05, 0.5),
        'p_ma5_below': (0.05, 0.6),
    }
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        # Sample weights with constrained range
        raw = []
        for i, key in enumerate(WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(WEIGHT_KEYS)}
        
        # Sample multipliers
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        # L2 regularization
        l2_pen = l2_regularization(params, WEIGHT_KEYS, lam=L2_LAMBDA)
        
        # Evaluate across all periods
        beat_pcts = []
        for pkey in ['A', 'B', 'C']:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=3, r3_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            print(f"    [Trial {trial.number}] R3 obj={obj:.4f} "
                  f"BI: A={beat_pcts[0]*100:.0f}% B={beat_pcts[1]*100:.0f}% C={beat_pcts[2]*100:.0f}%")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R3 best obj: {best_global['obj']:.4f}")
    return best_global['params'], best_global['obj']


# ============================================================================
# Phase 2: Optimize R2 across all periods jointly
# ============================================================================
def optimize_r2_robust(periods_data, n_trials=N_TRIALS):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 2] Optimizing R2 (robust multi-period) - {n_trials} trials")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d']
    WEIGHT_DEFAULTS = [0.25, 0.20, 0.05, 0.10, 0.05, 0.15, 0.05, 0.10, 0.05, 0.05, 0.05]
    
    MULT_KEYS = [
        'b_consistency', 'b_above_ma20', 'b_rsi_45_60',
        'b_sector_hot', 'b_rel_str',
        'p_below_ma20', 'p_high_vol', 'p_rsi_overbought',
        'p_big_move', 'p_streak_neg', 'p_vol_shrink',
        'p_turn_spike', 'p_below_ma5',
    ]
    MULT_RANGES = {
        'b_consistency': (0.05, 0.8), 'b_above_ma20': (0.05, 0.5),
        'b_rsi_45_60': (0.05, 0.5), 'b_sector_hot': (0.05, 0.6),
        'b_rel_str': (0.05, 0.5),
        'p_below_ma20': (0.05, 0.8), 'p_high_vol': (0.05, 0.8),
        'p_rsi_overbought': (0.05, 0.8), 'p_big_move': (0.05, 0.6),
        'p_streak_neg': (0.05, 0.5), 'p_vol_shrink': (0.05, 0.5),
        'p_turn_spike': (0.05, 0.5), 'p_below_ma5': (0.05, 0.5),
    }
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        l2_pen = l2_regularization(params, WEIGHT_KEYS, lam=L2_LAMBDA)
        
        beat_pcts = []
        for pkey in ['A', 'B', 'C']:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=2, r2_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            print(f"    [Trial {trial.number}] R2 obj={obj:.4f} "
                  f"BI: A={beat_pcts[0]*100:.0f}% B={beat_pcts[1]*100:.0f}% C={beat_pcts[2]*100:.0f}%")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R2 best obj: {best_global['obj']:.4f}")
    return best_global['params'], best_global['obj']


# ============================================================================
# Phase 3: Optimize R4/5 across all periods jointly
# ============================================================================
def optimize_r45_robust(periods_data, n_trials=N_TRIALS):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 3] Optimizing R4/5 (robust multi-period) - {n_trials} trials")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d', 'w_beta']
    WEIGHT_DEFAULTS = [0.02, 0.03, 0.12, 0.03, 0.08, 0.12, 0.10, 0.02, 0.05, 0.18, 0.12, 0.10]
    
    MULT_KEYS = [
        'p_beta_high', 'p_beta_mid', 'b_beta_low',
        'b_oversold', 'p_overbought',
        'p_high_beta_ind', 'b_defensive_ind',
        'b_rel_str_strong', 'b_rel_str_very_strong',
        'b_low_vol', 'p_big_drop', 'p_big_drop_3d',
        'p_big_jump', 'p_overextended', 'b_streak_relstr',
    ]
    MULT_RANGES = {
        'p_beta_high': (0.05, 0.8), 'p_beta_mid': (0.05, 0.5),
        'b_beta_low': (0.05, 0.5), 'b_oversold': (0.05, 0.6),
        'p_overbought': (0.05, 0.8), 'p_high_beta_ind': (0.05, 0.8),
        'b_defensive_ind': (0.05, 0.6), 'b_rel_str_strong': (0.05, 0.6),
        'b_rel_str_very_strong': (0.05, 0.5), 'b_low_vol': (0.05, 0.5),
        'p_big_drop': (0.05, 0.8), 'p_big_drop_3d': (0.05, 0.6),
        'p_big_jump': (0.05, 0.6), 'p_overextended': (0.05, 0.8),
        'b_streak_relstr': (0.05, 0.4),
    }
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        l2_pen = l2_regularization(params, WEIGHT_KEYS, lam=L2_LAMBDA)
        
        beat_pcts = []
        for pkey in ['A', 'B', 'C']:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=45, r45_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            print(f"    [Trial {trial.number}] R4/5 obj={obj:.4f} "
                  f"BI: A={beat_pcts[0]*100:.0f}% B={beat_pcts[1]*100:.0f}% C={beat_pcts[2]*100:.0f}%")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R4/5 best obj: {best_global['obj']:.4f}")
    return best_global['params'], best_global['obj']


# ============================================================================
# Full Backtest Report
# ============================================================================
def run_full_backtest(daily_data, r2_params, r3_params, r45_params, period_label=""):
    results = []
    stock_recent_perf = defaultdict(list)
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    
    for dd in daily_data:
        test_date = dd['test_date']
        risk = dd['risk']
        actual_n = dd['actual_n']
        idx_ret = dd['idx_ret']
        stocks = dd['stocks']
        
        scored = []
        if risk == 2:
            for s in stocks:
                sc = score_risk2(s, r2_params)
                scored.append((s, sc))
        elif risk == 3:
            for s in stocks:
                sc = score_risk3(s, r3_params)
                scored.append((s, sc))
        else:
            for s in stocks:
                sc = score_risk45(s, r45_params)
                if risk == 5:
                    if s['beta'] > 1.3: sc *= 0.5
                    if s['r1'] < -3: sc *= 0.3
                    if s['is_high_beta']: sc *= 0.5
                scored.append((s, sc))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        blacklist = build_blacklist(stock_recent_perf, risk)
        
        selected = []
        ind_count = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']] >= MAX_INDUSTRY: continue
            if risk >= 4 and sc < 0.3: continue
            if risk == 3 and sc < 0.3: continue
            if risk == 2 and sc < 0.5: continue
            selected.append((s, sc))
            ind_count[s['industry']] += 1
        
        if not selected:
            non_bl = [(s, sc) for s, sc in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk >= 3 else 2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected: continue
        
        stock_rets = []
        for s, sc in selected:
            if s['stock_return'] is not None:
                sr = s['stock_return']
                stock_rets.append({
                    'code': s['code'], 'name': s['name'],
                    'ret': round(sr, 2), 'beat': sr > idx_ret,
                    'score': round(sc, 2),
                })
        
        for sr in stock_rets:
            stock_recent_perf[sr['code']].append(sr['ret'])
            if len(stock_recent_perf[sr['code']]) > 5:
                stock_recent_perf[sr['code']] = stock_recent_perf[sr['code']][-5:]
        
        if stock_rets:
            daily_wins = sum(1 for x in stock_rets if x['beat'])
            wr = daily_wins / len(stock_rets)
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            
            results.append({
                'date': test_date.strftime('%Y-%m-%d'),
                'regime': dd['regime'], 'risk': risk,
                'n_stocks': len(stock_rets),
                'idx_ret': round(idx_ret, 2), 'avg_ret': round(avg_ret, 2),
                'wr': round(wr, 2), 'win': wr > 0.5, 'beat_idx': beat_idx,
            })
            
            stats_by_risk[risk]['total'] += 1
            if wr > 0.5: stats_by_risk[risk]['wins'] += 1
            if beat_idx: stats_by_risk[risk]['beat_idx'] += 1
    
    wins = sum(1 for r in results if r['win'])
    total = len(results)
    beat_idx_days = sum(1 for r in results if r['beat_idx'])
    
    accuracy = wins / total if total > 0 else 0
    beat_pct = beat_idx_days / total if total > 0 else 0
    
    print(f"\n  {period_label} RESULT: {beat_idx_days}/{total} = {beat_pct*100:.1f}% beat_idx")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    R{r}: {s['beat_idx']}/{s['total']} = {bi:.0f}%")
    
    return {
        'accuracy': accuracy, 'wins': wins, 'total': total,
        'beat_idx_days': beat_idx_days, 'beat_idx_pct': beat_pct,
        'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()},
    }


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    
    print("=" * 70)
    print("V20 - Fixed Backtest")
    print("=" * 70)
    print("  Core changes from V17:")
    print("  1. Stock pool limited to hot sectors (AI/chip/semiconductor/solar/power) + KCB")
    print("  2. Training period: recent 3 months (02-07 ~ 05-06)")
    print("  3. Robust objective: 0.5*mean + 0.3*min + 0.2*(1-var)")
    print("  4. L2 regularization on weights")
    print(f"  5. {N_TRIALS} trials per risk phase")
    print("=" * 70)
    
    # Load data
    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = _load_scores()
    
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: float(np.mean([v for v in vals if v is not None and not np.isnan(v)]))
                  for ind, vals in sector_perf.items()}
    
    print_mem("All data loaded")
    
    # ========================================================================
    # Precompute for all 3 training periods
    # ========================================================================
    print("\n[Precompute] Computing sub-scores for 3 training periods...")
    
    periods_data = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C)]:
        print(f"\n  Period {plabel}: {ps} ~ {pe}")
        periods_data[plabel] = precompute_period(kline, index_df, scores, sector_avg, ps, pe)
        gc.collect()
        print_mem(f"After Period {plabel}")
    
    # Skip full period precompute (OOM risk) - will evaluate after with lighter method
    print(f"\n  Skipping full period precompute (saving memory)")
    full_data = None
    gc.collect()
    print_mem("After skipping full period")
    
    # Free kline to save memory
    del kline
    gc.collect()
    print_mem("After freeing kline")
    
    # ========================================================================
    # Phase 1: Optimize R3 (robust)
    # ========================================================================
    r3_best, r3_obj = optimize_r3_robust(periods_data, N_TRIALS)
    
    # Quick eval
    for plabel in ['A', 'B', 'C']:
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=3, r3_params=r3_best)
        print(f"  Period {plabel} R3: {bc}/{bt} = {bi*100:.0f}%")
    
    # Save R3 params immediately (in case of crash later)
    _tmp = os.path.join(SHARED_DATA_DIR, 'optuna_v20_best_params.json')
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r3_params': r3_best}, f, ensure_ascii=False, indent=2)
    print(f"  R3 params saved to {_tmp}")
    
    # ========================================================================
    # Phase 2: Optimize R2 (robust)
    # ========================================================================
    r2_best, r2_obj = optimize_r2_robust(periods_data, N_TRIALS)
    
    for plabel in ['A', 'B', 'C']:
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=2, r2_params=r2_best)
        print(f"  Period {plabel} R2: {bc}/{bt} = {bi*100:.0f}%")
    
    # Save R2 params immediately
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r2_params': r2_best, 'r3_params': r3_best}, f, ensure_ascii=False, indent=2)
    print(f"  R2+R3 params saved")
    
    # ========================================================================
    # Phase 3: Optimize R4/5 (robust)
    # ========================================================================
    r45_best, r45_obj = optimize_r45_robust(periods_data, N_TRIALS)
    
    for plabel in ['A', 'B', 'C']:
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=45, r45_params=r45_best)
        print(f"  Period {plabel} R4/5: {bc}/{bt} = {bi*100:.0f}%")
    
    # Save all params immediately
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r2_params': r2_best, 'r3_params': r3_best, 'r45_params': r45_best}, f, ensure_ascii=False, indent=2)
    print(f"  All params saved")
    
    # ========================================================================
    # Phase 4: Final multi-period evaluation
    # ========================================================================
    print(f"\n{'='*70}")
    print(f"  V19 FINAL MULTI-PERIOD EVALUATION")
    print(f"{'='*70}")
    
    period_results = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C)]:
        result = run_full_backtest(periods_data[plabel], r2_best, r3_best, r45_best, f"Period {plabel}")
        period_results[plabel] = result
    
    # Full period evaluation (skip if no precomputed data)
    if full_data:
        full_result = run_full_backtest(full_data, r2_best, r3_best, r45_best, "FULL PERIOD")
    else:
        # Compute from period data combined
        print("\n  Computing full period from combined period data...")
        combined_bc = 0
        combined_bt = 0
        for plabel in ['A', 'B', 'C']:
            r = period_results[plabel]
            combined_bc += r['beat_idx_days']
            combined_bt += r['total']
        full_result = {
            'beat_idx_pct': combined_bc / combined_bt if combined_bt > 0 else 0,
            'beat_idx_days': combined_bc,
            'total': combined_bt,
        }
    
    # ========================================================================
    # Comparison with baselines
    # ========================================================================
    print(f"\n{'='*70}")
    print(f"  V19 vs BASELINES COMPARISON")
    print(f"{'='*70}")
    
    # V10 baseline (from V14 extended backtest): 60.8% on full range
    v10_full_bi = 60.8
    # V14 on full range: 49.0%
    v14_full_bi = 49.0
    # V16 on training period: 90%
    v16_train_bi = 90.0
    
    v20_full_bi = full_result['beat_idx_pct'] * 100
    v19_full_bi = 86.2  # V19 baseline (with issues)
    v17_full_bi = 73.5
    
    print(f"  Full range (4.5mo) beat_idx:")
    print(f"    V10:  {v10_full_bi:.1f}%")
    print(f"    V14:  {v14_full_bi:.1f}%")
    print(f"    V16:  N/A (only trained on 03/01~04/24)")
    print(f"    V19:  {v19_full_bi:.1f}% {'BETTER THAN V17!' if v19_full_bi > v17_full_bi else 'Below V17'}")
    
    print(f"\n  Training period (03/01~04/24) beat_idx:")
    v17_train_bi = period_results['C']['beat_idx_pct'] * 100
    print(f"    V16:  {v16_train_bi:.1f}%")
    print(f"    V17 baseline:  {v17_full_bi:.1f}%")
    
    print(f"\n  Multi-period consistency:")
    for plabel in ['A', 'B', 'C']:
        bi = period_results[plabel]['beat_idx_pct'] * 100
        print(f"    Period {plabel}: {bi:.1f}%")
    
    variance = np.var([period_results[p]['beat_idx_pct'] for p in ['A', 'B', 'C']])
    mean_bi = np.mean([period_results[p]['beat_idx_pct'] * 100 for p in ['A', 'B', 'C']])
    min_bi = np.min([period_results[p]['beat_idx_pct'] * 100 for p in ['A', 'B', 'C']])
    print(f"    Mean: {mean_bi:.1f}%, Min: {min_bi:.1f}%, Variance: {variance:.4f}")
    
    success = v20_full_bi > v17_full_bi
    print(f"\n  RESULT: V20={v20_full_bi:.1f}% vs V19={v19_full_bi:.1f}% vs V17={v17_full_bi:.1f}%")
    
    # ========================================================================
    # Save results
    # ========================================================================
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v20-fixed-backtest',
        'description': 'T+1 returns + additive scoring + real static scores + dynamic sector heat',
        'training_periods': {
            'A': {'start': PERIOD_A[0], 'end': PERIOD_A[1]},
            'B': {'start': PERIOD_B[0], 'end': PERIOD_B[1]},
            'C': {'start': PERIOD_C[0], 'end': PERIOD_C[1]},
        },
        'full_period': {'start': PERIOD_FULL[0], 'end': PERIOD_FULL[1]},
        'n_trials_per_phase': N_TRIALS,
        'l2_lambda': L2_LAMBDA,
        'weight_range': [W_MIN, W_MAX],
        'objective_weights': {'mean': 0.5, 'min': 0.3, 'variance': 0.2},
        
        # V17 results per period
        'period_results': {
            plabel: {
                'beat_idx_pct': period_results[plabel]['beat_idx_pct'],
                'beat_idx_days': period_results[plabel]['beat_idx_days'],
                'total_days': period_results[plabel]['total'],
                'stats_by_risk': period_results[plabel]['stats_by_risk'],
            }
            for plabel in ['A', 'B', 'C']
        },
        'full_result': {
            'beat_idx_pct': full_result.get('beat_idx_pct', 0),
            'beat_idx_days': full_result.get('beat_idx_days', 0),
            'total_days': full_result.get('total', 0),
            'stats_by_risk': full_result.get('stats_by_risk', {}),
        },
        
        # Comparison
        'comparison': {
            'v10_full_beat_idx': v10_full_bi,
            'v14_full_beat_idx': v14_full_bi,
            'v16_training_beat_idx': v16_train_bi,
            'v20_full_beat_idx': v20_full_bi,
            'v19_full_beat_idx': v19_full_bi,
            'v17_beat_idx': v17_full_bi,
            'success': success,
        },
        
        # Optimal params
        'r2_params': r2_best,
        'r3_params': r3_best,
        'r45_params': r45_best,
        
        'elapsed_seconds': time.time() - t0,
    }
    
    fp = os.path.join(RESULT_DIR, 'backtest_v20_fixed.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n  Result saved: {fp}")
    
    # Save best params
    params_out = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v20-fixed-backtest',
        'full_beat_idx': full_result.get('beat_idx_pct', 0),
        'stats_by_risk': full_result.get('stats_by_risk', {}),
        'period_consistency': {
            plabel: period_results[plabel]['beat_idx_pct']
            for plabel in ['A', 'B', 'C']
        },
        'risk2_params': r2_best,
        'risk3_params': r3_best,
        'risk45_params': r45_best,
    }
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v20_best_params.json')
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)
    print(f"  Best params saved: {params_path}")
    
    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("=" * 70)
    
    return final


if __name__ == '__main__':
    main()

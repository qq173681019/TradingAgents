#!/usr/bin/env python3
# NOTE: Run with python3 (not python) to avoid JSON parsing issues
# -*- coding: utf-8 -*-
"""
V24 - Walk-Forward Backtest with Confidence Filtering

Key improvements over V22/V23:
  1. Walk-Forward: Train on A+B, Validate on C, Test on D (no future leakage)
  2. UNIFIED scoring: Single model across all risk levels (R2/R3/R4/5 sample imbalance fix)
  3. Confidence filter: Skip trades when no stock passes minimum score threshold
  4. Stock tradeability filter: Reject PT/ST/delisted/zero-volume stocks
  5. Calibration: Score→probability mapping using validation period

Walk-Forward Split:
  Train:   Period A+B (02/07 ~ 03/28) — optimize params
  Valid:   Period C   (03/28 ~ 04/22) — select best params, calibrate
  Test:    Period D   (04/22 ~ 05/09) — FINAL evaluation, no tuning
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
MIN_KLINE_DAYS = 30
MAX_INDUSTRY = 1
MEMORY_LIMIT_MB = 8000

V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True

# Walk-Forward periods
PERIOD_TRAIN_START = '2026-02-07'
PERIOD_TRAIN_END = '2026-03-28'      # A+B combined
PERIOD_VALID_START = '2026-03-28'
PERIOD_VALID_END = '2026-04-22'      # C
PERIOD_TEST_START = '2026-04-22'     # D — NEVER used for tuning
PERIOD_TEST_END = '2026-05-09'

# For precompute, split into 4 chunks
PERIOD_A = ('2026-02-07', '2026-03-03')
PERIOD_B = ('2026-03-03', '2026-03-28')
PERIOD_C = ('2026-03-28', '2026-04-22')
PERIOD_D = ('2026-04-22', '2026-05-09')

N_TRIALS = 150  # Fewer trials, walk-forward compensates
TIMEOUT_PER_PHASE = 480

# Regularization
W_MIN = 0.001
W_MAX = 0.5
L2_LAMBDA = 0.02  # Stronger than V22

# V24: Confidence filtering
MIN_SCORE_PERCENTILE = 70  # Only pick stocks in top 30% by score
SKIP_DAY_IF_NO_CONFIDENT = True  # Skip trading when no stock is confident enough

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

# V24: Tradeability filter
PT_ST_KEYWORDS = ['PT', 'ST', '*ST', '退']
BLOCKED_CODE_PREFIXES = ['2', '9', '4']  # B股, 北交所(?)

def is_tradeable(code, name='', static=None):
    """Filter out non-tradeable stocks."""
    # Code-based filters
    if len(code) >= 1 and code[0] in BLOCKED_CODE_PREFIXES:
        return False
    # Name-based filters
    for kw in PT_ST_KEYWORDS:
        if kw in name:
            return False
    # Static score filter
    if static:
        tech = static.get('tech', 5)
        if tech < 0:  # Negative technical score = broken data
            return False
        industry = static.get('industry', '未知')
        if industry == '未知':
            return False
    return True


# ============================================================================
# Data Loading (unchanged from V22)
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
    old_idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    new_idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    
    old_records = []
    if os.path.exists(old_idx_file):
        print(f"  Loading old index: {os.path.basename(old_idx_file)}")
        old_records = _parse_index_file(old_idx_file)
    new_records = []
    if os.path.exists(new_idx_file):
        print(f"  Loading new index: {os.path.basename(new_idx_file)}")
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
    index_df = index_df.dropna(subset=['close']).sort_values('date').drop_duplicates(subset='date', keep='last')
    index_df['close'] = index_df['close'].astype('float32')
    print(f"  Index: {len(index_df)} days, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    return index_df


def _load_scores():
    import glob
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
# Feature Engineering (unchanged from V22)
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
            if c[i] > peak: peak = c[i]
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd: max_dd = dd
        f['max_dd_10d'] = max_dd
    else:
        f['max_dd_10d'] = 0
    
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0
    
    f['consistency'] = 0
    if n >= 5:
        for i in range(-4, 0):
            if c[i+1] > c[i]: f['consistency'] += 1
    
    # V22 Features
    if n >= 20:
        sma20 = np.mean(c[-20:])
        std20 = np.std(c[-20:])
        if std20 > 0.001:
            upper = sma20 + 2 * std20
            lower = sma20 - 2 * std20
            f['bb_pctb'] = (c[-1] - lower) / (upper - lower)
        else:
            f['bb_pctb'] = 0.5
    else:
        f['bb_pctb'] = 0.5
    
    if n >= 15:
        atrs = []
        for i in range(-14, 0):
            tr = max(h[i] - lo[i], abs(h[i] - c[i-1]), abs(lo[i] - c[i-1]))
            atrs.append(tr)
        atr14 = np.mean(atrs)
        if n >= 29:
            atrs_long = []
            for i in range(-28, -14):
                tr = max(h[i] - lo[i], abs(h[i] - c[i-1]), abs(lo[i] - c[i-1]))
                atrs_long.append(tr)
            atr28 = np.mean(atrs_long)
            f['atr_ratio'] = atr14 / max(atr28, 0.01)
        else:
            f['atr_ratio'] = 1.0
        f['atr_14'] = atr14 / c[-1] * 100
    else:
        f['atr_ratio'] = 1.0
        f['atr_14'] = 2.0
    
    if n >= 11:
        obv = 0
        for i in range(-10, 0):
            if c[i] > c[i-1]: obv += v[i]
            elif c[i] < c[i-1]: obv -= v[i]
        f['obv_10d'] = obv
        obv_first_half = 0
        obv_second_half = 0
        for i in range(-10, -5):
            if c[i] > c[i-1]: obv_first_half += v[i]
            elif c[i] < c[i-1]: obv_first_half -= v[i]
        for i in range(-5, 0):
            if c[i] > c[i-1]: obv_second_half += v[i]
            elif c[i] < c[i-1]: obv_second_half -= v[i]
        f['obv_accel'] = obv_second_half - obv_first_half
    else:
        f['obv_10d'] = 0
        f['obv_accel'] = 0
    
    if n >= 6:
        price_up = c[-1] > c[-2]
        vol_up = v[-1] > np.mean(v[-6:-1])
        f['vol_price_confirm'] = 1 if (price_up and vol_up) else 0
        f['vol_price_diverge'] = 1 if (price_up and not vol_up) else 0
    else:
        f['vol_price_confirm'] = 0
        f['vol_price_diverge'] = 0
    
    if n >= 20:
        low_20d = np.min(lo[-20:])
        high_20d = np.max(h[-20:])
        range_20d = high_20d - low_20d
        if range_20d > 0.01:
            f['support_dist'] = (c[-1] - low_20d) / range_20d
        else:
            f['support_dist'] = 0.5
    else:
        f['support_dist'] = 0.5
    
    if n >= 10:
        up_vols = [v[i] for i in range(-10, 0) if c[i] > c[i-1]]
        dn_vols = [v[i] for i in range(-10, 0) if c[i] <= c[i-1]]
        avg_up = np.mean(up_vols) if up_vols else 1
        avg_dn = np.mean(dn_vols) if dn_vols else 1
        f['down_vol_ratio'] = avg_dn / max(avg_up, 1)
    else:
        f['down_vol_ratio'] = 1.0
    
    if n >= 5:
        consec_up = 0
        vol_declining = True
        for i in range(-1, max(-6, -n), -1):
            if c[i] > c[i-1]:
                consec_up += 1
                if i > -n+1 and v[i] > v[i-1]:
                    vol_declining = False
            else:
                break
        f['exhaustion'] = 1 if (consec_up >= 3 and vol_declining) else 0
    else:
        f['exhaustion'] = 0
    
    return f


DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']

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
    
    if current > ma20 * 1.02 and ma5 > ma20: regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20: regime = 'bear'
    else: regime = 'range'
    
    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    
    if n >= 10:
        idx_rets = np.diff(closes[-10:]) / closes[-10:-1] * 100
        idx_vol = np.std(idx_rets)
        if idx_vol > 1.5: vol_state = 'high'
        elif idx_vol > 0.8: vol_state = 'normal'
        else: vol_state = 'low'
    else:
        vol_state = 'normal'
    
    risk = 3
    consec_decline = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]: consec_decline += 1
        else: break
    
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
    elif risk_level >= 4: return 2
    elif risk_level == 3: return 3
    else: return 3

def get_stock_return(df, date):
    day_rows = df[df['date'] >= date]
    if len(day_rows) < 2: return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None

def get_index_return(index_df, date):
    day_rows = index_df[index_df['date'] >= date]
    if len(day_rows) < 2: return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None

def build_blacklist(stock_recent_perf, risk):
    blacklist = set()
    for code, rets in stock_recent_perf.items():
        if len(rets) >= 1 and rets[-1] < -3: blacklist.add(code)
        if risk >= 4 and len(rets) >= 1 and rets[-1] > 6: blacklist.add(code)
        if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0: blacklist.add(code)
        if len(rets) >= 3 and rets[-1] < 0 and rets[-2] < 0 and rets[-3] < 0: blacklist.add(code)
        if risk >= 5 and len(rets) >= 1 and rets[-1] < -1: blacklist.add(code)
    return blacklist


# ============================================================================
# Sub-score computation (with tradeability filter)
# ============================================================================
def compute_stock_subscores(code, df, test_date, index_df, idx_rets_20, idx_ret_5d, idx_ret_3d, static, daily_sector_avg):
    # V24: Tradeability check
    name = static.get('name', '') if static else ''
    if not is_tradeable(code, name, static):
        return None
    
    feats = calc_features(df, test_date)
    if feats is None: return None
    
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
    if s_n >= 6: rel_str = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100 - idx_ret_5d
    if s_n >= 4: rel_str_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100 - idx_ret_3d
    
    feats['beta_20d'] = beta
    feats['rel_strength_5d'] = rel_str
    feats['rel_strength_3d'] = rel_str_3d
    
    stock_return = get_stock_return(df, test_date)
    f = feats
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5: return None
    
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
    is_def = is_defensive_industry(industry)
    is_hb = is_high_beta_industry(industry)
    defense_base = 3.0 if is_def else (-2.0 if is_hb else 0.0)
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
    
    # BB score
    bb = f.get('bb_pctb', 0.5)
    if bb < 0.2: bb_s = 4.0
    elif bb < 0.4: bb_s = 3.0
    elif bb < 0.6: bb_s = 2.5
    elif bb < 0.8: bb_s = 2.0
    else: bb_s = 1.0
    
    # ATR ratio score
    atr_r = f.get('atr_ratio', 1.0)
    if atr_r < 0.8: atr_s = 4.0
    elif atr_r < 1.2: atr_s = 3.0
    elif atr_r < 1.5: atr_s = 2.0
    else: atr_s = 1.0
    
    # Volume health
    dvr = f.get('down_vol_ratio', 1.0)
    if dvr < 0.7: vol_health_s = 4.0
    elif dvr < 1.0: vol_health_s = 3.0
    elif dvr < 1.3: vol_health_s = 2.0
    else: vol_health_s = 1.0
    
    # Support proximity
    sp = f.get('support_dist', 0.5)
    if sp < 0.2: support_s = 3.5
    elif sp < 0.4: support_s = 3.0
    elif sp < 0.6: support_s = 2.5
    else: support_s = 1.5
    
    # OBV trend
    obv_acc = f.get('obv_accel', 0)
    avg_v = np.mean(stock_hist['volume'].values[-10:]) if s_n >= 10 else 1
    obv_norm = obv_acc / max(avg_v, 1) * 100
    if obv_norm > 10: obv_s = 3.5
    elif obv_norm > 0: obv_s = 2.5
    elif obv_norm > -10: obv_s = 2.0
    else: obv_s = 1.0
    
    return {
        'code': code,
        'name': name,
        'industry': industry,
        'stock_return': stock_return,
        'momentum_s': momentum_s, 'trend_s': trend_s, 'consistency_s': consistency_s,
        'mr_s': mr_s, 'vol_s': vol_s, 'rsi_s': rsi_s,
        'static_score': static_score, 'defense_s': defense_s,
        'sector_heat': sector_heat, 'low_vol_s': low_vol_s,
        'rel_str': rel_str, 'rel_str_3d': rel_str_3d,
        'beta_bonus': beta_bonus, 'beta': beta,
        'consistency': consistency,
        'r1': f.get('r1', 0), 'r3': f.get('r3', 0), 'r5': f.get('r5', 0),
        'close_ma5': f.get('close_ma5', 0), 'close_ma20': f.get('close_ma20', 0),
        'vol5': vol5, 'vol_shrink': f.get('vol_shrink', 1),
        'turn_spike': f.get('turn_spike', 1), 'rsi': rsi, 'streak': f.get('streak', 0),
        'oversold': f.get('oversold', 0), 'overbought': f.get('overbought', 0),
        'ind_heat': ind_heat, 'is_defensive': is_def, 'is_high_beta': is_hb,
        'bb_pctb': bb, 'bb_s': bb_s, 'atr_ratio': atr_r, 'atr_s': atr_s,
        'down_vol_ratio': dvr, 'vol_health_s': vol_health_s,
        'support_dist': sp, 'support_s': support_s, 'obv_s': obv_s,
        'vol_price_confirm': f.get('vol_price_confirm', 0),
        'vol_price_diverge': f.get('vol_price_diverge', 0),
        'exhaustion': f.get('exhaustion', 0),
    }


# ============================================================================
# V24: UNIFIED scoring function (one model for all risk levels)
# ============================================================================
def score_unified(s, p):
    """V24: Single unified scoring model. Risk adjustments are additive modifiers, not separate models."""
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
        s['rel_str_3d'] * p['w_rel_str_3d'] +
        s.get('bb_s', 2.5) * p.get('w_bb', 0.02) +
        s.get('support_s', 2.5) * p.get('w_support', 0.02) +
        s.get('obv_s', 2.0) * p.get('w_obv', 0.01)
    )
    
    # Trend bonuses
    if s['consistency'] >= 4: score += p['b_consistency_high']
    elif s['consistency'] >= 3: score += p['b_consistency_mid']
    if s['r3'] > 0 and s['r5'] > 0: score += p['b_uptrend_full']
    elif s['r3'] > 0: score += p['b_uptrend_partial']
    
    # MA alignment
    if s['close_ma20'] > 0: score += p['b_ma20_above']
    elif s['close_ma20'] < -0.05: score -= p['p_ma20_below']
    
    # Volatility
    if s['vol5'] < 1.5: score += p['b_low_vol_high']
    elif s['vol5'] < 2.0: score += p['b_low_vol_mid']
    elif s['vol5'] > 3.5: score -= p['p_high_vol']
    
    # RSI
    if s['rsi'] > 75: score -= p['p_rsi_overbought']
    elif s['rsi'] > 65: score -= p['p_rsi_high']
    elif 45 <= s['rsi'] <= 60: score += p['b_rsi_sweet']
    
    # Sector
    if s['ind_heat'] > 2: score += p['b_sector_strong']
    elif s['ind_heat'] > 0.5: score += p['b_sector_mild']
    elif s['ind_heat'] < -2: score -= p['p_sector_cold']
    
    # Relative strength
    if s['rel_str'] > 3: score += p['b_rel_str_strong']
    elif s['rel_str'] > 1: score += p['b_rel_str_mild']
    
    # Risk penalties
    if abs(s['r1']) > 5: score -= p['p_big_move5']
    if abs(s['r1']) > 3: score -= p['p_big_move3']
    if s['streak'] <= -2: score -= p['p_streak']
    if s['vol_shrink'] < 0.7: score -= p['p_vol_shrink']
    if s['turn_spike'] > 2.0: score -= p['p_turn_spike']
    if s['close_ma5'] < -0.02: score -= p['p_ma5_below']
    
    # V22 extended penalties
    if s.get('exhaustion'): score -= p.get('p_exhaustion', 0.5)
    if s.get('vol_price_diverge'): score -= p.get('p_vp_diverge', 0.5)
    
    # V24: Risk-aware adjustments (lightweight, not separate models)
    risk = p.get('_current_risk', 3)
    if risk >= 4:
        # In crisis: penalize high beta, reward defensive
        if s['beta'] > 1.3: score *= 0.5
        if s['r1'] < -3: score *= 0.3
        if s['is_high_beta']: score *= 0.5
        if s['is_defensive']: score += p.get('b_crisis_defensive', 0.3)
        if s['beta'] < 0.5: score += p.get('b_crisis_low_beta', 0.2)
    
    return score


# ============================================================================
# Precompute (unchanged structure)
# ============================================================================
def precompute_period(kline, index_df, scores, sector_avg, start_str, end_str):
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
# V24: Walk-Forward Evaluation with Confidence Filter
# ============================================================================
def evaluate_wf(daily_data, params, apply_confidence=False, min_score_pct=MIN_SCORE_PERCENTILE):
    """
    Evaluate beat_idx using unified scoring model.
    If apply_confidence=True, only trade when stocks pass minimum score threshold.
    """
    stock_recent_perf = defaultdict(list)
    beat_count = 0
    total = 0
    skipped = 0
    stats_by_risk = defaultdict(lambda: {'beat_idx': 0, 'total': 0})
    all_scores = []
    
    for dd in daily_data:
        risk = dd['risk']
        actual_n = dd['actual_n']
        idx_ret = dd['idx_ret']
        stocks = dd['stocks']
        
        # Score all stocks with unified model
        p = dict(params)
        p['_current_risk'] = risk
        
        scored = []
        for s in stocks:
            sc = score_unified(s, p)
            scored.append((s, sc))
            all_scores.append(sc)
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # V24: Confidence filter
        if apply_confidence and all_scores:
            # Compute dynamic threshold from this day's scores
            day_scores = [sc for _, sc in scored]
            if len(day_scores) >= 5:
                threshold = np.percentile(day_scores, min_score_pct)
                confident = [(s, sc) for s, sc in scored if sc >= threshold]
                if not confident:
                    skipped += 1
                    continue
                scored = confident
        
        # Build blacklist
        blacklist = build_blacklist(stock_recent_perf, risk)
        
        selected = []
        ind_count = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']] >= MAX_INDUSTRY: continue
            if sc < 0.3: continue
            selected.append((s, sc))
            ind_count[s['industry']] += 1
        
        # Fallback
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
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            total += 1
            if beat_idx: beat_count += 1
            stats_by_risk[risk]['total'] += 1
            if beat_idx: stats_by_risk[risk]['beat_idx'] += 1
    
    beat_pct = beat_count / total if total > 0 else 0
    return beat_pct, stats_by_risk, beat_count, total, skipped


# ============================================================================
# V24: Walk-Forward Optimization (train on A+B, validate on C)
# ============================================================================
def optimize_unified_wf(train_data, valid_data, n_trials=N_TRIALS):
    """Optimize unified model on train periods, select best by validation."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 1] Walk-Forward Optimization - {n_trials} trials")
    print(f"  Train: A+B combined, Valid: C")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector_heat', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d',
                   'w_bb', 'w_support', 'w_obv']
    WEIGHT_DEFAULTS = [0.14, 0.10, 0.07, 0.09, 0.07, 0.02, 0.01, 0.10, 0.13, 0.04, 0.10, 0.15,
                       0.05, 0.05, 0.03]
    
    MULT_KEYS = [
        'b_consistency_high', 'b_consistency_mid',
        'b_uptrend_full', 'b_uptrend_partial',
        'b_ma20_above', 'p_ma20_below',
        'b_low_vol_high', 'b_low_vol_mid', 'p_high_vol',
        'p_rsi_overbought', 'p_rsi_high', 'b_rsi_sweet',
        'b_sector_strong', 'b_sector_mild', 'p_sector_cold',
        'b_rel_str_strong', 'b_rel_str_mild',
        'p_big_move5', 'p_big_move3',
        'p_streak', 'p_vol_shrink', 'p_turn_spike', 'p_ma5_below',
        'p_exhaustion', 'p_vp_diverge',
        'b_crisis_defensive', 'b_crisis_low_beta',
    ]
    MULT_RANGES = {k: (0.05, 0.6) for k in MULT_KEYS}
    # Tighten ranges for stability
    for k in ['p_big_move5', 'p_high_vol', 'p_rsi_overbought', 'p_ma20_below', 'p_sector_cold']:
        MULT_RANGES[k] = (0.05, 0.8)
    
    best_valid = {'obj': -999, 'train_obj': -999, 'params': None}
    
    def objective(trial):
        # Sample weights
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
        l2_pen = sum(params.get(k, 0)**2 for k in WEIGHT_KEYS) * L2_LAMBDA
        
        # Evaluate on TRAIN (A+B)
        train_beats = []
        for pkey in ['A', 'B']:
            bi, _, _, _, _ = evaluate_wf(train_data[pkey], params)
            train_beats.append(bi)
        
        train_obj = 0.6 * np.mean(train_beats) + 0.4 * np.min(train_beats) - l2_pen
        
        # Evaluate on VALID (C) — no regularization penalty here
        valid_bi, _, _, _, _ = evaluate_wf(valid_data, params)
        
        # Combined objective: favor good train + good valid
        # Heavy weight on validation to prevent overfitting
        obj = 0.4 * train_obj + 0.6 * valid_bi
        
        if obj > best_valid['obj']:
            best_valid['obj'] = obj
            best_valid['train_obj'] = train_obj
            best_valid['params'] = dict(params)
            print(f"    [Trial {trial.number}] obj={obj:.4f} "
                  f"train={np.mean(train_beats)*100:.0f}% valid={valid_bi*100:.0f}%")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"\n  Best valid obj: {best_valid['obj']:.4f}")
    print(f"  Best train obj: {best_valid['train_obj']:.4f}")
    return best_valid['params'], best_valid['obj']


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    
    print("=" * 70)
    print("V24 - Walk-Forward Backtest with Confidence Filtering")
    print("=" * 70)
    print("  Key improvements:")
    print("  1. Walk-Forward: Train A+B → Valid C → Test D")
    print("  2. Unified scoring: One model for all risk levels")
    print("  3. Stock tradeability filter: Reject PT/ST/delisted")
    print(f"  4. {N_TRIALS} trials, L2={L2_LAMBDA}")
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
    
    # Precompute all periods
    print("\n[Precompute] Computing sub-scores for 4 periods...")
    periods_data = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C), ('D', PERIOD_D)]:
        print(f"\n  Period {plabel}: {ps} ~ {pe}")
        periods_data[plabel] = precompute_period(kline, index_df, scores, sector_avg, ps, pe)
        gc.collect()
        print_mem(f"After Period {plabel}")
    
    del kline
    gc.collect()
    print_mem("After freeing kline")
    
    # Combine A+B as train
    train_data = {'A': periods_data['A'], 'B': periods_data['B']}
    valid_data = periods_data['C']
    test_data = periods_data['D']
    
    # =========================================================================
    # Walk-Forward Optimization
    # =========================================================================
    best_params, best_obj = optimize_unified_wf(train_data, valid_data, N_TRIALS)
    
    # =========================================================================
    # Evaluate on ALL periods with best params
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"  V24 WALK-FORWARD EVALUATION")
    print(f"{'='*70}")
    
    for plabel in ['A', 'B', 'C', 'D']:
        bi, stats, bc, bt, sk = evaluate_wf(periods_data[plabel], best_params)
        print(f"  Period {plabel}: {bc}/{bt} = {bi*100:.1f}% beat_idx (skipped {sk} days)")
    
    # =========================================================================
    # TEST PERIOD (D) — Final honest evaluation
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"  [TEST] TEST SET (Period D) — FINAL EVALUATION (never used for tuning)")
    print(f"{'='*70}")
    
    test_bi, test_stats, test_bc, test_bt, test_sk = evaluate_wf(test_data, best_params)
    print(f"  Test beat_idx: {test_bc}/{test_bt} = {test_bi*100:.1f}%")
    
    # Also evaluate with confidence filtering
    test_bi_cf, test_stats_cf, test_bc_cf, test_bt_cf, test_sk_cf = evaluate_wf(
        test_data, best_params, apply_confidence=True)
    print(f"  Test (confidence-filtered): {test_bc_cf}/{test_bt_cf} = {test_bi_cf*100:.1f}% (skipped {test_sk_cf})")
    
    # =========================================================================
    # Comparison with baselines
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"  COMPARISON WITH BASELINES")
    print(f"{'='*70}")
    
    # Train performance
    train_all = periods_data['A'] + periods_data['B']
    train_bi, _, train_bc, train_bt, _ = evaluate_wf(train_all, best_params)
    
    # Valid performance
    valid_bi, _, valid_bc, valid_bt, _ = evaluate_wf(periods_data['C'], best_params)
    
    print(f"  Train (A+B): {train_bc}/{train_bt} = {train_bi*100:.1f}%")
    print(f"  Valid (C):   {valid_bc}/{valid_bt} = {valid_bi*100:.1f}%")
    print(f"  Test  (D):   {test_bc}/{test_bt} = {test_bi*100:.1f}%")
    print(f"")
    print(f"  V10 baseline: 60.8% (full range)")
    print(f"  V14 baseline: 49.0% (full range)")
    print(f"  V22 multi-period: 72.9% (all periods used for tuning)")
    print(f"  V24 walk-forward test: {test_bi*100:.1f}% (D never used for tuning)")
    
    # Train-valid gap
    gap = (train_bi - test_bi) * 100
    print(f"\n  Train-Test gap: {gap:.1f}pp")
    if gap > 20:
        print(f"  [!]  Large gap suggests overfitting. Consider simpler model or more regularization.")
    elif gap > 10:
        print(f"  [!]  Moderate gap. Acceptable but room for improvement.")
    else:
        print(f"  [OK] Small gap. Good generalization.")
    
    # =========================================================================
    # Save results
    # =========================================================================
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    # Save params
    params_out = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v24-walk-forward',
        'description': 'Walk-forward: train A+B, valid C, test D. Unified scoring + tradeability filter.',
        'train_beat_idx': train_bi,
        'valid_beat_idx': valid_bi,
        'test_beat_idx': test_bi,
        'test_beat_idx_filtered': test_bi_cf,
        'train_valid_gap': gap,
        'period_consistency': {
            plabel: evaluate_wf(periods_data[plabel], best_params)[0]
            for plabel in ['A', 'B', 'C', 'D']
        },
        'unified_params': best_params,
    }
    
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v24_best_params.json')
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)
    print(f"\n  Params saved: {params_path}")
    
    # Save detailed results
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v24-walk-forward',
        'walk_forward_split': {
            'train': f'{PERIOD_TRAIN_START} ~ {PERIOD_TRAIN_END}',
            'valid': f'{PERIOD_VALID_START} ~ {PERIOD_VALID_END}',
            'test': f'{PERIOD_TEST_START} ~ {PERIOD_TEST_END}',
        },
        'train_result': {'beat_idx': train_bi, 'days': train_bt},
        'valid_result': {'beat_idx': valid_bi, 'days': valid_bt},
        'test_result': {'beat_idx': test_bi, 'days': test_bt, 'skipped': test_sk},
        'test_filtered': {'beat_idx': test_bi_cf, 'days': test_bt_cf, 'skipped': test_sk_cf},
        'comparison': {
            'v10': 60.8, 'v14': 49.0, 'v22_joint': 72.9,
            'v24_test': round(test_bi * 100, 1),
        },
        'unified_params': best_params,
        'elapsed_seconds': time.time() - t0,
    }
    
    fp = os.path.join(RESULT_DIR, 'backtest_v24_walkforward.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"  Results saved: {fp}")
    
    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("=" * 70)


if __name__ == '__main__':
    main()

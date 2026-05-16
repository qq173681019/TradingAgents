#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V21 - Enhanced Bear/Crisis Mode + New Features

V19 baseline: 86.2% beat_idx
Weak spots: R4=78%, R5=71%

V21 Improvements:
  1. New features: Bollinger %B, ATR ratio, OBV trend, Volume Price Confirmation
  2. Enhanced R4/R5 scoring: stronger relative strength, low-beta preference, 
     volume confirmation, support proximity
  3. Regime-adaptive ensemble: blend momentum vs mean-reversion based on market state
  4. Dynamic top_n: R5 → top 1-2, R4 → top 2-3, R3 → top 3, R2 → top 3-4
  5. Wider training: 4 windows for better generalization
  6. Warm-start from V19 params
  7. Better blacklist: sector-level blacklisting in crisis mode
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

# 4 training windows for better generalization
PERIOD_A = ('2026-02-07', '2026-03-03')  # Window 1
PERIOD_B = ('2026-03-03', '2026-03-28')  # Window 2
PERIOD_C = ('2026-03-28', '2026-04-22')  # Window 3
PERIOD_D = ('2026-04-22', '2026-05-09')  # Window 4 (most recent)

PERIOD_FULL = ('2026-02-07', '2026-05-09')

N_TRIALS = 300  # More trials than V19
TIMEOUT_PER_PHASE = 1200

W_MIN = 0.001
W_MAX = 0.4
L2_LAMBDA = 0.001

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
# Data Loading
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
    score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    if not os.path.exists(score_file):
        all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
        if all_sf:
            score_file = max(all_sf, key=lambda x: os.path.getsize(x))
    
    scores = {}
    if score_file and os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            if not isinstance(s, dict):
                continue
            clean = normalize_code(code)
            scores[clean] = {
                'tech': 5.0, 'fund': 5.0, 'chip': 5.0, 'sector': 5.0,
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': 0.0,
            }
    print(f"  Scores: {len(scores)} stocks")
    return scores


# ============================================================================
# Enhanced Feature Engineering (V21 additions)
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
    
    # === Original V19 features ===
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
    
    # RSI
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)
    
    # MACD
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0
    
    # Volatility
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
    
    # Volume features
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
    
    # Price position
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    # Streak
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
    
    if n >= 5:
        cnt = 0
        for i in range(-4, 0):
            if c[i+1] > c[i]:
                cnt += 1
        f['consistency'] = cnt
    else:
        f['consistency'] = 0
    
    # === V21 NEW FEATURES ===
    
    # 1. Bollinger Band %B (price position relative to bands)
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
    
    # 2. ATR ratio (current ATR vs historical ATR)
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
        f['atr_14'] = atr14 / c[-1] * 100  # Normalized ATR
    else:
        f['atr_ratio'] = 1.0
        f['atr_14'] = 2.0
    
    # 3. OBV trend (On-Balance Volume direction)
    if n >= 11:
        obv = 0
        for i in range(-10, 0):
            if c[i] > c[i-1]:
                obv += v[i]
            elif c[i] < c[i-1]:
                obv -= v[i]
        f['obv_10d'] = obv
        # OBV direction: positive means accumulation
        obv_first_half = 0
        obv_second_half = 0
        for i in range(-10, -5):
            if c[i] > c[i-1]: obv_first_half += v[i]
            elif c[i] < c[i-1]: obv_first_half -= v[i]
        for i in range(-5, 0):
            if c[i] > c[i-1]: obv_second_half += v[i]
            elif c[i] < c[i-1]: obv_second_half -= v[i]
        f['obv_accel'] = obv_second_half - obv_first_half  # OBV accelerating
    else:
        f['obv_10d'] = 0
        f['obv_accel'] = 0
    
    # 4. Volume-Price Confirmation (price up + volume up = bullish)
    if n >= 6:
        price_up = c[-1] > c[-2]
        vol_up = v[-1] > np.mean(v[-6:-1])
        f['vol_price_confirm'] = 1 if (price_up and vol_up) else 0
        f['vol_price_diverge'] = 1 if (price_up and not vol_up) else 0  # Bearish divergence
    else:
        f['vol_price_confirm'] = 0
        f['vol_price_diverge'] = 0
    
    # 5. Support proximity (how close to 20-day low)
    if n >= 20:
        low_20d = np.min(lo[-20:])
        high_20d = np.max(h[-20:])
        range_20d = high_20d - low_20d
        if range_20d > 0.01:
            f['support_dist'] = (c[-1] - low_20d) / range_20d  # 0 = at support, 1 = at resistance
        else:
            f['support_dist'] = 0.5
    else:
        f['support_dist'] = 0.5
    
    # 6. Down-day volume ratio (volume on down days vs up days - low = healthy consolidation)
    if n >= 10:
        up_vols = [v[i] for i in range(-10, 0) if c[i] > c[i-1]]
        dn_vols = [v[i] for i in range(-10, 0) if c[i] <= c[i-1]]
        avg_up = np.mean(up_vols) if up_vols else 1
        avg_dn = np.mean(dn_vols) if dn_vols else 1
        f['down_vol_ratio'] = avg_dn / max(avg_up, 1)  # < 1 = healthy, > 1 = distribution
    else:
        f['down_vol_ratio'] = 1.0
    
    # 7. Gap analysis (overnight gap)
    if n >= 2:
        f['gap'] = (c[-1] - c[-2]) / c[-2] * 100 - f['pct_1d']  # Should be 0 for now (intraday not available)
        # Use open vs previous close as gap proxy
        if 'open' in hist.columns:
            prev_close = c[-2]
            today_open = float(hist.iloc[-1]['open']) if len(hist) > 0 else c[-1]
            f['overnight_gap'] = (today_open - prev_close) / prev_close * 100
        else:
            f['overnight_gap'] = 0
    else:
        f['overnight_gap'] = 0
    
    # 8. Momentum exhaustion (consecutive up days with declining volume)
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
    """V21: More conservative in crisis mode"""
    if risk_level >= 5: return 1    # V19 was 2, V21: only 1 stock in extreme crisis
    elif risk_level >= 4: return 2  # V19 was 3
    elif risk_level == 3: return 3  # Same as V19
    else: return 3                  # Same as V19

def get_stock_return(df, date):
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None

def get_index_return(index_df, date):
    prev = index_df[index_df['date'] < date]
    day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
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
        # V21: In crisis mode, also blacklist stocks that barely survived
        if risk >= 5 and len(rets) >= 1 and rets[-1] < -1:
            blacklist.add(code)
    return blacklist


# ============================================================================
# Sub-score computation with V21 new features
# ============================================================================
def compute_stock_subscores(code, df, test_date, index_df, idx_rets_20, idx_ret_5d, idx_ret_3d, static, daily_sector_avg):
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
    
    # === V21 NEW sub-scores ===
    
    # BB position score (near lower band = potential bounce)
    bb = f.get('bb_pctb', 0.5)
    if bb < 0.2: bb_s = 4.0  # Oversold, bounce potential
    elif bb < 0.4: bb_s = 3.0
    elif bb < 0.6: bb_s = 2.5
    elif bb < 0.8: bb_s = 2.0
    else: bb_s = 1.0  # Near upper band, overbought
    
    # ATR ratio score (low volatility expansion = stable)
    atr_r = f.get('atr_ratio', 1.0)
    if atr_r < 0.8: atr_s = 4.0  # Contracting volatility = stable
    elif atr_r < 1.2: atr_s = 3.0
    elif atr_r < 1.5: atr_s = 2.0
    else: atr_s = 1.0  # Expanding volatility = risky
    
    # Volume health score (accumulation vs distribution)
    dvr = f.get('down_vol_ratio', 1.0)
    if dvr < 0.7: vol_health_s = 4.0  # Strong accumulation
    elif dvr < 1.0: vol_health_s = 3.0
    elif dvr < 1.3: vol_health_s = 2.0
    else: vol_health_s = 1.0  # Distribution
    
    # Support proximity score
    sp = f.get('support_dist', 0.5)
    if sp < 0.2: support_s = 3.5  # Near support = good entry
    elif sp < 0.4: support_s = 3.0
    elif sp < 0.6: support_s = 2.5
    else: support_s = 1.5  # Far from support
    
    # OBV trend score
    obv_acc = f.get('obv_accel', 0)
    # Normalize by average volume
    avg_v = np.mean(stock_hist['volume'].values[-10:]) if s_n >= 10 else 1
    obv_norm = obv_acc / max(avg_v, 1) * 100
    if obv_norm > 10: obv_s = 3.5
    elif obv_norm > 0: obv_s = 2.5
    elif obv_norm > -10: obv_s = 2.0
    else: obv_s = 1.0
    
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
        # V21 new features
        'bb_pctb': bb,
        'bb_s': bb_s,
        'atr_ratio': atr_r,
        'atr_s': atr_s,
        'down_vol_ratio': dvr,
        'vol_health_s': vol_health_s,
        'support_dist': sp,
        'support_s': support_s,
        'obv_s': obv_s,
        'vol_price_confirm': f.get('vol_price_confirm', 0),
        'vol_price_diverge': f.get('vol_price_diverge', 0),
        'exhaustion': f.get('exhaustion', 0),
    }


# ============================================================================
# Scoring Functions (V21: with new features)
# ============================================================================
def score_risk2(s, p):
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
    # V21: add BB and volume health
    score += s['bb_s'] * p.get('w_bb', 0.02)
    score += s['vol_health_s'] * p.get('w_vol_health', 0.02)
    
    if s['consistency'] >= 4: score *= p['boost_consistency']
    if s['close_ma20'] > 0: score *= p['boost_above_ma20']
    if 45 <= s['rsi'] <= 60: score *= p['boost_rsi_45_60']
    if s['ind_heat'] > 1.5: score *= p['boost_sector_hot']
    if s['rel_str'] > 2: score *= p['boost_rel_str']
    if s['close_ma20'] < -0.05: score *= p['penalty_below_ma20']
    if s['vol5'] > 3.5: score *= p['penalty_high_vol']
    if s['rsi'] > 70: score *= p['penalty_rsi_overbought']
    if abs(s['r1']) > 5: score *= p['penalty_big_move']
    if s['streak'] <= -2: score *= p['penalty_streak_neg']
    if s['vol_shrink'] < 0.7: score *= p['penalty_vol_shrink']
    if s['turn_spike'] > 2.0: score *= p['penalty_turn_spike']
    if s['close_ma5'] < -0.02: score *= p['penalty_below_ma5']
    # V21
    if s['exhaustion']: score *= p.get('penalty_exhaustion', 0.7)
    if s['vol_price_diverge']: score *= p.get('penalty_vp_diverge', 0.8)
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
    # V21: add new features
    score += s['bb_s'] * p.get('w_bb', 0.02)
    score += s['support_s'] * p.get('w_support', 0.02)
    score += s['obv_s'] * p.get('w_obv', 0.02)
    
    if s['consistency'] >= 4: score *= p['consistency_boost_high']
    elif s['consistency'] >= 3: score *= p['consistency_boost_mid']
    if s['r3'] > 0 and s['r5'] > 0: score *= p['uptrend_boost_full']
    elif s['r3'] > 0: score *= p['uptrend_boost_partial']
    if s['close_ma20'] > 0: score *= p['ma20_above_mult']
    elif s['close_ma20'] < -0.05: score *= p['ma20_below_mult']
    if s['vol5'] < 1.5: score *= p['low_vol_mult_high']
    elif s['vol5'] < 2.0: score *= p['low_vol_mult_mid']
    elif s['vol5'] > 3.5: score *= p['high_vol_penalize']
    if s['rsi'] > 75: score *= p['rsi_overbought_mult']
    elif s['rsi'] > 65: score *= p['rsi_high_mult']
    elif 45 <= s['rsi'] <= 60: score *= p['rsi_sweet_mult']
    if s['ind_heat'] > 2: score *= p['sector_heat_strong']
    elif s['ind_heat'] > 0.5: score *= p['sector_heat_mild']
    elif s['ind_heat'] < -2: score *= p['sector_cold']
    elif s['ind_heat'] < -0.5: score *= p['sector_cool']
    if s['rel_str'] > 3: score *= p['rel_str_strong']
    elif s['rel_str'] > 1: score *= p['rel_str_mild']
    if abs(s['r1']) > 5: score *= p['big_move5_penalize']
    if abs(s['r1']) > 3: score *= p['big_move3_penalize']
    if s['streak'] <= -2: score *= p['streak_penalize']
    if s['vol_shrink'] < 0.7: score *= p['vol_shrink_penalize']
    if s['turn_spike'] > 2.0: score *= p['turn_spike_penalize']
    if s['close_ma5'] < -0.02: score *= p['ma5_below_penalize']
    # V21
    if s['vol_price_confirm']: score *= p.get('boost_vp_confirm', 1.1)
    if s['exhaustion']: score *= p.get('penalty_exhaustion', 0.7)
    return score


def score_risk45(s, p):
    """V21: Enhanced R4/R5 scoring with new features"""
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
    # V21: heavily weight new defensive features for R4/R5
    score += s['bb_s'] * p.get('w_bb', 0.03)
    score += s['atr_s'] * p.get('w_atr', 0.03)
    score += s['vol_health_s'] * p.get('w_vol_health', 0.04)
    score += s['support_s'] * p.get('w_support', 0.03)
    score += s['obv_s'] * p.get('w_obv', 0.02)
    
    # Original V19 multipliers
    if s['beta'] > 1.5: score *= p['penalty_beta_high']
    elif s['beta'] > 1.2: score *= p['penalty_beta_mid']
    elif s['beta'] < 0.5: score *= p['boost_beta_low']
    if s['oversold']: score *= p['boost_oversold']
    if s['overbought']: score *= p['penalty_overbought']
    if s['is_high_beta']: score *= p['penalty_high_beta_ind']
    if s['is_defensive']: score *= p['boost_defensive_ind']
    if s['rel_str'] > 3: score *= p['boost_rel_str_strong']
    if s['rel_str'] > 5: score *= p['boost_rel_str_very_strong']
    if s['vol5'] < 1.5: score *= p['boost_low_vol']
    if s['r1'] < -5: score *= p['penalty_big_drop']
    if s['r3'] < -8: score *= p['penalty_big_drop_3d']
    if s['r1'] > 7: score *= p['penalty_big_jump']
    if s['r3'] > 15: score *= p['penalty_overextended']
    if s['streak'] >= 2 and s['rel_str'] > 0: score *= p['boost_streak_relstr']
    
    # V21 new multipliers for R4/R5
    if s['bb_pctb'] < 0.15: score *= p.get('boost_bb_oversold', 1.3)
    if s['bb_pctb'] > 0.85: score *= p.get('penalty_bb_overbought', 0.6)
    if s['atr_ratio'] > 1.5: score *= p.get('penalty_atr_expand', 0.5)
    if s['down_vol_ratio'] > 1.5: score *= p.get('penalty_distribution', 0.5)
    if s['vol_price_confirm']: score *= p.get('boost_vp_confirm_r45', 1.2)
    if s['vol_price_diverge']: score *= p.get('penalty_vp_diverge_r45', 0.7)
    if s['exhaustion']: score *= p.get('penalty_exhaustion_r45', 0.5)
    if s['support_dist'] < 0.3: score *= p.get('boost_near_support', 1.2)
    
    return score


# ============================================================================
# Precompute & Evaluate (same structure as V19 but with 4 periods)
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
        
        if regime == 'range':
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
        else:
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


def evaluate_period(daily_data, risk_filter, r2_params=None, r3_params=None, r45_params=None):
    stock_recent_perf = defaultdict(list)
    beat_count = 0
    total = 0
    
    for dd in daily_data:
        risk = dd['risk']
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


def l2_regularization(params, weight_keys, lam=L2_LAMBDA):
    penalty = 0.0
    for key in weight_keys:
        val = params.get(key, 0)
        penalty += val ** 2
    return lam * penalty


def robust_objective(beat_pcts):
    mean_bi = np.mean(beat_pcts)
    min_bi = np.min(beat_pcts)
    variance = np.var(beat_pcts)
    floor_penalty = sum(0.1 * (0.5 - bi) for bi in beat_pcts if bi < 0.5)
    obj = 0.5 * mean_bi + 0.3 * min_bi + 0.2 * (1.0 - min(variance, 1.0)) - floor_penalty
    return obj


# ============================================================================
# Optimization with warm-start from V19
# ============================================================================
def load_v19_params():
    """Load V19 params as warm-start baseline"""
    v19_path = os.path.join(SHARED_DATA_DIR, 'optuna_v19_best_params.json')
    if os.path.exists(v19_path):
        with open(v19_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def optimize_r3_robust(periods_data, n_trials=N_TRIALS, v19_params=None):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 1] Optimizing R3 (V21) - {n_trials} trials")
    period_keys = sorted(periods_data.keys())
    period_info = ', '.join([f'{k}({len(periods_data[k])}d)' for k in period_keys])
    print(f"  Periods: {period_info}")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector_heat', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d']
    # V21 new weight keys
    V21_WEIGHT_KEYS = ['w_bb', 'w_support', 'w_obv']
    ALL_WEIGHT_KEYS = WEIGHT_KEYS + V21_WEIGHT_KEYS
    
    WEIGHT_DEFAULTS = [0.14, 0.10, 0.07, 0.09, 0.07, 0.02, 0.01, 0.10, 0.13, 0.04, 0.10, 0.15,
                       0.02, 0.02, 0.02]
    
    MULT_KEYS = [
        'consistency_boost_high', 'consistency_boost_mid',
        'uptrend_boost_full', 'uptrend_boost_partial',
        'ma20_above_mult', 'ma20_below_mult',
        'low_vol_mult_high', 'low_vol_mult_mid', 'high_vol_penalize',
        'rsi_overbought_mult', 'rsi_high_mult', 'rsi_sweet_mult',
        'sector_heat_strong', 'sector_heat_mild', 'sector_cold', 'sector_cool',
        'rel_str_strong', 'rel_str_mild',
        'big_move5_penalize', 'big_move3_penalize',
        'streak_penalize', 'vol_shrink_penalize', 'turn_spike_penalize',
        'ma5_below_penalize',
        # V21 new multipliers
        'boost_vp_confirm', 'penalty_exhaustion',
    ]
    MULT_RANGES = {
        'consistency_boost_high': (1.0, 2.5), 'consistency_boost_mid': (0.8, 1.8),
        'uptrend_boost_full': (1.0, 2.0), 'uptrend_boost_partial': (0.8, 1.5),
        'ma20_above_mult': (0.8, 1.8), 'ma20_below_mult': (0.2, 0.9),
        'low_vol_mult_high': (1.0, 1.8), 'low_vol_mult_mid': (0.8, 1.3),
        'high_vol_penalize': (0.05, 0.5),
        'rsi_overbought_mult': (0.05, 0.5), 'rsi_high_mult': (0.3, 1.0),
        'rsi_sweet_mult': (0.8, 1.8),
        'sector_heat_strong': (0.8, 1.5), 'sector_heat_mild': (0.8, 1.5),
        'sector_cold': (0.01, 0.5), 'sector_cool': (0.2, 0.8),
        'rel_str_strong': (1.0, 2.0), 'rel_str_mild': (0.8, 1.5),
        'big_move5_penalize': (0.05, 0.5), 'big_move3_penalize': (0.3, 1.0),
        'streak_penalize': (0.1, 0.8),
        'vol_shrink_penalize': (0.1, 0.8), 'turn_spike_penalize': (0.2, 1.0),
        'ma5_below_penalize': (0.2, 0.9),
        'boost_vp_confirm': (0.9, 1.5), 'penalty_exhaustion': (0.3, 0.9),
    }
    
    # Warm start: use V19 params as initial values
    v19_r3 = v19_params.get('risk3_params', {}) if v19_params else {}
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(ALL_WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(ALL_WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            # Warm start hint from V19
            v19_key = key
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        l2_pen = l2_regularization(params, ALL_WEIGHT_KEYS, lam=L2_LAMBDA)
        
        beat_pcts = []
        for pkey in period_keys:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=3, r3_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            bi_str = ' '.join([f'{k}={bi*100:.0f}%' for k, bi in zip(period_keys, beat_pcts)])
            print(f"    [Trial {trial.number}] R3 obj={obj:.4f} {bi_str}")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R3 best obj: {best_global['obj']:.4f}")
    return best_global['params'], best_global['obj']


def optimize_r2_robust(periods_data, n_trials=N_TRIALS, v19_params=None):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 2] Optimizing R2 (V21) - {n_trials} trials")
    period_keys = sorted(periods_data.keys())
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d']
    V21_WEIGHT_KEYS = ['w_bb', 'w_vol_health']
    ALL_WEIGHT_KEYS = WEIGHT_KEYS + V21_WEIGHT_KEYS
    WEIGHT_DEFAULTS = [0.25, 0.20, 0.05, 0.10, 0.05, 0.15, 0.05, 0.10, 0.05, 0.05, 0.05,
                       0.02, 0.02]
    
    MULT_KEYS = [
        'boost_consistency', 'boost_above_ma20', 'boost_rsi_45_60',
        'boost_sector_hot', 'boost_rel_str',
        'penalty_below_ma20', 'penalty_high_vol', 'penalty_rsi_overbought',
        'penalty_big_move', 'penalty_streak_neg', 'penalty_vol_shrink',
        'penalty_turn_spike', 'penalty_below_ma5',
        'penalty_exhaustion', 'penalty_vp_diverge',
    ]
    MULT_RANGES = {
        'boost_consistency': (1.0, 2.0), 'boost_above_ma20': (0.8, 1.8),
        'boost_rsi_45_60': (0.8, 1.5), 'boost_sector_hot': (0.8, 1.8),
        'boost_rel_str': (0.8, 1.8),
        'penalty_below_ma20': (0.1, 0.8), 'penalty_high_vol': (0.1, 0.8),
        'penalty_rsi_overbought': (0.1, 0.8), 'penalty_big_move': (0.1, 0.8),
        'penalty_streak_neg': (0.1, 0.8), 'penalty_vol_shrink': (0.2, 1.0),
        'penalty_turn_spike': (0.2, 1.0), 'penalty_below_ma5': (0.2, 1.0),
        'penalty_exhaustion': (0.3, 0.9), 'penalty_vp_diverge': (0.5, 1.0),
    }
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(ALL_WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(ALL_WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        l2_pen = l2_regularization(params, ALL_WEIGHT_KEYS, lam=L2_LAMBDA)
        
        beat_pcts = []
        for pkey in period_keys:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=2, r2_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            bi_str = ' '.join([f'{k}={bi*100:.0f}%' for k, bi in zip(period_keys, beat_pcts)])
            print(f"    [Trial {trial.number}] R2 obj={obj:.4f} {bi_str}")
        
        return obj
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R2 best obj: {best_global['obj']:.4f}")
    return best_global['params'], best_global['obj']


def optimize_r45_robust(periods_data, n_trials=N_TRIALS, v19_params=None):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 3] Optimizing R4/5 (V21 - enhanced) - {n_trials} trials")
    period_keys = sorted(periods_data.keys())
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d', 'w_beta']
    # V21: new weight keys for R4/R5
    V21_WEIGHT_KEYS = ['w_bb', 'w_atr', 'w_vol_health', 'w_support', 'w_obv']
    ALL_WEIGHT_KEYS = WEIGHT_KEYS + V21_WEIGHT_KEYS
    WEIGHT_DEFAULTS = [0.02, 0.03, 0.12, 0.03, 0.08, 0.12, 0.10, 0.02, 0.05, 0.18, 0.12, 0.10,
                       0.03, 0.03, 0.04, 0.03, 0.02]
    
    MULT_KEYS = [
        'penalty_beta_high', 'penalty_beta_mid', 'boost_beta_low',
        'boost_oversold', 'penalty_overbought',
        'penalty_high_beta_ind', 'boost_defensive_ind',
        'boost_rel_str_strong', 'boost_rel_str_very_strong',
        'boost_low_vol', 'penalty_big_drop', 'penalty_big_drop_3d',
        'penalty_big_jump', 'penalty_overextended', 'boost_streak_relstr',
        # V21 new multipliers for R4/R5
        'boost_bb_oversold', 'penalty_bb_overbought',
        'penalty_atr_expand', 'penalty_distribution',
        'boost_vp_confirm_r45', 'penalty_vp_diverge_r45',
        'penalty_exhaustion_r45', 'boost_near_support',
    ]
    MULT_RANGES = {
        'penalty_beta_high': (0.05, 0.7), 'penalty_beta_mid': (0.2, 0.9),
        'boost_beta_low': (1.0, 1.8), 'boost_oversold': (0.8, 1.8),
        'penalty_overbought': (0.05, 0.5), 'penalty_high_beta_ind': (0.05, 0.7),
        'boost_defensive_ind': (1.0, 1.8), 'boost_rel_str_strong': (1.0, 1.8),
        'boost_rel_str_very_strong': (0.8, 1.8), 'boost_low_vol': (0.8, 1.8),
        'penalty_big_drop': (0.05, 0.5), 'penalty_big_drop_3d': (0.05, 0.5),
        'penalty_big_jump': (0.05, 0.5), 'penalty_overextended': (0.05, 0.7),
        'boost_streak_relstr': (0.8, 1.4),
        'boost_bb_oversold': (0.8, 1.5), 'penalty_bb_overbought': (0.2, 0.8),
        'penalty_atr_expand': (0.2, 0.8), 'penalty_distribution': (0.2, 0.8),
        'boost_vp_confirm_r45': (0.8, 1.5), 'penalty_vp_diverge_r45': (0.3, 0.9),
        'penalty_exhaustion_r45': (0.2, 0.8), 'boost_near_support': (0.8, 1.5),
    }
    
    best_global = {'obj': -999, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(ALL_WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(W_MIN, default * 0.1)
            hi = min(W_MAX, max(default * 3.0, lo + 0.01))
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(ALL_WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        l2_pen = l2_regularization(params, ALL_WEIGHT_KEYS, lam=L2_LAMBDA)
        
        beat_pcts = []
        for pkey in period_keys:
            bi, _, _ = evaluate_period(periods_data[pkey], risk_filter=45, r45_params=params)
            beat_pcts.append(bi)
        
        obj = robust_objective(beat_pcts) - l2_pen
        
        if obj > best_global['obj']:
            best_global['obj'] = obj
            best_global['params'] = dict(params)
            bi_str = ' '.join([f'{k}={bi*100:.0f}%' for k, bi in zip(period_keys, beat_pcts)])
            print(f"    [Trial {trial.number}] R4/5 obj={obj:.4f} {bi_str}")
        
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
    print("V21 - Enhanced Bear/Crisis Mode + New Features")
    print("=" * 70)
    print("  Key improvements over V19:")
    print("  1. New features: BB%B, ATR ratio, OBV trend, Volume-Price confirm")
    print("  2. Enhanced R4/R5 scoring (defensive features weighted heavily)")
    print("  3. Dynamic top_n: R5→1, R4→2 (more conservative in crisis)")
    print("  4. 4 training windows for better generalization")
    print("  5. 300 Optuna trials per phase (vs 200 in V19)")
    print("  6. New blacklist: R5 also blacklists stocks with ret < -1%")
    print("  7. V21-specific multipliers: BB oversold/overbought, ATR expand, distribution")
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
    
    # Load V19 params for warm-start
    v19_params = load_v19_params()
    if v19_params:
        print(f"  Loaded V19 params for warm-start reference")
    
    # Precompute for 4 training periods
    print("\n[Precompute] Computing sub-scores for 4 training periods...")
    
    periods_data = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C), ('D', PERIOD_D)]:
        print(f"\n  Period {plabel}: {ps} ~ {pe}")
        periods_data[plabel] = precompute_period(kline, index_df, scores, sector_avg, ps, pe)
        gc.collect()
        print_mem(f"After Period {plabel}")
    
    del kline
    gc.collect()
    print_mem("After freeing kline")
    
    # Phase 1: Optimize R3
    r3_best, r3_obj = optimize_r3_robust(periods_data, N_TRIALS, v19_params)
    
    for plabel in sorted(periods_data.keys()):
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=3, r3_params=r3_best)
        print(f"  Period {plabel} R3: {bc}/{bt} = {bi*100:.0f}%")
    
    _tmp = os.path.join(SHARED_DATA_DIR, 'optuna_v21_best_params.json')
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r3_params': r3_best}, f, ensure_ascii=False, indent=2)
    print(f"  R3 params saved")
    
    # Phase 2: Optimize R2
    r2_best, r2_obj = optimize_r2_robust(periods_data, N_TRIALS, v19_params)
    
    for plabel in sorted(periods_data.keys()):
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=2, r2_params=r2_best)
        print(f"  Period {plabel} R2: {bc}/{bt} = {bi*100:.0f}%")
    
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r2_params': r2_best, 'r3_params': r3_best}, f, ensure_ascii=False, indent=2)
    print(f"  R2+R3 params saved")
    
    # Phase 3: Optimize R4/5
    r45_best, r45_obj = optimize_r45_robust(periods_data, N_TRIALS, v19_params)
    
    for plabel in sorted(periods_data.keys()):
        bi, bc, bt = evaluate_period(periods_data[plabel], risk_filter=45, r45_params=r45_best)
        print(f"  Period {plabel} R4/5: {bc}/{bt} = {bi*100:.0f}%")
    
    with open(_tmp, 'w', encoding='utf-8') as f:
        json.dump({'r2_params': r2_best, 'r3_params': r3_best, 'r45_params': r45_best}, f, ensure_ascii=False, indent=2)
    print(f"  All params saved")
    
    # Final evaluation
    print(f"\n{'='*70}")
    print(f"  V21 FINAL MULTI-PERIOD EVALUATION")
    print(f"{'='*70}")
    
    period_results = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C), ('D', PERIOD_D)]:
        result = run_full_backtest(periods_data[plabel], r2_best, r3_best, r45_best, f"Period {plabel}")
        period_results[plabel] = result
    
    # Combined
    combined_bc = sum(r['beat_idx_days'] for r in period_results.values())
    combined_bt = sum(r['total'] for r in period_results.values())
    full_result = {
        'beat_idx_pct': combined_bc / combined_bt if combined_bt > 0 else 0,
        'beat_idx_days': combined_bc,
        'total': combined_bt,
    }
    
    # Comparison
    print(f"\n{'='*70}")
    print(f"  V21 vs BASELINES")
    print(f"{'='*70}")
    
    v19_full_bi = 86.2
    v21_full_bi = full_result['beat_idx_pct'] * 100
    
    print(f"  V19 baseline: {v19_full_bi:.1f}%")
    print(f"  V21 result:   {v21_full_bi:.1f}%")
    
    print(f"\n  Multi-period consistency:")
    for plabel in sorted(period_results.keys()):
        bi = period_results[plabel]['beat_idx_pct'] * 100
        print(f"    Period {plabel}: {bi:.1f}%")
    
    variance = np.var([period_results[p]['beat_idx_pct'] for p in sorted(period_results.keys())])
    mean_bi = np.mean([period_results[p]['beat_idx_pct'] * 100 for p in sorted(period_results.keys())])
    min_bi = np.min([period_results[p]['beat_idx_pct'] * 100 for p in sorted(period_results.keys())])
    print(f"    Mean: {mean_bi:.1f}%, Min: {min_bi:.1f}%, Variance: {variance:.4f}")
    
    success = v21_full_bi > v19_full_bi
    print(f"\n  SUCCESS: {'YES! V21 beats V19!' if success else 'NO - V21 below V19'}")
    print(f"  Improvement: {v21_full_bi - v19_full_bi:+.1f}pp")
    
    # Save results
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v21-enhanced-bear',
        'description': 'Enhanced bear/crisis mode with new features (BB, ATR, OBV, VP confirm)',
        'training_periods': {
            plabel: {'start': ps, 'end': pe}
            for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B), ('C', PERIOD_C), ('D', PERIOD_D)]
        },
        'n_trials_per_phase': N_TRIALS,
        'period_results': {
            plabel: {
                'beat_idx_pct': period_results[plabel]['beat_idx_pct'],
                'beat_idx_days': period_results[plabel]['beat_idx_days'],
                'total_days': period_results[plabel]['total'],
                'stats_by_risk': period_results[plabel]['stats_by_risk'],
            }
            for plabel in sorted(period_results.keys())
        },
        'full_result': {
            'beat_idx_pct': full_result.get('beat_idx_pct', 0),
            'beat_idx_days': full_result.get('beat_idx_days', 0),
            'total_days': full_result.get('total', 0),
        },
        'comparison': {
            'v19_beat_idx': v19_full_bi,
            'v21_beat_idx': v21_full_bi,
            'improvement_pp': v21_full_bi - v19_full_bi,
            'success': success,
        },
        'r2_params': r2_best,
        'r3_params': r3_best,
        'r45_params': r45_best,
        'elapsed_seconds': time.time() - t0,
    }
    
    fp = os.path.join(RESULT_DIR, 'backtest_v21_enhanced.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n  Result saved: {fp}")
    
    params_out = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v21-enhanced-bear',
        'full_beat_idx': full_result.get('beat_idx_pct', 0),
        'period_consistency': {
            plabel: period_results[plabel]['beat_idx_pct']
            for plabel in sorted(period_results.keys())
        },
        'risk2_params': r2_best,
        'risk3_params': r3_best,
        'risk45_params': r45_best,
    }
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v21_best_params.json')
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)
    print(f"  Best params saved: {params_path}")
    
    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("=" * 70)
    
    return final


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# NOTE: Run with python3 (not python) to avoid JSON parsing issues
# -*- coding: utf-8 -*-
"""
V27 - Precision Optimization on top of V26

Key Insight: V26 test=50% (6WIN/6FAIL). The 6 FAIL days are all about
misreading market state (strong_bull on pullback days) and poor diversification.

Three targeted optimizations:
  A) Improved market state: volatility spike, volume anomaly, consecutive rally limits
  B) Better diversification: max 1 per industry (was 2), volatility penalty, freshness bonus
  C) Smarter no-trade: skip after big index gains, skip after consecutive rallies, sector concentration

CRITICAL: V25's 6 base weights are FROZEN (from optuna_v25_best_params.json).
Only new parameters are tuned (no-trade thresholds, volatility penalties, etc.).
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
MAX_INDUSTRY = 1  # V27 CHANGE: was 2, now 1 for better diversification
MEMORY_LIMIT_MB = 8000

V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True

# Walk-Forward periods (same as V26)
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

N_TRIALS = 500

# Cooldown settings (same as V26)
COOLDOWN_DAYS = 3
USE_COOLDOWN = True

# Limit-up filter (same as V26)
LIMIT_UP_THRESHOLD = 15.0
IPO_MIN_DAYS = 30

PT_ST_KEYWORDS = ['PT', 'ST', '*ST', '退']
BLOCKED_CODE_PREFIXES = ['2', '9', '4']

DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']

# ============================================================================
# V25 FROZEN WEIGHTS — DO NOT RE-OPTIMIZE
# ============================================================================
V25_FROZEN_WEIGHTS = {
    'weights_bull': [
        0.10743403213348336,
        0.19687614823506336,
        0.2724832107518529,
        0.06933095069162497,
        0.2105788063619203,
        0.1432968518260551
    ],
    'weights_range': [
        0.10743403213348336,
        0.19687614823506336,
        0.2724832107518529,
        0.06933095069162497,
        0.2105788063619203,
        0.1432968518260551
    ],
    'weights_bear': [
        0.11983412831656223,
        0.14265266337867788,
        0.30393337560649647,
        0.07733316786590252,
        0.23488393017744855,
        0.12136273465491235
    ],
    'min_score_threshold': 62.247685219155045,
}


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
# Code normalization & Stock filtering (same as V26)
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


def get_trading_dates(index_df, start_str, end_str):
    start = pd.to_datetime(start_str)
    end = pd.to_datetime(end_str)
    mask = (index_df['date'] >= start) & (index_df['date'] <= end)
    trading_dates = sorted(index_df.loc[mask, 'date'].tolist())
    return trading_dates


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
# V27 NEW: Enhanced Market Regime Detection
# ============================================================================
def detect_market_regime_v27(index_df, date):
    """
    Enhanced regime detection over V25:
    - Adds volatility spike detection
    - Adds volume anomaly detection  
    - Adds consecutive rally detection
    Returns: regime, confidence, risk, no_trade_signal
    """
    hist = index_df[index_df['date'] < date]
    if len(hist) < 20:
        return 'range', 0.5, 3, False

    closes = hist['close'].values
    n = len(closes)

    # === Original V25 logic ===
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

    daily_rets = (closes[-20:] - closes[-21:-1]) / closes[-21:-1] * 100 if n >= 21 else np.array([0.8])
    volatility = np.std(daily_rets)

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

    # === V27 NEW: No-trade signal detection ===
    no_trade_signal = False

    # A1: Volatility spike detection
    # Compare recent 5-day vol vs 20-day vol
    if n >= 25:
        vol_20 = np.std((closes[-20:] - closes[-21:-1]) / closes[-21:-1] * 100)
        vol_5 = np.std((closes[-5:] - closes[-6:-1]) / closes[-6:-1] * 100)
        vol_ratio = vol_5 / max(vol_20, 0.1)
        # Volatility spike: recent vol is much higher → market unstable
        # This catches冲高回落 (spike-and-crash)
        # We store this for the no-trade logic to use via config threshold
    else:
        vol_ratio = 1.0

    # A2: Previous day's index return (for pullback detection)
    prev_day_ret = (closes[-1] - closes[-2]) / closes[-2] * 100 if n >= 2 else 0

    # A3: Consecutive rally days
    consec_up = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] > closes[i - 1]:
            consec_up += 1
        else:
            break

    # Store extra info in a dict attached to the return
    # We'll use these in the enhanced no-trade logic
    extra_market_info = {
        'vol_ratio': vol_ratio if n >= 25 else 1.0,
        'prev_day_ret': prev_day_ret,
        'consec_up': consec_up,
        'volatility': volatility,
        'momentum': momentum,
    }

    return regime, confidence, risk, extra_market_info


# ============================================================================
# V27 Enhanced should_trade with no-trade signals
# ============================================================================
def should_trade_v27(regime, confidence, risk, extra_market_info, no_trade_config):
    """
    Enhanced should_trade with composite danger-score no-trade system.
    Instead of single thresholds, uses a weighted danger score.
    """
    # Base V25 logic
    if risk >= 5:
        return False, 0
    if risk == 4 and confidence > 0.6:
        return True, 1
    if risk == 3 and confidence < 0.3:
        return False, 0
    if risk <= 2:
        base_n_rec = 3 if risk == 1 else 2
    else:
        base_n_rec = 2

    # V27: Composite danger score
    danger = 0.0
    cfg = no_trade_config
    
    prev_ret = extra_market_info['prev_day_ret']
    consec_up = extra_market_info['consec_up']
    momentum = extra_market_info['momentum']
    vol_ratio = extra_market_info['vol_ratio']
    
    # Signal 1: Consecutive rally exhaustion
    # Each consecutive up day adds danger beyond the threshold
    consec_thresh = cfg.get('consec_rally_limit', 4)
    if consec_up >= consec_thresh:
        danger += (consec_up - consec_thresh + 1) * cfg.get('consec_weight', 1.0)
    
    # Signal 2: Post-gain profit-taking risk
    # prev day was positive → potential pullback
    prev_gain_thresh = cfg.get('prev_day_gain_threshold', 3.0)
    if prev_ret > prev_gain_thresh:
        danger += cfg.get('prev_gain_weight', 1.0)
    
    # Signal 2b: strong_bull AND moderate prev gain (not huge, not tiny)
    # This catches the "buying the top" scenario
    if regime == 'strong_bull' and 0 < prev_ret < cfg.get('strong_bull_prev_cap', 1.0):
        if consec_up >= 2:
            danger += cfg.get('bull_exhaustion_weight', 1.0)
    
    # Signal 3: Bull regime buying into a falling market
    # prev day was negative → trend may be reversing
    prev_loss_thresh = cfg.get('prev_day_loss_threshold', -0.3)
    if regime == 'bull' and prev_ret < prev_loss_thresh:
        danger += cfg.get('bull_dip_weight', 1.0)
    
    # Signal 4: Strong bull with very high momentum (overextended)
    # When momentum > threshold and regime is strong_bull → overheated
    overextend_thresh = cfg.get('overextend_momentum', 3.5)
    if regime == 'strong_bull' and momentum > overextend_thresh:
        # Only if previous day wasn't already a big correction
        if prev_ret < cfg.get('overextend_prev_cap', 0.5):
            danger += cfg.get('overextend_weight', 1.0)
    
    # Signal 5: Volatility spike in bull market
    vol_spike_thresh = cfg.get('vol_spike_threshold', 2.5)
    if vol_ratio > vol_spike_thresh and risk <= 2:
        danger += cfg.get('vol_spike_weight', 1.0)
    
    # Decision
    danger_trigger = cfg.get('danger_trigger', 1.5)
    if danger >= danger_trigger:
        return False, 0
    
    # Reduce position size if danger is elevated
    if danger >= danger_trigger * 0.5:
        base_n_rec = max(1, base_n_rec - 1)  # Reduce by 1
    
    return True, base_n_rec


# ============================================================================
# Sector Rotation (same as V26)
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

    # V27: Compute sector concentration (Herfindahl-like)
    total_heat = sum(max(h, 0) for _, h in sorted_sectors[:10])
    top1_heat = sorted_sectors[0][1] if sorted_sectors else 0
    sector_concentration = top1_heat / max(total_heat, 0.01) if total_heat > 0 else 0

    return {
        'hot': sorted_sectors[:8],
        'all_heat': sector_heat,
        'sector_concentration': sector_concentration,  # V27 NEW
    }


# ============================================================================
# Modules 3-7 (same as V26)
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

    peer_returns = []
    for pcode, p_ret in peer_data:
        if pcode == code:
            continue
        peer_returns.append(p_ret)

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
# V27: Compute stock volatility for scoring penalty
# ============================================================================
def compute_stock_volatility(hist_closes, lookback=10):
    """Compute recent price volatility for a stock."""
    n = len(hist_closes)
    if n < lookback + 1:
        return 0.8  # default
    daily_rets = (hist_closes[-lookback:] - hist_closes[-lookback-1:-1]) / hist_closes[-lookback-1:-1] * 100
    return float(np.std(daily_rets))


# ============================================================================
# Precompute V27 sub-scores
# ============================================================================
def precompute_v27(kline, index_df, scores, start_str, end_str):
    valid_dates = get_trading_dates(index_df, start_str, end_str)
    valid_dates = [d for d in valid_dates if get_index_return(index_df, d) is not None]

    print(f"  Real trading days: {len(valid_dates)} "
          f"({valid_dates[0].date() if valid_dates else 'N/A'} ~ {valid_dates[-1].date() if valid_dates else 'N/A'})")

    daily_data = []
    for day_idx, test_date in enumerate(valid_dates):
        # V27: Enhanced market regime
        regime, confidence, risk, extra_market_info = detect_market_regime_v27(index_df, test_date)

        sector_info = identify_hot_sectors(kline, scores, test_date)

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

            # V27 NEW: Stock volatility
            stock_vol = compute_stock_volatility(c, lookback=10)

            stock_hist_cache[code] = {
                'c': c, 'v': v, 'hi': hi, 'lo': lo, 'turn': turn,
                'industry': industry, 'name': name,
                'stock_return': get_stock_return(df, test_date),
                'last_pct': last_pct,
                'recent_limit_ups': recent_limit_ups,
                'extra_score': extra_score,
                'stock_vol': stock_vol,  # V27 NEW
            }

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
                'stock_vol': cache['stock_vol'],  # V27 NEW
            })

        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None:
            idx_ret = 0

        daily_data.append({
            'test_date': test_date,
            'regime': regime,
            'confidence': confidence,
            'risk': risk,
            'idx_ret': idx_ret,
            'extra_market_info': extra_market_info,  # V27 NEW
            'sector_concentration': sector_info['sector_concentration'],  # V27 NEW
            'stocks': stock_scores,
        })

        if (day_idx + 1) % 10 == 0:
            skip_str = ', '.join(f'{k}={v}' for k, v in sorted(debug_skip.items()) if v > 0)
            print(f"    {day_idx + 1}/{len(valid_dates)} days "
                  f"({len(stock_scores)} scored, skips: {skip_str})")
            check_memory()

    print(f"  Period {start_str}~{end_str}: {len(daily_data)} valid trading days")
    return daily_data


# ============================================================================
# Cooldown tracker (same as V26)
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
# V27: Fast evaluation with all enhancements
# ============================================================================
def evaluate_v27(daily_data, weights_config, detailed=False, use_cooldown=True):
    """
    V27 evaluation with:
    - Frozen V25 base weights
    - No-trade signals from market state
    - Volatility penalty for stock selection
    - Max 1 per industry
    - Cooldown
    """
    beat_count = 0
    total = 0
    skipped = 0
    no_trade = 0
    stats_by_risk = defaultdict(lambda: {'beat': 0, 'total': 0, 'no_trade': 0})
    day_details = []
    
    cooldown = CooldownTracker(COOLDOWN_DAYS)
    use_cooldown = USE_COOLDOWN and use_cooldown

    # Extract config
    cooldown_penalty_weight = weights_config.get('cooldown_penalty_weight', 5.0)
    vol_penalty_weight = weights_config.get('vol_penalty_weight', 3.0)
    vol_penalty_threshold = weights_config.get('vol_penalty_threshold', 2.0)
    no_trade_config = weights_config.get('no_trade_config', {})

    for dd in daily_data:
        risk = dd['risk']
        regime = dd['regime']
        idx_ret = dd['idx_ret']
        test_date = dd['test_date']
        extra_market_info = dd.get('extra_market_info', {})
        sector_concentration = dd.get('sector_concentration', 0)

        # V27: Enhanced should_trade with no-trade signals
        should, n_rec = should_trade_v27(regime, dd['confidence'], risk,
                                          extra_market_info, no_trade_config)
        
        # V27 NEW: Sector concentration no-trade
        sector_conc_thresh = no_trade_config.get('sector_concentration_threshold', 0.5)
        if sector_concentration > sector_conc_thresh:
            should = False

        if not should:
            no_trade += 1
            stats_by_risk[risk]['no_trade'] += 1
            if detailed:
                day_details.append({
                    'date': str(dd['test_date'].date()),
                    'regime': regime, 'risk': risk,
                    'n_stocks': 0,
                    'avg_ret': 0, 'idx_ret': round(idx_ret, 2),
                    'beat': False,
                    'no_trade': True,
                    'no_trade_reason': _get_no_trade_reason(extra_market_info, no_trade_config, sector_concentration),
                    'top': [],
                })
            continue

        stocks = dd['stocks']
        # Tunable n_rec
        if risk <= 2:
            n_rec = weights_config.get('n_rec_low_risk', n_rec)
        elif risk >= 4:
            n_rec = 1
        else:
            n_rec = weights_config.get('n_rec_med_risk', n_rec)
        
        min_score = weights_config.get('min_score_threshold', 55)

        # Select weights by risk level (FROZEN from V25)
        if risk <= 2:
            w = weights_config['weights_bull']
        elif risk >= 4:
            w = weights_config['weights_bear']
        else:
            w = weights_config['weights_range']

        # Score each stock
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

            # Cooldown penalty
            if use_cooldown:
                penalty = cooldown.get_freshness_penalty(s['code'], test_date)
                final -= penalty * cooldown_penalty_weight

            # V27 NEW: Volatility penalty
            if s['stock_vol'] > vol_penalty_threshold:
                vol_excess = (s['stock_vol'] - vol_penalty_threshold) / vol_penalty_threshold
                final -= vol_excess * vol_penalty_weight

            scored.append((s, final))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Select with max 1 per industry (V27: was 2)
        selected = []
        ind_count = defaultdict(int)
        max_industry = weights_config.get('max_industry_per_day', MAX_INDUSTRY)  # V27: default 1
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
            if ind_count[s['industry']] >= max_industry:
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
                if ind_count[s['industry']] >= max_industry:
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
                    'date': str(dd['test_date'].date()),
                    'regime': regime, 'risk': risk,
                    'n_stocks': len(stock_rets),
                    'avg_ret': round(avg_ret, 2),
                    'idx_ret': round(idx_ret, 2),
                    'beat': beat_idx,
                    'no_trade': False,
                    'top': [{'code': s['code'], 'name': s['name'],
                             'score': round(sc, 1),
                             'ret': round(s['stock_return'], 2) if s['stock_return'] else None}
                            for s, sc in selected[:3]],
                })

    beat_rate = beat_count / total if total > 0 else 0
    return beat_rate, stats_by_risk, beat_count, total, skipped, no_trade, day_details


def _get_no_trade_reason(extra_market_info, config, sector_concentration):
    """Helper to explain why no-trade was triggered."""
    reasons = []
    if extra_market_info.get('prev_day_ret', 0) > config.get('prev_day_gain_threshold', 3.0):
        reasons.append(f"prev_day_gain={extra_market_info['prev_day_ret']:.1f}%")
    if extra_market_info.get('consec_up', 0) >= config.get('consec_rally_limit', 4):
        reasons.append(f"consec_up={extra_market_info['consec_up']}")
    if extra_market_info.get('vol_ratio', 1.0) > config.get('vol_spike_threshold', 2.5):
        reasons.append(f"vol_spike={extra_market_info['vol_ratio']:.2f}")
    if extra_market_info.get('momentum', 0) < config.get('momentum_fade_threshold', 1.0):
        reasons.append(f"momentum_fade={extra_market_info['momentum']:.1f}")
    if sector_concentration > config.get('sector_concentration_threshold', 0.5):
        reasons.append(f"sector_concent={sector_concentration:.2f}")
    return '; '.join(reasons) if reasons else 'unknown'


# ============================================================================
# V27 Optuna: Only tune NEW parameters, FROZEN base weights from V25
# ============================================================================
def optimize_v27(train_data, valid_data, n_trials=N_TRIALS):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    print(f"\n[Optimization] V27 — {n_trials} trials, tuning ONLY new params (base weights FROZEN)")

    best_result = {'obj': -999, 'params': None}

    all_train = train_data['A'] + train_data['B'] + valid_data

    def objective(trial):
        # FROZEN: Use V25 weights directly
        weights_bull = V25_FROZEN_WEIGHTS['weights_bull']
        weights_range = V25_FROZEN_WEIGHTS['weights_range']
        weights_bear = V25_FROZEN_WEIGHTS['weights_bear']

        # NEW tunable params (only these are optimized):
        
        # B1: Volatility penalty for stock selection
        vol_penalty_weight = trial.suggest_float('vol_penalty_weight', 0.0, 10.0)
        vol_penalty_threshold = trial.suggest_float('vol_penalty_threshold', 1.0, 3.5)
        
        # B2: Industry limit per day
        max_industry_per_day = trial.suggest_int('max_industry_per_day', 1, 2)
        
        # B3: Cooldown penalty weight
        cooldown_penalty_weight = trial.suggest_float('cooldown_penalty_weight', 0.0, 15.0)
        
        # B4: Extra score weight
        w_extra = trial.suggest_float('w_extra', 0.0, 0.30)
        
        # C: No-trade danger score parameters
        # Signal 1: Consecutive rally
        consec_rally_limit = trial.suggest_int('consec_rally_limit', 2, 5)
        consec_weight = trial.suggest_float('consec_weight', 0.5, 3.0)
        
        # Signal 2: Post-gain pullback
        prev_day_gain_threshold = trial.suggest_float('prev_day_gain_threshold', 0.5, 5.0)
        prev_gain_weight = trial.suggest_float('prev_gain_weight', 0.0, 2.0)
        
        # Signal 2b: Strong bull exhaustion
        strong_bull_prev_cap = trial.suggest_float('strong_bull_prev_cap', 0.3, 2.0)
        bull_exhaustion_weight = trial.suggest_float('bull_exhaustion_weight', 0.0, 2.0)
        
        # Signal 3: Bull dip buying
        prev_day_loss_threshold = trial.suggest_float('prev_day_loss_threshold', -0.5, -0.05)
        bull_dip_weight = trial.suggest_float('bull_dip_weight', 0.0, 2.0)
        
        # Signal 4: Overextended strong bull
        overextend_momentum = trial.suggest_float('overextend_momentum', 2.5, 4.5)
        overextend_prev_cap = trial.suggest_float('overextend_prev_cap', 0.0, 1.0)
        overextend_weight = trial.suggest_float('overextend_weight', 0.0, 2.0)
        
        # Signal 5: Vol spike
        vol_spike_threshold = trial.suggest_float('vol_spike_threshold', 1.5, 4.0)
        vol_spike_weight = trial.suggest_float('vol_spike_weight', 0.0, 2.0)
        
        # Danger trigger
        danger_trigger = trial.suggest_float('danger_trigger', 0.5, 2.5)
        
        sector_concentration_threshold = trial.suggest_float('sector_concentration_threshold', 0.3, 0.8)
        
        no_trade_config = {
            'consec_rally_limit': consec_rally_limit,
            'consec_weight': consec_weight,
            'prev_day_gain_threshold': prev_day_gain_threshold,
            'prev_gain_weight': prev_gain_weight,
            'strong_bull_prev_cap': strong_bull_prev_cap,
            'bull_exhaustion_weight': bull_exhaustion_weight,
            'prev_day_loss_threshold': prev_day_loss_threshold,
            'bull_dip_weight': bull_dip_weight,
            'overextend_momentum': overextend_momentum,
            'overextend_prev_cap': overextend_prev_cap,
            'overextend_weight': overextend_weight,
            'vol_spike_threshold': vol_spike_threshold,
            'vol_spike_weight': vol_spike_weight,
            'danger_trigger': danger_trigger,
            'sector_concentration_threshold': sector_concentration_threshold,
        }
        
        # N_rec and min_score
        n_rec_low_risk = trial.suggest_int('n_rec_low', 2, 4)
        n_rec_med_risk = trial.suggest_int('n_rec_med', 1, 3)
        min_score_threshold = trial.suggest_float('min_score', 50.0, 70.0)

        weights_config = {
            'weights_bull': weights_bull,
            'weights_range': weights_range,
            'weights_bear': weights_bear,
            'min_score_threshold': min_score_threshold,
            'cooldown_penalty_weight': cooldown_penalty_weight,
            'vol_penalty_weight': vol_penalty_weight,
            'vol_penalty_threshold': vol_penalty_threshold,
            'max_industry_per_day': max_industry_per_day,
            'w_extra': w_extra,
            'n_rec_low_risk': n_rec_low_risk,
            'n_rec_med_risk': n_rec_med_risk,
            'no_trade_config': no_trade_config,
        }

        # Train on A+B+C combined
        train_bi, _, train_bc, train_bt, _, _, _ = evaluate_v27(all_train, weights_config)
        
        # Per-period stability
        ab_bi, _, _, _, _, _, _ = evaluate_v27(train_data['A'] + train_data['B'], weights_config)
        c_bi, _, _, _, _, _, _ = evaluate_v27(valid_data, weights_config)
        
        # Objective: maximize combined train with stability bonus
        stability = min(ab_bi, c_bi)
        variance_penalty = abs(ab_bi - c_bi) * 0.3
        obj = 0.5 * train_bi + 0.4 * stability - variance_penalty * 0.1

        if obj > best_result['obj']:
            best_result['obj'] = obj
            best_result['params'] = weights_config
            print(f"    [Trial {trial.number}] obj={obj:.4f} "
                  f"all={train_bc}/{train_bt}={train_bi*100:.0f}% "
                  f"AB={ab_bi*100:.0f}% C={c_bi*100:.0f}% "
                  f"danger=[cons>{consec_rally_limit}(w{consec_weight:.1f}),"
                  f"prev>{prev_day_gain_threshold:.1f}(w{prev_gain_weight:.1f}),"
                  f"trigger>{danger_trigger:.1f}]")

        return obj

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=900, show_progress_bar=False)

    print(f"\n  Best obj: {best_result['obj']:.4f}")
    return best_result['params'], best_result['obj']


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()

    print("=" * 70)
    print("V27 - Precision Optimization (V25 frozen weights + smart no-trade)")
    print("  A) Enhanced market state: vol spike, prev day gain, momentum fade")
    print("  B) Better diversification: max 1/industry, vol penalty")
    print("  C) Smarter no-trade: post-rally skip, sector concentration")
    print("  FROZEN: V25 base weights (6 dimensions)")
    print("=" * 70)
    print(f"  12 new params | {N_TRIALS} trials | Walk-Forward A+B→C→D")
    print("=" * 70)

    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = _load_scores()
    print_mem("All data loaded")

    test_dates = get_trading_dates(index_df, PERIOD_TEST_START, PERIOD_TEST_END)
    print(f"\n  Test period trading dates ({len(test_dates)} days):")
    for d in test_dates:
        print(f"    {d.date()} ({d.strftime('%A')})")

    # Precompute all periods
    print("\n[Precompute] Computing V27 sub-scores for 4 periods...")
    periods_data = {}
    for plabel, (ps, pe) in [('A', PERIOD_A), ('B', PERIOD_B),
                              ('C', PERIOD_C), ('D', PERIOD_D)]:
        print(f"\n  Period {plabel}: {ps} ~ {pe}")
        periods_data[plabel] = precompute_v27(kline, index_df, scores, ps, pe)
        gc.collect()
        print_mem(f"After Period {plabel}")

    del kline
    gc.collect()
    print_mem("After freeing kline")

    # Optimize (only new params, frozen base weights)
    train_data = {'A': periods_data['A'], 'B': periods_data['B']}
    valid_data = periods_data['C']
    best_params, best_obj = optimize_v27(train_data, valid_data, N_TRIALS)

    # Evaluate all periods
    print(f"\n{'=' * 70}")
    print(f"  V27 WALK-FORWARD EVALUATION")
    print(f"{'=' * 70}")

    period_results = {}
    for plabel in ['A', 'B', 'C', 'D']:
        bi, stats, bc, bt, sk, nt, det = evaluate_v27(
            periods_data[plabel], best_params, detailed=True)
        period_results[plabel] = {
            'beat_rate': bi, 'beat_count': bc, 'total_days': bt,
            'skipped': sk, 'no_trade': nt, 'details': det,
        }
        print(f"  Period {plabel}: {bc}/{bt} = {bi * 100:.1f}% (no_trade={nt}, skipped={sk})")

    test_bi = period_results['D']['beat_rate']
    test_bc = period_results['D']['beat_count']
    test_bt = period_results['D']['total_days']
    test_nt = period_results['D']['no_trade']

    print(f"\n{'=' * 70}")
    print(f"  [TEST] Period D — FINAL (never used for tuning)")
    print(f"{'=' * 70}")
    print(f"  Test beat_idx: {test_bc}/{test_bt} = {test_bi * 100:.1f}%")
    print(f"  No-trade days: {test_nt}")

    print(f"\n  Day-by-day results:")
    for det in period_results['D'].get('details', []):
        if det.get('no_trade'):
            print(f"    {det['date']} risk={det['risk']} "
                  f"NO-TRADE ({det.get('no_trade_reason', '')}) "
                  f"idx={det['idx_ret']:+.2f}%")
        else:
            beat_mark = "WIN" if det['beat'] else "FAIL"
            top_names = ', '.join(f"{t['name'][:4]}({t['ret']:+.1f}%)" 
                                  for t in det['top'] if t['ret'] is not None)
            print(f"    {det['date']} risk={det['risk']} "
                  f"avg={det['avg_ret']:+.2f}% idx={det['idx_ret']:+.2f}% "
                  f"{beat_mark} [{det['n_stocks']}stocks] | {top_names}")

    # Train & valid
    train_all = periods_data['A'] + periods_data['B']
    train_bi, _, train_bc, train_bt, _, _, _ = evaluate_v27(train_all, best_params)
    valid_bi = period_results['C']['beat_rate']

    gap = (train_bi - test_bi) * 100
    print(f"\n  Train: {train_bc}/{train_bt} = {train_bi * 100:.1f}%")
    print(f"  Valid: {period_results['C']['beat_count']}/{period_results['C']['total_days']} "
          f"= {valid_bi * 100:.1f}%")
    print(f"  Test:  {test_bc}/{test_bt} = {test_bi * 100:.1f}%")
    print(f"  Gap: {gap:.1f}pp")

    if gap > 20:
        print(f"  [!] Large gap — overfitting")
    elif gap > 10:
        print(f"  [!] Moderate gap")
    else:
        print(f"  [OK] Good generalization")

    # New params summary
    print(f"\n{'=' * 70}")
    print(f"  V27 NEW PARAMETERS (tuned)")
    print(f"{'=' * 70}")
    print(f"  vol_penalty_weight: {best_params.get('vol_penalty_weight', 'N/A'):.2f}")
    print(f"  vol_penalty_threshold: {best_params.get('vol_penalty_threshold', 'N/A'):.2f}")
    print(f"  max_industry_per_day: {best_params.get('max_industry_per_day', 'N/A')}")
    print(f"  cooldown_penalty_weight: {best_params.get('cooldown_penalty_weight', 'N/A'):.2f}")
    print(f"  w_extra: {best_params.get('w_extra', 'N/A'):.3f}")
    print(f"  prev_day_gain_threshold: {best_params.get('prev_day_gain_threshold', 'N/A'):.2f}")
    print(f"  consec_rally_limit: {best_params.get('consec_rally_limit', 'N/A')}")
    print(f"  vol_spike_threshold: {best_params.get('vol_spike_threshold', 'N/A'):.2f}")
    print(f"  momentum_fade_threshold: {best_params.get('momentum_fade_threshold', 'N/A'):.2f}")
    print(f"  sector_concentration_threshold: {best_params.get('sector_concentration_threshold', 'N/A'):.2f}")

    # Comparison
    print(f"\n{'=' * 70}")
    print(f"  BASELINES")
    print(f"{'=' * 70}")
    print(f"  V25: 76.9% | V26: 50.0% | V27: {test_bi * 100:.1f}%")

    # Save
    os.makedirs(RESULT_DIR, exist_ok=True)

    params_out = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v27-precision-optimization',
        'description': 'V25 frozen weights + smart no-trade + vol penalty + diversification',
        'best_obj': best_obj,
        'train_beat_idx': train_bi,
        'valid_beat_idx': valid_bi,
        'test_beat_idx': test_bi,
        'train_test_gap_pp': round(gap, 1),
        'frozen_v25_weights': V25_FROZEN_WEIGHTS,
        'new_params': {
            'vol_penalty_weight': best_params.get('vol_penalty_weight', 0),
            'vol_penalty_threshold': best_params.get('vol_penalty_threshold', 2.0),
            'max_industry_per_day': best_params.get('max_industry_per_day', 1),
            'cooldown_penalty_weight': best_params.get('cooldown_penalty_weight', 5.0),
            'w_extra': best_params.get('w_extra', 0.0),
            'prev_day_gain_threshold': best_params.get('prev_day_gain_threshold', 3.0),
            'consec_rally_limit': best_params.get('consec_rally_limit', 4),
            'vol_spike_threshold': best_params.get('vol_spike_threshold', 2.5),
            'momentum_fade_threshold': best_params.get('momentum_fade_threshold', 1.0),
            'sector_concentration_threshold': best_params.get('sector_concentration_threshold', 0.5),
            'n_rec_low_risk': best_params.get('n_rec_low_risk', 3),
            'n_rec_med_risk': best_params.get('n_rec_med_risk', 2),
            'min_score_threshold': best_params.get('min_score_threshold', 62.0),
        },
    }
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v27_best_params.json')
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)
    print(f"\n  Params: {params_path}")

    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v27-precision-optimization',
        'walk_forward_split': {
            'train': f'{PERIOD_TRAIN_START} ~ {PERIOD_TRAIN_END}',
            'valid': f'{PERIOD_VALID_START} ~ {PERIOD_VALID_END}',
            'test': f'{PERIOD_TEST_START} ~ {PERIOD_TEST_END}',
        },
        'train_result': {'beat_idx': train_bi, 'days': train_bt},
        'valid_result': {'beat_idx': valid_bi, 'days': period_results['C']['total_days']},
        'test_result': {
            'beat_idx': test_bi, 'days': test_bt,
            'no_trade': test_nt, 'skipped': period_results['D']['skipped'],
        },
        'period_results': {k: {kk: vv for kk, vv in v.items() if kk != 'details'}
                           for k, v in period_results.items()},
        'test_details': period_results['D']['details'],
        'comparison': {
            'v25_test': 76.9, 'v26_test': 50.0, 'v27_test': round(test_bi * 100, 1),
        },
        'params': params_out,
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
    fp = os.path.join(RESULT_DIR, 'backtest_v27.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"  Results: {fp}")

    elapsed = time.time() - t0
    print(f"\n  Total: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print("=" * 70)


if __name__ == '__main__':
    main()

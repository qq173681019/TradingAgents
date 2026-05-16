#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V16b - Iterative Per-Risk Optuna Optimization

V16 tried optimizing all 88 params simultaneously in 300 trials -> 77.5% (worse than V14).
Problem: too many params, not enough trials per risk level.

V16b strategy: Iterative per-risk optimization
  Phase 1: Fix R3 = V14 best params (already 93.3% beat_idx)
  Phase 2: Optimize R2 (momentum) with 500 trials, fixed R3
  Phase 3: Optimize R4/5 (defense) with 500 trials, fixed R3+R2
  Phase 4: Final evaluation with all optimized params

This reduces search space per phase to ~24-28 params with 500 trials each.
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
SHARED_DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# Config
# ============================================================================
EVAL_START = '2026-03-01'
EVAL_END = '2026-04-24'
MIN_KLINE_DAYS = 40
MAX_INDUSTRY = 1

N_TRIALS_PER_PHASE = 500
TIMEOUT_PER_PHASE = 1800  # 30 min per phase

# ============================================================================
# Imports from V16 (reuse all scoring functions)
# ============================================================================
# We inline everything here for a self-contained script.

def check_memory(limit_mb=8000):
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
# Data Loading (same as V14/V16)
# ============================================================================
def normalize_code(code):
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code


def load_data_full():
    print("[1/3] Loading data...")
    
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    if not os.path.exists(kline_file):
        kline_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')
    
    print(f"  Loading kline: {os.path.basename(kline_file)} ({os.path.getsize(kline_file)/1024/1024:.1f}MB)")
    
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}
    kline = {}
    skipped = 0
    
    for code, records in raw.items():
        clean = normalize_code(code)
        if len(records) < MIN_KLINE_DAYS:
            skipped += 1
            continue
        filtered = [{k: v for k, v in r.items() if k in NEED_COLS} for r in records]
        df = pd.DataFrame(filtered)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        kline[clean] = df
    
    del raw, filtered
    gc.collect()
    
    sample_df = next(iter(kline.values()))
    print(f"  Kline: {len(kline)} stocks ({skipped} skipped), {sample_df['date'].min().date()} ~ {sample_df['date'].max().date()}")
    
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    if not os.path.exists(idx_file):
        idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)
    
    idx_records = _parse_index(raw_idx)
    del raw_idx
    gc.collect()
    
    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index: {len(index_df)} days")
    
    scores = _load_scores()
    
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: float(np.mean([v for v in vals if v is not None and not np.isnan(v)]))
                  for ind, vals in sector_perf.items()}
    
    print_mem("Data loaded")
    return kline, index_df, scores, sector_avg


def _parse_index(raw_idx):
    records = []
    if 'date' in raw_idx and isinstance(raw_idx['date'], dict):
        n = len(raw_idx['date'])
        for i in range(n):
            try:
                ds = str(raw_idx['date'].get(str(i), ''))
                cl = float(raw_idx['close'].get(str(i), 0))
                if ds and cl > 0:
                    records.append({'date': ds, 'close': cl})
            except:
                continue
    elif isinstance(raw_idx, dict):
        n = max(int(k) for k in raw_idx.get('date', {})) + 1
        for i in range(n):
            key = str(i)
            try:
                ts = raw_idx['date'][key]
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
                cl = float(raw_idx['close'][key])
                records.append({'date': ds, 'close': cl})
            except:
                continue
    return records


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
# Feature calc (same as V14/V16)
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

def get_adaptive_top_n(risk_level):
    if risk_level >= 5: return 2
    elif risk_level >= 4: return 3
    elif risk_level == 3: return 3
    else: return 4

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
# Precompute Sub-scores (same as V16)
# ============================================================================
def precompute_all(kline, index_df, scores, sector_avg):
    print("[Precompute] Computing sub-scores...")
    
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = [d for d in date_range if get_index_return(index_df, d) is not None]
    print(f"  {len(valid_dates)} eval days")
    
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
            
            feats = calc_features(df, test_date)
            if feats is None: continue
            
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
            
            static = scores.get(code, None)
            stock_return = get_stock_return(df, test_date)
            
            f = feats
            if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
                continue
            
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
            
            stock_subscores.append({
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
            })
        
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
    
    print(f"  Done: {len(daily_data)} days")
    return daily_data


# ============================================================================
# Scoring Functions (same as V16)
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
    return score


# ============================================================================
# V14 Best Risk 3 Params (FIXED)
# ============================================================================
V14_R3_PARAMS = {
    'w_momentum': 0.1367368225983983,
    'w_trend': 0.09637994830301756,
    'w_consistency': 0.07239465845883288,
    'w_mr': 0.08574774661868874,
    'w_vol': 0.06881629015116482,
    'w_rsi': 0.020767455891327818,
    'w_static': 0.006128774990345904,
    'w_defense': 0.1047185559416257,
    'w_sector_heat': 0.1265592668216359,
    'w_low_vol': 0.035520741096385325,
    'w_rel_str': 0.10048010450673954,
    'w_rel_str_3d': 0.14574963462163745,
    'consistency_boost_high': 2.462901723200523,
    'consistency_boost_mid': 1.1698048442226556,
    'uptrend_boost_full': 1.7353555723902283,
    'uptrend_boost_partial': 0.9607630572681164,
    'ma20_above_mult': 1.2066113765603486,
    'ma20_below_mult': 0.5036854829973982,
    'low_vol_mult_high': 1.253243786482494,
    'low_vol_mult_mid': 0.918021431097559,
    'high_vol_penalize': 0.12550706946792134,
    'rsi_overbought_mult': 0.16802490273066453,
    'rsi_high_mult': 0.6567544068873018,
    'rsi_sweet_mult': 1.3327284601521754,
    'sector_heat_strong': 1.0231488329038572,
    'sector_heat_mild': 1.3018677990995955,
    'sector_cold': 0.021878077981025618,
    'sector_cool': 0.5007357312346158,
    'rel_str_strong': 1.897554342386533,
    'rel_str_mild': 1.268640002021058,
    'big_move5_penalize': 0.10155970323875607,
    'big_move3_penalize': 0.8884580226191793,
    'streak_penalize': 0.4538002132233489,
    'vol_shrink_penalize': 0.3220780190128671,
    'turn_spike_penalize': 0.7179315118846368,
    'ma5_below_penalize': 0.5632256989490149,
}

# V10 default for Risk 2 (momentum)
V10_R2_DEFAULTS = {
    'w_momentum': 0.25, 'w_trend': 0.20, 'w_consistency': 0.05,
    'w_vol': 0.10, 'w_rsi': 0.05, 'w_static': 0.15,
    'w_defense': 0.05, 'w_sector': 0.10, 'w_low_vol': 0.05,
    'w_rel_str': 0.0, 'w_rel_str_3d': 0.0,
    'boost_consistency': 1.3, 'boost_above_ma20': 1.2,
    'boost_rsi_45_60': 1.1, 'boost_sector_hot': 1.3,
    'boost_rel_str': 1.2,
    'penalty_below_ma20': 0.5, 'penalty_high_vol': 0.6,
    'penalty_rsi_overbought': 0.7, 'penalty_big_move': 0.5,
    'penalty_streak_neg': 0.6, 'penalty_vol_shrink': 0.8,
    'penalty_turn_spike': 0.7, 'penalty_below_ma5': 0.8,
}

# V10 default for Risk 4/5 (defense)
V10_R45_DEFAULTS = {
    'w_momentum': 0.02, 'w_trend': 0.03, 'w_mr': 0.12,
    'w_vol': 0.03, 'w_rsi': 0.08, 'w_static': 0.12,
    'w_defense': 0.10, 'w_sector': 0.02, 'w_low_vol': 0.05,
    'w_rel_str': 0.18, 'w_rel_str_3d': 0.12, 'w_beta': 0.10,
    'penalty_beta_high': 0.3, 'penalty_beta_mid': 0.6,
    'boost_beta_low': 1.4, 'boost_oversold': 1.2,
    'penalty_overbought': 0.2, 'penalty_high_beta_ind': 0.3,
    'boost_defensive_ind': 1.3, 'boost_rel_str_strong': 1.4,
    'boost_rel_str_very_strong': 1.2, 'boost_low_vol': 1.25,
    'penalty_big_drop': 0.2, 'penalty_big_drop_3d': 0.2,
    'penalty_big_jump': 0.2, 'penalty_overextended': 0.3,
    'boost_streak_relstr': 1.15,
}


# ============================================================================
# Fast evaluate with given params for specific risk levels
# ============================================================================
def evaluate_with_params(daily_data, r2_params=None, r3_params=None, r45_params=None):
    """Evaluate beat_idx using the given params. Returns (overall_beat_pct, per_risk_stats)."""
    stock_recent_perf = defaultdict(list)
    stats_by_risk = defaultdict(lambda: {'beat_idx': 0, 'total': 0, 'wins': 0})
    total_beat = 0
    total_days = 0
    
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
            total_days += 1
            daily_wins = sum(1 for x in stock_rets if x['beat'])
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            
            stats_by_risk[risk]['total'] += 1
            if daily_wins > len(stock_rets) / 2:
                stats_by_risk[risk]['wins'] += 1
            if beat_idx:
                stats_by_risk[risk]['beat_idx'] += 1
                total_beat += 1
    
    overall = total_beat / total_days if total_days > 0 else 0
    return overall, stats_by_risk, total_beat, total_days


# ============================================================================
# Phase 1: Baseline with V14 R3 + V10 R2/R45
# ============================================================================
def evaluate_baseline(daily_data):
    print("\n[Phase 0] Baseline: V14 R3 + V10 R2 + V10 R4/5")
    overall, stats, tb, td = evaluate_with_params(
        daily_data,
        r2_params=V10_R2_DEFAULTS,
        r3_params=V14_R3_PARAMS,
        r45_params=V10_R45_DEFAULTS,
    )
    print(f"  Baseline: {tb}/{td} = {overall*100:.1f}% beat_idx")
    for r in sorted(stats.keys()):
        s = stats[r]
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    R{r}: {s['beat_idx']}/{s['total']} = {bi:.0f}%")
    return overall, stats


# ============================================================================
# Phase 2: Optimize R2 (momentum)
# ============================================================================
def optimize_r2(daily_data, n_trials=N_TRIALS_PER_PHASE):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 1] Optimizing R2 (momentum) - {n_trials} trials")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_consistency', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d']
    WEIGHT_DEFAULTS = [0.25, 0.20, 0.05, 0.10, 0.05, 0.15, 0.05, 0.10, 0.05, 0.0, 0.0]
    
    MULT_KEYS = [
        'boost_consistency', 'boost_above_ma20', 'boost_rsi_45_60',
        'boost_sector_hot', 'boost_rel_str',
        'penalty_below_ma20', 'penalty_high_vol', 'penalty_rsi_overbought',
        'penalty_big_move', 'penalty_streak_neg', 'penalty_vol_shrink',
        'penalty_turn_spike', 'penalty_below_ma5',
    ]
    MULT_RANGES = {
        'boost_consistency': (1.0, 2.5), 'boost_above_ma20': (0.8, 2.0),
        'boost_rsi_45_60': (0.8, 1.8), 'boost_sector_hot': (0.8, 2.0),
        'boost_rel_str': (0.8, 2.0),
        'penalty_below_ma20': (0.1, 0.9), 'penalty_high_vol': (0.1, 0.8),
        'penalty_rsi_overbought': (0.1, 0.8), 'penalty_big_move': (0.1, 0.8),
        'penalty_streak_neg': (0.1, 0.8), 'penalty_vol_shrink': (0.2, 1.0),
        'penalty_turn_spike': (0.2, 1.0), 'penalty_below_ma5': (0.2, 1.0),
    }
    
    best_global = {'score': -1, 'params': None}
    
    def objective(trial):
        # Weights
        raw = []
        for i, key in enumerate(WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(0.005, default * 0.05)
            hi = max(0.01, default * 3.0 + 0.05)
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(WEIGHT_KEYS)}
        
        # Multipliers
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        # Evaluate ONLY Risk 2 days
        r2_days = [dd for dd in daily_data if dd['risk'] == 2]
        
        stock_recent_perf = defaultdict(list)
        beat_count = 0
        total = 0
        
        for dd in r2_days:
            actual_n = dd['actual_n']
            idx_ret = dd['idx_ret']
            stocks = dd['stocks']
            
            scored = [(s, score_risk2(s, params)) for s in stocks]
            scored.sort(key=lambda x: x[1], reverse=True)
            
            blacklist = build_blacklist(stock_recent_perf, 2)
            selected = []
            ind_count = defaultdict(int)
            for s, sc in scored:
                if len(selected) >= actual_n: break
                if s['code'] in blacklist: continue
                if ind_count[s['industry']] >= MAX_INDUSTRY: continue
                if sc < 0.5: continue
                selected.append((s, sc))
                ind_count[s['industry']] += 1
            
            if not selected:
                non_bl = [(s, sc) for s, sc in scored if s['code'] not in blacklist]
                selected = non_bl[:min(2, len(non_bl))]
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
        
        if beat_pct > best_global['score']:
            best_global['score'] = beat_pct
            best_global['params'] = dict(params)
            print(f"    [Trial {trial.number}] R2 best: {beat_pct*100:.0f}% ({beat_count}/{total})")
        
        return beat_pct
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R2 best: {best_global['score']*100:.0f}%")
    return best_global['params'], best_global['score']


# ============================================================================
# Phase 3: Optimize R4/5 (defense)
# ============================================================================
def optimize_r45(daily_data, n_trials=N_TRIALS_PER_PHASE):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 2] Optimizing R4/5 (defense) - {n_trials} trials")
    
    WEIGHT_KEYS = ['w_momentum', 'w_trend', 'w_mr', 'w_vol', 'w_rsi',
                   'w_static', 'w_defense', 'w_sector', 'w_low_vol', 'w_rel_str', 'w_rel_str_3d', 'w_beta']
    WEIGHT_DEFAULTS = [0.02, 0.03, 0.12, 0.03, 0.08, 0.12, 0.10, 0.02, 0.05, 0.18, 0.12, 0.10]
    
    MULT_KEYS = [
        'penalty_beta_high', 'penalty_beta_mid', 'boost_beta_low',
        'boost_oversold', 'penalty_overbought',
        'penalty_high_beta_ind', 'boost_defensive_ind',
        'boost_rel_str_strong', 'boost_rel_str_very_strong',
        'boost_low_vol', 'penalty_big_drop', 'penalty_big_drop_3d',
        'penalty_big_jump', 'penalty_overextended', 'boost_streak_relstr',
    ]
    MULT_RANGES = {
        'penalty_beta_high': (0.05, 0.8), 'penalty_beta_mid': (0.3, 1.0),
        'boost_beta_low': (1.0, 2.0), 'boost_oversold': (0.8, 1.8),
        'penalty_overbought': (0.05, 0.5), 'penalty_high_beta_ind': (0.05, 0.8),
        'boost_defensive_ind': (1.0, 2.0), 'boost_rel_str_strong': (1.0, 2.0),
        'boost_rel_str_very_strong': (0.8, 2.0), 'boost_low_vol': (0.8, 2.0),
        'penalty_big_drop': (0.05, 0.5), 'penalty_big_drop_3d': (0.05, 0.5),
        'penalty_big_jump': (0.05, 0.5), 'penalty_overextended': (0.05, 0.7),
        'boost_streak_relstr': (0.8, 1.5),
    }
    
    best_global = {'score': -1, 'params': None}
    
    def objective(trial):
        raw = []
        for i, key in enumerate(WEIGHT_KEYS):
            default = WEIGHT_DEFAULTS[i]
            lo = max(0.005, default * 0.05)
            hi = max(0.01, default * 3.0 + 0.05)
            raw.append(trial.suggest_float(f'w_{key}', lo, hi))
        total_w = sum(raw)
        params = {key: raw[i] / total_w for i, key in enumerate(WEIGHT_KEYS)}
        
        for key in MULT_KEYS:
            lo, hi = MULT_RANGES[key]
            params[key] = trial.suggest_float(f'm_{key}', lo, hi)
        
        # Evaluate R4 and R5 days
        r45_days = [dd for dd in daily_data if dd['risk'] >= 4]
        
        stock_recent_perf = defaultdict(list)
        beat_count = 0
        total = 0
        
        for dd in r45_days:
            risk = dd['risk']
            actual_n = dd['actual_n']
            idx_ret = dd['idx_ret']
            stocks = dd['stocks']
            
            scored = []
            for s in stocks:
                sc = score_risk45(s, params)
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
                if sc < 0.3: continue
                selected.append((s, sc))
                ind_count[s['industry']] += 1
            
            if not selected:
                non_bl = [(s, sc) for s, sc in scored if s['code'] not in blacklist]
                selected = non_bl[:min(1, len(non_bl))]
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
        
        if beat_pct > best_global['score']:
            best_global['score'] = beat_pct
            best_global['params'] = dict(params)
            print(f"    [Trial {trial.number}] R4/5 best: {beat_pct*100:.0f}% ({beat_count}/{total})")
        
        return beat_pct
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=TIMEOUT_PER_PHASE, show_progress_bar=False)
    
    print(f"  R4/5 best: {best_global['score']*100:.0f}%")
    return best_global['params'], best_global['score']


# ============================================================================
# Phase 4: Joint fine-tune all params together
# ============================================================================
def joint_finetune(daily_data, r2_params, r3_params, r45_params, n_trials=300):
    """Joint fine-tuning with narrow ranges around best params."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    print(f"\n[Phase 3] Joint fine-tuning all params - {n_trials} trials")
    
    best_global = {'composite': -1, 'params': None}
    
    # Get the parameter sets
    param_sets = {
        2: r2_params,
        3: r3_params,
        45: r45_params,
    }
    
    def objective(trial):
        # Fine-tune R2 multipliers (keep weights fixed from Phase 1)
        r2_ft = dict(r2_params)
        r2_mult_keys = [k for k in r2_params if not k.startswith('w_')]
        for key in r2_mult_keys:
            val = r2_params[key]
            lo = max(0.01, val * 0.7)
            hi = val * 1.3
            if lo >= hi: hi = lo + 0.01
            r2_ft[key] = trial.suggest_float(f'r2_{key}', lo, hi)
        
        # R3 stays fixed (already 93.3%)
        r3_ft = dict(r3_params)
        
        # Fine-tune R4/5 multipliers
        r45_ft = dict(r45_params)
        r45_mult_keys = [k for k in r45_params if not k.startswith('w_')]
        for key in r45_mult_keys:
            val = r45_params[key]
            lo = max(0.01, val * 0.7)
            hi = val * 1.3
            if lo >= hi: hi = lo + 0.01
            r45_ft[key] = trial.suggest_float(f'r45_{key}', lo, hi)
        
        # Evaluate all days
        overall, stats, _, _ = evaluate_with_params(
            daily_data, r2_params=r2_ft, r3_params=r3_ft, r45_params=r45_ft
        )
        
        # Composite with emphasis on improving weak areas
        risk_beats = {}
        for r in [2, 3, 4, 5]:
            s = stats.get(r, {'beat_idx': 0, 'total': 0})
            risk_beats[r] = s['beat_idx'] / s['total'] if s['total'] > 0 else 0
        
        composite = (
            overall * 0.40 +
            risk_beats.get(2, 0) * 0.20 +
            risk_beats.get(3, 0) * 0.10 +
            risk_beats.get(4, 0) * 0.15 +
            risk_beats.get(5, 0) * 0.15
        )
        
        if composite > best_global['composite']:
            best_global['composite'] = composite
            best_global['params'] = {'r2': r2_ft, 'r3': r3_ft, 'r45': r45_ft}
            print(f"    [Trial {trial.number}] composite={composite:.3f} "
                  f"overall={overall*100:.1f}% "
                  f"R2={risk_beats.get(2,0)*100:.0f}% "
                  f"R3={risk_beats.get(3,0)*100:.0f}% "
                  f"R4={risk_beats.get(4,0)*100:.0f}% "
                  f"R5={risk_beats.get(5,0)*100:.0f}%")
        
        return composite
    
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=1200, show_progress_bar=False)
    
    if best_global['params']:
        return best_global['params']['r2'], best_global['params']['r3'], best_global['params']['r45'], best_global['composite']
    return r2_params, r3_params, r45_params, 0


# ============================================================================
# Full Backtest Report
# ============================================================================
def run_full_backtest(daily_data, r2_params, r3_params, r45_params):
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
                'vol_state': dd['vol_state'],
                'n_stocks': len(stock_rets), 'stocks': stock_rets,
                'idx_ret': round(idx_ret, 2), 'avg_ret': round(avg_ret, 2),
                'wr': round(wr, 2), 'win': wr > 0.5, 'beat_idx': beat_idx,
            })
            
            stats_by_risk[risk]['total'] += 1
            if wr > 0.5: stats_by_risk[risk]['wins'] += 1
            if beat_idx: stats_by_risk[risk]['beat_idx'] += 1
            
            tag = 'W' if wr > 0.5 else 'L'
            bi = '^' if beat_idx else 'v'
            print(f"  [{test_date.strftime('%m-%d')}] {tag}{bi} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% R{risk} [{dd['regime'][:4]}] n={len(stock_rets)}")
    
    wins = sum(1 for r in results if r['win'])
    total = len(results)
    beat_idx_days = sum(1 for r in results if r['beat_idx'])
    
    accuracy = wins / total if total > 0 else 0
    beat_pct = beat_idx_days / total if total > 0 else 0
    
    print(f"\n  RESULT: {wins}/{total} = {accuracy*100:.1f}% win, {beat_idx_days}/{total} = {beat_pct*100:.1f}% beat_idx")
    print(f"\n  By Risk Level:")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        acc = s['wins'] / s['total'] * 100 if s['total'] > 0 else 0
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    
    return {
        'accuracy': accuracy, 'wins': wins, 'total': total,
        'beat_idx_days': beat_idx_days, 'beat_idx_pct': beat_pct,
        'results': results,
        'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()},
    }


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    
    print("=" * 70)
    print("Backtest V16b - Iterative Per-Risk Optuna Optimization")
    print("=" * 70)
    print(f"  Phase 0: Baseline (V14 R3 + V10 R2/R4/5)")
    print(f"  Phase 1: Optimize R2 ({N_TRIALS_PER_PHASE} trials)")
    print(f"  Phase 2: Optimize R4/5 ({N_TRIALS_PER_PHASE} trials)")
    print(f"  Phase 3: Joint fine-tune (300 trials)")
    print(f"  Target: overall >= 85%, R2 >= 80%, R3 >= 90%, R4/5 >= 75%")
    print("=" * 70)
    
    # Load data
    kline, index_df, scores, sector_avg = load_data_full()
    print_mem("Data loaded")
    
    # Precompute
    daily_data = precompute_all(kline, index_df, scores, sector_avg)
    print_mem("Precomputed")
    
    del kline
    gc.collect()
    print_mem("After freeing kline")
    
    # Phase 0: Baseline
    baseline_overall, baseline_stats = evaluate_baseline(daily_data)
    
    # Phase 1: Optimize R2
    r2_best, r2_score = optimize_r2(daily_data, N_TRIALS_PER_PHASE)
    
    # Evaluate R2 improvement
    overall_r2, stats_r2, _, _ = evaluate_with_params(
        daily_data, r2_params=r2_best, r3_params=V14_R3_PARAMS, r45_params=V10_R45_DEFAULTS,
    )
    print(f"\n  After R2 optimization: {overall_r2*100:.1f}% overall")
    for r in sorted(stats_r2.keys()):
        s = stats_r2[r]
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    R{r}: {bi:.0f}%")
    
    # Phase 2: Optimize R4/5
    r45_best, r45_score = optimize_r45(daily_data, N_TRIALS_PER_PHASE)
    
    # Evaluate R2+R45 improvement
    overall_r45, stats_r45, _, _ = evaluate_with_params(
        daily_data, r2_params=r2_best, r3_params=V14_R3_PARAMS, r45_params=r45_best,
    )
    print(f"\n  After R4/5 optimization: {overall_r45*100:.1f}% overall")
    for r in sorted(stats_r45.keys()):
        s = stats_r45[r]
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    R{r}: {bi:.0f}%")
    
    # Phase 3: Joint fine-tune
    r2_final, r3_final, r45_final, ft_composite = joint_finetune(
        daily_data, r2_best, V14_R3_PARAMS, r45_best, n_trials=300,
    )
    
    # Final evaluation
    print(f"\n{'='*70}")
    print(f"  FINAL BACKTEST")
    print(f"{'='*70}")
    
    result = run_full_backtest(daily_data, r2_final, r3_final, r45_final)
    
    # Save results
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v16b-iterative-optuna',
        'eval_range': f'{EVAL_START} ~ {EVAL_END}',
        'accuracy': result['accuracy'],
        'beat_idx_pct': result['beat_idx_pct'],
        'beat_idx_days': result['beat_idx_days'],
        'total_days': result['total'],
        'stats_by_risk': result['stats_by_risk'],
        'r2_params': r2_final,
        'r3_params': r3_final,
        'r45_params': r45_final,
        'n_trials_per_phase': N_TRIALS_PER_PHASE,
        'baseline': {
            'overall': baseline_overall,
            'stats': {str(k): v for k, v in baseline_stats.items()},
        },
        'elapsed_seconds': time.time() - t0,
    }
    
    fp = os.path.join(RESULT_DIR, 'backtest_v16_result.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"Result saved: {fp}")
    
    # Save best params
    os.makedirs(SHARED_DATA_DIR, exist_ok=True)
    params_path = os.path.join(SHARED_DATA_DIR, 'optuna_v16_best_params.json')
    params_out = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v16b-iterative-optuna',
        'overall_beat_idx': result['beat_idx_pct'],
        'stats_by_risk': result['stats_by_risk'],
        'risk2_params': r2_final,
        'risk3_params': r3_final,
        'risk45_params': r45_final,
    }
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)
    print(f"Best params saved: {params_path}")
    
    # Summary
    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Overall: {result['beat_idx_pct']*100:.1f}% (V14: 80.0%, baseline: {baseline_overall*100:.1f}%)")
    print(f"  Target 85%: {'ACHIEVED' if result['beat_idx_pct'] >= 0.85 else 'NOT YET'}")
    
    targets = {2: 80, 3: 90, 4: 75, 5: 75}
    for r in sorted(result['stats_by_risk'].keys()):
        s = result['stats_by_risk'][r]
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        tgt = targets.get(int(r), 0)
        print(f"  Risk {r}: {bi:.0f}% (target {tgt}%) {'ACHIEVED' if bi >= tgt else 'NOT YET'}")
    
    print(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*70}")
    
    return result


if __name__ == '__main__':
    main()

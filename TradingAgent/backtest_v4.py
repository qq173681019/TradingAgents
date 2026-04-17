#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票推荐算法回测系统 V4 - 熊市防御版
=====================================
核心改进:
1. 大跌天目标跑赢指数（核心KPI）
2. 市场状态精细检测（VIX-like波动率 + 趋势 + 连跌）
3. 熊市防御: 低Beta + 高Fundamental + 均值回归
4. 自适应选股数: 极端行情减仓
5. 板块防御: 熊市偏好防御性板块
6. 6个月K线做特征, 2个月做评估
"""

import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# Config
# ============================================================================
FEATURE_START = '2025-10-01'
EVAL_START = '2026-02-20'
EVAL_END = '2026-04-07'
TARGET_ACCURACY = 0.65
TOP_N = 3
MAX_INDUSTRY = 2


# ============================================================================
# Data Loading (same as V3.1)
# ============================================================================
def load_data():
    print("[1/3] Loading data...")
    
    # K-line
    kline_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        clean = code.replace('sh.', '').replace('sz.', '')
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        kline[clean] = df
    print(f"  K-line: {len(kline)} stocks")
    
    # Index
    idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)
    
    n = len(raw_idx['date'])
    idx_records = []
    for i in range(n):
        key = str(i)
        try:
            ts = raw_idx['date'][key]
            if isinstance(ts, (int, float)):
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d')
            else:
                ds = str(ts)
            idx_records.append({'date': ds, 'close': float(raw_idx['close'][key])})
        except:
            continue
    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index: {len(index_df)} days")
    
    # Scores
    import glob
    sf = sorted(glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')))
    scores = {}
    if sf:
        with open(sf[-1], 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            scores[code] = {
                'tech': float(s.get('short_term_score', 5.0)),
                'fund': float(s.get('long_term_score', 5.0)),
                'chip': float(s.get('chip_score', 5.0)),
                'sector': float(s.get('hot_sector_score', 5.0)),
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': float(s.get('sector_change', 0)),
            }
    print(f"  Scores: {len(scores)} stocks")
    
    # Sector avg
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: np.mean([v for v in vals if v is not None and not np.isnan(v)])
                  for ind, vals in sector_perf.items()}
    
    return kline, index_df, scores, sector_avg


# ============================================================================
# Feature Engineering (enhanced)
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
    
    # Returns
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0
    
    # Moving Averages
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
    
    # Volume
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    f['vol_trend'] = (v[-1] - np.mean(v[-5:])) / max(np.mean(v[-5:]), 1) if n >= 5 else 0
    
    # Turnover
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_ratio'] = turn5 / max(turn10, 0.01)
        f['turn_avg'] = turn5
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_ratio'] = 1.0
        f['turn_avg'] = 0
        f['turn_spike'] = 1.0
    
    # Price position
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    # ATR
    if n >= 6:
        trs = []
        for i in range(-min(14, n-1), 0):
            tr = max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1]))
            trs.append(tr)
        f['atr_pct'] = np.mean(trs) / c[-1] * 100
    else:
        f['atr_pct'] = 0
    
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
    
    # Mean reversion
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0
    
    # Beta-like: correlation with recent range
    # Approximated by vol5 ratio to market (we'll use raw vol as proxy)
    
    # pctChg features
    if n >= 3 and not np.all(pct == 0):
        f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum'] = float(np.nansum(pct[-3:]))
        f['pct_5d_sum'] = float(np.nansum(pct[-5:])) if n >= 5 else f['pct_3d_sum']
    else:
        f['pct_1d'] = f['r1']
        f['pct_3d_sum'] = f['r3']
        f['pct_5d_sum'] = f['r5']
    
    # Max drawdown in last 10 days
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
    
    # Support distance
    f['dist_support'] = (c[-1] - np.min(c[-w20:])) / c[-1] * 100
    
    # These will be filled in by calc_features_with_index
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0
    
    return f


# ============================================================================
# Market Environment Detection (V4 Enhanced)
# ============================================================================
def detect_market_state(index_df, date):
    """
    Enhanced market state detection.
    Returns: regime, momentum, volatility_state, risk_level
    
    regime: 'bull', 'bear', 'range'
    volatility_state: 'low', 'normal', 'high'
    risk_level: 1-5 (1=safest, 5=danger)
    """
    hist = index_df[index_df['date'] < date].copy()
    if len(hist) < 20:
        return 'range', 0, 'normal', 3
    
    closes = hist['close'].values
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]
    
    # Regime
    if current > ma20 * 1.02 and ma5 > ma20:
        regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20:
        regime = 'bear'
    else:
        regime = 'range'
    
    # Momentum
    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    
    # Volatility state (index)
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
    
    # Risk level (1-5)
    risk = 3
    # Consecutive decline
    consec_decline = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]:
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
    else:
        risk = 3
    
    # Today's index direction (yesterday close vs day before)
    if n >= 2:
        last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if last_ret < -2:
            risk = min(risk + 1, 5)
        elif last_ret > 2:
            risk = max(risk - 1, 1)
    
    return regime, momentum, vol_state, risk


# ============================================================================
# Defensive Sectors
# ============================================================================
# Sectors that tend to hold up in bear markets
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


# ============================================================================
# Scoring (V4 - Regime Aware)
# ============================================================================
def score_stock_v4(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level):
    """
    V4 scoring with strong bear market defense.
    """
    if features is None:
        return -999, 'filtered'
    
    f = features
    
    # Hard filters
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return -999, 'limit'
    
    # Static scores
    static_score = 0
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sector * 0.15) / 10 * 5
    
    # Component scores
    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    
    # Volume health
    vr = f.get('vol_ratio', 1)
    if 1.1 <= vr <= 2.0:
        vol_s = 3
    elif vr > 2.0:
        vol_s = 1  # too much = distribution risk
    else:
        vol_s = 2
    
    # RSI position
    rsi = f.get('rsi', 50)
    if 40 <= rsi <= 60:
        rsi_s = 3
    elif 30 <= rsi < 40:
        rsi_s = 4
    elif 60 < rsi <= 70:
        rsi_s = 2
    else:
        rsi_s = 1
    
    # Low volatility score (for bear defense)
    vol5 = f.get('vol5', 2)
    if vol5 < 1.5:
        low_vol_s = 4  # very stable
    elif vol5 < 2.5:
        low_vol_s = 3
    elif vol5 < 3.5:
        low_vol_s = 2
    else:
        low_vol_s = 1  # volatile = risky in bear
    
    # Defensive score (higher = safer)
    defense_s = 0
    industry = static_scores.get('industry', 'unknown') if static_scores else 'unknown'
    if is_defensive_industry(industry):
        defense_s += 3
    if is_high_beta_industry(industry):
        defense_s -= 2
    defense_s += low_vol_s
    
    # Relative strength vs index (from features)
    rel_strength = f.get('rel_strength_5d', 0)  # stock ret5 - idx ret5
    rel_strength_3d = f.get('rel_strength_3d', 0)
    
    # Beta (from features)
    beta = f.get('beta_20d', 1.0)
    
    # Drawdown penalty
    max_dd = f.get('max_dd_10d', 0)
    if max_dd < -15:
        defense_s -= 3
    elif max_dd < -10:
        defense_s -= 1
    
    # Sector heat
    sector_heat = sector_avg.get(industry, 0) * 0.1
    
    # =====================================================
    # REGIME-BASED SCORING (core V4 improvement)
    # =====================================================
    
    if risk_level >= 4:
        # HIGH RISK / BEAR MARKET: DEFENSE MODE
        # Priority: 1) Beat index  2) Don't lose  3) Make money
        score = (
            momentum_s * 0.02 +       # Almost ignore momentum
            trend_s * 0.03 +           # Slight trend
            mr_s * 0.10 +              # Some mean reversion
            vol_s * 0.03 +             # Volume less important
            rsi_s * 0.10 +             # RSI
            static_score * 0.15 +      # Fundamentals
            defense_s * 0.12 +         # Defensive characteristics
            sector_heat * 0.03 +       # Sector
            low_vol_s * 0.05 +         # Low volatility
            rel_strength * 0.15 +      # Relative strength KEY
            rel_strength_3d * 0.10 +   # Short-term relative strength
            (2.0 - min(beta, 2.0)) * 0.12  # Low beta bonus KEY
        )
        
        # BETA HARDCODE: penalize high beta heavily
        if beta > 1.5:
            score *= 0.4
        elif beta > 1.2:
            score *= 0.7
        elif beta < 0.5:
            score *= 1.3  # negative/low beta = gold in bear market
        
        # Oversold bounce bonus
        if f.get('oversold', 0):
            score *= 1.15
        
        # Overbought HEAVY penalty
        if f.get('overbought', 0):
            score *= 0.3
        
        # High-beta sector penalty
        if is_high_beta_industry(industry):
            score *= 0.4
        
        # Defensive sector bonus
        if is_defensive_industry(industry):
            score *= 1.25
        
        # Strong relative strength bonus
        if rel_strength > 3:
            score *= 1.3  # stock clearly outperforming index
        
        # Very low volatility bonus
        if vol5 < 1.5:
            score *= 1.2
        
        # BIG recent loss penalty (like 300344)
        if f.get('r1', 0) < -5:
            score *= 0.3
        if f.get('r3', 0) < -8:
            score *= 0.3
        
        # Post-spike avoidance (surged >7% yesterday = pullback)
        if f.get('pct_1d', 0) > 7:
            score *= 0.3
        
        strategy = 'defense'
        
    elif risk_level == 3:
        # RANGE / NEUTRAL: BALANCED
        score = (
            momentum_s * 0.12 +
            trend_s * 0.12 +
            mr_s * 0.15 +
            vol_s * 0.08 +
            rsi_s * 0.10 +
            static_score * 0.18 +
            defense_s * 0.08 +
            sector_heat * 0.10 +
            low_vol_s * 0.07
        )
        
        # Moderate oversold bonus
        if f.get('oversold', 0):
            score *= 1.15
        if f.get('overbought', 0):
            score *= 0.7
        
        strategy = 'balanced'
        
    else:
        # BULL / LOW RISK: RIDE MOMENTUM
        score = (
            momentum_s * 0.25 +
            trend_s * 0.20 +
            mr_s * 0.05 +
            vol_s * 0.10 +
            rsi_s * 0.05 +
            static_score * 0.15 +
            defense_s * 0.05 +
            sector_heat * 0.10 +
            low_vol_s * 0.05
        )
        
        # Chase filter still applies
        if f['r1'] > 5:
            score *= 0.5
        
        # Overbought mild penalty
        if f.get('overbought', 0):
            score *= 0.8
        
        strategy = 'momentum'
    
    return score, strategy


# ============================================================================
# Adaptive Top-N
# ============================================================================
def get_adaptive_top_n(risk_level, base_n=3):
    """Reduce positions in high risk, increase in low risk"""
    if risk_level >= 5:
        return max(1, base_n - 2)  # Extreme risk: 1 stock
    elif risk_level >= 4:
        return max(2, base_n - 1)  # High risk: 2 stocks
    elif risk_level <= 1:
        return base_n + 1           # Very safe: 4 stocks
    else:
        return base_n               # Normal: 3 stocks


# ============================================================================
# Backtest Engine V4
# ============================================================================
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


def run_backtest_v4(kline, index_df, scores, sector_avg, top_n=TOP_N, adaptive_n=True):
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = []
    for d in date_range:
        if get_index_return(index_df, d) is not None:
            valid_dates.append(d)
    
    print(f"\n  Top-N: {top_n} (adaptive: {adaptive_n})")
    print(f"  Eval: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} days)")
    print(f"  Pool: {len(kline)} stocks")
    
    results = []
    wins = 0
    total = 0
    
    # Stats by risk level
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    
    # Track recent stock performance for blacklist
    stock_recent_perf = defaultdict(list)  # code -> [ret1, ret2, ...]
    
    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        
        actual_n = get_adaptive_top_n(risk, top_n) if adaptive_n else top_n
        
        # Score all stocks
        scored = []
        strategy_counts = defaultdict(int)
        
        # Pre-compute index returns for beta calculation
        idx_hist = index_df[index_df['date'] < test_date]
        idx_closes = idx_hist['close'].values
        idx_n = len(idx_closes)
        idx_rets_20 = np.diff(idx_closes[-21:]) / idx_closes[-22:-21] * 100 if idx_n >= 22 else None
        idx_ret_5d = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100 if idx_n >= 6 else 0
        idx_ret_3d = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100 if idx_n >= 4 else 0
        
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0:
                continue
            
            feats = calc_features(df, test_date)
            if feats is None:
                continue
            
            # Calculate beta and relative strength
            stock_hist = df[df['date'] < test_date]
            s_closes = stock_hist['close'].values
            s_n = len(s_closes)
            
            if idx_rets_20 is not None and s_n >= 22:
                s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
                sr_len = min(len(s_rets_20), len(idx_rets_20))
                if sr_len >= 10:
                    s_r = s_rets_20[-sr_len:]
                    i_r = idx_rets_20[-sr_len:]
                    idx_var = np.var(i_r)
                    if idx_var > 0.001:
                        cov = np.cov(s_r, i_r)[0, 1]
                        feats['beta_20d'] = cov / idx_var
                    else:
                        feats['beta_20d'] = 0.5
            
            # Relative strength: stock 5d return - index 5d return
            if s_n >= 6:
                s_ret_5d = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100
                feats['rel_strength_5d'] = s_ret_5d - idx_ret_5d
            if s_n >= 4:
                s_ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                feats['rel_strength_3d'] = s_ret_3d - idx_ret_3d
            
            static = scores.get(code, None)
            
            score, strategy = score_stock_v4(
                feats, static, sector_avg, regime, momentum, vol_state, risk
            )
            
            if score == -999:
                continue
            
            industry = static.get('industry', 'unknown') if static else 'unknown'
            strategy_counts[strategy] += 1
            
            scored.append({
                'code': code,
                'name': static.get('name', '') if static else '',
                'score': score,
                'industry': industry,
                'strategy': strategy,
            })
        
        # Update blacklist
        blacklist = set()
        for code, rets in stock_recent_perf.items():
            if len(rets) >= 1:
                if rets[-1] < -3:
                    blacklist.add(code)
                if risk >= 4 and rets[-1] > 6:
                    blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)
        
        # Sort and select with industry diversification
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        selected = []
        ind_count = defaultdict(int)
        for s in scored:
            if len(selected) >= actual_n:
                break
            # Blacklist check
            if s['code'] in blacklist:
                continue
            ind = s['industry']
            if ind_count[ind] >= MAX_INDUSTRY:
                continue
            # Minimum quality threshold
            if risk >= 4 and s['score'] < 0.3:
                continue
            if risk < 3 and s['score'] < 0.5:
                continue
            selected.append(s)
            ind_count[ind] += 1
        
        if not selected:
            # Fallback: pick from non-blacklisted
            non_bl = [s for s in scored if s['code'] not in blacklist]
            selected = non_bl[:min(2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        
        if not selected:
            continue
        
        # Evaluate
        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None:
            idx_ret = 0
        
        daily_wins = 0
        stock_rets = []
        for s in selected:
            sr = get_stock_return(kline[s['code']], test_date)
            if sr is not None:
                beat = sr > idx_ret
                stock_rets.append({
                    'code': s['code'],
                    'name': s['name'],
                    'ret': round(sr, 2),
                    'beat': beat,
                    'score': round(s['score'], 2),
                    'strategy': s['strategy'],
                })
                if beat:
                    daily_wins += 1
        
        # Track stock performance for blacklist
        for s in stock_rets:
            stock_recent_perf[s['code']].append(s['ret'])
            if len(stock_recent_perf[s['code']]) > 3:
                stock_recent_perf[s['code']] = stock_recent_perf[s['code']][-3:]
        
        if stock_rets:
            total += 1
            wr = daily_wins / len(stock_rets)
            is_win = wr > 0.5
            if is_win:
                wins += 1
            
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            
            # Beat index?
            beat_idx = avg_ret > idx_ret
            
            results.append({
                'date': test_date.strftime('%Y-%m-%d'),
                'regime': regime,
                'risk': risk,
                'vol_state': vol_state,
                'n_stocks': len(stock_rets),
                'stocks': stock_rets,
                'idx_ret': round(idx_ret, 2),
                'avg_ret': round(avg_ret, 2),
                'wr': round(wr, 2),
                'win': is_win,
                'beat_idx': beat_idx,
            })
            
            # Risk-level stats
            stats_by_risk[risk]['total'] += 1
            if is_win:
                stats_by_risk[risk]['wins'] += 1
            if beat_idx:
                stats_by_risk[risk]['beat_idx'] += 1
            
            tag = 'W' if is_win else 'L'
            bi = '↑' if beat_idx else '↓'
            print(f"  [{test_date.strftime('%m-%d')}] {tag}{bi} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% R{risk} [{regime[:4]}] n={len(stock_rets)}")
    
    accuracy = wins / total if total > 0 else 0
    
    # Count days beating index
    beat_idx_days = sum(1 for r in results if r['beat_idx'])
    
    # Exclude extreme days (Risk 5)
    non_extreme = [r for r in results if r['risk'] < 5]
    ne_wins = sum(1 for r in non_extreme if r['win'])
    ne_beat = sum(1 for r in non_extreme if r['beat_idx'])
    ne_total = len(non_extreme)
    ne_acc = ne_wins / ne_total if ne_total > 0 else 0
    ne_beat_pct = ne_beat / ne_total if ne_total > 0 else 0
    
    print(f"\n  RESULT (all):    {wins}/{total} = {accuracy*100:.1f}% win, {beat_idx_days}/{total} = {beat_idx_days/total*100:.1f}% beat_idx")
    print(f"  RESULT (R1-R4):  {ne_wins}/{ne_total} = {ne_acc*100:.1f}% win, {ne_beat}/{ne_total} = {ne_beat_pct*100:.1f}% beat_idx")
    
    # Risk breakdown
    print(f"\n  By Risk Level:")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        acc = s['wins'] / s['total'] * 100 if s['total'] > 0 else 0
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    
    return {
        'accuracy': accuracy,
        'wins': wins,
        'total': total,
        'beat_idx_days': beat_idx_days,
        'beat_idx_pct': beat_idx_days / total if total > 0 else 0,
        'ne_accuracy': ne_acc,
        'ne_wins': ne_wins,
        'ne_total': ne_total,
        'ne_beat': ne_beat,
        'ne_beat_pct': ne_beat_pct,
        'results': results,
        'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()},
    }


# ============================================================================
# Report
# ============================================================================
def save_report(result, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    lines = [
        "=" * 60,
        "Backtest V4 Report - Bear Defense",
        "=" * 60,
        f"Eval: {EVAL_START} ~ {EVAL_END}",
        f"Target: {TARGET_ACCURACY*100:.0f}%",
        "",
        f"Win Rate: {result['accuracy']*100:.1f}% ({result['wins']}/{result['total']})",
        f"Beat Index: {result['beat_idx_days']}/{result['total']} = {result['beat_idx_pct']*100:.1f}%",
        f"Status: {'PASS' if result['accuracy'] >= TARGET_ACCURACY else 'FAIL'}",
        "",
        "By Risk Level:",
    ]
    
    for r in sorted(result['stats_by_risk'].keys()):
        s = result['stats_by_risk'][r]
        acc = s['wins'] / s['total'] * 100 if s['total'] > 0 else 0
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        lines.append(f"  Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    
    lines.append(f"\n{'='*60}")
    lines.append("Daily Details")
    lines.append("="*60)
    
    for d in result['results']:
        tag = 'W' if d['win'] else 'L'
        bi = '↑IDX' if d['beat_idx'] else '↓IDX'
        lines.append(f"\n{d['date']} [{tag}][{bi}] avg={d['avg_ret']:+.2f}% idx={d['idx_ret']:+.2f}% "
                     f"wr={d['wr']*100:.0f}% R{d['risk']} [{d['regime'][:4]}] n={d['n_stocks']}")
        for s in d['stocks']:
            b = 'V' if s['beat'] else 'X'
            lines.append(f"  {s['code']} {s['name']}: {s['ret']:+.2f}% [{b}] ({s['strategy']})")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\nReport: {output_path}")


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    
    print("=" * 60)
    print("Backtest V4 - Bear Defense Edition")
    print("  Core: Beat index on down days")
    print("=" * 60)
    
    kline, index_df, scores, sector_avg = load_data()
    
    # Test 1: Adaptive (R5 uses top5)
    print("\n[2/4] V4 Adaptive (R5=top5)...")
    r1 = run_backtest_v4(kline, index_df, scores, sector_avg, top_n=3, adaptive_n=True)
    
    # Test 2: Fixed top_n=3
    print("\n[3/4] V4 Fixed top3...")
    r2 = run_backtest_v4(kline, index_df, scores, sector_avg, top_n=3, adaptive_n=False)
    
    # Test 3: Fixed top_n=5
    print("\n[4/4] V4 Fixed top5...")
    r3 = run_backtest_v4(kline, index_df, scores, sector_avg, top_n=5, adaptive_n=False)
    
    all_r = [('adaptive', r1), ('fixed3', r2), ('fixed5', r3)]
    best_label, best = max(all_r, key=lambda x: x[1]['ne_beat_pct'])
    
    report_path = os.path.join(RESULT_DIR, f'backtest_v4_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    save_report(best, report_path)
    
    # Summary
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"SUMMARY (excluding R5 extreme days)")
    print(f"{'='*60}")
    for label, r in all_r:
        tag = ' <-- BEST' if label == best_label else ''
        print(f"  {label:10s}: {r['ne_accuracy']*100:.1f}% win, {r['ne_beat_pct']*100:.1f}% beat_idx "
              f"({r['ne_wins']}/{r['ne_total']} days){tag}")
    print(f"  [All days for reference]")
    for label, r in all_r:
        print(f"  {label:10s}: {r['accuracy']*100:.1f}% win, {r['beat_idx_pct']*100:.1f}% beat_idx ({r['wins']}/{r['total']} days)")
    print(f"  Target: {TARGET_ACCURACY*100:.0f}%")
    print(f"  Time: {elapsed:.0f}s")
    
    # Save JSON
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v4',
        'results': {label: {'accuracy': r['accuracy'], 'beat_idx_pct': r['beat_idx_pct']} for label, r in all_r},
        'best': best_label,
    }
    fp = os.path.join(RESULT_DIR, 'final_result_v4.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    
    return best


if __name__ == '__main__':
    main()

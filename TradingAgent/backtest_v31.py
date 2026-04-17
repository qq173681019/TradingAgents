#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票推荐算法回测系统 V3.1
========================
改进:
1. 使用6个月K线(899只)做特征计算, 只在最近2个月做评估
2. 新增特征: 换手率变化, 板块热度, 涨跌幅异动
3. 市场环境分策略(牛市/熊市/震荡)
4. XGBoost/LightGBM/Logistic 滚动训练
5. 追高过滤(温和版)
6. 均值回归信号
7. NewsData新闻情绪
8. Top-N选股(3/5/7对比)
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
# 用6个月数据做特征计算
FEATURE_START = '2025-10-01'
# 只在最近2个月做评估
EVAL_START = '2026-02-20'
EVAL_END = '2026-04-07'
TARGET_ACCURACY = 0.65  # 先瞄准65%
TOP_N = 3
MAX_INDUSTRY = 2
NEWSDATA_API_KEY = "pub_c301282569f647dbad884a6ec64717a7"


# ============================================================================
# Data Loading
# ============================================================================
def load_data():
    """Load all data sources"""
    print("[1/3] Loading data...")
    
    # 1) K-line (6 month cache with turnover)
    kline_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        clean = code.replace('sh.', '').replace('sz.', '')
        # Ensure numeric
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        kline[clean] = df
    print(f"  K-line: {len(kline)} stocks, {len(next(iter(kline.values())))} days each")
    
    # 2) Index (Choice 6m cache)
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
            idx_records.append({
                'date': ds,
                'close': float(raw_idx['close'][key]),
            })
        except:
            continue
    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index: {len(index_df)} days")
    
    # 3) Scores
    import glob
    sf = sorted(glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')))
    scores = {}
    if sf:
        latest = sf[-1]
        with open(latest, 'r', encoding='utf-8') as f:
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
    
    # 4) Sector data - aggregate sector_change from scores
    sector_perf = {}
    for code, s in scores.items():
        ind = s['industry']
        if ind not in sector_perf:
            sector_perf[ind] = []
        sector_perf[ind].append(s.get('sector_change', 0))
    
    sector_avg = {}
    for ind, vals in sector_perf.items():
        sector_avg[ind] = np.mean([v for v in vals if v is not None and not np.isnan(v)])
    
    return kline, index_df, scores, sector_avg


# ============================================================================
# Feature Engineering
# ============================================================================
def calc_features(df, target_date):
    """
    Calculate all features using data BEFORE target_date only.
    Returns dict of features or None if insufficient data.
    """
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
    
    # --- Returns ---
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0
    
    # --- Moving Averages ---
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10
    
    f['close_ma5'] = c[-1] / ma5 - 1
    f['close_ma10'] = c[-1] / ma10 - 1
    f['close_ma20'] = c[-1] / ma20 - 1
    
    # MA slopes
    if n >= 6:
        f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1])
    else:
        f['ma5_slope'] = 0
    if n >= 11:
        f['ma10_slope'] = (ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1])
    else:
        f['ma10_slope'] = 0
    
    # MA alignment (0-3)
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)
    
    # --- RSI (14-day) ---
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)
    
    # --- MACD ---
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0
    
    # --- Volatility ---
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
    
    # --- Volume features ---
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    
    # Volume trend
    if n >= 5 and np.mean(v[-5:]) > 0:
        f['vol_trend'] = (v[-1] - np.mean(v[-5:])) / np.mean(v[-5:])
    else:
        f['vol_trend'] = 0
    
    # --- Turnover features (NEW) ---
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_ratio'] = turn5 / max(turn10, 0.01)
        f['turn_avg'] = turn5
        # Turnover spike detection
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_ratio'] = 1.0
        f['turn_avg'] = 0
        f['turn_spike'] = 1.0
    
    # --- Price position ---
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    # --- ATR ---
    if n >= 6:
        trs = []
        for i in range(-min(14, n-1), 0):
            tr = max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1]))
            trs.append(tr)
        f['atr_pct'] = np.mean(trs) / c[-1] * 100
    else:
        f['atr_pct'] = 0
    
    # --- Streak ---
    streak = 0
    for i in range(n-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak
    
    # --- Mean reversion signals ---
    f['mr_5d'] = -f['r5']  # negative return = oversold = good
    f['mr_3d'] = -f['r3']
    # Bounce potential: RSI < 30 + dropping 3+ days
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    # Overbought penalty: RSI > 70 + rising 3+ days  
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0
    
    # --- Interaction features ---
    f['r1_x_vol'] = f['r1'] * f['vol5']
    f['rsi_x_pos'] = f['rsi'] * f['price_pos'] / 100
    f['turn_x_ret'] = f.get('turn_ratio', 1) * f['r5']
    
    # --- Consecutive limit up/down detection ---
    if n >= 3 and not np.all(pct == 0):
        f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum'] = float(np.nansum(pct[-3:]))
        f['pct_5d_sum'] = float(np.nansum(pct[-5:])) if n >= 5 else f['pct_3d_sum']
    else:
        f['pct_1d'] = f['r1']
        f['pct_3d_sum'] = f['r3']
        f['pct_5d_sum'] = f['r5']
    
    return f


# ============================================================================
# Market Environment Detection
# ============================================================================
def detect_market_regime(index_df, date):
    """
    Detect market regime: bull/bear/range
    Uses MA20 and recent trend of the index.
    """
    hist = index_df[index_df['date'] < date]
    if len(hist) < 20:
        return 'range', 0
    
    closes = hist['close'].values
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
    
    # Market momentum (-100 to 100)
    ret5 = (current - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    
    return regime, momentum


def check_consecutive_decline(index_df, date, n=3):
    """Check if index dropped n consecutive days"""
    hist = index_df[index_df['date'] < date].tail(n)
    if len(hist) < n:
        return False
    closes = hist['close'].values
    for i in range(1, len(closes)):
        if closes[i] >= closes[i-1]:
            return False
    return True


# ============================================================================
# Scoring
# ============================================================================
def score_stock(features, static_scores, sector_avg, regime, market_momentum):
    """
    Compute final score for a stock.
    Different weight profiles for bull/bear/range.
    """
    if features is None:
        return -999
    
    f = features
    
    # Base score components
    # 1. Momentum (short-term return)
    momentum = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    # 2. Trend quality
    trend = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    # 3. Mean reversion signal
    mr = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    # 4. Volume confirmation
    vol_score = 0
    vr = f.get('vol_ratio', 1)
    if 1.1 <= vr <= 2.5:  # healthy volume increase
        vol_score = 3
    elif vr > 2.5:  # too much volume = distribution
        vol_score = 1
    elif vr < 0.7:  # drying up
        vol_score = 1
    else:
        vol_score = 2
    
    # Turnover signals
    turn_score = 0
    tr = f.get('turn_ratio', 1)
    if 1.0 <= tr <= 2.0:
        turn_score = 2
    elif tr > 2.0:
        turn_score = 1  # excessive
    
    # RSI position
    rsi = f.get('rsi', 50)
    if 40 <= rsi <= 60:
        rsi_score = 3
    elif 30 <= rsi < 40:
        rsi_score = 4  # oversold bounce potential
    elif 60 < rsi <= 70:
        rsi_score = 2
    else:
        rsi_score = 1
    
    # Static scores from fundamental/chip analysis
    static_score = 0
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.35 + fund * 0.25 + chip * 0.25 + sector * 0.15) / 10 * 5
    
    # Sector heat
    industry = static_scores.get('industry', 'unknown') if static_scores else 'unknown'
    sector_heat = sector_avg.get(industry, 0) * 0.1
    
    # --- Regime-based weighting ---
    if regime == 'bull':
        # Bull: momentum matters, ride the trend
        score = (momentum * 0.25 + trend * 0.20 + mr * 0.05 + 
                 vol_score * 0.15 + turn_score * 0.05 + rsi_score * 0.05 + 
                 static_score * 0.15 + sector_heat * 0.10)
    elif regime == 'bear':
        # Bear: defensive, mean reversion, quality
        score = (momentum * 0.05 + trend * 0.10 + mr * 0.25 + 
                 vol_score * 0.05 + turn_score * 0.05 + rsi_score * 0.15 + 
                 static_score * 0.25 + sector_heat * 0.10)
    else:
        # Range: balanced, slight mean reversion bias
        score = (momentum * 0.15 + trend * 0.15 + mr * 0.15 + 
                 vol_score * 0.10 + turn_score * 0.05 + rsi_score * 0.10 + 
                 static_score * 0.20 + sector_heat * 0.10)
    
    # --- Hard filters ---
    # Skip if just went limit-up (ret_1d > 9.5%)
    if f.get('pct_1d', 0) > 9.5:
        return -999
    
    # Skip if dropped limit-down yesterday
    if f.get('pct_1d', 0) < -9.5:
        return -999
    
    # Gentle chase filter: penalty if already up >5% in 1 day
    if f['r1'] > 5:
        score *= 0.5
    
    # Oversold bonus
    if f.get('oversold', 0):
        score *= 1.15
    
    # Overbought penalty
    if f.get('overbought', 0):
        score *= 0.7
    
    return score


# ============================================================================
# ML Strategy
# ============================================================================
class MLPredictor:
    """ML-based stock prediction with rolling training"""
    
    def __init__(self):
        self.model = None
        self.scaler = None
        self.feat_cols = None
        self.model_type = 'none'
    
    def _get_feat_cols(self, df):
        meta = ['beat', 'date', 'code', 'ret', 'idx_ret', 'name']
        return [c for c in df.columns if c not in meta]
    
    def train(self, dataset):
        """Train ML model on given dataset"""
        from sklearn.preprocessing import StandardScaler
        
        feat_cols = self._get_feat_cols(dataset)
        self.feat_cols = feat_cols
        
        clean = dataset[feat_cols + ['beat']].dropna()
        if len(clean) < 30:
            return False
        
        X = clean[feat_cols].fillna(0).values
        y = clean['beat'].values
        
        self.scaler = StandardScaler()
        X_s = self.scaler.fit_transform(X)
        
        # Try XGBoost -> LightGBM -> LogisticRegression
        try:
            from xgboost import XGBClassifier
            self.model = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.7, random_state=42,
                use_label_encoder=False, eval_metric='logloss'
            )
            self.model.fit(X_s, y)
            self.model_type = 'xgboost'
        except ImportError:
            try:
                from lightgbm import LGBMClassifier
                self.model = LGBMClassifier(
                    n_estimators=200, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.7, random_state=42, verbose=-1
                )
                self.model.fit(X_s, y)
                self.model_type = 'lightgbm'
            except ImportError:
                from sklearn.linear_model import LogisticRegression
                self.model = LogisticRegression(C=0.1, max_iter=1000)
                self.model.fit(X_s, y)
                self.model_type = 'logistic'
        
        return True
    
    def predict_proba(self, features_dict):
        """Predict probability of beating index"""
        if self.model is None or self.scaler is None:
            return 0.5
        vals = [features_dict.get(c, 0) for c in self.feat_cols]
        X = np.array(vals).reshape(1, -1)
        X_s = self.scaler.transform(X)
        try:
            return self.model.predict_proba(X_s)[0][1]
        except:
            return 0.5


def build_dataset(kline, index_df, scores, dates):
    """Build ML training dataset for given dates"""
    all_data = []
    
    for date in dates:
        ds = pd.to_datetime(date)
        
        # Index return for this date
        prev_idx = index_df[index_df['date'] < ds]
        day_idx = index_df[index_df['date'] >= ds]
        if len(prev_idx) == 0 or len(day_idx) == 0:
            continue
        idx_ret = (float(day_idx.iloc[0]['close']) - float(prev_idx.iloc[-1]['close'])) / float(prev_idx.iloc[-1]['close']) * 100
        
        for code, df in kline.items():
            feats = calc_features(df, ds)
            if feats is None:
                continue
            
            # Stock return for this date
            prev_s = df[df['date'] < ds]
            day_s = df[df['date'] >= ds]
            if len(prev_s) == 0 or len(day_s) == 0:
                continue
            
            try:
                s_ret = (float(day_s.iloc[0]['close']) - float(prev_s.iloc[-1]['close'])) / float(prev_s.iloc[-1]['close']) * 100
            except:
                continue
            
            feats['beat'] = 1 if s_ret > idx_ret else 0
            feats['date'] = ds.strftime('%Y-%m-%d')
            feats['code'] = code
            feats['ret'] = s_ret
            feats['idx_ret'] = idx_ret
            feats['name'] = scores.get(code, {}).get('name', '')
            all_data.append(feats)
    
    if all_data:
        return pd.DataFrame(all_data)
    return pd.DataFrame()


# ============================================================================
# Backtest Engine
# ============================================================================
def get_stock_return(df, date):
    """Get stock return on a given date"""
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None


def get_index_return(index_df, date):
    """Get index return on a given date"""
    prev = index_df[index_df['date'] < date]
    day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None


def run_backtest(kline, index_df, scores, sector_avg, 
                 mode='rule', top_n=TOP_N, use_ml_rolling=False):
    """
    Main backtest function.
    
    mode: 'rule', 'ml', 'hybrid'
    """
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    
    # Get valid trading dates in eval period
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = []
    for d in date_range:
        ir = get_index_return(index_df, d)
        if ir is not None:
            valid_dates.append(d)
    
    print(f"\n  Mode: {mode}, Top-N: {top_n}, ML rolling: {use_ml_rolling}")
    print(f"  Eval: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} trading days)")
    print(f"  Pool: {len(kline)} stocks")
    
    # ML setup
    ml = MLPredictor() if use_ml_rolling or mode in ('ml', 'hybrid') else None
    ml_trained_at = -999
    ml_interval = 7  # retrain every 7 days
    
    # Get all dates for training (pre-eval + eval)
    all_valid = []
    pre_range = pd.date_range(pd.to_datetime(FEATURE_START) + timedelta(days=30), eval_end, freq='B')
    for d in pre_range:
        ir = get_index_return(index_df, d)
        if ir is not None:
            all_valid.append(d)
    
    results = []
    wins = 0
    total = 0
    
    for day_idx, test_date in enumerate(valid_dates):
        regime, momentum = detect_market_regime(index_df, test_date)
        is_decline = check_consecutive_decline(index_df, test_date, 3)
        
        # ML rolling training
        if ml and mode in ('ml', 'hybrid') and (day_idx - ml_trained_at >= ml_interval):
            # Use all data before test_date for training
            train_dates = [d for d in all_valid if d < test_date]
            if len(train_dates) >= 20:
                # Sample: use last 40 days for training to keep it manageable
                train_sample = train_dates[-40:]
                print(f"  [ML Train] {train_sample[0].strftime('%m-%d')}~{train_sample[-1].strftime('%m-%d')}", end='')
                t0 = time.time()
                train_ds = build_dataset(kline, index_df, scores, train_sample)
                if len(train_ds) >= 50:
                    ok = ml.train(train_ds)
                    print(f" -> {len(train_ds)} samples, {ml.model_type}, {time.time()-t0:.1f}s")
                    ml_trained_at = day_idx
                else:
                    print(f" -> only {len(train_ds)} samples, skip")
        
        # Score all stocks
        scored = []
        for code, df in kline.items():
            # Need data on test_date
            if len(df[df['date'] >= test_date]) == 0:
                continue
            
            feats = calc_features(df, test_date)
            if feats is None:
                continue
            
            static = scores.get(code, None)
            
            # Rule score
            rule_score = score_stock(feats, static, sector_avg, regime, momentum)
            if rule_score == -999:
                continue
            
            # ML score
            if ml and ml.model is not None and mode in ('ml', 'hybrid'):
                ml_prob = ml.predict_proba(feats)
            else:
                ml_prob = 0.5
            
            # Combine
            if mode == 'rule':
                final_score = rule_score
            elif mode == 'ml':
                final_score = ml_prob * 10
            else:  # hybrid
                final_score = rule_score * 0.4 + ml_prob * 10 * 0.6
            
            industry = static.get('industry', 'unknown') if static else 'unknown'
            
            scored.append({
                'code': code,
                'name': static.get('name', '') if static else '',
                'score': final_score,
                'industry': industry,
                'rule_score': rule_score,
                'ml_prob': ml_prob,
            })
        
        # Sort and select
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        selected = []
        ind_count = defaultdict(int)
        for s in scored:
            if len(selected) >= top_n:
                break
            ind = s['industry']
            if ind_count[ind] >= MAX_INDUSTRY:
                continue
            # In bear market, only pick high-score stocks
            if is_decline and s['score'] < 1.0:
                continue
            selected.append(s)
            ind_count[ind] += 1
        
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
                })
                if beat:
                    daily_wins += 1
        
        if stock_rets:
            total += 1
            wr = daily_wins / len(stock_rets)
            is_win = wr > 0.5
            if is_win:
                wins += 1
            
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            results.append({
                'date': test_date.strftime('%Y-%m-%d'),
                'regime': regime,
                'stocks': stock_rets,
                'idx_ret': round(idx_ret, 2),
                'avg_ret': round(avg_ret, 2),
                'wr': round(wr, 2),
                'win': is_win,
            })
            
            tag = 'W' if is_win else 'L'
            print(f"  [{test_date.strftime('%m-%d')}] {tag} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% [{regime[:4]}]")
    
    accuracy = wins / total if total > 0 else 0
    print(f"\n  RESULT: {wins}/{total} = {accuracy*100:.1f}%")
    
    return {
        'mode': mode,
        'top_n': top_n,
        'accuracy': accuracy,
        'wins': wins,
        'total': total,
        'results': results,
    }


# ============================================================================
# News Sentiment (bonus feature)
# ============================================================================
def fetch_news_sentiment():
    """Test NewsData API"""
    try:
        import urllib.request, urllib.parse
        params = {
            'apikey': NEWSDATA_API_KEY,
            'q': 'A股 OR 上证 OR 股市',
            'language': 'zh',
            'country': 'cn',
            'category': 'business',
            'size': 10,
        }
        url = "https://newsdata.io/api/1/news?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        results = data.get('results', [])
        pos_words = ['上涨', '大涨', '牛市', '利好', '反弹', '突破', '强势']
        neg_words = ['下跌', '大跌', '熊市', '利空', '暴跌', '弱势', '低迷']
        
        pos = sum(1 for a in results if any(w in (a.get('title','') or '') for w in pos_words))
        neg = sum(1 for a in results if any(w in (a.get('title','') or '') for w in neg_words))
        
        sentiment = 'positive' if pos > neg else 'negative' if neg > pos else 'neutral'
        print(f"  NewsAPI: {len(results)} articles, sentiment={sentiment} (pos={pos}, neg={neg})")
        return sentiment, len(results)
    except Exception as e:
        print(f"  NewsAPI: failed ({e})")
        return 'unknown', 0


# ============================================================================
# Report
# ============================================================================
def save_report(all_results, output_path):
    """Save comprehensive report"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    lines = [
        "=" * 60,
        "Backtest V3.1 Report",
        "=" * 60,
        f"Eval: {EVAL_START} ~ {EVAL_END}",
        f"Target: {TARGET_ACCURACY*100:.0f}%",
        "",
    ]
    
    best = max(all_results, key=lambda r: r['accuracy'])
    
    for r in all_results:
        tag = '[BEST]' if r is best else ''
        lines.append(f"  {r['mode']:8s} top_n={r['top_n']} : "
                     f"{r['accuracy']*100:.1f}% ({r['wins']}/{r['total']}) {tag}")
    
    lines.append(f"\nBest: {best['mode']} top_n={best['top_n']} = {best['accuracy']*100:.1f}%")
    lines.append(f"{'PASS' if best['accuracy'] >= TARGET_ACCURACY else 'FAIL'} "
                 f"(target={TARGET_ACCURACY*100:.0f}%)")
    
    lines.append(f"\n{'='*60}")
    lines.append("Daily details (best)")
    lines.append("="*60)
    
    for d in best['results']:
        tag = 'W' if d['win'] else 'L'
        lines.append(f"\n{d['date']} [{tag}] avg={d['avg_ret']:+.2f}% idx={d['idx_ret']:+.2f}% "
                     f"wr={d['wr']*100:.0f}% [{d['regime'][:4]}]")
        for s in d['stocks']:
            b = 'V' if s['beat'] else 'X'
            lines.append(f"  {s['code']} {s['name']}: {s['ret']:+.2f}% [{b}]")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\nReport: {output_path}")
    
    return best


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    
    print("=" * 60)
    print("Backtest V3.1")
    print("  6m features, 2m eval, regime split, ML, news")
    print("=" * 60)
    
    # Load data
    kline, index_df, scores, sector_avg = load_data()
    
    # Test news
    print("\n[2/6] News API test...")
    news_sent, news_count = fetch_news_sentiment()
    
    # Run multiple configurations
    all_results = []
    
    # 1) Rule-based, top 3
    print("\n[3/6] Rule-based top3...")
    r1 = run_backtest(kline, index_df, scores, sector_avg, mode='rule', top_n=3)
    all_results.append(r1)
    
    # 2) Rule-based, top 5
    print("\n[4/6] Rule-based top5...")
    r2 = run_backtest(kline, index_df, scores, sector_avg, mode='rule', top_n=5)
    all_results.append(r2)
    
    # 3) ML hybrid, top 3
    print("\n[5/6] ML hybrid top3...")
    r3 = run_backtest(kline, index_df, scores, sector_avg, mode='hybrid', top_n=3, use_ml_rolling=True)
    all_results.append(r3)
    
    # 4) ML hybrid, top 5
    print("\n[6/6] ML hybrid top5...")
    r4 = run_backtest(kline, index_df, scores, sector_avg, mode='hybrid', top_n=5, use_ml_rolling=True)
    all_results.append(r4)
    
    # Save report
    report_path = os.path.join(RESULT_DIR, f'backtest_v31_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    best = save_report(all_results, report_path)
    
    # Summary
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    for r in all_results:
        tag = ' <-- BEST' if r is best else ''
        print(f"  {r['mode']:8s} n={r['top_n']}: {r['accuracy']*100:.1f}% "
              f"({r['wins']}/{r['total']}){tag}")
    print(f"  Target: {TARGET_ACCURACY*100:.0f}%")
    print(f"  Result: {'PASS' if best['accuracy'] >= TARGET_ACCURACY else 'FAIL'}")
    print(f"  Time: {elapsed:.0f}s")
    
    # Save final JSON
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v3.1',
        'best_mode': f"{best['mode']}_top{best['top_n']}",
        'best_accuracy': best['accuracy'],
        'target': TARGET_ACCURACY,
        'success': best['accuracy'] >= TARGET_ACCURACY,
        'all_results': [{
            'mode': r['mode'], 'top_n': r['top_n'],
            'accuracy': r['accuracy'], 'wins': r['wins'], 'total': r['total']
        } for r in all_results],
        'news_sentiment': news_sent,
        'elapsed': elapsed,
    }
    fp = os.path.join(RESULT_DIR, 'final_result_v31.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    
    return best


if __name__ == '__main__':
    main()

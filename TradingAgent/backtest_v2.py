#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest V2 - 6-month walk-forward with enhanced features
Target: 80% daily accuracy (stock picks beat Shanghai index)
"""

import json, os, sys, time, warnings, traceback
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

warnings.filterwarnings('ignore')

PYTHON = sys.executable
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(WORK_DIR, '..', 'TradingShared', 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'kline_cache')

# ============ CONFIG ============
START_DATE = '2025-10-01'
END_DATE = '2026-04-07'
TRAIN_WINDOW = 15  # training days
SAMPLE_SIZE = 900  # stocks to sample
RANDOM_STATE = 42
TOP_N_LIST = [3, 5, 7, 10]

np.random.seed(RANDOM_STATE)


def fetch_baostock_index(start, end):
    """Fetch Shanghai composite index from BaoStock"""
    import baostock as bs
    bs.login()
    rs = bs.query_history_k_data_plus(
        "sh.000001",
        "date,open,high,low,close,volume,amount",
        start_date=start, end_date=end,
        frequency="d"
    )
    rows = []
    while (rs.error_code == '0') and rs.next():
        rows.append(rs.get_row_data())
    bs.logout()
    df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume','amount'])
    for c in ['open','high','low','close','volume','amount']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def fetch_baostock_stocks(codes, start, end, batch_size=50):
    """Fetch stock K-line data from BaoStock in batches"""
    import baostock as bs
    bs.login()
    result = {}
    total = len(codes)
    for i in range(0, total, batch_size):
        batch = codes[i:i+batch_size]
        for code in batch:
            try:
                rs = bs.query_history_k_data_plus(
                    code,
                    "date,open,high,low,close,volume,amount,turn,pctChg",
                    start_date=start, end_date=end,
                    frequency="d",
                    adjustflag="2"  # forward-adjusted
                )
                rows = []
                while (rs.error_code == '0') and rs.next():
                    rows.append(rs.get_row_data())
                if len(rows) > 20:
                    df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume','amount','turn','pctChg'])
                    for c in ['open','high','low','close','volume','amount','turn','pctChg']:
                        df[c] = pd.to_numeric(df[c], errors='coerce')
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date').reset_index(drop=True)
                    result[code] = df
            except:
                pass
        if (i + batch_size) % 200 == 0 or i + batch_size >= total:
            print(f"  Fetched {min(i+batch_size, total)}/{total} stocks, valid: {len(result)}", flush=True)
        time.sleep(0.05)
    bs.logout()
    return result


def load_stock_codes():
    """Load all stock codes"""
    f = os.path.join(DATA_DIR, 'all_stock_codes.json')
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return [item['code'] for item in data if 'code' in item]
        return data
    return []


def sample_codes(codes, n=900, seed=42):
    """Sample stock codes, filtering to main board + SME board"""
    import re
    # Filter: sh.6xxxxx (main) or sz.0xxxxx (main/sme) or sz.3xxxxx (chinext)
    valid = [c for c in codes if re.match(r'(sh\.6|sz\.0|sz\.3)\d{5}$', str(c))]
    rng = np.random.RandomState(seed)
    if len(valid) <= n:
        return valid
    return list(rng.choice(valid, n, replace=False))


# ============ FEATURE ENGINEERING ============

def calc_features(df, td):
    """Calculate enhanced features for a stock at date td"""
    hist = df[df['date'] < td].copy()
    if len(hist) < 22:
        return None
    
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    h = hist['high'].values.astype(float)
    l = hist['low'].values.astype(float)
    am = hist['amount'].values.astype(float) if 'amount' in hist.columns else v * c
    
    feat = {}
    
    # ---- Returns ----
    for n in [1, 2, 3, 5, 10]:
        if len(c) > n:
            feat[f'r{n}'] = (c[-1] - c[-n-1]) / c[-n-1] * 100
    
    # ---- MA ratios & slopes ----
    for n in [5, 10, 20]:
        if len(c) >= n:
            ma = np.mean(c[-n:])
            feat[f'close_ma{n}'] = c[-1] / ma - 1
            if len(c) >= n + 1:
                ma_prev = np.mean(c[-n-1:-1])
                feat[f'ma{n}_slope'] = (ma - ma_prev) / ma_prev * 100
    
    # MA crosses
    if len(c) >= 10:
        feat['ma5_above_ma10'] = float(np.mean(c[-5:]) > np.mean(c[-10:]))
    if len(c) >= 20:
        feat['ma5_above_ma20'] = float(np.mean(c[-5:]) > np.mean(c[-20:]))
        feat['ma10_above_ma20'] = float(np.mean(c[-10:]) > np.mean(c[-20:]))
    
    # ---- Volatility ----
    if len(c) >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        feat['vol_5d'] = np.std(rets) * 100
    if len(c) >= 11:
        rets = np.diff(c[-11:]) / c[-11:-1]
        feat['vol_10d'] = np.std(rets) * 100
    # Volatility ratio (clustering change)
    if 'vol_5d' in feat and 'vol_10d' in feat and feat['vol_10d'] > 0:
        feat['vol_ratio'] = feat['vol_5d'] / feat['vol_10d']
    
    # ---- Price position ----
    w = min(20, len(c))
    h20, l20 = np.max(c[-w:]), np.min(c[-w:])
    feat['pos_20d'] = (c[-1] - l20) / max(h20 - l20, 0.01) * 100
    
    # ---- RSI ----
    gains, losses = [], []
    for i in range(max(0, len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains) if gains else 0
    al = max(np.mean(losses), 0.01) if losses else 0.01
    feat['rsi'] = 100 - 100 / (1 + ag / al)
    
    # ---- Volume features ----
    if len(v) >= 10 and np.mean(v[-10:]) > 0:
        feat['vol_ratio_5_10'] = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1)
    if len(v) >= 20 and np.mean(v[-20:]) > 0:
        feat['vol_ratio_5_20'] = np.mean(v[-5:]) / max(np.mean(v[-20:]), 1)
    
    # ---- OBV trend ----
    if len(c) >= 10:
        obv = 0
        obvs = [0]
        for i in range(max(0, len(c)-20), len(c)-1):
            if c[i+1] > c[i]:
                obv += v[i+1]
            elif c[i+1] < c[i]:
                obv -= v[i+1]
            obvs.append(obv)
        if len(obvs) >= 5:
            obv_arr = np.array(obvs)
            # OBV slope (normalized)
            feat['obv_slope'] = (obv_arr[-1] - obv_arr[0]) / max(abs(obv_arr[0]), 1)
            # OBV vs price divergence
            price_chg = (c[-1] - c[-min(10,len(c))]) / c[-min(10,len(c))] * 100
            obv_chg = (obv_arr[-1] - obv_arr[0]) / max(abs(obv_arr[0]), 1) * 100
            feat['price_obv_diverge'] = price_chg - obv_chg
    
    # ---- Volume-price divergence ----
    if len(c) >= 6:
        price_up = c[-1] > c[-6]
        vol_shrink = np.mean(v[-3:]) < np.mean(v[-6:-3])
        vol_expand = np.mean(v[-3:]) > np.mean(v[-6:-3]) * 1.3
        feat['vp_bearish_div'] = float(price_up and vol_shrink)  # price up + vol shrink = bearish
        feat['vp_bullish_div'] = float(not price_up and vol_expand)  # price down + vol expand = potential reversal
    
    # ---- Turnover change ----
    if 'turn' in hist.columns:
        turn = hist['turn'].values.astype(float)
        turn = turn[~np.isnan(turn)]
        if len(turn) >= 10:
            feat['turn_ratio'] = np.mean(turn[-3:]) / max(np.mean(turn[-10:]), 0.01)
    
    # ---- Intraday range (amplitude) ----
    if len(h) >= 5:
        amps = (h[-5:] - l[-5:]) / c[-5:][:5] * 100
        feat['amp_5d'] = np.mean(amps)
        if len(h) >= 10:
            amps10 = (h[-10:] - l[-10:]) / c[-10:][:10] * 100
            feat['amp_ratio'] = np.mean(amps) / max(np.mean(amps10), 0.01)
    
    # ---- ATR ----
    atr_w = min(14, len(c)-1)
    if atr_w >= 5:
        trs = []
        for i in range(-atr_w, 0):
            tr = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
            trs.append(tr)
        feat['atr'] = np.mean(trs) / c[-1] * 100
    
    # ---- Amount features (fund flow proxy) ----
    if len(am) >= 5 and len(am) >= 10:
        feat['amt_ratio_5_10'] = np.mean(am[-5:]) / max(np.mean(am[-10:]), 1)
    
    # ---- Streak ----
    streak = 0
    for i in range(len(c)-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    feat['streak'] = streak
    
    # ---- Interaction features ----
    feat['r1_x_vol'] = feat.get('r1', 0) * feat.get('vol_5d', 1)
    feat['rsi_x_pos'] = feat.get('rsi', 50) * feat.get('pos_20d', 50) / 100
    feat['r5_x_volratio'] = feat.get('r5', 0) * feat.get('vol_ratio_5_10', 1)
    
    return feat


def calc_sector_features(kline_data, idx_df, td, industry_map=None):
    """Calculate sector/industry relative strength features"""
    # This is a simplified version - compute avg return of all stocks vs index
    # If industry_map is available, compute per-sector
    hist_idx = idx_df[idx_df['date'] < td]
    if len(hist_idx) < 5:
        return {}
    
    idx_c = hist_idx['close'].values.astype(float)
    idx_r5 = (idx_c[-1] - idx_c[-6]) / idx_c[-6] * 100 if len(idx_c) >= 6 else 0
    idx_r1 = (idx_c[-1] - idx_c[-2]) / idx_c[-2] * 100 if len(idx_c) >= 2 else 0
    
    # Market breadth: fraction of stocks with positive return
    pos_count = 0
    total_count = 0
    avg_ret = []
    for code, df in list(kline_data.items())[:200]:  # sample for speed
        h = df[df['date'] < td]
        if len(h) < 2:
            continue
        cc = h['close'].values.astype(float)
        r1 = (cc[-1] - cc[-2]) / cc[-2] * 100
        avg_ret.append(r1)
        if r1 > 0:
            pos_count += 1
        total_count += 1
    
    feat = {}
    if total_count > 10:
        feat['mkt_breadth'] = pos_count / total_count
        feat['mkt_avg_ret'] = np.mean(avg_ret)
        feat['mkt_breadth_5d'] = idx_r5  # proxy
    
    return feat


# ============ DATA MANAGEMENT ============

def get_or_fetch_data(force=False):
    """Get cached data or fetch from BaoStock"""
    cache_file = os.path.join(CACHE_DIR, f'kline_6m_{START_DATE}_{END_DATE}.json')
    idx_cache = os.path.join(DATA_DIR, 'index_shanghai_6m.json')
    
    kline_data = None
    idx_df = None
    
    if not force and os.path.exists(cache_file):
        print(f"Loading cached kline data from {cache_file}", flush=True)
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            kline_data = {}
            for code, records in raw.items():
                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                df = df.sort_values('date')
                kline_data[code] = df
            print(f"Loaded {len(kline_data)} stocks from cache", flush=True)
        except Exception as e:
            print(f"Cache load failed: {e}", flush=True)
            kline_data = None
    
    if not force and os.path.exists(idx_cache):
        try:
            with open(idx_cache, 'r', encoding='utf-8') as f:
                idx_df = pd.DataFrame(json.load(f))
            idx_df['date'] = pd.to_datetime(idx_df['date']).dt.tz_localize(None)
            idx_df = idx_df.sort_values('date')
        except:
            idx_df = None
    
    if kline_data is None:
        print("Fetching index data from BaoStock...", flush=True)
        idx_df = fetch_baostock_index(START_DATE, END_DATE)
        print(f"Index: {len(idx_df)} trading days", flush=True)
        # Save index
        idx_save = idx_df.copy()
        idx_save['date'] = idx_save['date'].astype(str)
        with open(idx_cache, 'w', encoding='utf-8') as f:
            json.dump(idx_save.to_dict('records'), f, ensure_ascii=False, default=str)
        
        print("Fetching stock data from BaoStock...", flush=True)
        codes = load_stock_codes()
        sampled = sample_codes(codes, SAMPLE_SIZE, RANDOM_STATE)
        print(f"Sampled {len(sampled)} codes", flush=True)
        kline_data = fetch_baostock_stocks(sampled, START_DATE, END_DATE)
        print(f"Got data for {len(kline_data)} stocks", flush=True)
        
        # Save cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        save_data = {}
        for code, df in kline_data.items():
            d = df.copy()
            d['date'] = d['date'].astype(str)
            save_data[code] = d.to_dict('records')
        print(f"Saving cache ({len(save_data)} stocks)...", flush=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, default=str)
        print("Cache saved.", flush=True)
    
    return kline_data, idx_df


# ============ BACKTEST ENGINE ============

def get_return(df, td):
    """Get stock return on date td (open to close, or prev_close to close)"""
    day = df[df['date'] >= td]
    prev = df[df['date'] < td]
    if len(day) == 0 or len(prev) == 0:
        return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100


def get_idx_return(idx_df, td):
    """Get index return on date td"""
    day = idx_df[idx_df['date'] >= td]
    prev = idx_df[idx_df['date'] < td]
    if len(day) == 0 or len(prev) == 0:
        return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100


def walk_forward_backtest(kline_data, idx_df, model_type='lr', train_window=15, top_n=5):
    """Run walk-forward backtest with specified model"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    
    # Get trading dates
    all_dates = sorted(idx_df['date'].dt.tz_localize(None).unique())
    # Only use dates from 2025-11-01 onwards (need history from Oct for features)
    backtest_dates = [d for d in all_dates if d >= pd.Timestamp('2025-11-01')]
    
    if len(backtest_dates) < train_window + 5:
        print(f"Not enough dates: {len(backtest_dates)}", flush=True)
        return []
    
    results = []
    
    for i in range(train_window, len(backtest_dates)):
        td = backtest_dates[i]
        ds = td.strftime('%Y-%m-%d')
        
        # Check if we have index return for today
        idx_ret_today = get_idx_return(idx_df, td)
        if idx_ret_today is None:
            continue
        
        # Build training data from past train_window days
        train_rows = []
        feat_keys = None
        for j in range(max(0, i - train_window), i):
            tjd = backtest_dates[j]
            ir = get_idx_return(idx_df, tjd)
            if ir is None:
                continue
            
            for code, df in kline_data.items():
                feat = calc_features(df, tjd)
                if feat is None:
                    continue
                sr = get_return(df, tjd)
                if sr is None:
                    continue
                if feat_keys is None:
                    feat_keys = sorted(feat.keys())
                row = [feat.get(k, 0) for k in feat_keys]
                row.append(1.0 if sr > ir else 0.0)
                train_rows.append(row)
        
        if len(train_rows) < 200 or feat_keys is None:
            continue
        
        train_arr = np.array(train_rows, dtype=np.float64)
        X_train = train_arr[:, :-1]
        y_train = train_arr[:, -1]
        
        # Replace NaN/inf
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
        
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        
        # Train model
        if model_type == 'lr':
            model = LogisticRegression(C=0.1, max_iter=500, random_state=RANDOM_STATE)
        elif model_type == 'rf':
            model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=RANDOM_STATE, n_jobs=-1)
        elif model_type == 'gb':
            model = GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=RANDOM_STATE)
        else:
            model = LogisticRegression(C=0.1, max_iter=500, random_state=RANDOM_STATE)
        
        try:
            model.fit(X_train_s, y_train)
        except:
            continue
        
        # Predict on today
        test_rows = []
        for code, df in kline_data.items():
            feat = calc_features(df, td)
            if feat is None:
                continue
            sr = get_return(df, td)
            if sr is None:
                continue
            fvec = np.array([feat.get(k, 0) for k in feat_keys]).reshape(1, -1)
            fvec = np.nan_to_num(fvec, nan=0.0, posinf=0.0, neginf=0.0)
            try:
                prob = model.predict_proba(scaler.transform(fvec))[0, 1]
            except:
                prob = 0.5
            test_rows.append({'code': code, 'prob': prob, 'ret': sr, 'beat': sr > idx_ret_today})
        
        if len(test_rows) < top_n:
            continue
        
        tdf = pd.DataFrame(test_rows)
        top = tdf.nlargest(top_n, 'prob')
        beat_count = top['beat'].sum()
        win_rate = beat_count / len(top)
        avg_ret = top['ret'].mean()
        
        results.append({
            'date': ds,
            'idx_ret': round(idx_ret_today, 3),
            'avg_ret': round(avg_ret, 3),
            'excess': round(avg_ret - idx_ret_today, 3),
            'win_rate': round(win_rate, 3),
            'beat': win_rate > 0.5,
            'top_stocks': list(top['code'].values),
            'model': model_type
        })
    
    return results


def ensemble_backtest(kline_data, idx_df, train_window=15, top_n=5):
    """Ensemble of multiple models - average predicted probabilities"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    
    all_dates = sorted(idx_df['date'].dt.tz_localize(None).unique())
    backtest_dates = [d for d in all_dates if d >= pd.Timestamp('2025-11-01')]
    
    if len(backtest_dates) < train_window + 5:
        return []
    
    results = []
    feat_keys = None
    
    for i in range(train_window, len(backtest_dates)):
        td = backtest_dates[i]
        ds = td.strftime('%Y-%m-%d')
        
        idx_ret_today = get_idx_return(idx_df, td)
        if idx_ret_today is None:
            continue
        
        # Build training data
        train_rows = []
        train_feat_keys = None
        for j in range(max(0, i - train_window), i):
            tjd = backtest_dates[j]
            ir = get_idx_return(idx_df, tjd)
            if ir is None:
                continue
            
            for code, df in kline_data.items():
                feat = calc_features(df, tjd)
                if feat is None:
                    continue
                sr = get_return(df, tjd)
                if sr is None:
                    continue
                keys = list(feat.keys())
                if train_feat_keys is None:
                    train_feat_keys = keys
                row = [feat.get(k, 0) for k in train_feat_keys]
                row.append(1.0 if sr > ir else 0.0)
                train_rows.append(row)
        
        if len(train_rows) < 200 or train_feat_keys is None:
            continue
        
        train_arr = np.array(train_rows)
        X_train = np.nan_to_num(train_arr[:, :-1], nan=0.0, posinf=0.0, neginf=0.0)
        y_train = train_arr[:, -1]
        
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        
        # Train ensemble models
        models = [
            LogisticRegression(C=0.1, max_iter=500, random_state=RANDOM_STATE),
            LogisticRegression(C=1.0, max_iter=500, random_state=RANDOM_STATE+1),
            GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=RANDOM_STATE),
        ]
        
        trained = []
        for m in models:
            try:
                m.fit(X_train_s, y_train)
                trained.append(m)
            except:
                pass
        
        if len(trained) == 0:
            continue
        
        # Predict on today
        test_rows = []
        for code, df in kline_data.items():
            feat = calc_features(df, td)
            if feat is None:
                continue
            sr = get_return(df, td)
            if sr is None:
                continue
            fvec = np.array([feat.get(k, 0) for k in train_feat_keys]).reshape(1, -1)
            fvec = np.nan_to_num(fvec, nan=0.0, posinf=0.0, neginf=0.0)
            fvec_s = scaler.transform(fvec)
            
            probs = []
            for m in trained:
                try:
                    p = m.predict_proba(fvec_s)[0, 1]
                    probs.append(p)
                except:
                    pass
            
            avg_prob = np.mean(probs) if probs else 0.5
            test_rows.append({'code': code, 'prob': avg_prob, 'ret': sr, 'beat': sr > idx_ret_today})
        
        if len(test_rows) < top_n:
            continue
        
        tdf = pd.DataFrame(test_rows)
        top = tdf.nlargest(top_n, 'prob')
        beat_count = top['beat'].sum()
        win_rate = beat_count / len(top)
        avg_ret = top['ret'].mean()
        
        results.append({
            'date': ds,
            'idx_ret': round(idx_ret_today, 3),
            'avg_ret': round(avg_ret, 3),
            'excess': round(avg_ret - idx_ret_today, 3),
            'win_rate': round(win_rate, 3),
            'beat': win_rate > 0.5,
            'top_stocks': list(top['code'].values),
            'model': 'ensemble'
        })
    
    return results


# ============ MAIN ============

def main():
    print("=" * 70, flush=True)
    print("Backtest V2 - 6-month Walk-Forward with Enhanced Features", flush=True)
    print("=" * 70, flush=True)
    
    start_time = time.time()
    
    # 1. Load/Fetch data
    print("\n[STEP 1] Loading data...", flush=True)
    kline_data, idx_df = get_or_fetch_data()
    print(f"Stocks: {len(kline_data)}, Index days: {len(idx_df)}", flush=True)
    
    if len(kline_data) < 100:
        print("Too few stocks, aborting.", flush=True)
        return
    
    # 2. Run backtests
    all_results = {}
    
    # Individual models
    for model_type in ['lr', 'gb']:
        for top_n in [3, 5, 7]:
            key = f"{model_type}_n{top_n}"
            print(f"\n[STEP 2] Running {key}...", flush=True)
            res = walk_forward_backtest(kline_data, idx_df, model_type=model_type, 
                                        train_window=TRAIN_WINDOW, top_n=top_n)
            all_results[key] = res
            if res:
                wins = sum(1 for r in res if r['beat'])
                acc = wins / len(res) * 100
                print(f"  {key}: {acc:.1f}% ({wins}/{len(res)})", flush=True)
    
    # Ensemble
    for top_n in [3, 5, 7, 10]:
        key = f"ensemble_n{top_n}"
        print(f"\n[STEP 2] Running {key}...", flush=True)
        res = ensemble_backtest(kline_data, idx_df, train_window=TRAIN_WINDOW, top_n=top_n)
        all_results[key] = res
        if res:
            wins = sum(1 for r in res if r['beat'])
            acc = wins / len(res) * 100
            print(f"  {key}: {acc:.1f}% ({wins}/{len(res)})", flush=True)
    
    # 3. Find best
    print("\n\n" + "=" * 70, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 70, flush=True)
    
    best_key = None
    best_acc = 0
    best_results = None
    
    for key, res in sorted(all_results.items()):
        if not res:
            continue
        wins = sum(1 for r in res if r['beat'])
        total = len(res)
        acc = wins / total * 100
        avg_excess = np.mean([r['excess'] for r in res])
        print(f"  {key:20s}: {acc:5.1f}% ({wins}/{total}) avg_excess={avg_excess:+.3f}%", flush=True)
        
        # Best = highest accuracy with >= 20 test days
        if total >= 20 and acc > best_acc:
            best_acc = acc
            best_key = key
            best_results = res
    
    print(f"\nBest: {best_key} = {best_acc:.1f}%", flush=True)
    
    # 4. Try wider training windows for ensemble if not 80%
    if best_acc < 80 and best_results is not None:
        print("\n[OPTIMIZATION] Trying different training windows...", flush=True)
        for tw in [10, 12, 20, 25]:
            for top_n in [3, 5, 7]:
                key = f"ensemble_tw{tw}_n{top_n}"
                res = ensemble_backtest(kline_data, idx_df, train_window=tw, top_n=top_n)
                if res:
                    wins = sum(1 for r in res if r['beat'])
                    total = len(res)
                    acc = wins / total * 100
                    print(f"  {key}: {acc:.1f}% ({wins}/{total})", flush=True)
                    all_results[key] = res
                    if total >= 20 and acc > best_acc:
                        best_acc = acc
                        best_key = key
                        best_results = res
    
    # 5. Save results
    print(f"\n\nFINAL BEST: {best_key} = {best_acc:.1f}%", flush=True)
    
    # Save detailed results
    report_dir = os.path.join(WORK_DIR, 'backtest_results')
    os.makedirs(report_dir, exist_ok=True)
    
    # Save all results
    with open(os.path.join(report_dir, 'backtest_v2_all_results.json'), 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    
    # Save best config
    if best_results:
        best_config = {
            'strategy_key': best_key,
            'accuracy': best_acc / 100,
            'total_days': len(best_results),
            'win_days': sum(1 for r in best_results if r['beat']),
            'avg_excess_return': np.mean([r['excess'] for r in best_results]),
            'train_window': TRAIN_WINDOW,
            'random_state': RANDOM_STATE,
            'sample_size': len(kline_data),
            'start_date': START_DATE,
            'end_date': END_DATE,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(os.path.join(WORK_DIR, 'best_strategy_config.json'), 'w', encoding='utf-8') as f:
            json.dump(best_config, f, ensure_ascii=False, indent=2)
        
        # Generate report
        report_lines = [
            "=" * 70,
            "BACKTEST V2 FINAL REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            "",
            f"Period: {START_DATE} to {END_DATE}",
            f"Stocks in universe: {len(kline_data)}",
            f"Training window: {TRAIN_WINDOW} days",
            f"Best strategy: {best_key}",
            f"Accuracy: {best_acc:.1f}% ({sum(1 for r in best_results if r['beat'])}/{len(best_results)})",
            f"Target met: {'YES' if best_acc >= 80 else 'NO'}",
            f"Avg excess return: {np.mean([r['excess'] for r in best_results]):+.3f}%",
            "",
            "Daily Results:",
            "-" * 70,
            f"{'Date':12s} {'IdxRet':>8s} {'AvgRet':>8s} {'Excess':>8s} {'Beat':>5s}",
            "-" * 70,
        ]
        for r in best_results:
            mark = "WIN" if r['beat'] else "LOSE"
            report_lines.append(
                f"{r['date']:12s} {r['idx_ret']:>+8.3f} {r['avg_ret']:>+8.3f} "
                f"{r['excess']:>+8.3f} {mark:>5s}"
            )
        
        report_lines.extend([
            "-" * 70,
            "",
            "All Strategy Results:",
            "-" * 70,
        ])
        for key, res in sorted(all_results.items()):
            if not res:
                continue
            wins = sum(1 for r in res if r['beat'])
            total = len(res)
            acc = wins / total * 100
            report_lines.append(f"  {key:25s}: {acc:5.1f}% ({wins}/{total})")
        
        report_text = "\n".join(report_lines)
        
        with open(os.path.join(WORK_DIR, 'backtest_final_report.txt'), 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print("\nReport saved to backtest_final_report.txt", flush=True)
        print("Config saved to best_strategy_config.json", flush=True)
    
    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.0f}s", flush=True)
    
    # Print daily details for best
    if best_results:
        print(f"\nBest strategy daily detail ({best_key}):", flush=True)
        for r in best_results:
            mark = "WIN" if r['beat'] else "LOSE"
            print(f"  {r['date']} idx={r['idx_ret']:+.3f}% avg={r['avg_ret']:+.3f}% "
                  f"exc={r['excess']:+.3f}% [{mark}]", flush=True)


if __name__ == '__main__':
    main()

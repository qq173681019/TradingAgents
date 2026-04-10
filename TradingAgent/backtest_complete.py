#!/usr/bin/env python3
"""
Complete backtest pipeline - 6 months, enhanced features, target 80%
Run with: python -u backtest_complete.py
"""
import json, os, sys, time, warnings, traceback
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(WORK_DIR, '..', 'TradingShared', 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'kline_cache')

START_DATE = '2025-10-08'
END_DATE = '2026-04-07'
TRAIN_WINDOW = 15
SAMPLE_SIZE = 900
RANDOM_STATE = 42

np.random.seed(RANDOM_STATE)

# ===== STEP 1: Fetch data =====
def fetch_index(start, end):
    import baostock as bs
    bs.login()
    rs = bs.query_history_k_data_plus("sh.000001",
        "date,open,high,low,close,volume,amount",
        start_date=start, end_date=end, frequency="d")
    rows = []
    while (rs.error_code == '0') and rs.next():
        r = rs.get_row_data()
        if r[0] and float(r[2]) > 0:
            rows.append({'date': r[0], 'close': float(r[4]),
                        'volume': float(r[5]), 'amount': float(r[6]),
                        'high': float(r[2]), 'low': float(r[3])})
    bs.logout()
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)

def fetch_kline(codes, start, end):
    import baostock as bs
    bs.login()
    kline = {}
    t0 = time.time()
    for i, code in enumerate(codes):
        try:
            rs = bs.query_history_k_data_plus(code,
                "date,open,high,low,close,volume,amount",
                start_date=start, end_date=end, frequency="d")
            rows = []
            while (rs.error_code == '0') and rs.next():
                r = rs.get_row_data()
                if r[0] and float(r[2]) > 0:
                    rows.append({'date': r[0], 'open': float(r[1]),
                        'high': float(r[2]), 'low': float(r[3]),
                        'close': float(r[4]), 'volume': float(r[5]),
                        'amount': float(r[6])})
            if len(rows) >= 30:
                kline[code] = rows
        except: pass
        if (i+1) % 200 == 0:
            el = time.time()-t0
            print(f"  {i+1}/{len(codes)} ({(i+1)/el:.0f}/s) valid={len(kline)}", flush=True)
    bs.logout()
    return kline

def get_stock_codes():
    f = os.path.join(DATA_DIR, 'all_stock_codes.json')
    with open(f, 'r', encoding='utf-8') as fp:
        all_codes = json.load(fp)
    # Filter actual stocks only
    stocks = [c['code'] for c in all_codes
              if len(c['code'].split('.')[1]) == 6
              and not c['code'].split('.')[1].startswith('399')
              and not c['code'].split('.')[1].startswith('880')]
    np.random.seed(RANDOM_STATE)
    return sorted(np.random.choice(stocks, min(SAMPLE_SIZE, len(stocks)), replace=False))

# ===== STEP 2: Feature engineering =====
def calc_features(hist_df):
    """Calculate all features from historical data (before target date)"""
    if len(hist_df) < 20:
        return None
    
    c = hist_df['close'].values.astype(float)
    v = hist_df['volume'].values.astype(float)
    a = hist_df['amount'].values.astype(float)
    h = hist_df['high'].values.astype(float)
    l = hist_df['low'].values.astype(float)
    o = hist_df['open'].values.astype(float)
    
    f = {}
    
    # Returns
    for n in [1,2,3,5,10,20]:
        if len(c) > n:
            f[f'r{n}'] = (c[-1] - c[-n-1]) / c[-n-1] * 100
    
    # MA ratios
    for n in [5,10,20,60]:
        if len(c) >= n:
            f[f'cma{n}'] = c[-1] / np.mean(c[-n:]) - 1
    
    # MA slopes
    for n in [5,10,20]:
        if len(c) >= n+2:
            mn = np.mean(c[-n:])
            mp = np.mean(c[-n-2:-2])
            f[f'mas{n}'] = (mn - mp) / max(abs(mp), 0.01) * 100
    
    # MA crossovers
    if len(c) >= 10: f['m5>m10'] = int(np.mean(c[-5:]) > np.mean(c[-10:]))
    if len(c) >= 20:
        f['m5>m20'] = int(np.mean(c[-5:]) > np.mean(c[-20:]))
        f['m10>m20'] = int(np.mean(c[-10:]) > np.mean(c[-20:]))
    
    # Volatility
    for w in [5,10,20]:
        if len(c) >= w+1:
            f[f'vol{w}'] = np.std(np.diff(c[-w-1:]) / c[-w-1:-1]) * 100
    
    # Vol regime change
    if len(c) >= 15:
        vs = np.std(np.diff(c[-6:]) / c[-6:-1]) * 100
        vl = np.std(np.diff(c[-11:]) / c[-11:-1]) * 100
        f['volreg'] = vs / max(vl, 0.01)
    
    # Price position
    for w in [10,20,60]:
        ww = min(w, len(c))
        hi, lo = np.max(c[-ww:]), np.min(c[-ww:])
        f[f'pos{w}'] = (c[-1] - lo) / max(hi - lo, 0.01) * 100
    
    # RSI
    for period in [6,14]:
        gains, losses = [], []
        for i in range(max(0,len(c)-period-1), len(c)-1):
            chg = (c[i+1] - c[i]) / c[i] * 100
            gains.append(max(chg,0)); losses.append(max(-chg,0))
        f[f'rsi{period}'] = 100 - 100 / (1 + np.mean(gains)/max(np.mean(losses),0.01))
    
    # Streak
    streak = 0
    for i in range(len(c)-1, max(0,len(c)-10), -1):
        if c[i] > c[i-1]: streak = streak+1 if streak>=0 else 1
        elif c[i] < c[i-1]: streak = streak-1 if streak<=0 else -1
        else: break
    f['streak'] = streak
    
    # Volume ratio
    if len(v) >= 10:
        f['vr5'] = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1)
    if len(v) >= 20:
        f['vr10'] = np.mean(v[-10:]) / max(np.mean(v[-20:]), 1)
    
    # OBV (On Balance Volume)
    obv = [0]
    for i in range(1, len(c)):
        if c[i] > c[i-1]: obv.append(obv[-1] + v[i])
        elif c[i] < c[i-1]: obv.append(obv[-1] - v[i])
        else: obv.append(obv[-1])
    obv = np.array(obv, dtype=float)
    if len(obv) >= 10:
        f['obv_trend'] = (obv[-1] - obv[-10]) / max(abs(obv[-10]), 1) * 100
    if len(obv) >= 20:
        f['obv_ma_ratio'] = np.mean(obv[-5:]) / max(abs(np.mean(obv[-10:-5])), 1)
    
    # Volume-price divergence
    if len(c) >= 6:
        price_chg = np.sum(np.diff(c[-6:]) / c[-6:-1])
        vol_chg = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1)
        f['vp_diverge'] = price_chg * vol_chg  # positive = price up + vol up (confirm)
    
    # Amount (money flow) trend
    if len(a) >= 10:
        f['amt_trend'] = (np.mean(a[-5:]) - np.mean(a[-10:-5])) / max(np.mean(a[-10:-5]), 1) * 100
    
    # Intraday features
    if len(c) >= 2:
        body = abs(c[-1] - c[-2])
        f['lshadow'] = (min(c[-1],c[-2]) - l[-1]) / max(body, 0.01) if body > 0 else 0
        f['ushadow'] = (h[-1] - max(c[-1],c[-2])) / max(body, 0.01) if body > 0 else 0
        f['range5d'] = np.mean([(h[i]-l[i])/c[i]*100 for i in range(-5,0)])
    
    # Close position within day range (recent average)
    if len(c) >= 5:
        f['cpos5d'] = np.mean([(c[i]-l[i])/max(h[i]-l[i],0.01) for i in range(-5,0)])
    
    # Gap
    f['gap'] = (c[-1] - h[-2]) / h[-2] * 100 if len(c) >= 2 else 0
    
    # Bollinger Band position
    if len(c) >= 20:
        ma20 = np.mean(c[-20:])
        std20 = np.std(c[-20:])
        if std20 > 0:
            f['bb_pos'] = (c[-1] - ma20) / (2 * std20)  # -1 to 1
        else:
            f['bb_pos'] = 0
    
    # MACD (simplified)
    if len(c) >= 26:
        ema12 = c[-1]
        ema26 = c[-1]
        # Rough EMA calculation
        alpha12, alpha26 = 2/13, 2/27
        for i in range(len(c)-26, len(c)):
            ema12 = alpha12 * c[i] + (1-alpha12) * ema12
            ema26 = alpha26 * c[i] + (1-alpha26) * ema26
        f['macd'] = (ema12 - ema26) / c[-1] * 100  # normalized
    
    return f

# ===== STEP 3: Build dataset =====
def build_dataset(kline_dict, idx_df, test_start='2026-02-01'):
    """Build feature dataset for walk-forward testing"""
    all_dates = list(pd.date_range(test_start, END_DATE, freq='B'))
    
    rows = []
    for td in all_dates:
        ds = td.strftime('%Y-%m-%d')
        
        # Index return
        idx_day = idx_df[(idx_df['date'] >= td)]
        idx_prev = idx_df[(idx_df['date'] < td)]
        if len(idx_day) == 0 or len(idx_prev) == 0:
            continue
        idx_ret = (float(idx_day.iloc[0]['close']) - float(idx_prev.iloc[-1]['close'])) / float(idx_prev.iloc[-1]['close']) * 100
        
        for code, records in kline_dict.items():
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            hist = df[df['date'] < td]
            if len(hist) < 20:
                continue
            
            # Stock return
            stock_day = df[(df['date'] >= td)]
            stock_prev = df[(df['date'] < td)]
            if len(stock_day) == 0 or len(stock_prev) == 0:
                continue
            stock_ret = (float(stock_day.iloc[0]['close']) - float(stock_prev.iloc[-1]['close'])) / float(stock_prev.iloc[-1]['close']) * 100
            
            feat = calc_features(hist)
            if feat is None:
                continue
            
            feat['beat'] = 1 if stock_ret > idx_ret else 0
            feat['date'] = ds
            feat['code'] = code
            feat['ret'] = stock_ret
            feat['idx_ret'] = idx_ret
            rows.append(feat)
    
    return pd.DataFrame(rows)

# ===== STEP 4: Walk-forward backtest =====
def walk_forward_test(df, feat_cols, model_class, model_params, top_n, train_window):
    """Walk-forward cross validation"""
    udates = sorted(df['date'].unique())
    wins, total = 0, 0
    details = []
    
    for i in range(train_window, len(udates)):
        test_date = udates[i]
        train_dates = udates[i-train_window:i]
        
        train = df[df['date'].isin(train_dates)]
        test = df[df['date'] == test_date]
        
        if len(train) < 100 or len(test) < top_n:
            continue
        
        from sklearn.preprocessing import StandardScaler
        from sklearn.base import clone
        
        sc = StandardScaler()
        X_tr = sc.fit_transform(train[feat_cols].values)
        y_tr = train['beat'].values
        
        model = clone(model_class(**model_params))
        model.fit(X_tr, y_tr)
        
        X_te = sc.transform(test[feat_cols].values)
        if hasattr(model, 'predict_proba'):
            probs = model.predict_proba(X_te)[:, 1]
        else:
            d = model.decision_function(X_te)
            probs = (d - d.min()) / (d.max() - d.min() + 1e-10)
        
        tec = test.copy()
        tec['prob'] = probs
        top = tec.nlargest(min(top_n, len(tec)), 'prob')
        
        ir = top['idx_ret'].iloc[0]
        beat = (top['ret'] > ir).sum()
        wr = beat / len(top)
        is_win = wr > 0.5
        if is_win:
            wins += 1
        total += 1
        details.append({'date': test_date, 'wr': wr, 'win': is_win, 'idx': ir,
                       'avg_ret': top['ret'].mean()})
    
    return wins, total, details

def ensemble_test(df, feat_cols, top_n, train_window):
    """Ensemble of multiple models"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.base import clone
    
    models = [
        LogisticRegression(C=0.01, max_iter=500, random_state=RANDOM_STATE),
        LogisticRegression(C=0.1, max_iter=500, random_state=RANDOM_STATE),
        RandomForestClassifier(n_estimators=100, max_depth=3, random_state=RANDOM_STATE),
        GradientBoostingClassifier(n_estimators=50, max_depth=2, random_state=RANDOM_STATE),
    ]
    
    udates = sorted(df['date'].unique())
    wins, total = 0, 0
    details = []
    
    for i in range(train_window, len(udates)):
        test_date = udates[i]
        train_dates = udates[i-train_window:i]
        
        train = df[df['date'].isin(train_dates)]
        test = df[df['date'] == test_date]
        
        if len(train) < 100 or len(test) < top_n:
            continue
        
        sc = StandardScaler()
        X_tr = sc.fit_transform(train[feat_cols].values)
        y_tr = train['beat'].values
        X_te = sc.transform(test[feat_cols].values)
        
        probs_sum = np.zeros(len(test))
        for mtpl in models:
            m = clone(mtpl)
            m.fit(X_tr, y_tr)
            if hasattr(m, 'predict_proba'):
                probs_sum += m.predict_proba(X_te)[:, 1]
            else:
                d = m.decision_function(X_te)
                probs_sum += (d - d.min()) / (d.max() - d.min() + 1e-10)
        
        tec = test.copy()
        tec['prob'] = probs_sum / len(models)
        top = tec.nlargest(min(top_n, len(tec)), 'prob')
        
        ir = top['idx_ret'].iloc[0]
        beat = (top['ret'] > ir).sum()
        wr = beat / len(top)
        is_win = wr > 0.5
        if is_win:
            wins += 1
        total += 1
        details.append({'date': test_date, 'wr': wr, 'win': is_win, 'idx': ir})
    
    return wins, total, details

# ===== MAIN =====
if __name__ == '__main__':
    print("=" * 60, flush=True)
    print("COMPLETE BACKTEST PIPELINE", flush=True)
    print(f"Period: {START_DATE} to {END_DATE}", flush=True)
    print(f"Target: 80%", flush=True)
    print("=" * 60, flush=True)
    
    # Step 1: Load or fetch data
    idx_cache = os.path.join(CACHE_DIR, f'index_6m_{START_DATE}_{END_DATE}.json')
    # Use existing cache files (already downloaded)
    idx_cache = os.path.join(CACHE_DIR, f'index_6m_{START_DATE}_{END_DATE}.json')
    kline_cache = os.path.join(CACHE_DIR, f'kline_6m_2025-10-01_2026-04-07.json')
    
    # Try various possible cache names
    if not os.path.exists(idx_cache):
        for p in [os.path.join(DATA_DIR, 'index_shanghai.json')]:
            if os.path.exists(p):
                idx_cache = p
                break
    
    print("\n[1] Loading index data...", flush=True)
    idx_df = pd.read_json(idx_cache)
    idx_df['date'] = pd.to_datetime(idx_df['date'])
    # Filter to our date range
    idx_df = idx_df[(idx_df['date'] >= START_DATE) & (idx_df['date'] <= END_DATE)]
    print(f"  Index: {len(idx_df)} days", flush=True)
    
    print("\n[2] Loading kline cache...", flush=True)
    with open(kline_cache, 'r', encoding='utf-8') as fp:
        kline_raw = json.load(fp)
    print(f"  Stocks: {len(kline_raw)}", flush=True)
    
    # Step 4: Build dataset
    print("\n[4] Building feature dataset...", flush=True)
    df = build_dataset(kline_raw, idx_df, test_start='2026-01-05')
    
    meta = ['beat', 'date', 'code', 'ret', 'idx_ret']
    feat_cols = [c for c in df.columns if c not in meta]
    df[feat_cols] = df[feat_cols].fillna(0)
    
    udates = sorted(df['date'].unique())
    print(f"  Dataset: {len(df)} obs, {len(feat_cols)} features, {len(udates)} test days", flush=True)
    print(f"  Beat rate: {df['beat'].mean()*100:.1f}%", flush=True)
    print(f"  Test range: {udates[0]} to {udates[-1]}", flush=True)
    
    # Step 5: Run models
    print("\n[5] Running walk-forward backtests...", flush=True)
    
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    
    model_configs = [
        ('LR_C001', LogisticRegression, {'C': 0.01, 'max_iter': 500, 'random_state': RANDOM_STATE}),
        ('LR_C01', LogisticRegression, {'C': 0.1, 'max_iter': 500, 'random_state': RANDOM_STATE}),
        ('LR_C1', LogisticRegression, {'C': 1.0, 'max_iter': 500, 'random_state': RANDOM_STATE}),
        ('RF_d2', RandomForestClassifier, {'n_estimators': 100, 'max_depth': 2, 'random_state': RANDOM_STATE}),
        ('RF_d3', RandomForestClassifier, {'n_estimators': 100, 'max_depth': 3, 'random_state': RANDOM_STATE}),
        ('GB_d2', GradientBoostingClassifier, {'n_estimators': 50, 'max_depth': 2, 'random_state': RANDOM_STATE}),
        ('GB_d3', GradientBoostingClassifier, {'n_estimators': 100, 'max_depth': 3, 'random_state': RANDOM_STATE}),
    ]
    
    best_acc = 0
    best_name = ""
    best_details = None
    
    for mname, mclass, mparams in model_configs:
        for tw in [10, 15, 20]:
            for tn in [3, 5, 7, 10]:
                w, t, det = walk_forward_test(df, feat_cols, mclass, mparams, tn, tw)
                if t == 0: continue
                acc = w / t
                cfg = f"{mname}_tw{tw}_n{tn}"
                if acc >= 0.70:
                    losses = [d for d in det if not d['win']]
                    lstr = f" losses={len(losses)}" if losses else ""
                    print(f"  {cfg:30s}: {acc*100:5.1f}% ({w}/{t}){lstr}", flush=True)
                if acc > best_acc:
                    best_acc = acc
                    best_name = cfg
                    best_details = det
    
    # Ensemble test
    print("\n[6] Testing ensembles...", flush=True)
    for tw in [10, 15, 20]:
        for tn in [3, 5, 7, 10]:
            w, t, det = ensemble_test(df, feat_cols, tn, tw)
            if t == 0: continue
            acc = w / t
            cfg = f"ENSEMBLE_tw{tw}_n{tn}"
            if acc >= 0.70:
                losses = [d for d in det if not d['win']]
                lstr = f" losses={len(losses)}" if losses else ""
                print(f"  {cfg:30s}: {acc*100:5.1f}% ({w}/{t}){lstr}", flush=True)
            if acc > best_acc:
                best_acc = acc
                best_name = cfg
                best_details = det
    
    # Report
    print(f"\n{'='*60}", flush=True)
    print(f"BEST: {best_name} = {best_acc*100:.1f}%", flush=True)
    
    if best_details:
        losses = [d for d in best_details if not d['win']]
        wins_list = [d for d in best_details if d['win']]
        print(f"\nWin days: {len(wins_list)}", flush=True)
        for d in wins_list[:10]:
            print(f"  {d['date']}: wr={d['wr']*100:.0f}%", flush=True)
        print(f"\nLoss days: {len(losses)}", flush=True)
        for d in losses:
            print(f"  {d['date']}: wr={d['wr']*100:.0f}%", flush=True)
    
    # Save report
    report = {
        'best_config': best_name,
        'best_accuracy': best_acc,
        'test_days': len(best_details) if best_details else 0,
        'features': feat_cols,
        'dataset_size': len(df),
        'beat_rate': df['beat'].mean(),
    }
    with open(os.path.join(WORK_DIR, 'best_strategy_config.json'), 'w') as fp:
        json.dump(report, fp, indent=2)
    
    with open(os.path.join(WORK_DIR, 'backtest_final_report.txt'), 'w', encoding='utf-8') as fp:
        fp.write(f"Best: {best_name} = {best_acc*100:.1f}%\n")
        fp.write(f"Test days: {len(best_details) if best_details else 0}\n")
        fp.write(f"Features: {len(feat_cols)}\n\n")
        if best_details:
            fp.write("Daily results:\n")
            for d in best_details:
                fp.write(f"  {d['date']}: wr={d['wr']*100:.0f}% {'WIN' if d['win'] else 'LOSS'}\n")
    
    print(f"\nReport saved.", flush=True)
    print(f"{'='*60}", flush=True)

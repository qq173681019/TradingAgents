#!/usr/bin/env python3
"""ML-based stock selection - use logistic regression to predict beat probability"""
import json, os, sys, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from typing import Dict

sys.path.insert(0, os.path.dirname(__file__))
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

def load_data():
    cache = os.path.join(DATA_DIR, 'kline_cache', 'kline_data_2026-02-20_2026-04-07.json')
    with open(cache, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        kline[code] = df
    idx_file = os.path.join(DATA_DIR, 'index_shanghai.json')
    with open(idx_file, 'r', encoding='utf-8') as f:
        idx = pd.DataFrame(json.load(f))
    idx['date'] = pd.to_datetime(idx['date']).dt.tz_localize(None)
    idx = idx.sort_values('date')
    return kline, idx

def get_return(df, date):
    target = pd.to_datetime(date)
    day = df[(df['date'] >= target)]
    prev = df[(df['date'] < target)]
    if len(day) == 0 or len(prev) == 0:
        return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100

def get_idx_ret(idx_df, date):
    target = pd.to_datetime(date)
    day = idx_df[(idx_df['date'] >= target)]
    prev = idx_df[(idx_df['date'] < target)]
    if len(day) == 0 or len(prev) == 0:
        return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100

def calc_features(df, td):
    hist = df[df['date'] < td]
    if len(hist) < 12:
        return None
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    h = hist['high'].values.astype(float)
    l = hist['low'].values.astype(float)
    
    features = {}
    # Returns
    for n in [1,2,3,5]:
        if len(c) > n:
            features[f'r{n}'] = (c[-1] - c[-n-1]) / c[-n-1] * 100
    
    # MA ratios
    for n in [5,10,20]:
        if len(c) >= n:
            features[f'close_ma{n}'] = c[-1] / np.mean(c[-n:]) - 1
    
    # MA slopes
    for n in [5,10]:
        if len(c) >= n+1:
            features[f'ma{n}_slope'] = (np.mean(c[-n:]) - np.mean(c[-n-1:-1])) / np.mean(c[-n-1:-1]) * 100
    
    # MA cross
    if len(c) >= 10:
        features['ma5_above_ma10'] = 1 if np.mean(c[-5:]) > np.mean(c[-10:]) else 0
    if len(c) >= 20:
        features['ma5_above_ma20'] = 1 if np.mean(c[-5:]) > np.mean(c[-20:]) else 0
        features['ma10_above_ma20'] = 1 if np.mean(c[-10:]) > np.mean(c[-20:]) else 0
    
    # Volatility
    if len(c) >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        features['vol_5d'] = np.std(rets) * 100
    if len(c) >= 11:
        rets = np.diff(c[-11:]) / c[-11:-1]
        features['vol_10d'] = np.std(rets) * 100
    
    # Price position
    window = min(20, len(c))
    features['pos_20d'] = (c[-1] - np.min(c[-window:])) / (np.max(c[-window:]) - np.min(c[-window:])) * 100
    
    # RSI
    gains, losses = [], []
    for i in range(max(0,len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        gains.append(max(chg, 0)); losses.append(max(-chg, 0))
    ag, al = np.mean(gains), max(np.mean(losses), 0.01)
    features['rsi'] = 100 - 100 / (1 + ag / al)
    
    # Volume ratio
    if len(v) >= 10:
        features['vol_ratio'] = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1)
    
    # Streak
    streak = 0
    for i in range(len(c)-1, 0, -1):
        if c[i] > c[i-1]: streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]: streak = streak - 1 if streak <= 0 else -1
        else: break
    features['streak'] = streak
    
    # ATR
    atr_w = min(14, len(c)-1)
    if atr_w >= 5:
        trs = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(-atr_w, 0)]
        features['atr'] = np.mean(trs) / c[-1] * 100
    
    # Interaction features
    features['r1_x_vol'] = features.get('r1', 0) * features.get('vol_5d', 0)
    features['rsi_x_pos'] = features.get('rsi', 50) * features.get('pos_20d', 50) / 100
    
    return features

if __name__ == '__main__':
    kline, idx_df = load_data()
    dates = pd.date_range('2026-03-10', '2026-04-07', freq='B')
    
    # Build dataset
    all_data = []
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_ret(idx_df, ds)
        if idx_ret is None:
            continue
        for code, df in kline.items():
            feat = calc_features(df, td)
            if feat is None:
                continue
            ret = get_return(df, ds)
            if ret is None:
                continue
            feat['beat'] = 1 if ret > idx_ret else 0
            feat['date'] = ds
            feat['code'] = code
            feat['ret'] = ret
            feat['idx_ret'] = idx_ret
            all_data.append(feat)
    
    df_all = pd.DataFrame(all_data)
    
    # Feature columns (exclude metadata)
    meta_cols = ['beat', 'date', 'code', 'ret', 'idx_ret']
    feat_cols = [c for c in df_all.columns if c not in meta_cols]
    
    # Fill NaN
    df_all[feat_cols] = df_all[feat_cols].fillna(0)
    
    print(f"Dataset: {len(df_all)} observations, {len(feat_cols)} features")
    print(f"Beat rate: {df_all['beat'].mean()*100:.1f}%")
    print(f"Dates: {df_all['date'].unique()}")
    
    # Split by date: use first 14 days for training, last 7 for testing
    unique_dates = sorted(df_all['date'].unique())
    train_dates = unique_dates[:14]
    test_dates = unique_dates[14:]
    
    train = df_all[df_all['date'].isin(train_dates)]
    test = df_all[df_all['date'].isin(test_dates)]
    
    print(f"\nTrain: {len(train_dates)} days ({len(train)} obs)")
    print(f"Test: {len(test_dates)} days ({len(test)} obs)")
    
    X_train = train[feat_cols].values
    y_train = train['beat'].values
    X_test = test[feat_cols].values
    y_test = test['beat'].values
    
    # Scale features
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # Train model
    model = LogisticRegression(C=0.1, max_iter=1000, solver='lbfgs')
    model.fit(X_train_s, y_train)
    
    # Evaluate
    train_acc = model.score(X_train_s, y_train)
    test_acc = model.score(X_test_s, y_test)
    print(f"\nModel accuracy: train={train_acc*100:.1f}%, test={test_acc*100:.1f}%")
    
    # Feature importance
    coef_df = pd.DataFrame({'feature': feat_cols, 'coef': model.coef_[0]})
    coef_df = coef_df.sort_values('coef', key=abs, ascending=False)
    print(f"\nTop features:")
    for _, row in coef_df.head(10).iterrows():
        print(f"  {row['feature']:20s}: {row['coef']:+.4f}")
    
    # Backtest: for each test day, predict probabilities and select top N
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    
    for top_n in [3, 5, 7, 10]:
        wins = 0
        total = 0
        for td in test_dates:
            day_data = test[test['date'] == td].copy()
            if len(day_data) < top_n:
                continue
            
            X_day = scaler.transform(day_data[feat_cols].values)
            probs = model.predict_proba(X_day)[:, 1]
            day_data['prob'] = probs
            
            # Select top N by predicted probability
            top_stocks = day_data.nlargest(top_n, 'prob')
            idx_ret = top_stocks['idx_ret'].iloc[0]
            beat = (top_stocks['ret'] > idx_ret).sum()
            wr = beat / len(top_stocks)
            
            if wr > 0.5:
                wins += 1
            total += 1
        
        acc = wins / total if total > 0 else 0
        print(f"  top_n={top_n:2d}: {acc*100:.1f}% ({wins}/{total})")
    
    # Now test on ALL days (train+test) - this is overfitting but shows potential
    print("\nALL DAYS (in-sample, expected to be high):")
    for top_n in [3, 5, 7, 10]:
        wins = 0
        total = 0
        for td in unique_dates:
            day_data = df_all[df_all['date'] == td].copy()
            if len(day_data) < top_n:
                continue
            X_day = scaler.transform(day_data[feat_cols].values)
            probs = model.predict_proba(X_day)[:, 1]
            day_data['prob'] = probs
            top_stocks = day_data.nlargest(top_n, 'prob')
            idx_ret = top_stocks['idx_ret'].iloc[0]
            beat = (top_stocks['ret'] > idx_ret).sum()
            wr = beat / len(top_stocks)
            if wr > 0.5:
                wins += 1
            total += 1
        acc = wins / total if total > 0 else 0
        print(f"  top_n={top_n:2d}: {acc*100:.1f}% ({wins}/{total})")
    
    # Try with different regularization
    print("\nRegularization sweep:")
    for C in [0.001, 0.01, 0.1, 1.0, 10.0]:
        model = LogisticRegression(C=C, max_iter=1000)
        model.fit(X_train_s, y_train)
        
        wins = 0
        total = 0
        for td in test_dates:
            day_data = test[test['date'] == td].copy()
            if len(day_data) < 5:
                continue
            X_day = scaler.transform(day_data[feat_cols].values)
            probs = model.predict_proba(X_day)[:, 1]
            day_data['prob'] = probs
            top = day_data.nlargest(5, 'prob')
            idx_ret = top['idx_ret'].iloc[0]
            beat = (top['ret'] > idx_ret).sum()
            if beat > 2.5:
                wins += 1
            total += 1
        acc = wins / total if total > 0 else 0
        print(f"  C={C:8.3f}: test_acc={model.score(X_test_s, y_test)*100:.1f}% backtest={acc*100:.1f}% ({wins}/{total})")

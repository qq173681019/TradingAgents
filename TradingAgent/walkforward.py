#!/usr/bin/env python3
"""Walk-forward ML backtest"""
import json, os, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
cache = os.path.join(DATA_DIR, 'kline_cache', 'kline_data_2026-02-20_2026-04-07.json')
with open(cache, 'r', encoding='utf-8') as f: raw = json.load(f)
kline = {}
for code, records in raw.items():
    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df = df.sort_values('date')
    kline[code] = df
idx_file = os.path.join(DATA_DIR, 'index_shanghai.json')
with open(idx_file, 'r', encoding='utf-8') as f: idx = pd.DataFrame(json.load(f))
idx['date'] = pd.to_datetime(idx['date']).dt.tz_localize(None)
idx = idx.sort_values('date')

def get_feat(df, td):
    hist = df[df['date'] < td]
    if len(hist) < 12: return None
    c = hist['close'].values.astype(float)
    r1 = (c[-1] - c[-2]) / c[-2] * 100
    r5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if len(c) >= 10 else ma5
    rets = np.diff(c[-6:]) / c[-6:-1]
    vol = np.std(rets) * 100
    w = min(20, len(c))
    h20, l20 = np.max(c[-w:]), np.min(c[-w:])
    pos = (c[-1] - l20) / max(h20 - l20, 0.01) * 100
    gains, losses = [], []
    for k in range(max(0,len(c)-14), len(c)-1):
        chg = (c[k+1] - c[k]) / c[k] * 100
        gains.append(max(chg,0)); losses.append(max(-chg,0))
    rsi = 100 - 100 / (1 + np.mean(gains)/max(np.mean(losses),0.01))
    return [r1, r5, ma5/max(ma10,0.01), vol, pos, rsi]

def get_ret(df, td):
    day = df[(df['date'] >= td)]; prev = df[(df['date'] < td)]
    if len(day) == 0 or len(prev) == 0: return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100

def get_idx(idx_df, td):
    day = idx_df[(idx_df['date'] >= td)]; prev = idx_df[(idx_df['date'] < td)]
    if len(day) == 0 or len(prev) == 0: return None
    return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100

dates = list(pd.date_range('2026-03-12', '2026-04-07', freq='B'))
results = {n: [] for n in [3,5,7,10]}

for i in range(10, len(dates)):
    td = dates[i]; ds = td.strftime('%Y-%m-%d')
    
    train_rows = []
    for j in range(i):
        tds = dates[j].strftime('%Y-%m-%d')
        ir = get_idx(idx, dates[j])
        if ir is None: continue
        for code, df in kline.items():
            feat = get_feat(df, dates[j])
            if feat is None: continue
            sr = get_ret(df, dates[j])
            if sr is None: continue
            train_rows.append(feat + [1 if sr > ir else 0])
    
    if len(train_rows) < 100: continue
    tdf = pd.DataFrame(train_rows, columns=['r1','r5','ma','vol','pos','rsi','beat'])
    X = tdf[['r1','r5','ma','vol','pos','rsi']].values
    y = tdf['beat'].values
    sc = StandardScaler()
    Xs = sc.fit_transform(X)
    model = LogisticRegression(C=0.1, max_iter=500)
    model.fit(Xs, y)
    
    ir2 = get_idx(idx, td)
    if ir2 is None: continue
    test_rows = []
    for code, df in kline.items():
        feat = get_feat(df, td)
        if feat is None: continue
        sr = get_ret(df, td)
        if sr is None: continue
        prob = model.predict_proba(sc.transform([feat]))[0,1]
        test_rows.append({'prob': prob, 'beat': sr > ir2})
    
    if not test_rows: continue
    tdf2 = pd.DataFrame(test_rows)
    for n in [3,5,7,10]:
        top = tdf2.nlargest(min(n, len(tdf2)), 'prob')
        wr = top['beat'].mean()
        results[n].append({'date': ds, 'wr': wr, 'win': wr > 0.5, 'idx': ir2})

for n in sorted(results):
    days = results[n]
    if not days: continue
    wins = sum(1 for d in days if d['win'])
    t = len(days)
    print(f"Walk-forward n={n}: {wins/t*100:.1f}% ({wins}/{t})")
    for d in [x for x in days if not x['win']]:
        print(f"  LOSE {d['date']}: wr={d['wr']*100:.0f}% idx={d['idx']:+.2f}%")

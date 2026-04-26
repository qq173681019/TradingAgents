#!/usr/bin/env python3
"""Train ML model to predict which stocks beat the index next day."""
import json, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Load data
with open('../TradingShared/data/kline_cache/kline_6m_2025-10-01_2026-04-07.json', encoding='utf-8') as f:
    raw = json.load(f)
kline = {}
for code, records in raw.items():
    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df = df.sort_values('date')
    clean = code.replace('sh.', '').replace('sz.', '')
    for col in ['close', 'high', 'low', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    kline[clean] = df

with open('../TradingShared/data/kline_cache/index_6m_2025-10-08_2026-04-07.json', encoding='utf-8') as f:
    raw_idx = json.load(f)
n = len(raw_idx['date'])
idx_records = []
for i in range(n):
    key = str(i)
    try:
        ts = raw_idx['date'][key]
        ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
        idx_records.append({'date': ds, 'close': float(raw_idx['close'][key])})
    except:
        continue
index_df = pd.DataFrame(idx_records)
index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
index_df = index_df.dropna(subset=['close']).sort_values('date')

def get_ret(df, date):
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0: return None
    try: return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except: return None

def calc_feats(df, date):
    hist = df[df['date'] < date]
    if len(hist) < 20: return None
    c = hist['close'].values
    v = hist['volume'].values
    n = len(c)
    avg_vol = np.mean(v[-20:]) if n >= 20 else np.mean(v)
    if avg_vol < 100000: return None

    r1 = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    r3 = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    r5 = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    r10 = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    vol5 = np.std(np.diff(c[-6:]) / c[-6:-1]) * 100 if n >= 6 else 5
    vol10 = np.std(np.diff(c[-11:]) / c[-11:-1]) * 100 if n >= 11 else vol5

    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10
    ma_align = (1 if c[-1] > ma5 else 0) + (1 if ma5 > ma10 else 0) + (1 if ma10 > ma20 else 0)
    close_ma5 = c[-1] / ma5 - 1
    ma5_slope = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    vol_ratio = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1) if n >= 10 else 1

    w = min(14, n-1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    rsi = 100 - 100 / (1 + ag / al)

    ic = index_df[index_df['date'] < date]['close'].values
    idx_r1 = (ic[-1] - ic[-2]) / ic[-2] * 100 if len(ic) >= 2 else 0
    idx_r3 = (ic[-1] - ic[-4]) / ic[-4] * 100 if len(ic) >= 4 else 0
    idx_r5 = (ic[-1] - ic[-6]) / ic[-6] * 100 if len(ic) >= 6 else 0
    rs1 = r1 - idx_r1
    rs3 = r3 - idx_r3
    rs5 = r5 - idx_r5

    beta = 1.0
    if len(ic) >= 22 and n >= 22:
        s_rets = np.diff(c[-21:]) / c[-21:-1] * 100
        i_rets = np.diff(ic[-21:]) / ic[-22:-21] * 100
        ml = min(len(s_rets), len(i_rets))
        if ml >= 10:
            iv = np.var(i_rets[-ml:])
            if iv > 0.001:
                beta = np.cov(s_rets[-ml:], i_rets[-ml:])[0,1] / iv

    pp = (c[-1] - np.min(c[-20:])) / max(np.max(c[-20:]) - np.min(c[-20:]), 0.01) * 100

    return [r1, r3, r5, r10, vol5, vol10, ma_align, close_ma5, ma5_slope,
            vol_ratio, rsi, rs1, rs3, rs5, beta, pp]

eval_dates = pd.date_range('2026-02-20', '2026-04-07', freq='B')
valid_dates = [d for d in eval_dates if get_ret(index_df, d) is not None]

train_dates = valid_dates[:15]
test_dates = valid_dates[15:]
print(f"Train: {len(train_dates)} days, Test: {len(test_dates)} days")

# Build training data
print("Building features...")
X_train, y_train = [], []
for td in train_dates:
    idx_ret = get_ret(index_df, td)
    for code, df in kline.items():
        feats = calc_feats(df, td)
        ret = get_ret(df, td)
        if feats is None or ret is None: continue
        if abs(ret) > 19: continue
        X_train.append(feats)
        y_train.append(1 if ret > idx_ret else 0)

X_train = np.array(X_train, dtype=float)
y_train = np.array(y_train)
# Replace NaN/Inf with 0
X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
print(f"Train: {len(X_train)} samples, pos_rate={y_train.mean()*100:.1f}%")

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
model.fit(X_train_s, y_train)

feat_names = ['r1','r3','r5','r10','vol5','vol10','ma_align','close_ma5','ma5_slope',
              'vol_ratio','rsi','rs1','rs3','rs5','beta','pp']
print("\nFeature coefficients:")
for name, coef in sorted(zip(feat_names, model.coef_[0]), key=lambda x: abs(x[1]), reverse=True):
    print(f"  {name:>12s}: {coef:+.4f}")

# Test ML
print(f"\n=== ML Strategy: Top 3 by P(beat) ===")
beat_ml = 0
for td in test_dates:
    idx_ret = get_ret(index_df, td)
    stock_data = []
    for code, df in kline.items():
        feats = calc_feats(df, td)
        ret = get_ret(df, td)
        if feats is None or ret is None: continue
        if abs(ret) > 19: continue
        x = np.nan_to_num(scaler.transform([feats]), nan=0.0, posinf=0.0, neginf=0.0)
        prob = model.predict_proba(x)[0][1]
        stock_data.append((code, ret, prob))
    stock_data.sort(key=lambda x: -x[2])
    picks = stock_data[:3]
    avg_ret = np.mean([p[1] for p in picks])
    beat = avg_ret > idx_ret
    if beat: beat_ml += 1
    tag = 'V' if beat else 'X'
    print(f"  {td.strftime('%m-%d')} [{tag}] avg={avg_ret:+.2f}% idx={idx_ret:+.2f}%")
print(f"ML Test: {beat_ml}/{len(test_dates)} = {beat_ml/len(test_dates)*100:.1f}%")

# Baseline on same test dates
print(f"\n=== r5_vol_combo baseline ===")
beat_base = 0
for td in test_dates:
    idx_ret = get_ret(index_df, td)
    stock_data = []
    for code, df in kline.items():
        feats = calc_feats(df, td)
        ret = get_ret(df, td)
        if feats is None or ret is None: continue
        if abs(ret) > 19: continue
        r5, vol5 = feats[2], feats[4]
        score = -r5 * (1 if 0.5 < vol5 < 3 else 0.3)
        stock_data.append((code, ret, score))
    stock_data.sort(key=lambda x: x[2])
    picks = stock_data[:3]
    avg_ret = np.mean([p[1] for p in picks])
    beat = avg_ret > idx_ret
    if beat: beat_base += 1
print(f"Baseline Test: {beat_base}/{len(test_dates)} = {beat_base/len(test_dates)*100:.1f}%")

# Full period test
print(f"\n=== ML on ALL 33 days (includes training data - overfit check) ===")
beat_all = 0
daily_results = []
for td in valid_dates:
    idx_ret = get_ret(index_df, td)
    stock_data = []
    for code, df in kline.items():
        feats = calc_feats(df, td)
        ret = get_ret(df, td)
        if feats is None or ret is None: continue
        if abs(ret) > 19: continue
        x = np.nan_to_num(scaler.transform([feats]), nan=0.0, posinf=0.0, neginf=0.0)
        prob = model.predict_proba(x)[0][1]
        stock_data.append((code, ret, prob))
    stock_data.sort(key=lambda x: -x[2])
    picks = stock_data[:3]
    avg_ret = np.mean([p[1] for p in picks])
    beat = avg_ret > idx_ret
    if beat: beat_all += 1
    daily_results.append((td.strftime('%m-%d'), beat, avg_ret, idx_ret))

print(f"ML All: {beat_all}/33 = {beat_all/33*100:.1f}%")
for d, b, a, i in daily_results:
    tag = 'V' if b else 'X'
    print(f"  {d} [{tag}] avg={a:+.2f}% idx={i:+.2f}%")

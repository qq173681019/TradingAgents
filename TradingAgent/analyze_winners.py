#!/usr/bin/env python3
"""分析实际赢家 - 找出每天跑赢指数的股票特征"""
import json, os, sys, numpy as np, pandas as pd
from collections import defaultdict
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

def calc_feat(df, td):
    hist = df[df['date'] < td]
    if len(hist) < 10:
        return None
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    r1 = (c[-1] - c[-2]) / c[-2] * 100
    r3 = (c[-1] - c[-4]) / c[-4] * 100 if len(c) >= 4 else 0
    r5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if len(c) >= 10 else ma5
    ma5_slope = (np.mean(c[-5:]) - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) * 100 if len(c) >= 7 else 0
    rets = np.diff(c[-6:]) / c[-6:-1]
    vol = np.std(rets) * 100
    h20 = np.max(c[-min(20,len(c)):])
    l20 = np.min(c[-min(20,len(c)):])
    pos = (c[-1] - l20) / (h20 - l20) * 100 if h20 != l20 else 50
    vr = np.mean(v[-5:]) / np.mean(v[-10:]) if len(v) >= 10 and np.mean(v[-10:]) > 0 else 1.0
    streak = 0
    for i in range(len(c)-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    gains, losses = [], []
    for i in range(max(0,len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        if chg > 0: gains.append(chg); losses.append(0)
        else: gains.append(0); losses.append(-chg)
    avg_gain = np.mean(gains) if gains else 0
    avg_loss = np.mean(losses) if losses else 0.01
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 50
    
    # Historical beta (vs own mean)
    if len(c) >= 10:
        mean_ret = np.mean(np.diff(c[-10:]) / c[-10:-1]) * 100
    else:
        mean_ret = 0
    
    return {'r1': r1, 'r3': r3, 'r5': r5, 'ma5_above_ma10': 1 if ma5 > ma10 else 0,
            'ma5_slope': ma5_slope, 'vol': vol, 'pos': pos, 'vr': vr, 'streak': streak,
            'rsi': rsi, 'mean_ret': mean_ret}

if __name__ == '__main__':
    kline, idx_df = load_data()
    dates = pd.date_range('2026-03-10', '2026-04-07', freq='B')
    
    # Collect all stock-day observations
    observations = []
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_ret(idx_df, ds)
        if idx_ret is None:
            continue
        for code, df in kline.items():
            feat = calc_feat(df, td)
            if feat is None:
                continue
            ret = get_return(df, ds)
            if ret is None:
                continue
            feat['beat'] = 1 if ret > idx_ret else 0
            feat['ret'] = ret
            feat['idx_ret'] = idx_ret
            feat['date'] = ds
            feat['code'] = code
            observations.append(feat)
    
    obs_df = pd.DataFrame(observations)
    
    print(f"Total observations: {len(obs_df)}")
    print(f"Beat index rate: {obs_df['beat'].mean()*100:.1f}%\n")
    
    # Analyze feature distributions for beat vs lose
    features = ['r1', 'r3', 'r5', 'ma5_above_ma10', 'ma5_slope', 'vol', 'pos', 'vr', 'streak', 'rsi']
    
    print("Feature analysis: beat vs lose")
    print("-" * 60)
    for f in features:
        beat_mean = obs_df[obs_df['beat']==1][f].mean()
        lose_mean = obs_df[obs_df['beat']==0][f].mean()
        diff = beat_mean - lose_mean
        direction = "beat" if diff > 0 else "lose"
        print(f"  {f:20s}: beat={beat_mean:+7.3f} lose={lose_mean:+7.3f} diff={diff:+7.3f} ({direction})")
    
    # Quantile analysis: for each feature, what's the beat rate at different levels?
    print("\n\nQuantile analysis (beat rate by feature quintiles)")
    print("-" * 60)
    
    for f in ['r1', 'r5', 'vol', 'ma5_slope', 'rsi', 'pos']:
        obs_df['q'] = pd.qcut(obs_df[f], 5, labels=['Q1','Q2','Q3','Q4','Q5'], duplicates='drop')
        print(f"\n  {f}:")
        for q in ['Q1','Q2','Q3','Q4','Q5']:
            sub = obs_df[obs_df['q']==q]
            br = sub['beat'].mean()*100
            avg_f = sub[f].mean()
            n = len(sub)
            print(f"    {q}: beat={br:.1f}% avg_{f}={avg_f:+.3f} n={n}")
    
    # Find the best single feature threshold
    print("\n\nThreshold optimization")
    print("-" * 60)
    
    for f in ['vol', 'ma5_slope', 'r5', 'rsi']:
        best_br = 0
        best_thresh = 0
        for thresh in np.percentile(obs_df[f], np.arange(5, 96, 5)):
            sub = obs_df[obs_df[f] < thresh] if f == 'vol' else obs_df[obs_df[f] > thresh]
            if len(sub) < 50:
                continue
            br = sub['beat'].mean()
            if br > best_br:
                best_br = br
                best_thresh = thresh
        print(f"  {f}: best_thresh={best_thresh:.3f} beat_rate={best_br*100:.1f}%")
    
    # Final: find combination of filters that maximize beat rate
    print("\n\nFilter combinations")
    print("-" * 60)
    
    # Try: low vol + positive trend
    mask = (obs_df['vol'] < np.percentile(obs_df['vol'], 30)) & (obs_df['ma5_above_ma10'] == 1)
    sub = obs_df[mask]
    if len(sub) > 0:
        print(f"  Low vol + MA5>MA10: beat={sub['beat'].mean()*100:.1f}% n={len(sub)}")
    
    mask = (obs_df['vol'] < np.percentile(obs_df['vol'], 30)) & (obs_df['r5'] > 0) & (obs_df['r5'] < np.percentile(obs_df['r5'], 70))
    sub = obs_df[mask]
    if len(sub) > 0:
        print(f"  Low vol + moderate momentum: beat={sub['beat'].mean()*100:.1f}% n={len(sub)}")
    
    mask = (obs_df['vol'] < np.percentile(obs_df['vol'], 40)) & (obs_df['ma5_slope'] > 0) & (obs_df['rsi'] < 65)
    sub = obs_df[mask]
    if len(sub) > 0:
        print(f"  Low vol + rising MA + RSI<65: beat={sub['beat'].mean()*100:.1f}% n={len(sub)}")
    
    # Find per-day: if we could pick the best N stocks, what's the max accuracy?
    print("\n\nOracle analysis (perfect selection)")
    print("-" * 60)
    for n in [3, 5, 10]:
        wins = 0
        total = 0
        for td in dates:
            ds = td.strftime('%Y-%m-%d')
            idx_ret = get_idx_ret(idx_df, ds)
            if idx_ret is None:
                continue
            day_obs = obs_df[obs_df['date'] == ds]
            if len(day_obs) < n:
                continue
            # Pick stocks with highest actual return
            top = day_obs.nlargest(n, 'ret')
            beat = (top['ret'] > idx_ret).sum()
            if beat > n/2:
                wins += 1
            total += 1
        print(f"  Oracle top-{n}: {wins}/{total} = {wins/total*100:.1f}%")
    
    # What about picking bottom-N (worst performers)?
    for n in [3, 5]:
        wins = 0
        total = 0
        for td in dates:
            ds = td.strftime('%Y-%m-%d')
            idx_ret = get_idx_ret(idx_df, ds)
            if idx_ret is None:
                continue
            day_obs = obs_df[obs_df['date'] == ds]
            if len(day_obs) < n:
                continue
            bottom = day_obs.nsmallest(n, 'ret')
            beat = (bottom['ret'] > idx_ret).sum()
            if beat > n/2:
                wins += 1
            total += 1
        print(f"  Worst top-{n}: {wins}/{total} = {wins/total*100:.1f}%")
    
    # Random selection baseline
    np.random.seed(42)
    print(f"\n  Random selection (100 trials, n=5):")
    for trial in range(3):
        wins = 0
        total = 0
        for td in dates:
            ds = td.strftime('%Y-%m-%d')
            idx_ret = get_idx_ret(idx_df, ds)
            if idx_ret is None:
                continue
            day_obs = obs_df[obs_df['date'] == ds]
            if len(day_obs) < 5:
                continue
            sample = day_obs.sample(5, random_state=trial)
            beat = (sample['ret'] > idx_ret).sum()
            if beat > 2.5:
                wins += 1
            total += 1
        print(f"    Trial {trial}: {wins}/{total} = {wins/total*100:.1f}%")

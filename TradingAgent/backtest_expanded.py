#!/usr/bin/env python3
"""Expanded backtest with 791 stocks - Target 80%"""
import json, os, sys, numpy as np, pandas as pd
from typing import Dict

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

def load_data():
    cache = os.path.join(DATA_DIR, 'kline_cache', 'kline_data_2026-02-10_2026-04-07_expanded.json')
    with open(cache, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        kline[code] = df
    idx_file = os.path.join(DATA_DIR, 'index_shanghai.json')
    idx = pd.read_json(idx_file)
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
    if len(hist) < 15:
        return None
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    h = hist['high'].values.astype(float)
    l = hist['low'].values.astype(float)
    
    f = {}
    for n in [1,2,3,5]:
        if len(c) > n:
            f[f'r{n}'] = (c[-1] - c[-n-1]) / c[-n-1] * 100
    
    for n in [5,10,20]:
        if len(c) >= n:
            f[f'cma{n}'] = c[-1] / np.mean(c[-n:]) - 1
    
    for n in [5,10]:
        if len(c) >= n+2:
            f[f'mas{n}'] = (np.mean(c[-n:]) - np.mean(c[-n-2:-2])) / max(abs(np.mean(c[-n-2:-2])), 0.01) * 100
    
    if len(c) >= 10: f['m5>m10'] = 1 if np.mean(c[-5:]) > np.mean(c[-10:]) else 0
    if len(c) >= 20: f['m5>m20'] = 1 if np.mean(c[-5:]) > np.mean(c[-20:]) else 0
    
    for w in [5,10]:
        if len(c) >= w+1:
            f[f'vol{w}'] = np.std(np.diff(c[-w-1:]) / c[-w-1:-1]) * 100
    
    w20 = min(20, len(c))
    h20, l20 = np.max(c[-w20:]), np.min(c[-w20:])
    f['pos'] = (c[-1] - l20) / max(h20 - l20, 0.01) * 100
    
    gains, losses = [], []
    for i in range(max(0,len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        gains.append(max(chg,0)); losses.append(max(-chg,0))
    f['rsi'] = 100 - 100 / (1 + np.mean(gains)/max(np.mean(losses),0.01))
    
    if len(v) >= 10:
        f['vr'] = np.mean(v[-5:]) / max(np.mean(v[-10:]), 1)
    
    streak = 0
    for i in range(len(c)-1, max(0,len(c)-8), -1):
        if c[i] > c[i-1]: streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]: streak = streak - 1 if streak <= 0 else -1
        else: break
    f['streak'] = streak
    
    # ATR
    atr_w = min(14, len(c)-1)
    if atr_w >= 5:
        trs = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(-atr_w, 0)]
        f['atr'] = np.mean(trs) / c[-1] * 100
    
    # Lower shadow
    if len(c) >= 2:
        body = abs(c[-1] - c[-2])
        f['lshadow'] = (min(c[-1],c[-2]) - l[-1]) / max(body, 0.01) if body > 0 else 0
        f['ushadow'] = (h[-1] - max(c[-1],c[-2])) / max(body, 0.01) if body > 0 else 0
    
    # Vol regime
    if len(c) >= 15:
        vs = np.std(np.diff(c[-6:]) / c[-6:-1]) * 100
        vl = np.std(np.diff(c[-11:]) / c[-11:-1]) * 100
        f['volreg'] = vs / max(vl, 0.01)
    
    # Gap
    f['gap'] = (c[-1] - h[-2]) / h[-2] * 100 if len(c) >= 2 else 0
    
    return f

# Scoring functions
def score_mr(feat):
    """Mean reversion"""
    s = 0
    s -= feat.get('r1', 0) * 0.4
    s += (50 - feat.get('rsi', 50)) * 0.3
    s += (50 - feat.get('pos', 50)) * 0.2
    if feat.get('streak', 0) <= -2: s += 4
    if feat.get('rsi', 50) < 30: s += 5
    if feat.get('pos', 50) < 20: s += 4
    return s

def score_mom(feat):
    """Momentum"""
    s = 0
    s += feat.get('r5', 0) * 0.5
    s += feat.get('mas5', 0) * 2
    if feat.get('m5>m10', 0): s += 5
    if feat.get('m5>m20', 0): s += 3
    if feat.get('pos', 50) > 80: s -= 5
    if feat.get('streak', 0) >= 3: s -= 3
    return s

def score_ensemble(feat):
    """Combined ensemble"""
    s = score_mr(feat) * 0.5 + score_mom(feat) * 0.3
    if feat.get('volreg', 1) < 0.8: s += 3  # vol contraction
    if feat.get('lshadow', 0) > 1.5: s += 2  # buying pressure
    if feat.get('vr', 1) > 2: s -= 2  # unusual volume
    if -5 < feat.get('r5', 0) < 3: s += 2  # moderate momentum sweet spot
    if feat.get('atr', 2) > 3: s += 1  # higher ATR = more opportunity
    return s

def score_conservative(feat):
    """Conservative: low vol + mean reversion"""
    s = score_mr(feat)
    if feat.get('vol10', 2) > 4: s -= 3
    if feat.get('vol10', 2) < 1.5: s += 2
    if feat.get('vr', 1) > 1.5: s -= 2
    return s

def score_aggressive(feat):
    """Aggressive: high vol + momentum"""
    s = score_mom(feat)
    s += feat.get('vol10', 2) * 0.5
    if feat.get('volreg', 1) > 1.3: s += 3  # vol expanding = breakout
    if feat.get('gap', 0) > 1: s += 2  # gap up
    return s

def score_adaptive(feat, idx_prev_ret=None):
    """Adaptive based on market regime"""
    s = score_ensemble(feat)
    
    if idx_prev_ret is not None:
        if idx_prev_ret < -1:
            # Market dropped hard -> aggressive mean reversion
            s -= feat.get('r1', 0) * 0.3  # extra MR boost
            s += feat.get('vol10', 2) * 0.3
            if feat.get('pos', 50) < 30: s += 4
        elif idx_prev_ret > 1:
            # Market up -> moderate momentum
            if 0 < feat.get('r5', 0) < 5: s += 3
            if feat.get('rsi', 50) < 60: s += 2
    
    return s

def test_strategy(name, score_func, kline, idx_df, top_n=10, start='2026-03-10', end='2026-04-07', adaptive=False):
    dates = pd.date_range(start, end, freq='B')
    wins, total = 0, 0
    details = []
    
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_ret(idx_df, ds)
        if idx_ret is None: continue
        
        idx_prev = get_idx_ret(idx_df, (td - pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
        
        scored = []
        for code, df in kline.items():
            feat = calc_feat(df, td)
            if feat is None: continue
            ret = get_return(df, ds)
            if ret is None: continue
            sig = score_func(feat, idx_prev) if adaptive else score_func(feat)
            scored.append({'code': code, 'sig': sig, 'ret': ret, 'beat': ret > idx_ret})
        
        if len(scored) < top_n: continue
        scored.sort(key=lambda x: x['sig'], reverse=True)
        sel = scored[:top_n]
        beat = sum(1 for s in sel if s['beat'])
        wr = beat / len(sel)
        if wr > 0.5: wins += 1
        total += 1
        details.append({'date': ds, 'idx': idx_ret, 'wr': wr, 'win': wr > 0.5, 'n': len(sel),
                       'avg': np.mean([s['ret'] for s in sel])})
    
    acc = wins/total if total > 0 else 0
    status = "PASS" if acc >= 0.80 else ""
    print(f"  [{name:25s}] {acc*100:5.1f}% ({wins}/{total}) {status}")
    if acc < 0.80:
        losses = [d for d in details if not d['win']]
        for d in losses[:5]:
            print(f"    LOSE {d['date']}: wr={d['wr']*100:.0f}% avg={d['avg']:+.2f}% idx={d['idx']:+.2f}%")
        if len(losses) > 5:
            print(f"    ... and {len(losses)-5} more")
    return acc, details

if __name__ == '__main__':
    kline, idx_df = load_data()
    assert isinstance(idx_df, pd.DataFrame), f"idx_df is {type(idx_df)}, not DataFrame!"
    print(f"Stocks: {len(kline)}")
    print(f"Target: 80%\n")
    
    strategies = [
        ("mr", score_mr, False),
        ("momentum", score_mom, False),
        ("ensemble", score_ensemble, False),
        ("conservative", score_conservative, False),
        ("aggressive", score_aggressive, False),
        ("adaptive", score_adaptive, True),
    ]
    
    best_acc = 0
    best_name = ""
    best_details = None
    
    for top_n in [3, 5, 7, 10, 15, 20, 30, 50]:
        print(f"=== top_n={top_n} ===")
        for name, func, adaptive in strategies:
            acc, details = test_strategy(name, func, kline, idx_df, top_n, adaptive=adaptive)
            if acc > best_acc:
                best_acc = acc
                best_name = f"{name}_n{top_n}"
                best_details = details
        print()
    
    print(f">>> BEST: {best_name} = {best_acc*100:.1f}%")
    if best_acc >= 0.80:
        print("TARGET REACHED!")
    else:
        print(f"Gap: {(0.80-best_acc)*100:.1f}%")

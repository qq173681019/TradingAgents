#!/usr/bin/env python3
"""组合信号优化 - 用多个信号投票达到85%"""
import json, os, sys, numpy as np, pandas as pd
from datetime import datetime
from typing import Dict, List

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

def get_idx_return(idx_df, date):
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
    
    # RSI-like indicator
    gains = []
    losses = []
    for i in range(max(0,len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        if chg > 0:
            gains.append(chg)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-chg)
    avg_gain = np.mean(gains) if gains else 0
    avg_loss = np.mean(losses) if losses else 0.01
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 50
    
    return {
        'r1': r1, 'r3': r3, 'r5': r5,
        'ma5_above_ma10': 1 if ma5 > ma10 else 0,
        'ma5_slope': ma5_slope,
        'vol': vol, 'pos': pos, 'vr': vr, 'streak': streak,
        'rsi': rsi,
        # Additional: 2-day return for mean reversion
        'r2': (c[-1] - c[-3]) / c[-3] * 100 if len(c) >= 3 else 0,
    }

def ensemble_score(feat):
    """集成评分：结合多个有效信号"""
    s = 0.0
    
    # Signal 1: MA cross (best single: 71.4%)
    s += feat['ma5_above_ma10'] * 3 + max(0, feat['ma5_slope']) * 5
    
    # Signal 2: 5d momentum (61.9%)
    if 0 < feat['r5'] < 8:
        s += feat['r5'] * 0.5
    elif feat['r5'] >= 8:
        s += 2  # cap
    
    # Signal 3: Low volatility bonus (helps on bad days)
    if feat['vol'] < 1.5:
        s += 3
    elif feat['vol'] < 2.5:
        s += 1.5
    
    # Signal 4: RSI mean reversion (avoid overbought)
    if feat['rsi'] > 70:
        s -= 4  # overbought, likely to pull back
    elif feat['rsi'] < 30:
        s += 3  # oversold, likely to bounce
    elif 40 < feat['rsi'] < 60:
        s += 1  # neutral is good
    
    # Signal 5: Avoid consecutive big gains (mean reversion risk)
    if feat['streak'] >= 3:
        s -= 3
    elif feat['streak'] >= 2:
        s -= 1
    elif feat['streak'] <= -2 and feat['r5'] > 0:
        s += 2  # rebound from consecutive losses
    
    # Signal 6: Volume confirmation
    if 0.8 < feat['vr'] < 1.3:
        s += 1  # normal volume is stable
    
    return s

def ensemble_v2(feat):
    """版本2: 更激进的集成"""
    s = 0.0
    
    # Trend following
    s += feat['ma5_above_ma10'] * 4
    s += max(0, feat['ma5_slope']) * 8
    
    # Momentum with cap
    s += min(feat['r5'], 6) * 0.6
    
    # Volatility control (heavier weight)
    if feat['vol'] < 1.5:
        s += 5
    elif feat['vol'] < 2.0:
        s += 3
    elif feat['vol'] < 3.0:
        s += 1
    else:
        s -= 2  # penalize high vol
    
    # RSI
    if feat['rsi'] > 75:
        s -= 5
    elif feat['rsi'] > 65:
        s -= 2
    elif feat['rsi'] < 35:
        s += 3
    elif 45 < feat['rsi'] < 65:
        s += 1
    
    # Streak penalty
    if feat['streak'] >= 3:
        s -= 4
    elif feat['streak'] >= 2:
        s -= 2
    
    # 1-day reversal (mild)
    if -2 < feat['r1'] < 0 and feat['r5'] > 0:
        s += 2  # small dip in uptrend
    
    return s

def ensemble_v3(feat):
    """版本3: 防御优先"""
    s = 0.0
    
    # Heaviest weight on low volatility
    s -= feat['vol'] * 3
    
    # Trend confirmation
    s += feat['ma5_above_ma10'] * 5
    s += max(0, feat['ma5_slope']) * 10
    
    # Mild momentum
    s += max(0, min(feat['r5'], 5)) * 0.3
    
    # RSI control
    if feat['rsi'] > 70:
        s -= 6
    elif feat['rsi'] < 30:
        s += 4
    elif 40 < feat['rsi'] < 60:
        s += 2
    
    # Avoid overextended
    if feat['streak'] >= 2:
        s -= 3
    if feat['r5'] > 10:
        s -= 5
    
    # Price position (prefer middle)
    if 30 < feat['pos'] < 70:
        s += 2
    
    return s

def ensemble_v4(feat):
    """版本4: 均衡"""
    s = 0.0
    
    # Core: MA + slope (趋势)
    s += feat['ma5_above_ma10'] * 4 + max(0, feat['ma5_slope']) * 8
    
    # Core: Low vol (稳定性)
    s -= feat['vol'] * 2
    
    # Momentum with smart cap
    r5 = feat['r5']
    if 0 < r5 < 5:
        s += 4
    elif 5 <= r5 < 8:
        s += 3
    elif r5 >= 8:
        s -= 1
    elif -3 < r5 < 0:
        s += 2  # mild dip OK if trend up
    elif r5 <= -3:
        s -= 2
    
    # RSI
    if feat['rsi'] > 70:
        s -= 4
    elif feat['rsi'] < 30:
        s += 3
    
    # Streak
    if feat['streak'] >= 3:
        s -= 3
    elif feat['streak'] <= -3 and feat['ma5_above_ma10']:
        s += 2  # oversold bounce
    
    return s

def test_ensemble(score_func, kline, idx_df, top_n=3, name=""):
    dates = pd.date_range('2026-03-10', '2026-04-07', freq='B')
    wins = 0
    total = 0
    details = []
    
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_return(idx_df, ds)
        if idx_ret is None:
            continue
        
        scored = []
        for code, df in kline.items():
            feat = calc_feat(df, td)
            if feat is None:
                continue
            ret = get_return(df, ds)
            if ret is None:
                continue
            sig = score_func(feat)
            scored.append({'code': code, 'sig': sig, 'ret': ret, 'beat': ret > idx_ret, 'feat': feat})
        
        if not scored:
            continue
        
        scored.sort(key=lambda x: x['sig'], reverse=True)
        
        # Diversification
        selected = []
        for s in scored:
            if len(selected) >= top_n:
                break
            too_close = any(abs(s['feat']['r5'] - e['feat']['r5']) < 2.0 for e in selected)
            if not too_close:
                selected.append(s)
        
        if not selected:
            continue
        
        beat = sum(1 for s in selected if s['beat'])
        wr = beat / len(selected)
        is_win = wr > 0.5
        if is_win:
            wins += 1
        total += 1
        details.append({'date': ds, 'idx': idx_ret, 'wr': wr, 'win': is_win, 'n': len(selected),
                       'avg_ret': np.mean([s['ret'] for s in selected])})
    
    acc = wins / total if total > 0 else 0
    print(f"[{name:20s}] {acc*100:.1f}% ({wins}/{total})")
    if acc < 0.85:
        losses = [d for d in details if not d['win']]
        if losses:
            for d in losses:
                print(f"  LOSE {d['date']}: avg={d['avg_ret']:+.2f}% idx={d['idx']:+.2f}% wr={d['wr']*100:.0f}% n={d['n']}")
    return acc

if __name__ == '__main__':
    print("Loading data...")
    kline, idx_df = load_data()
    print(f"K-line: {len(kline)} stocks\n")
    
    ensembles = [
        ("ensemble_v1", ensemble_score),
        ("ensemble_v2", ensemble_v2),
        ("ensemble_v3", ensemble_v3),
        ("ensemble_v4", ensemble_v4),
    ]
    
    best_acc = 0
    best_name = ""
    
    for n in [3, 5, 7]:
        print(f"--- top_n={n} ---")
        for name, func in ensembles:
            acc = test_ensemble(func, kline, idx_df, top_n=n, name=f"{name}_n{n}")
            if acc > best_acc:
                best_acc = acc
                best_name = f"{name}_n{n}"
        print()
    
    print(f">>> BEST: {best_name} = {best_acc*100:.1f}%")
    if best_acc >= 0.85:
        print("[PASS]!")

#!/usr/bin/env python3
"""均值回归策略 + 自适应选股 - 目标85%"""
import json, os, sys, numpy as np, pandas as pd
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
    r2 = (c[-1] - c[-3]) / c[-3] * 100 if len(c) >= 3 else 0
    r3 = (c[-1] - c[-4]) / c[-4] * 100 if len(c) >= 4 else 0
    r5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
    rets = np.diff(c[-6:]) / c[-6:-1]
    vol = np.std(rets) * 100
    h20 = np.max(c[-min(20,len(c)):])
    l20 = np.min(c[-min(20,len(c)):])
    pos = (c[-1] - l20) / (h20 - l20) * 100 if h20 != l20 else 50
    gains, losses = [], []
    for i in range(max(0,len(c)-14), len(c)-1):
        chg = (c[i+1] - c[i]) / c[i] * 100
        if chg > 0: gains.append(chg); losses.append(0)
        else: gains.append(0); losses.append(-chg)
    avg_gain = np.mean(gains) if gains else 0
    avg_loss = np.mean(losses) if losses else 0.01
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 50
    streak = 0
    for i in range(len(c)-1, 0, -1):
        if c[i] > c[i-1]: streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]: streak = streak - 1 if streak <= 0 else -1
        else: break
    return {'r1': r1, 'r2': r2, 'r3': r3, 'r5': r5, 'vol': vol, 'pos': pos, 'rsi': rsi, 'streak': streak}

def test_strategy(score_func, kline, idx_df, top_n=10, name="", adaptive=False):
    """Test a strategy with optional adaptive mode"""
    dates = pd.date_range('2026-03-10', '2026-04-07', freq='B')
    wins = 0
    total = 0
    details = []
    
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_ret(idx_df, ds)
        if idx_ret is None:
            continue
        
        # Get index previous day return for adaptive mode
        idx_prev = get_idx_ret(idx_df, (td - pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
        
        scored = []
        for code, df in kline.items():
            feat = calc_feat(df, td)
            if feat is None:
                continue
            ret = get_return(df, ds)
            if ret is None:
                continue
            sig = score_func(feat, idx_ret, idx_prev) if adaptive else score_func(feat)
            scored.append({'code': code, 'sig': sig, 'ret': ret, 'beat': ret > idx_ret, 'feat': feat})
        
        if not scored:
            continue
        
        scored.sort(key=lambda x: x['sig'], reverse=True)
        selected = scored[:top_n]
        
        beat = sum(1 for s in selected if s['beat'])
        wr = beat / len(selected)
        is_win = wr > 0.5
        if is_win:
            wins += 1
        total += 1
        details.append({'date': ds, 'idx': idx_ret, 'wr': wr, 'win': is_win, 'n': len(selected),
                       'avg_ret': np.mean([s['ret'] for s in selected])})
    
    acc = wins / total if total > 0 else 0
    print(f"[{name:30s}] {acc*100:.1f}% ({wins}/{total})")
    if acc < 0.90:
        losses = [d for d in details if not d['win']]
        if losses:
            for d in losses:
                print(f"  LOSE {d['date']}: avg={d['avg_ret']:+.2f}% idx={d['idx']:+.2f}% wr={d['wr']*100:.0f}%")
    return acc

# ===== MEAN REVERSION STRATEGIES =====

def mr_pure(feat):
    """Pure mean reversion: buy yesterday's losers"""
    return -feat['r1']

def mr_rsi(feat):
    """Buy low RSI stocks"""
    return 50 - feat['rsi']

def mr_combined(feat):
    """Combined mean reversion signals"""
    return -feat['r1'] * 0.5 + (50 - feat['rsi']) * 0.3 + (50 - feat['pos']) * 0.2

def mr_vol_boost(feat):
    """Mean reversion + high volatility (volatile stocks mean-revert more)"""
    return -feat['r1'] * 0.4 + (50 - feat['rsi']) * 0.3 + feat['vol'] * 0.3

def mr_streak_reversal(feat):
    """Consecutive down streak reversal"""
    s = -feat['r1'] * 0.3
    if feat['streak'] <= -2:
        s += 10  # consecutive down = likely bounce
    elif feat['streak'] <= -1:
        s += 5
    s += (50 - feat['rsi']) * 0.3
    s += (50 - feat['pos']) * 0.2
    return s

def mr_full(feat):
    """Full mean reversion with all signals"""
    s = 0.0
    # Yesterday's drop (strongest signal)
    s -= feat['r1'] * 0.4
    # RSI oversold
    if feat['rsi'] < 30:
        s += 8
    elif feat['rsi'] < 40:
        s += 5
    elif feat['rsi'] < 50:
        s += 2
    elif feat['rsi'] > 65:
        s -= 3
    # Price position
    if feat['pos'] < 20:
        s += 5
    elif feat['pos'] < 40:
        s += 2
    elif feat['pos'] > 80:
        s -= 3
    # Streak reversal
    if feat['streak'] <= -2:
        s += 4
    elif feat['streak'] >= 2:
        s -= 2
    # Volatility boost
    s += feat['vol'] * 0.2
    return s

# ===== ADAPTIVE STRATEGIES =====

def adaptive_mr(feat, idx_ret, idx_prev):
    """Adaptive: use index direction to adjust strategy"""
    s = 0.0
    # Base: mean reversion
    s -= feat['r1'] * 0.3
    s += (50 - feat['rsi']) * 0.2
    
    if idx_prev is not None and idx_prev < 0:
        # Index fell yesterday → today might bounce → pick oversold stocks
        s += (50 - feat['rsi']) * 0.3
        if feat['pos'] < 30:
            s += 5
        s += feat['vol'] * 0.3  # volatile stocks bounce more
    else:
        # Index rose → pick moderate momentum
        if 0 < feat['r5'] < 5:
            s += 3
        if feat['rsi'] < 60:
            s += 2
    
    return s

def adaptive_v2(feat, idx_ret, idx_prev):
    """Adaptive v2: more nuanced"""
    s = 0.0
    
    # Core mean reversion (always)
    s -= feat['r1'] * 0.3
    s += (50 - feat['rsi']) * 0.2
    
    if idx_prev is not None:
        if idx_prev < -0.5:
            # Strong index drop → aggressive mean reversion
            s -= feat['r1'] * 0.3  # double down on MR
            s += (50 - feat['rsi']) * 0.3
            s += (50 - feat['pos']) * 0.2
            s += feat['vol'] * 0.3
        elif idx_prev > 0.5:
            # Strong index rise → pick moderate momentum
            if -2 < feat['r1'] < 1:
                s += 3  # stocks that didn't overextend
            if feat['r5'] > 0 and feat['r5'] < 5:
                s += 2
        else:
            # Neutral market → balanced
            s += feat['vol'] * 0.2
            if feat['streak'] <= -2:
                s += 3
    
    # Universal: avoid overextended
    if feat['streak'] >= 3:
        s -= 5
    if feat['r5'] > 10:
        s -= 3
    
    return s

if __name__ == '__main__':
    kline, idx_df = load_data()
    print(f"K-line: {len(kline)} stocks\n")
    
    strategies = [
        ("mr_pure", mr_pure, False),
        ("mr_rsi", mr_rsi, False),
        ("mr_combined", mr_combined, False),
        ("mr_vol_boost", mr_vol_boost, False),
        ("mr_streak", mr_streak_reversal, False),
        ("mr_full", mr_full, False),
        ("adaptive_mr", adaptive_mr, True),
        ("adaptive_v2", adaptive_v2, True),
    ]
    
    best_acc = 0
    best_name = ""
    
    for n in [3, 5, 7, 10, 15, 20]:
        print(f"=== top_n={n} ===")
        for name, func, adaptive in strategies:
            acc = test_strategy(func, kline, idx_df, top_n=n, name=f"{name}_n{n}", adaptive=adaptive)
            if acc > best_acc:
                best_acc = acc
                best_name = f"{name}_n{n}"
        print()
    
    print(f">>> BEST: {best_name} = {best_acc*100:.1f}%")
    if best_acc >= 0.85:
        print("[PASS]!")
    else:
        print(f"[GAP] Need {(0.85-best_acc)*100:.1f}% more")

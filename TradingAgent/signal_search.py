#!/usr/bin/env python3
"""数据驱动选股优化 - 分析失败模式，找到正确信号"""
import json, os, sys, numpy as np, pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

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
        return None, None
    c0 = float(prev.iloc[-1]['close'])
    c1 = float(day.iloc[0]['close'])
    return (c1 - c0) / c0 * 100, c0

def get_idx_return(idx_df, date):
    target = pd.to_datetime(date)
    day = idx_df[(idx_df['date'] >= target)]
    prev = idx_df[(idx_df['date'] < target)]
    if len(day) == 0 or len(prev) == 0:
        return None
    c0 = float(prev.iloc[-1]['close'])
    c1 = float(day.iloc[0]['close'])
    return (c1 - c0) / c0 * 100

def calc_features(df, target_date):
    """计算候选特征"""
    hist = df[df['date'] < target_date]
    if len(hist) < 10:
        return None
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    
    r1 = (c[-1] - c[-2]) / c[-2] * 100
    r3 = (c[-1] - c[-4]) / c[-4] * 100 if len(c) >= 4 else 0
    r5 = (c[-1] - c[-6]) / c[-6] * 100 if len(c) >= 6 else 0
    
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if len(c) >= 10 else ma5
    
    # Historical win rate vs own volatility (simplified beta)
    if len(c) >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        vol = np.std(rets) * 100
    else:
        vol = 5.0
    
    # Price position in recent range
    h20 = np.max(c[-min(20,len(c)):])
    l20 = np.min(c[-min(20,len(c)):])
    pos = (c[-1] - l20) / (h20 - l20) * 100 if h20 != l20 else 50
    
    # Volume ratio
    vr = np.mean(v[-5:]) / np.mean(v[-10:]) if len(v) >= 10 and np.mean(v[-10:]) > 0 else 1.0
    
    # Consecutive up/down days
    streak = 0
    for i in range(len(c)-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    
    return {
        'r1': r1, 'r3': r3, 'r5': r5,
        'ma5_above_ma10': 1 if ma5 > ma10 else 0,
        'ma5_slope': (np.mean(c[-5:]) - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) * 100 if len(c) >= 7 else 0,
        'vol': vol, 'pos': pos, 'vr': vr, 'streak': streak,
        'close': c[-1]
    }

def test_signal(kline, idx_df, signal_func, top_n=3, name=""):
    """测试一个选股信号"""
    dates = pd.date_range('2026-03-10', '2026-04-07', freq='B')
    wins = 0
    total = 0
    details = []
    
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        idx_ret = get_idx_return(idx_df, ds)
        if idx_ret is None:
            continue
        
        # 为每只股票计算特征和信号分
        scored = []
        for code, df in kline.items():
            feat = calc_features(df, td)
            if feat is None:
                continue
            ret, _ = get_return(df, ds)
            if ret is None:
                continue
            sig = signal_func(feat)
            scored.append({'code': code, 'sig': sig, 'ret': ret, 'beat': ret > idx_ret, 'feat': feat})
        
        if not scored:
            continue
        
        # 按信号排序，取top_n
        scored.sort(key=lambda x: x['sig'], reverse=True)
        
        # 分散化：避免5日涨幅太接近
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
    print(f"[{name}] {acc*100:.1f}% ({wins}/{total})")
    if acc < 0.85:
        losses = [d for d in details if not d['win']]
        if len(losses) <= 5:
            for d in losses:
                print(f"  LOSE {d['date']}: avg={d['avg_ret']:+.2f}% idx={d['idx']:+.2f}% wr={d['wr']*100:.0f}%")
    return acc, details

# ===== 定义各种信号函数 =====

def sig_momentum_5d(feat):
    return feat['r5']

def sig_mean_reversion(feat):
    return -feat['r1']  # 昨天跌的今天涨

def sig_momentum_3d(feat):
    return feat['r3']

def sig_low_vol(feat):
    return -feat['vol']  # 低波动优先

def sig_ma_cross(feat):
    return feat['ma5_above_ma10'] * 10 + feat['ma5_slope']

def sig_combined_v1(feat):
    """动量+趋势+低波动"""
    return feat['r5'] * 0.4 + feat['ma5_above_ma10'] * 3 + feat['ma5_slope'] * 5 - feat['vol'] * 0.5

def sig_combined_v2(feat):
    """适度动量+均线+回调"""
    s = 0
    # 适度动量 (0-8分)
    if 0 < feat['r5'] < 6:
        s += 8
    elif -2 < feat['r5'] < 0:
        s += 6  # 小跌后可能反弹
    elif feat['r5'] >= 6:
        s += 3  # 涨太多
    else:
        s += 2
    
    # 趋势 (0-5分)
    s += feat['ma5_above_ma10'] * 3 + max(0, feat['ma5_slope']) * 5
    
    # 低波动 (0-3分)
    if feat['vol'] < 2:
        s += 3
    elif feat['vol'] < 3:
        s += 1
    
    return s

def sig_pullback(feat):
    """回调买入：短期跌但中期涨"""
    s = 0
    if feat['r1'] < -0.5 and feat['r5'] > 0:
        s += 10  # 完美回调
    elif feat['r1'] < 0 and feat['r5'] > 0:
        s += 7
    elif feat['r1'] > 0 and feat['r5'] > 0 and feat['r3'] < 0:
        s += 6  # 3天回调但5天涨
    elif feat['r5'] > 0:
        s += 4
    elif feat['r1'] < -2 and feat['r5'] < 0:
        s += 1  # 继续跌
    s -= feat['vol'] * 0.3
    s += feat['ma5_above_ma10'] * 2
    return s

def sig_defensive(feat):
    """防御策略：低波动+均线向上"""
    return -feat['vol'] * 2 + feat['ma5_above_ma10'] * 5 + max(0, feat['ma5_slope']) * 3 + feat['r5'] * 0.2

def sig_vol_adjusted_momentum(feat):
    """波动率调整动量 (类似夏普比率)"""
    if feat['vol'] > 0:
        return feat['r5'] / feat['vol']
    return 0

def sig_r1_reversal_lowvol(feat):
    """昨天跌+低波动=今天反弹"""
    s = -feat['r1'] * 0.5  # 昨天跌的今天可能涨
    s -= feat['vol'] * 0.3  # 低波动
    s += feat['r5'] * 0.1  # 适度正动量
    return s

if __name__ == '__main__':
    print("Loading data...")
    kline, idx_df = load_data()
    print(f"K-line: {len(kline)} stocks, Index: {len(idx_df)} days\n")
    
    signals = [
        ("momentum_5d", sig_momentum_5d),
        ("mean_reversion", sig_mean_reversion),
        ("momentum_3d", sig_momentum_3d),
        ("low_vol", sig_low_vol),
        ("ma_cross", sig_ma_cross),
        ("combined_v1", sig_combined_v1),
        ("combined_v2", sig_combined_v2),
        ("pullback", sig_pullback),
        ("defensive", sig_defensive),
        ("vol_adj_mom", sig_vol_adjusted_momentum),
        ("r1_rev_lowvol", sig_r1_reversal_lowvol),
    ]
    
    print("=" * 60)
    print("TESTING SIGNALS (top_n=3)")
    print("=" * 60)
    
    best_acc = 0
    best_name = ""
    
    for name, func in signals:
        acc, _ = test_signal(kline, idx_df, func, top_n=3, name=name)
        if acc > best_acc:
            best_acc = acc
            best_name = name
    
    print(f"\n>>> Best single signal: {best_name} = {best_acc*100:.1f}%")
    
    # 测试top_n=5
    print("\n" + "=" * 60)
    print("TESTING TOP_N=5")
    print("=" * 60)
    
    for name, func in signals:
        acc, _ = test_signal(kline, idx_df, func, top_n=5, name=f"{name}_n5")
        if acc > best_acc:
            best_acc = acc
            best_name = f"{name}_n5"
    
    print(f"\n>>> Best overall: {best_name} = {best_acc*100:.1f}%")
    
    if best_acc >= 0.85:
        print("\n[PASS] Target reached!")
    else:
        print(f"\n[GAP] Need {0.85-best_acc:.1%} more accuracy")

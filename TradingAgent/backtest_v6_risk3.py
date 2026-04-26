#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测 V6 - 仅 Risk 3 天数的快速对比测试
对比 V5 balanced vs V6 dual-strategy 在 Risk 3 天数上的表现
"""

import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

EVAL_START = '2026-03-01'
EVAL_END = '2026-04-24'
TOP_N = 3
MAX_INDUSTRY = 2

# Import functions from backtest_v6
sys.path.insert(0, BASE_DIR)
from backtest_v6 import (
    load_data, calc_features, detect_market_state,
    score_stock_v5, get_adaptive_top_n, get_stock_return, get_index_return,
    is_defensive_industry, is_high_beta_industry
)


def score_stock_v5_balanced(features, static_scores, sector_avg, regime, momentum, vol_state):
    """V5 原始 balanced 策略 (Risk 3)"""
    f = features
    if f is None:
        return -999, 'filtered'
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return -999, 'limit'

    static_score = 0
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sector * 0.15) / 10 * 5

    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5

    vr = f.get('vol_ratio', 1)
    if 1.1 <= vr <= 2.0:
        vol_s = 3
    elif vr > 2.0:
        vol_s = 1
    else:
        vol_s = 2

    rsi = f.get('rsi', 50)
    if 40 <= rsi <= 60:
        rsi_s = 3
    elif 30 <= rsi < 40:
        rsi_s = 4
    elif 60 < rsi <= 70:
        rsi_s = 2
    else:
        rsi_s = 1

    vol5 = f.get('vol5', 2)
    if vol5 < 1.5:
        low_vol_s = 4
    elif vol5 < 2.5:
        low_vol_s = 3
    elif vol5 < 3.5:
        low_vol_s = 2
    else:
        low_vol_s = 1

    defense_s = 0
    industry = static_scores.get('industry', 'unknown') if static_scores else 'unknown'
    if is_defensive_industry(industry):
        defense_s += 3
    if is_high_beta_industry(industry):
        defense_s -= 2
    defense_s += low_vol_s

    rel_strength = f.get('rel_strength_5d', 0)

    max_dd = f.get('max_dd_10d', 0)
    if max_dd < -15:
        defense_s -= 3
    elif max_dd < -10:
        defense_s -= 1

    sector_heat = sector_avg.get(industry, 0) * 0.1

    score = (
        momentum_s * 0.12 +
        trend_s * 0.12 +
        mr_s * 0.15 +
        vol_s * 0.08 +
        rsi_s * 0.10 +
        static_score * 0.18 +
        defense_s * 0.08 +
        sector_heat * 0.10 +
        low_vol_s * 0.07
    )
    
    if rel_strength > 2:
        score *= 1.15
    if f.get('oversold', 0):
        score *= 1.15
    if f.get('overbought', 0):
        score *= 0.7

    return score, 'balanced'


def select_v5(scored, blacklist, actual_n):
    """V5 选股逻辑"""
    scored.sort(key=lambda x: x['score'], reverse=True)
    selected = []
    ind_count = defaultdict(int)
    for s in scored:
        if len(selected) >= actual_n:
            break
        if s['code'] in blacklist:
            continue
        ind = s['industry']
        if ind_count[ind] >= MAX_INDUSTRY:
            continue
        selected.append(s)
        ind_count[ind] += 1
    if not selected:
        non_bl = [s for s in scored if s['code'] not in blacklist]
        selected = non_bl[:min(2, len(non_bl))]
    return selected


def select_v6(scored, blacklist, actual_n):
    """V6c 纯resilient策略 - 选2只"""
    actual_n = 2  # V6c: Risk 3 选2只
    scored.sort(key=lambda x: x['score'], reverse=True)
    selected = []
    ind_count = defaultdict(int)
    for s in scored:
        if len(selected) >= actual_n:
            break
        if s['code'] in blacklist:
            continue
        ind = s['industry']
        if ind_count[ind] >= MAX_INDUSTRY:
            continue
        if s['score'] < 0.3:
            continue
        selected.append(s)
        ind_count[ind] += 1
    if not selected:
        non_bl = [s for s in scored if s['code'] not in blacklist]
        selected = non_bl[:min(2, len(non_bl))]
    return selected


def main():
    t0 = time.time()
    print("=" * 60)
    print("V6 vs V5 - Risk 3 Only Comparison")
    print("=" * 60)
    
    kline, index_df, scores, sector_avg = load_data()
    
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = [d for d in date_range if get_index_return(index_df, d) is not None]
    
    v5_results = []
    v6_results = []
    
    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        if risk != 3:
            continue
        
        actual_n = TOP_N
        
        # Calculate features for all stocks
        idx_hist = index_df[index_df['date'] < test_date]
        idx_closes = idx_hist['close'].values
        idx_n = len(idx_closes)
        if idx_n >= 22:
            idx_diff = np.diff(idx_closes[-21:])
            idx_base = idx_closes[-21:-1]
            idx_rets_20 = idx_diff[:len(idx_base)] / idx_base[:len(idx_diff)] * 100
        else:
            idx_rets_20 = None
        idx_ret_5d = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100 if idx_n >= 6 else 0
        idx_ret_3d = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100 if idx_n >= 4 else 0
        
        scored_v5 = []
        scored_v6 = []
        
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0:
                continue
            feats = calc_features(df, test_date)
            if feats is None:
                continue
            
            stock_hist = df[df['date'] < test_date]
            s_closes = stock_hist['close'].values
            s_n = len(s_closes)
            
            if idx_rets_20 is not None and s_n >= 23:
                s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
                sr_len = min(len(s_rets_20), len(idx_rets_20))
                if sr_len >= 10:
                    s_r = s_rets_20[-sr_len:]
                    i_r = idx_rets_20[-sr_len:]
                    idx_var = np.var(i_r)
                    if idx_var > 0.001:
                        cov = np.cov(s_r, i_r)[0, 1]
                        feats['beta_20d'] = cov / idx_var
            
            if s_n >= 6:
                s_ret_5d = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100
                feats['rel_strength_5d'] = s_ret_5d - idx_ret_5d
            if s_n >= 4:
                s_ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                feats['rel_strength_3d'] = s_ret_3d - idx_ret_3d
            
            static = scores.get(code, None)
            industry = static.get('industry', 'unknown') if static else 'unknown'
            name = static.get('name', '') if static else ''
            
            # V5 score
            s5, strat5 = score_stock_v5_balanced(feats, static, sector_avg, regime, momentum, vol_state)
            if s5 != -999:
                scored_v5.append({'code': code, 'name': name, 'score': s5, 'industry': industry, 'strategy': strat5})
            
            # V6 score (from backtest_v6)
            s6, strat6 = score_stock_v5(feats, static, sector_avg, regime, momentum, vol_state, 3)
            if s6 != -999:
                scored_v6.append({'code': code, 'name': name, 'score': s6, 'industry': industry, 'strategy': strat6})
        
        # No blacklist for fair comparison
        blacklist = set()
        
        sel_v5 = select_v5(scored_v5, blacklist, actual_n)
        sel_v6 = select_v6(scored_v6, blacklist, actual_n)
        
        # Calculate returns
        idx_ret = get_index_return(index_df, test_date)
        
        v5_rets = []
        v5_detail = []
        for s in sel_v5:
            r = get_stock_return(kline[s['code']], test_date)
            if r is not None:
                v5_rets.append(r)
                v5_detail.append((s['code'], s['name'], r, s['strategy']))
        
        v6_rets = []
        v6_detail = []
        for s in sel_v6:
            r = get_stock_return(kline[s['code']], test_date)
            if r is not None:
                v6_rets.append(r)
                v6_detail.append((s['code'], s['name'], r, s['strategy']))
        
        v5_avg = np.mean(v5_rets) if v5_rets else 0
        v6_avg = np.mean(v6_rets) if v6_rets else 0
        
        v5_beat = v5_avg > idx_ret if idx_ret is not None else False
        v6_beat = v6_avg > idx_ret if idx_ret is not None else False
        
        v5_results.append({'date': test_date, 'avg': v5_avg, 'idx': idx_ret, 'beat': v5_beat, 'detail': v5_detail})
        v6_results.append({'date': test_date, 'avg': v6_avg, 'idx': idx_ret, 'beat': v6_beat, 'detail': v6_detail})
        
        v5_tag = 'W' if v5_beat else 'L'
        v6_tag = 'W' if v6_beat else 'L'
        delta = v6_avg - v5_avg
        print(f"\n{test_date.strftime('%Y-%m-%d')} idx={idx_ret:+.2f}%")
        print(f"  V5 [{v5_tag}] avg={v5_avg:+.2f}%: {', '.join(f'{n} {r:+.1f}% [{st}]' for c,n,r,st in v5_detail)}")
        print(f"  V6 [{v6_tag}] avg={v6_avg:+.2f}%: {', '.join(f'{n} {r:+.1f}% [{st}]' for c,n,r,st in v6_detail)}")
        print(f"  Δ={delta:+.2f}% {'↑V6' if delta > 0 else '↓V6' if delta < 0 else '='}")
    
    # Summary
    v5_beat_n = sum(1 for r in v5_results if r['beat'])
    v6_beat_n = sum(1 for r in v6_results if r['beat'])
    total = len(v5_results)
    
    print(f"\n{'='*60}")
    print(f"SUMMARY - Risk 3 Only ({total} days)")
    print(f"{'='*60}")
    print(f"  V5 beat_idx: {v5_beat_n}/{total} = {v5_beat_n/total*100:.1f}%  avg_ret={np.mean([r['avg'] for r in v5_results]):+.2f}%")
    print(f"  V6 beat_idx: {v6_beat_n}/{total} = {v6_beat_n/total*100:.1f}%  avg_ret={np.mean([r['avg'] for r in v6_results]):+.2f}%")
    
    v6_better = sum(1 for v5, v6 in zip(v5_results, v6_results) if v6['avg'] > v5['avg'])
    print(f"  V6 > V5: {v6_better}/{total} days")
    
    elapsed = time.time() - t0
    print(f"  Time: {elapsed:.0f}s")


if __name__ == '__main__':
    main()

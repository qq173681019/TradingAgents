#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V29 回测验证脚本
================
用过去60个交易日验证V29策略，看beat_idx。
"""
import json, os, sys, time
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# Reuse V29 modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_recommender_v29 import (
    TECH_LEADER_POOL_RAW, STOCK_META, TECH_TRACKS,
    choice_login, choice_logout, fetch_klines_batch, fetch_index_data,
    fetch_stock_names, score_v29, detect_no_trade_signals,
    detect_market_regime, select_v29,
    classify_tech_track, RECOMMEND_COUNT
)

def _normalize_date(d):
    """Normalize date string to YYYY-MM-DD format"""
    d = str(d).strip()
    if '/' in d:
        parts = d.split('/')
        if len(parts) == 3:
            y, m, day = parts
            return f"{y}-{int(m):02d}-{int(day):02d}"
    return d


def run_backtest(days=60):
    """回测过去N天"""
    print("=" * 60)
    print(f"V29 回测验证 — 过去 {days} 个交易日")
    print("=" * 60)
    
    choice_login()
    
    # 1. 获取所有K线数据（多取60天用于计算）
    print("\n[1/3] 获取K线数据...")
    all_codes = [item[0] for item in TECH_LEADER_POOL_RAW]
    klines = fetch_klines_batch(all_codes, days=days + 150)
    print(f"  获取 {len(klines)} 只股票")
    
    # 2. 获取指数
    print("\n[2/3] 获取指数数据...")
    index_records = fetch_index_data(days=days + 200)
    print(f"  指数: {len(index_records)} 天")
    
    # 3. 获取名称
    print("\n[3/3] 获取名称...")
    names = fetch_stock_names(all_codes)
    
    # 回测
    print(f"\n开始回测 (过去{days}个交易日)...")
    
    # 找到所有交易日期（从指数数据中取）
    all_dates = [r['date'] for r in index_records]
    # 回测起始日期
    test_start_idx = max(0, len(all_dates) - days)
    test_dates = all_dates[test_start_idx:]
    
    print(f"  回测区间: {test_dates[0]} ~ {test_dates[-1]}, 共 {len(test_dates)} 天")
    
    results = []
    wins = 0
    losses = 0
    no_trades = 0
    
    for i, test_date in enumerate(test_dates):
        # 截取到test_date之前的数据
        idx_up_to = [r for r in index_records if r['date'] <= test_date]
        klines_up_to = {}
        for code, records in klines.items():
            filtered = [r for r in records if r['date'] <= test_date]
            if len(filtered) >= 30:
                klines_up_to[code] = filtered
        
        if len(idx_up_to) < 30:
            continue
        
        # 不交易信号检测
        skip, signals = detect_no_trade_signals(idx_up_to)
        if skip:
            no_trades += 1
            results.append({
                'date': test_date, 'action': 'NO_TRADE',
                'signals': [s[0] for s in signals],
            })
            continue
        
        # 评分 (suppress output)
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            scored, regime, mkt_risk, confidence = score_v29(
                klines_up_to, names, {}, idx_up_to, debug=False)
        
        # 选股 (回测不用冷却期)
        selected = []
        tech_count = 0
        non_tech_count = 0
        for s in scored:
            if len(selected) >= RECOMMEND_COUNT:
                break
            track = s['track']
            is_tech = track not in ("非科技", "其他")
            if not is_tech and non_tech_count >= 1:
                continue
            if s['scores']['trend'] < 30:
                continue
            selected.append(s)
            if is_tech:
                tech_count += 1
            else:
                non_tech_count += 1
        
        if not selected:
            no_trades += 1
            results.append({'date': test_date, 'action': 'NO_MATCH'})
            continue
        
        # 找到test_date的下一天
        test_idx_pos = None
        for j, d in enumerate(all_dates):
            if d == test_date or _normalize_date(d) == _normalize_date(test_date):
                test_idx_pos = j
                break
        
        if test_idx_pos is None or test_idx_pos + 1 >= len(all_dates):
            continue
        
        next_date = all_dates[test_idx_pos + 1]
        
        # 计算推荐股票的次日收益
        stock_returns = []
        for s in selected:
            code = None
            for full_code in klines:
                clean = full_code.replace('.SZ', '').replace('.SH', '')
                if clean == s['code']:
                    code = full_code
                    break
            if not code:
                continue
            
            records = klines[code]
            # 找到test_date和next_date的数据
            test_idx = None
            next_idx = None
            for j, r in enumerate(records):
                rd = _normalize_date(r['date'])
                td = _normalize_date(test_date)
                nd = _normalize_date(next_date)
                if rd == td:
                    test_idx = j
                if rd == nd:
                    next_idx = j
                    break
            
            if test_idx is None or next_idx is None:
                continue
            
            ret = (records[next_idx]['close'] - records[test_idx]['close']) / records[test_idx]['close'] * 100
            stock_returns.append({
                'code': s['code'], 'name': s['name'],
                'track': s['track'], 'ret': ret,
            })
        
        if not stock_returns:
            continue
        
        avg_ret = np.mean([r['ret'] for r in stock_returns])
        
        # 计算指数收益
        idx_test = None
        idx_next = None
        for r in index_records:
            rd = _normalize_date(r['date'])
            if rd == _normalize_date(test_date):
                idx_test = r['close']
            if rd == _normalize_date(next_date):
                idx_next = r['close']
        
        if idx_test is None or idx_next is None:
            continue
        
        idx_ret = (idx_next - idx_test) / idx_test * 100
        
        # 判断胜负
        beat = avg_ret > idx_ret
        if beat:
            wins += 1
        else:
            losses += 1
        
        results.append({
            'date': test_date,
            'action': 'TRADE',
            'avg_ret': round(avg_ret, 2),
            'idx_ret': round(idx_ret, 2),
            'beat': beat,
            'stocks': stock_returns,
            'market': regime,
            'risk': mkt_risk,
        })
        
        status = '✅' if beat else '❌'
        stock_str = ', '.join(f"{r['name'][:4]}({r['ret']:+.1f}%)" for r in stock_returns)
        print(f"  {test_date} {status} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% | {stock_str}")
    
    choice_logout()
    
    # 统计
    trade_days = wins + losses
    beat_rate = wins / max(trade_days, 1) * 100
    
    print(f"\n{'=' * 60}")
    print(f"V29 回测结果")
    print(f"{'=' * 60}")
    print(f"  总交易日: {len(test_dates)}")
    print(f"  交易天数: {trade_days}")
    print(f"  不交易天: {no_trades}")
    print(f"  胜: {wins}, 负: {losses}")
    print(f"  Beat率: {beat_rate:.1f}%")
    
    # 保存结果
    result = {
        'version': 'V29',
        'test_days': len(test_dates),
        'trade_days': trade_days,
        'no_trade_days': no_trades,
        'wins': wins,
        'losses': losses,
        'beat_rate': round(beat_rate, 1),
        'test_details': results,
    }
    
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'backtest_results', 'backtest_v29.json')
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    # Convert numpy types
    def convert(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj
    result = convert(result)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存: {out_file}")
    
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=60)
    args = parser.parse_args()
    run_backtest(days=args.days)

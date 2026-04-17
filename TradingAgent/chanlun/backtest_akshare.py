"""
缠论大规模回测 - AKShare版
解决Tushare日限问题，用AKShare拉取日线数据做滑动窗口回测
"""

import sys
sys.path.insert(0, r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent')

import os, sys
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(k, None)

# 强制关闭 requests 代理
import requests
requests.Session.trust_env = False

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from chanlun.chanlun_core import analyze_chanlun
from chanlun.aggressive_scanner import score_stock
import json
import time
import traceback

OUTPUT_DIR = r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent\data\backtest_chanlun'
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_stock_pool(max_count=300):
    """用AKShare获取活跃A股列表，排除ST/北交所/停牌"""
    print("[1] 获取股票池...")
    df = ak.stock_zh_a_spot_em()
    
    # 过滤
    df = df[~df['名称'].str.contains('ST|退', na=False)]
    df = df[~df['代码'].str.startswith(('8', '4'), na=False)]  # 排除北交所
    df = df[df['成交量'] > 0]  # 排除停牌
    df = df[df['最新价'] >= 3]
    df = df[df['最新价'] <= 50]
    df = df[df['总市值'] <= 200e8]  # 200亿以下
    df = df[df['换手率'] >= 1.0]
    
    # 按成交额排序，取最活跃的
    df = df.sort_values('成交额', ascending=False).head(max_count)
    
    codes = df['代码'].tolist()
    print(f"  获取到 {len(codes)} 只股票")
    return codes


def fetch_daily_akshare(symbol: str, days: int = 120) -> pd.DataFrame:
    """用AKShare获取日线数据"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period='daily',
            start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            adjust='qfq'
        )
        if df is None or len(df) < 40:
            return None
        
        # 标准化
        col_map = {'日期': 'datetime', '开盘': 'open', '最高': 'high', 
                   '最低': 'low', '收盘': 'close', '成交量': 'volume'}
        df = df.rename(columns=col_map)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        return None


def run_backtest(max_stocks=300, delays=0.25):
    """大规模滑动窗口回测"""
    print("=" * 60)
    print("缠论大规模回测 (AKShare)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    codes = get_stock_pool(max_stocks)
    
    all_trades = []
    errors = 0
    
    for i, code in enumerate(codes):
        df_full = fetch_daily_akshare(code, days=150)
        if df_full is None or len(df_full) < 50:
            continue
        
        # 多个截断点，每个点模拟"当时分析、未来N天验证"
        for offset in [3, 5, 8]:
            if len(df_full) < offset + 40:
                continue
            
            df_slice = df_full.iloc[:-offset].copy()
            if len(df_slice) < 40:
                continue
            
            # 未来收益
            idx_future = len(df_slice) - 1 + offset
            if idx_future >= len(df_full):
                continue
            
            current_price = float(df_slice.iloc[-1]['close'])
            future_price = float(df_full.iloc[idx_future]['close'])
            actual_return = (future_price - current_price) / current_price * 100
            
            try:
                result = analyze_chanlun(df_slice)
                
                stock_info = {
                    'code': code,
                    'name': '',
                    'market_cap': 30e8,  # 近似值
                    'turnover_rate': 3.0,
                }
                
                score_result = score_stock(result, df_slice, stock_info)
                
                all_trades.append({
                    'symbol': code,
                    'offset_days': offset,
                    'score': score_result['score'],
                    'signal': score_result['signal'],
                    'trend': result['trend'],
                    'buy_point': result['last_buy_signal']['type'] if result.get('last_buy_signal') else None,
                    'zhongshu_count': len(result['zhongshu']),
                    'bi_count': len(result['bi']),
                    'actual_return': round(actual_return, 2),
                    'vol_ratio': score_result['details'].get('vol_ratio'),
                })
            except Exception:
                errors += 1
                continue
        
        # 进度
        if (i + 1) % 20 == 0:
            trades_so_far = len(all_trades)
            print(f"  进度: {i+1}/{len(codes)} | 样本: {trades_so_far} | 错误: {errors}")
        
        time.sleep(delays)
    
    print(f"\n完成! 共 {len(all_trades)} 个样本, {errors} 个错误")
    
    if not all_trades:
        print("无数据")
        return
    
    df_t = pd.DataFrame(all_trades)
    
    # === 统计报告 ===
    print("\n" + "=" * 60)
    print("📊 回测统计报告")
    print("=" * 60)
    
    # 1. 按评分阈值
    print("\n--- 按评分阈值 ---")
    print(f"  {'阈值':>8s} | {'笔数':>4s} | {'胜率':>6s} | {'均收':>7s} | {'大涨>5%':>7s} | {'大跌<-3%':>8s}")
    print("  " + "-" * 55)
    for t in [0, 20, 30, 40, 50, 60, 70]:
        s = df_t[df_t['score'] >= t]
        if len(s) < 5:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        risk = (s['actual_return'] < -3).mean() * 100
        print(f"  score>={t:2d} | {len(s):4d} | {wr:5.1f}% | {ar:+6.2f}% | {big:5.1f}% | {risk:6.1f}%")
    
    # 2. 按买点类型
    print("\n--- 按买点类型 ---")
    for bp in ['buy1', 'buy2', 'buy3']:
        label = {'buy1': '一买', 'buy2': '二买', 'buy3': '三买'}[bp]
        s = df_t[df_t['buy_point'] == bp]
        if len(s) < 3:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        print(f"  {label}: {len(s):4d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}% | 大涨{big:4.1f}%")
    
    no_buy = df_t[df_t['buy_point'].isna()]
    if len(no_buy) >= 3:
        wr = (no_buy['actual_return'] > 0).mean() * 100
        ar = no_buy['actual_return'].mean()
        print(f"  无买点: {len(no_buy):4d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}%")
    
    # 3. 按趋势
    print("\n--- 按趋势 ---")
    for trend in ['up', 'down', 'consolidation']:
        s = df_t[df_t['trend'] == trend]
        if len(s) < 3:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        print(f"  {trend:12s}: {len(s):4d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}%")
    
    # 4. 最佳组合
    print("\n--- 🏆 最佳组合 ---")
    combos = [
        ("score>=30", df_t['score'] >= 30),
        ("score>=40", df_t['score'] >= 40),
        ("score>=50", df_t['score'] >= 50),
        ("score>=30 + up", (df_t['score'] >= 30) & (df_t['trend'] == 'up')),
        ("score>=40 + up", (df_t['score'] >= 40) & (df_t['trend'] == 'up')),
        ("score>=30 + buy点", (df_t['score'] >= 30) & (df_t['buy_point'].notna())),
        ("score>=40 + buy点", (df_t['score'] >= 40) & (df_t['buy_point'].notna())),
        ("up + buy点", (df_t['trend'] == 'up') & (df_t['buy_point'].notna())),
        ("buy1 or buy2 + up", (df_t['buy_point'].isin(['buy1', 'buy2'])) & (df_t['trend'] == 'up')),
        ("buy3", df_t['buy_point'] == 'buy3'),
        ("score>=30 + vol>=2x", (df_t['score'] >= 30) & (df_t['vol_ratio'] >= 2.0)),
        ("score>=40 + vol>=2x", (df_t['score'] >= 40) & (df_t['vol_ratio'] >= 2.0)),
        ("score>=50 + vol>=1.5x", (df_t['score'] >= 50) & (df_t['vol_ratio'] >= 1.5)),
    ]
    
    print(f"  {'组合':35s} | {'笔数':>4s} | {'胜率':>6s} | {'均收':>7s} | {'大涨':>5s}")
    print("  " + "-" * 70)
    for name, mask in combos:
        s = df_t[mask]
        if len(s) < 5:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        print(f"  {name:35s} | {len(s):4d} | {wr:5.1f}% | {ar:+6.2f}% | {big:4.1f}%")
    
    # 5. 按预测天数
    print("\n--- 按预测天数 ---")
    for offset in [3, 5, 8]:
        s = df_t[df_t['offset_days'] == offset]
        if len(s) < 3:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        buy_s = s[s['buy_point'].notna()]
        if len(buy_s) >= 3:
            wr_b = (buy_s['actual_return'] > 0).mean() * 100
            ar_b = buy_s['actual_return'].mean()
            print(f"  {offset}日后: 全部{len(s):4d}笔胜率{wr:5.1f}%均收{ar:+.2f}% | 有买点{len(buy_s):4d}笔胜率{wr_b:5.1f}%均收{ar_b:+.2f}%")
        else:
            print(f"  {offset}日后: 全部{len(s):4d}笔胜率{wr:5.1f}%均收{ar:+.2f}%")
    
    # 保存
    out_file = os.path.join(OUTPUT_DIR, f'akshare_backtest_{datetime.now().strftime("%Y%m%d_%H%M")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    print(f"\n💾 保存: {out_file}")
    
    # 汇总
    print(f"\n{'='*60}")
    print(f"总样本: {len(all_trades)} | 股票: {len(codes)} | 错误: {errors}")
    print(f"{'='*60}")


if __name__ == '__main__':
    run_backtest(max_stocks=300, delays=0.25)

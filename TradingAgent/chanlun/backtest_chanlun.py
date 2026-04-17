"""
缠论滑动窗口回测 - Tushare版
用Tushare日线数据，不依赖东方财富API
"""

import sys
sys.path.insert(0, r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent')

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime
from chanlun.chanlun_core import analyze_chanlun
from chanlun.aggressive_scanner import score_stock
import time
import json
import os

TUSHARE_TOKEN = '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28'
OUTPUT_DIR = r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent\data\backtest_chanlun'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 50只测试股
TEST_STOCKS = [
    '000001.SZ', '000002.SZ', '000063.SZ', '000157.SZ', '000333.SZ',
    '000338.SZ', '000425.SZ', '000538.SZ', '000568.SZ', '000596.SZ',
    '000625.SZ', '000651.SZ', '000661.SZ', '000708.SZ', '000725.SZ',
    '000768.SZ', '000776.SZ', '000783.SZ', '000858.SZ', '000876.SZ',
    '000895.SZ', '000938.SZ', '000963.SZ', '000977.SZ',
    '002007.SZ', '002024.SZ', '002049.SZ', '002230.SZ', '002241.SZ',
    '002371.SZ', '002415.SZ', '002456.SZ',
    '300003.SZ', '300014.SZ', '300015.SZ', '300017.SZ', '300018.SZ',
    '300024.SZ', '300027.SZ', '300052.SZ',
    '600000.SH', '600009.SH', '600016.SH', '600019.SH', '600028.SH',
    '600030.SH', '600036.SH', '600048.SH', '600050.SH', '600104.SH',
]


def fetch_daily(ts_code: str) -> pd.DataFrame:
    try:
        pro = ts.pro_api(TUSHARE_TOKEN)
        df = pro.daily(ts_code=ts_code, start_date='20250901', end_date='20260411')
        if df is None or len(df) < 30:
            return None
        # Tushare日期倒序，需要正序
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df.rename(columns={
            'trade_date': 'datetime', 'vol': 'volume'
        })
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        print(f"  [ERR] {ts_code}: {e}")
        return None


def run_sliding_backtest():
    print("=" * 60)
    print("缠论滑动窗口回测 (Tushare)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    all_trades = []

    for i, ts_code in enumerate(TEST_STOCKS):
        df_full = fetch_daily(ts_code)
        if df_full is None:
            continue

        code = ts_code[:6]

        # 在多个截断点分析
        for offset in [3, 5, 10, 15, 20]:
            if len(df_full) < offset + 40:
                continue

            df_slice = df_full.iloc[:-offset].copy()
            if len(df_slice) < 30:
                continue

            # 未来offset天收益
            current_price = float(df_slice.iloc[-1]['close'])
            future_price = float(df_full.iloc[-1 + (len(df_full) - len(df_slice) - offset + offset - 1)]['close'])
            # 简化: 直接用 offset天后 的收盘价
            idx_future = len(df_slice) - 1 + offset
            if idx_future >= len(df_full):
                continue
            future_price = float(df_full.iloc[idx_future]['close'])
            actual_return = (future_price - current_price) / current_price * 100

            try:
                result = analyze_chanlun(df_slice)

                stock_info = {
                    'code': code,
                    'name': '',
                    'market_cap': 30e8,
                    'turnover_rate': 5.0,
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
                    'actual_return': round(actual_return, 2),
                    'vol_ratio': score_result['details'].get('vol_ratio'),
                })
            except Exception:
                continue

        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(TEST_STOCKS)}")
        time.sleep(0.15)

    print(f"\n共产生 {len(all_trades)} 个回测样本")

    if not all_trades:
        print("无数据")
        return

    df_t = pd.DataFrame(all_trades)

    # === 统计 ===
    print("\n" + "=" * 60)
    print("回测统计")
    print("=" * 60)

    # 1. 按评分阈值
    print("\n--- 按评分阈值 ---")
    for t in [0, 15, 20, 30, 40, 50, 60]:
        s = df_t[df_t['score'] >= t]
        if len(s) == 0:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        print(f"  score>={t:2d}: {len(s):3d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}% | 大涨率{big:4.1f}%")

    # 2. 按买点
    print("\n--- 按买点类型 ---")
    for bp in ['buy1', 'buy2', 'buy3', None]:
        label = {'buy1': '一买', 'buy2': '二买', 'buy3': '三买', None: '无买点'}[bp]
        s = df_t[df_t['buy_point'] == bp] if bp else df_t[df_t['buy_point'].isna()]
        if len(s) == 0:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        print(f"  {label}: {len(s):3d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}%")

    # 3. 按趋势
    print("\n--- 按趋势 ---")
    for trend in ['up', 'down', 'consolidation']:
        s = df_t[df_t['trend'] == trend]
        if len(s) == 0:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        print(f"  {trend:12s}: {len(s):3d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}%")

    # 4. 最优组合
    print("\n--- 最佳组合 ---")
    combos = [
        ("score>=30 + up", (df_t['score'] >= 30) & (df_t['trend'] == 'up')),
        ("score>=30 + buy_point", (df_t['score'] >= 30) & (df_t['buy_point'].notna())),
        ("score>=20 + up + buy", (df_t['score'] >= 20) & (df_t['trend'] == 'up') & (df_t['buy_point'].notna())),
        ("buy_point only", df_t['buy_point'].notna()),
        ("buy1 or buy2", df_t['buy_point'].isin(['buy1', 'buy2'])),
        ("score>=40", df_t['score'] >= 40),
    ]
    for name, mask in combos:
        s = df_t[mask]
        if len(s) == 0:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        print(f"  {name:30s}: {len(s):3d}笔 | 胜率{wr:5.1f}% | 均收{ar:+6.2f}% | 大涨{big:4.1f}%")

    # 5. 按 offset_days 分组看信号质量
    print("\n--- 按预测天数 ---")
    for offset in [3, 5, 10, 15, 20]:
        s = df_t[(df_t['offset_days'] == offset) & (df_t['buy_point'].notna())]
        if len(s) == 0:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        print(f"  {offset}日后: {len(s):3d}笔(有买点) | 胜率{wr:5.1f}% | 均收{ar:+6.2f}%")

    # 保存
    out_file = os.path.join(OUTPUT_DIR, f'tushare_backtest_{datetime.now().strftime("%Y%m%d_%H%M")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    print(f"\n保存: {out_file}")


if __name__ == '__main__':
    run_sliding_backtest()

"""
缠论大规模回测 - Tushare扩大版
今天Tushare额度重置，目标跑200+只股票
"""

import sys
sys.path.insert(0, r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent')

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime
from chanlun.chanlun_core import analyze_chanlun
from chanlun.aggressive_scanner import score_stock
import json, os, time, io, sys

# fix windows gbk encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TUSHARE_TOKEN = '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28'
OUTPUT_DIR = r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent\data\backtest_chanlun'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 扩大到200只: 沪深各100，覆盖各行业
TEST_STOCKS = [
    # 深市主板
    '000001.SZ','000002.SZ','000063.SZ','000069.SZ','000100.SZ',
    '000157.SZ','000333.SZ','000338.SZ','000425.SZ','000538.SZ',
    '000568.SZ','000596.SZ','000625.SZ','000651.SZ','000661.SZ',
    '000708.SZ','000725.SZ','000768.SZ','000776.SZ','000783.SZ',
    '000858.SZ','000876.SZ','000895.SZ','000938.SZ','000963.SZ',
    '000977.SZ','000988.SZ','000002.SZ','000009.SZ','000012.SZ',
    '000021.SZ','000027.SZ','000028.SZ','000031.SZ','000039.SZ',
    '000046.SZ','000050.SZ','000055.SZ','000059.SZ','000060.SZ',
    '000066.SZ','000070.SZ','000078.SZ','000088.SZ','000089.SZ',
    '000090.SZ','000099.SZ','000155.SZ','000156.SZ','000159.SZ',
    # 深市中小创
    '002007.SZ','002024.SZ','002049.SZ','002120.SZ','002142.SZ',
    '002179.SZ','002230.SZ','002241.SZ','002304.SZ','002352.SZ',
    '002371.SZ','002415.SZ','002456.SZ','002460.SZ','002475.SZ',
    '002493.SZ','002555.SZ','002594.SZ','002601.SZ','002602.SZ',
    '002709.SZ','002714.SZ','002812.SZ','002841.SZ','002916.SZ',
    # 创业板
    '300003.SZ','300014.SZ','300015.SZ','300017.SZ','300018.SZ',
    '300024.SZ','300027.SZ','300033.SZ','300034.SZ','300036.SZ',
    '300052.SZ','300059.SZ','300070.SZ','300073.SZ','300078.SZ',
    '300122.SZ','300124.SZ','300136.SZ','300142.SZ','300146.SZ',
    '300207.SZ','300223.SZ','300251.SZ','300257.SZ','300285.SZ',
    '300308.SZ','300315.SZ','300347.SZ','300394.SZ','300408.SZ',
    '300413.SZ','300418.SZ','300433.SZ','300450.SZ','300454.SZ',
    '300458.SZ','300496.SZ','300498.SZ','300502.SZ','300618.SZ',
    '300628.SZ','300630.SZ','300661.SZ','300750.SZ','300760.SZ',
    '300782.SZ','300832.SZ','300861.SZ','300888.SZ','300896.SZ',
    # 沪市主板
    '600000.SH','600009.SH','600016.SH','600019.SH','600028.SH',
    '600030.SH','600036.SH','600048.SH','600050.SH','600104.SH',
    '600109.SH','600111.SH','600115.SH','600118.SH','600150.SH',
    '600153.SH','600160.SH','600161.SH','600166.SH','600168.SH',
    '600170.SH','600176.SH','600177.SH','600183.SH','600188.SH',
    '600196.SH','600199.SH','600201.SH','600208.SH','600219.SH',
    '600221.SH','600233.SH','600271.SH','600276.SH','600298.SH',
    '600309.SH','600325.SH','600328.SH','600332.SH','600340.SH',
    '600348.SH','600352.SH','600362.SH','600369.SH','600372.SH',
    '600383.SH','600390.SH','600398.SH','600406.SH','600415.SH',
    '600426.SH','600433.SH','600436.SH','600438.SH','600446.SH',
    '600460.SH','600486.SH','600489.SH','600493.SH','600498.SH',
    '600503.SH','600507.SH','600511.SH','600516.SH','600517.SH',
    '600519.SH','600521.SH','600522.SH','600523.SH','600547.SH',
    '600549.SH','600570.SH','600571.SH','600580.SH','600584.SH',
    '600585.SH','600586.SH','600588.SH','600589.SH','600590.SH',
    '600595.SH','600597.SH','600598.SH','600600.SH','600601.SH',
    '600690.SH','600702.SH','600703.SH','600705.SH','600710.SH',
    '600711.SH','600713.SH','600714.SH','600715.SH','600716.SH',
    '600720.SH','600725.SH','600726.SH','600727.SH','600728.SH',
    '600729.SH','600733.SH','600734.SH','600737.SH','600739.SH',
    '600741.SH','600745.SH','600748.SH','600749.SH','600750.SH',
    '600763.SH','600764.SH','600765.SH','600770.SH','600773.SH',
    '600775.SH','600776.SH','600779.SH','600782.SH','600785.SH',
    '600786.SH','600787.SH','600789.SH','600790.SH','600791.SH',
]


def fetch_daily(ts_code: str) -> pd.DataFrame:
    try:
        pro = ts.pro_api(TUSHARE_TOKEN)
        df = pro.daily(ts_code=ts_code, start_date='20250901', end_date='20260411')
        if df is None or len(df) < 30:
            return None
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df.rename(columns={'trade_date': 'datetime', 'vol': 'volume'})
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        print(f"  [ERR] {ts_code}: {e}")
        return None


def run_backtest():
    print("=" * 60)
    print("缠论大规模回测 (Tushare 扩大版)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"股票数: {len(TEST_STOCKS)}")
    print("=" * 60)

    all_trades = []
    errors = 0
    success = 0

    for i, ts_code in enumerate(TEST_STOCKS):
        df_full = fetch_daily(ts_code)
        if df_full is None:
            continue

        code = ts_code[:6]
        success += 1

        # 多个截断点
        for offset in [3, 5, 8]:
            if len(df_full) < offset + 40:
                continue

            df_slice = df_full.iloc[:-offset].copy()
            if len(df_slice) < 40:
                continue

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
                    'bi_count': len(result['bi']),
                    'actual_return': round(actual_return, 2),
                    'vol_ratio': score_result['details'].get('vol_ratio'),
                })
            except Exception:
                errors += 1
                continue

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(TEST_STOCKS)} | 样本: {len(all_trades)} | 错误: {errors}")

        time.sleep(0.2)  # 避免触发限频

    print(f"\n完成! 成功: {success} | 样本: {len(all_trades)} | 错误: {errors}")

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
    for t in [0, 20, 30, 40, 50, 60, 70, 80]:
        s = df_t[df_t['score'] >= t]
        if len(s) < 5:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        risk = (s['actual_return'] < -3).mean() * 100
        print(f"  score>={t:2d} | {len(s):4d} | {wr:5.1f}% | {ar:+6.2f}% | {big:5.1f}% | {risk:6.1f}%")

    # 2. 按买点
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
        ("score>=60", df_t['score'] >= 60),
        ("score>=30 + up", (df_t['score'] >= 30) & (df_t['trend'] == 'up')),
        ("score>=40 + up", (df_t['score'] >= 40) & (df_t['trend'] == 'up')),
        ("score>=50 + up", (df_t['score'] >= 50) & (df_t['trend'] == 'up')),
        ("score>=30 + buy点", (df_t['score'] >= 30) & (df_t['buy_point'].notna())),
        ("score>=40 + buy点", (df_t['score'] >= 40) & (df_t['buy_point'].notna())),
        ("score>=50 + buy点", (df_t['score'] >= 50) & (df_t['buy_point'].notna())),
        ("up + buy点", (df_t['trend'] == 'up') & (df_t['buy_point'].notna())),
        ("buy1", df_t['buy_point'] == 'buy1'),
        ("buy2", df_t['buy_point'] == 'buy2'),
        ("buy3", df_t['buy_point'] == 'buy3'),
        ("buy1 + up", (df_t['buy_point'] == 'buy1') & (df_t['trend'] == 'up')),
        ("buy2 + up", (df_t['buy_point'] == 'buy2') & (df_t['trend'] == 'up')),
        ("buy3 + up", (df_t['buy_point'] == 'buy3') & (df_t['trend'] == 'up')),
        ("score>=30 + vol>=2x", (df_t['score'] >= 30) & (df_t['vol_ratio'] >= 2.0)),
        ("score>=40 + vol>=2x", (df_t['score'] >= 40) & (df_t['vol_ratio'] >= 2.0)),
        ("score>=40 + up + buy", (df_t['score'] >= 40) & (df_t['trend'] == 'up') & (df_t['buy_point'].notna())),
        ("score>=30 + up + vol>=1.5x", (df_t['score'] >= 30) & (df_t['trend'] == 'up') & (df_t['vol_ratio'] >= 1.5)),
    ]

    print(f"  {'组合':35s} | {'笔数':>4s} | {'胜率':>6s} | {'均收':>7s} | {'大涨':>5s} | {'大跌':>5s}")
    print("  " + "-" * 75)
    for name, mask in combos:
        s = df_t[mask]
        if len(s) < 5:
            continue
        wr = (s['actual_return'] > 0).mean() * 100
        ar = s['actual_return'].mean()
        big = (s['actual_return'] > 5).mean() * 100
        risk = (s['actual_return'] < -3).mean() * 100
        print(f"  {name:35s} | {len(s):4d} | {wr:5.1f}% | {ar:+6.2f}% | {big:4.1f}% | {risk:4.1f}%")

    # 5. 按预测天数
    print("\n--- 按预测天数 ---")
    for offset in [3, 5, 8]:
        s = df_t[df_t['offset_days'] == offset]
        buy_s = s[s['buy_point'].notna()]
        if len(buy_s) >= 3:
            wr = (buy_s['actual_return'] > 0).mean() * 100
            ar = buy_s['actual_return'].mean()
            print(f"  {offset}日后(有买点): {len(buy_s):4d}笔 | 胜率{wr:5.1f}% | 均收{ar:+.2f}%")

    # 保存
    out_file = os.path.join(OUTPUT_DIR, f'tushare_backtest_large_{datetime.now().strftime("%Y%m%d_%H%M")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    print(f"\n💾 保存: {out_file}")

    print(f"\n{'='*60}")
    print(f"总样本: {len(all_trades)} | 股票: {success}/{len(TEST_STOCKS)} | 错误: {errors}")
    print(f"{'='*60}")


if __name__ == '__main__':
    run_backtest()

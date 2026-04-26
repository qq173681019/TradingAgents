#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据扩充脚本 v2 - Tushare按日批量拉取
=====================================
策略: daily(trade_date=) 每次获取全市场~5500只股票
~120交易日 * 0.3s/次 = ~40秒完成

输出: kline_latest.json + index_latest.json
"""
import os, json, time
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime

KLINE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'TradingShared', 'data', 'kline_cache')
TUSHARE_TOKEN = '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28'
START_DATE = '20241001'
END_DATE = datetime.now().strftime('%Y%m%d')

print(f"=" * 60)
print(f"Tushare Batch Fetcher v2")
print(f"Date: {START_DATE} ~ {END_DATE}")
print(f"=" * 60)

import tushare as ts
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# === 1. Get trade calendar ===
print("\n[1/4] 获取交易日历...")
cal = pro.trade_cal(exchange='SSE', start_date=START_DATE, end_date=END_DATE,
                    fields='cal_date,is_open')
trade_dates = sorted(cal[cal['is_open'] == 1]['cal_date'].tolist())
print(f"  交易日: {len(trade_dates)} ({trade_dates[0]} ~ {trade_dates[-1]})")

# === 2. Fetch daily data by date ===
print(f"\n[2/4] 批量拉取日线数据 ({len(trade_dates)} 天)...")
all_stock_data = defaultdict(list)  # full_code -> [records]
ts_to_full = {}  # ts_code -> full_code mapping
total_records = 0
failed = 0

for i, td in enumerate(trade_dates):
    try:
        df = pro.daily(trade_date=td)
        if df is None or len(df) == 0:
            failed += 1
            continue

        date_str = f'{td[:4]}-{td[4:6]}-{td[6:8]}'

        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.split('.')[0]
            prefix = 'sh' if ts_code.endswith('.SH') else 'sz'
            full_code = f'{prefix}.{code}'

            ts_to_full[ts_code] = full_code

            close = row['close']
            vol = row['vol']
            if pd.isna(close) or close <= 0 or pd.isna(vol) or vol <= 0:
                continue

            all_stock_data[full_code].append({
                'date': date_str,
                'open': float(row['open']) if not pd.isna(row['open']) else float(close),
                'high': float(row['high']) if not pd.isna(row['high']) else float(close),
                'low': float(row['low']) if not pd.isna(row['low']) else float(close),
                'close': float(close),
                'volume': float(vol),
                'amount': float(row['amount']) * 1000 if not pd.isna(row['amount']) else 0,
                'pctChg': float(row['pct_chg']) if not pd.isna(row['pct_chg']) else 0,
            })
            total_records += 1

        if (i + 1) % 20 == 0 or i == len(trade_dates) - 1:
            pct = (i + 1) / len(trade_dates) * 100
            print(f"  {i+1}/{len(trade_dates)} ({pct:.0f}%) | "
                  f"股票: {len(all_stock_data)} | 记录: {total_records:,}")

    except Exception as e:
        failed += 1
        if 'limit' in str(e).lower() or '频繁' in str(e):
            print(f"  频率限制 at {td}, 等待10s...")
            time.sleep(10)
            try:
                df = pro.daily(trade_date=td)
                if df is not None:
                    date_str = f'{td[:4]}-{td[4:6]}-{td[6:8]}'
                    for _, row in df.iterrows():
                        ts_code = row['ts_code']
                        code = ts_code.split('.')[0]
                        prefix = 'sh' if ts_code.endswith('.SH') else 'sz'
                        full_code = f'{prefix}.{code}'
                        close = row['close']
                        if pd.isna(close) or close <= 0: continue
                        all_stock_data[full_code].append({
                            'date': date_str,
                            'open': float(row['open']) if not pd.isna(row['open']) else float(close),
                            'high': float(row['high']) if not pd.isna(row['high']) else float(close),
                            'low': float(row['low']) if not pd.isna(row['low']) else float(close),
                            'close': float(close),
                            'volume': float(row['vol']) if not pd.isna(row['vol']) else 0,
                            'amount': float(row['amount'])*1000 if not pd.isna(row['amount']) else 0,
                            'pctChg': float(row['pct_chg']) if not pd.isna(row['pct_chg']) else 0,
                        })
            except:
                pass
        time.sleep(0.3)

print(f"\n  完成: {len(all_stock_data)} 只股票, {total_records:,} 条记录, {failed} 天失败")

# === 3. Filter and sort records ===
print(f"\n[3/4] 数据清洗...")
# Filter: exclude stocks with too few records (new listings, suspended)
# Keep stocks with >= 60 trading days (enough for features)
filtered = {}
for code, records in all_stock_data.items():
    if len(records) >= 60:
        # Sort by date
        records.sort(key=lambda x: x['date'])
        filtered[code] = records

# Also exclude ST stocks (check if name contains ST)
# We don't have names here, but we can check for extreme price moves
# which are characteristic of ST stocks
final = {}
for code, records in filtered.items():
    # Check for extreme volatility (characteristic of problematic stocks)
    pct_sum = sum(abs(r['pctChg']) for r in records[-60:])
    avg_daily_move = pct_sum / min(60, len(records))
    # Keep stocks with reasonable volatility
    if avg_daily_move < 15:  # Not too crazy
        final[code] = records

all_stock_data = final
print(f"  清洗后: {len(all_stock_data)} 只 (排除数据不足和异常波动)")

# === 4. Get index data ===
print(f"\n[4/4] 获取指数数据...")
# Try Tushare index_daily first
index_data = None
try:
    idx_df = pro.index_daily(ts_code='000001.SH', start_date=START_DATE, end_date=END_DATE)
    if idx_df is not None and len(idx_df) > 0:
        idx_df = idx_df.sort_values('trade_date')
        index_data = {'date': {}, 'close': {}}
        for i, (_, row) in enumerate(idx_df.iterrows()):
            td = row['trade_date']
            index_data['date'][str(i)] = f'{td[:4]}-{td[4:6]}-{td[6:8]}'
            index_data['close'][str(i)] = float(row['close'])
        print(f"  上证指数(Tushare): {len(idx_df)} 天")
except Exception as e:
    print(f"  Tushare指数失败: {e}")

# Fallback: try to build from existing index file
if index_data is None:
    existing_idx = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    if os.path.exists(existing_idx):
        print(f"  使用现有指数文件: {existing_idx}")
        with open(existing_idx, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        print(f"  指数数据: {len(index_data['date'])} 天 (截止4/7)")

# === 5. Save ===
print(f"\n保存数据...")
end_str = datetime.now().strftime('%Y-%m-%d')

# K-line
kline_file = os.path.join(KLINE_CACHE, f'kline_full_{START_DATE}_{end_str}.json')
with open(kline_file, 'w', encoding='utf-8') as f:
    json.dump(all_stock_data, f, ensure_ascii=False)
size_mb = os.path.getsize(kline_file) / 1024 / 1024
print(f"  K-line: {os.path.basename(kline_file)} ({size_mb:.1f} MB)")

# Latest symlink
latest_kline = os.path.join(KLINE_CACHE, 'kline_latest.json')
with open(latest_kline, 'w', encoding='utf-8') as f:
    json.dump(all_stock_data, f, ensure_ascii=False)

# Index
if index_data:
    idx_file = os.path.join(KLINE_CACHE, f'index_full_{START_DATE}_{end_str}.json')
    with open(idx_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False)
    latest_idx = os.path.join(KLINE_CACHE, 'index_latest.json')
    with open(latest_idx, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False)
    print(f"  Index: {os.path.basename(idx_file)}")

# === Verify ===
print(f"\n{'='*60}")
print("数据验证")
print(f"{'='*60}")
codes = list(all_stock_data.keys())
sh = sum(1 for c in codes if c.startswith('sh.'))
sz = sum(1 for c in codes if c.startswith('sz.'))
print(f"  股票: {len(codes)} (沪:{sh} 深:{sz})")

all_dates = set()
lens = []
for code, records in all_stock_data.items():
    lens.append(len(records))
    for r in records:
        all_dates.add(r['date'])

if all_dates:
    sd = sorted(all_dates)
    print(f"  日期: {sd[0]} ~ {sd[-1]} ({len(all_dates)} 天)")
print(f"  每股记录: min={min(lens)}, max={max(lens)}, avg={np.mean(lens):.0f}")

if index_data:
    n = len(index_data['date'])
    print(f"  指数: {n} 天 ({index_data['date']['0']} ~ {index_data['date'][str(n-1)]})")

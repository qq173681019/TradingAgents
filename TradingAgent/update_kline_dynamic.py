#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态K线缓存更新 - 自动计算需要补充的日期范围
"""
import json, os, sys, time
from datetime import datetime, timedelta

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'

import akshare as ak
import pandas as pd

def convert_code(code):
    return code[2:]  # sh600000 -> 600000

def fetch_kline(code, start_date, end_date):
    ak_code = convert_code(code)
    try:
        df = ak.stock_zh_a_hist(symbol=ak_code, period="daily",
                                start_date=start_date, end_date=end_date, adjust="")
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            rec = {
                'date': str(row['日期'])[:10] if hasattr(row, '日期') else str(row.name)[:10],
                'open': float(row['开盘']) if pd.notna(row['开盘']) else None,
                'high': float(row['最高']) if pd.notna(row['最高']) else None,
                'low': float(row['最低']) if pd.notna(row['最低']) else None,
                'close': float(row['收盘']) if pd.notna(row['收盘']) else None,
                'volume': float(row['成交量']) if pd.notna(row['成交量']) else None,
            }
            if rec['close'] is not None:
                records.append(rec)
        return records
    except Exception as e:
        return []

def main():
    today = datetime.now().strftime('%Y%m%d')
    print(f"=" * 60)
    print(f"动态K线更新 | 今天: {today}")
    print(f"=" * 60)

    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"缓存: {len(cache)} 只股票")

    # 找最常见日期作为基准
    from collections import Counter
    dates = [r[-1].get('date', '') for r in cache.values() if r]
    c = Counter(dates)
    most_common = c.most_common(1)[0] if c else ('unknown', 0)
    print(f"最常见最后日期: {most_common[0]} ({most_common[1]} 只)")

    # 计算需要更新的日期范围
    base_date = most_common[0].replace('-', '')
    start_date = (datetime.strptime(base_date, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')
    end_date = today
    print(f"更新范围: {start_date} ~ {end_date}")

    # 找出需要更新的股票
    needs_update = []
    target_date = most_common[0]
    for code in cache:
        recs = cache[code]
        if not recs or recs[-1].get('date', '') < end_date:
            needs_update.append(code)
    print(f"需更新: {len(needs_update)} 只\n")

    if not needs_update:
        print("全部最新，无需更新！")
        return

    BATCH = 20
    DELAY = 0.5
    updated = 0
    failed = 0
    new_records = 0
    processed = 0

    for i in range(0, len(needs_update), BATCH):
        batch = needs_update[i:i + BATCH]
        for code in batch:
            recs = fetch_kline(code, start_date, end_date)
            if recs:
                existing_dates = {r['date'] for r in cache[code]}
                added = 0
                for rec in recs:
                    if rec['date'] not in existing_dates:
                        cache[code].append(rec)
                        added += 1
                if added:
                    cache[code].sort(key=lambda x: x['date'])
                    new_records += added
                updated += 1
            else:
                failed += 1
            processed += 1

        if processed % 100 < BATCH or processed == len(needs_update):
            print(f"  进度: {processed}/{len(needs_update)} ({processed*100//len(needs_update)}%) | 更新:{updated} 失败:{failed} 新记录:{new_records}")

        if processed % 200 < BATCH:
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        time.sleep(DELAY)

    # 最终保存
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

    # 验证
    dates2 = [r[-1].get('date', '') for r in cache.values() if r]
    c2 = Counter(dates2)
    print(f"\n更新后最新日期分布:")
    for dt, cnt in c2.most_common(5):
        print(f"  {dt}: {cnt} 只")
    print(f"\n完成! 更新:{updated} 失败:{failed} 新增记录:{new_records}")

if __name__ == '__main__':
    main()

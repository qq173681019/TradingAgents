#!/usr/bin/env python3
"""Fetch expanded K-line data - 800 stocks from baostock"""
import baostock as bs
import json, os, time, random

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
CACHE_FILE = os.path.join(DATA_DIR, 'kline_cache', 'kline_data_2026-02-10_2026-04-07_expanded.json')

# Load codes
with open(os.path.join(DATA_DIR, 'all_stock_codes.json'), 'r', encoding='utf-8') as f:
    all_codes = json.load(f)

# Filter: only actual stocks (6-digit codes starting with 6, 0, or 3, excluding indices)
stock_codes = []
for item in all_codes:
    code = item['code']
    num = code.split('.')[1]
    # Skip index codes (399xxx, 000xxx indices)
    if num.startswith('399') or num.startswith('880'):
        continue
    # Only keep 6-digit stock codes
    if len(num) != 6:
        continue
    stock_codes.append(code)

print(f"Filtered to {len(stock_codes)} actual stocks", flush=True)

# Random sample 800 for manageable speed
random.seed(42)
sample = sorted(random.sample(stock_codes, min(800, len(stock_codes))))
print(f"Sampled {len(sample)} stocks")

# Fetch K-line
print("\nFetching K-line data...")
lg = bs.login()

kline = {}
start_time = time.time()

for i, code in enumerate(sample):
    try:
        rs = bs.query_history_k_data_plus(
            code, "date,open,high,low,close,volume",
            start_date='2026-02-10', end_date='2026-04-07',
            frequency="d", adjustflag="2"
        )
        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row[0] and row[2] and float(row[2]) > 0:
                rows.append({
                    'date': row[0], 'open': float(row[1]),
                    'high': float(row[2]), 'low': float(row[3]),
                    'close': float(row[4]), 'volume': float(row[5])
                })
        if len(rows) >= 15:
            kline[code] = rows
    except:
        pass
    
    if (i+1) % 100 == 0:
        elapsed = time.time() - start_time
        rate = (i+1) / elapsed
        remaining = (len(sample) - i - 1) / rate
        print(f"  {i+1}/{len(sample)} ({rate:.0f}/s, ~{remaining:.0f}s left) - valid: {len(kline)}")

bs.logout()
elapsed = time.time() - start_time
print(f"\nDone! {len(kline)} stocks with valid K-line in {elapsed:.0f}s")

# Save
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
with open(CACHE_FILE, 'w', encoding='utf-8') as f:
    json.dump(kline, f)
print(f"Saved to {CACHE_FILE}")

"""Verify Tencent data source matches existing cache format"""
import os, json
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

import akshare as ak

# Load cache
with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r') as f:
    cache = json.load(f)

# Check existing data for sh600000
recs = cache['sh600000']
print("Cache last 3 records:")
for r in recs[-3:]:
    print(f"  {r}")

# Fetch from Tencent
df = ak.stock_zh_a_hist_tx(symbol='sh600000', start_date='20260424', end_date='20260428', adjust='qfq')
print("\nTencent data:")
print(df)
print(f"\nColumns: {df.columns.tolist()}")

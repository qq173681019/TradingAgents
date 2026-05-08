import sys
sys.stdout.reconfigure(line_buffering=True)

import json

# Check current state
f = open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r', encoding='utf-8')
d = json.load(f)
f.close()

print(f'Total stocks: {len(d)}')

# Check how many are updated to 5月6日
date_counts = {}
for code, klines in d.items():
    if isinstance(klines, list) and len(klines) > 0:
        last = klines[-1].get('date', '')
        date_counts[last] = date_counts.get(last, 0) + 1

for d_str, c in sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:10]:
    print(f'  {d_str}: {c} stocks')

# Count stocks that need updating
need_update = sum(1 for code, klines in d.items()
                  if isinstance(klines, list) and len(klines) > 0
                  and klines[-1].get('date', '') < '2026-05-06')
print(f'\nStocks still needing update: {need_update}')

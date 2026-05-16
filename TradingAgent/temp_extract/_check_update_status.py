"""Quick check: how many stocks need update"""
import json

with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r') as f:
    cache = json.load(f)

need_update = 0
up_to_date = 0
for code, recs in cache.items():
    last = recs[-1]['date']
    if last < '2026-05-06':
        need_update += 1
    else:
        up_to_date += 1

print(f"Total: {len(cache)} stocks")
print(f"Up to date (>= 2026-05-06): {up_to_date}")
print(f"Need update (< 2026-05-06): {need_update}")

# Show some examples of stocks that need update
print("\nSample stocks needing update:")
count = 0
for code, recs in cache.items():
    if recs[-1]['date'] < '2026-05-06':
        print(f"  {code}: last={recs[-1]['date']}, {len(recs)} records")
        count += 1
        if count >= 10:
            break

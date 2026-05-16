import json

with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r') as f:
    cache = json.load(f)

print(f'Total stocks: {len(cache)}')
for k in list(cache.keys())[:5]:
    recs = cache[k]
    print(f'  {k}: {recs[0]["date"]} ~ {recs[-1]["date"]}, {len(recs)} records')

from collections import Counter
last_dates = {}
for k, recs in cache.items():
    last_dates[k] = recs[-1]['date']
c = Counter(last_dates.values())
for d, cnt in c.most_common(5):
    print(f'  Last date={d}: {cnt} stocks')

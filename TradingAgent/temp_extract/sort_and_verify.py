"""Sort all records and save"""
import json

CACHE = r"D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json"

with open(CACHE, 'r', encoding='utf-8') as f:
    d = json.load(f)

print(f"Loaded: {len(d)} stocks")

for key in d:
    if d[key]:
        d[key].sort(key=lambda x: x['date'])

with open(CACHE, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False)

from collections import Counter
last_dates = Counter()
for key, recs in d.items():
    if recs:
        last_dates[recs[-1]['date']] += 1

up = sum(cnt for dt, cnt in last_dates.items() if dt >= '2026-05-06')
print(f"Coverage 2026-05-06: {up}/{len(d)} ({up*100//len(d)}%)")
print("Date distribution:")
for dt, cnt in sorted(last_dates.items()):
    tag = "OK" if dt >= "2026-05-06" else "OLD"
    print(f"  {dt}: {cnt} [{tag}]")

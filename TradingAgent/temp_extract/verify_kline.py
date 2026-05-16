"""Full verification of kline cache"""
import json
from collections import Counter

CACHE = r"D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json"

with open(CACHE, 'r', encoding='utf-8') as f:
    d = json.load(f)

print(f"Total stocks: {len(d)}")

# Sort all records
for key in d:
    if d[key]:
        d[key].sort(key=lambda x: x['date'])

# Last date distribution
last_dates = Counter()
for key, recs in d.items():
    if recs:
        last_dates[recs[-1]['date']] += 1
    else:
        last_dates['<empty>'] += 1

up = sum(cnt for dt, cnt in last_dates.items() if dt >= '2026-05-06')
print(f"\nCoverage 2026-05-06: {up}/{len(d)} ({up*100//len(d)}%)")
print("\nDate distribution:")
for dt, cnt in sorted(last_dates.items()):
    tag = "OK" if dt >= "2026-05-06" else "OLD"
    print(f"  {dt}: {cnt} [{tag}]")

# Check for any remaining slash-format dates
slash_count = 0
for key, recs in d.items():
    for r in recs:
        if '/' in r.get('date', ''):
            slash_count += 1
print(f"\nSlash-format dates remaining: {slash_count}")

# Check for duplicates within stocks
dup_count = 0
for key, recs in d.items():
    dates = [r['date'] for r in recs]
    if len(dates) != len(set(dates)):
        dup_count += 1
print(f"Stocks with duplicate dates: {dup_count}")

# Save sorted version
with open(CACHE, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False)
print(f"\nSaved sorted cache ({len(d)} stocks)")

import json

with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Count by last date
date_counts = {}
for code, klines in data.items():
    if isinstance(klines, list) and klines:
        ld = klines[-1].get('date', '')
        date_counts[ld] = date_counts.get(ld, 0) + 1

print('Last date distribution:')
for d_str, c in sorted(date_counts.items(), key=lambda x: x[0], reverse=True):
    print(f'  {d_str}: {c} stocks')

# Count stocks with 5月6日 data
updated_to_latest = sum(1 for code, klines in data.items()
                       if isinstance(klines, list) and klines 
                       and klines[-1].get('date', '') >= '2026-05-06')
print(f'\nUpdated to >= 2026-05-06: {updated_to_latest}')
print(f'Not updated: {len(data) - updated_to_latest}')

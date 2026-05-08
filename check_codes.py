import json

with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Show first 10 codes and their last dates
codes = list(data.keys())
print('First 10 codes:')
for c in codes[:10]:
    klines = data[c]
    if isinstance(klines, list) and klines:
        print(f'  {c}: last={klines[-1].get("date")}, first={klines[0].get("date")}')

# Check code formats
print(f'\nCode format samples:')
sh_count = sum(1 for c in codes if c.startswith('sh'))
sz_count = sum(1 for c in codes if c.startswith('sz'))
num_count = sum(1 for c in codes if c[0].isdigit())
print(f'  sh prefix: {sh_count}')
print(f'  sz prefix: {sz_count}')
print(f'  digit prefix: {num_count}')

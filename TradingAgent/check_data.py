import json

# Get all stock codes with names
stocks=json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\all_stock_codes.json',encoding='utf-8'))
print(f'Total stocks: {len(stocks)}')

# Get kline data
kline=json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_6m_2025-10-01_2026-04-07.json',encoding='utf-8'))
print(f'Kline stocks: {len(kline)}')

# Build code->name map
code2name = {}
for s in stocks:
    code2name[s['code']] = s['name']

# Count kline stocks that have names
matched = 0
for code_prefix in list(kline.keys())[:5]:
    code = code_prefix.split('.')[1] if '.' in code_prefix else code_prefix
    name = code2name.get(code, '???')
    print(f'{code_prefix} -> {name}')
    matched += 1

# Show date range
k0 = list(kline.keys())[0]
dates = [x['date'] for x in kline[k0]]
print(f'Date range: {dates[0]} to {dates[-1]}')

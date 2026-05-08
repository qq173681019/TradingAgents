import json
f = open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json','r',encoding='utf-8')
d = json.load(f)
keys = list(d.keys())
print(f'Total stocks: {len(keys)}')
sample = d[keys[0]]
print(f'Sample key: {keys[0]}')
print(f'Sample type: {type(sample)}')
if isinstance(sample, dict):
    print(f'Sample keys: {list(sample.keys())}')
    # Try to find date field
    for k,v in sample.items():
        if isinstance(v, list) and len(v) > 0:
            print(f'  {k}: list of {len(v)} items, first={v[0]}')
            if len(v) > 1:
                print(f'  {k}: last={v[-1]}')
elif isinstance(sample, list):
    print(f'Sample is list of {len(sample)} items')
    print(f'First: {sample[0]}')
    print(f'Last: {sample[-1]}')

import json

# Load kline
with open(r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json','r') as f:
    kline = json.load(f)

# Load index
with open(r'D:\GitHub\TradingAgents\TradingShared\data\index_shanghai_full.json','r') as f:
    idx = json.load(f)
idx_map = {d['date']: d['close'] for d in idx}

print('=== 5月4日推荐验证 ===')
stocks = [('sz002221','东华能源'), ('sz002125','湘潭电化'), ('sz002818','富森美')]
for code, name in stocks:
    if code in kline:
        recs = kline[code]
        for r in recs:
            d = r['date']
            if d in ('2026-05-05','2026-05-06'):
                c = r['close']
                print(f'  {code} {name}: {d} close={c}')
        # Get rec day close (5/4 = Sunday, so 5/6 is next trading day)
        last = recs[-1]
        ldate = last['date']
        lclose = last['close']
        print(f'  {code} {name}: latest={ldate} close={lclose}')
    else:
        print(f'  {code} {name}: NOT in kline')

# Index
for d in ['2026-05-05','2026-05-06']:
    close = idx_map.get(d)
    print(f'  SH Index {d}: {close}')

print()
print('=== 5月6日V17推荐 ===')
stocks2 = [('sz002034','旺能环境'), ('sh603611','诺力股份'), ('sh600668','尖峰集团')]
for code, name in stocks2:
    if code in kline:
        recs = kline[code]
        last = recs[-1]
        ldate = last['date']
        lclose = last['close']
        print(f'  {code} {name}: latest={ldate} close={lclose}')
    else:
        print(f'  {code} {name}: NOT in kline')

import json, sys
d = json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\comprehensive_stock_data.json','r',encoding='utf-8'))
stocks = d.get('stocks', d)
count = 0
for code, s in stocks.items():
    kline = s.get('kline_data', {})
    if isinstance(kline, dict):
        daily = kline.get('daily', [])
        if len(daily) >= 30:
            count += 1
print(f'Stocks with 30+ days kline: {count}')
for code in ['000001','600519','000002']:
    if code in stocks:
        kline = stocks[code].get('kline_data',{}).get('daily',[])
        name = stocks[code].get('basic_info',{}).get('name','?')
        print(f'{code} {name}: {len(kline)} days')
        if kline:
            print(f'  last3: {kline[-3:]}')

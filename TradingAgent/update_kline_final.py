"""Final pass: update remaining stocks with larger window"""
import json, os, time
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['NO_PROXY'] = '*'
import requests

session = requests.Session()
session.trust_env = False

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

remaining = []
for code in cache:
    if cache[code] and cache[code][-1].get('date', '') < '2026-05-06':
        remaining.append(code)

print(f'Remaining: {len(remaining)}')

updated = 0
suspended = 0
for code in remaining:
    url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{code},day,,,20,qfq'}
    r = session.get(url, params=params, timeout=5)
    data = r.json()
    sd = data.get('data', {}).get(code, {})
    klines = sd.get('qfqday', [])
    
    if klines:
        existing = cache[code]
        existing_dates = {rec['date'] for rec in existing}
        added = 0
        for k in klines:
            rec = {
                'date': k[0],
                'open': float(k[1]),
                'close': float(k[2]),
                'high': float(k[3]),
                'low': float(k[4]),
                'volume': float(k[5]),
            }
            if rec['date'] not in existing_dates:
                existing.append(rec)
                existing_dates.add(rec['date'])
                added += 1
        if added > 0:
            existing.sort(key=lambda x: x['date'])
            updated += 1
            last_date = existing[-1]['date']
            print(f'  {code}: +{added} records, last={last_date}')
        else:
            last_tencent = klines[-1][0]
            last_cache = existing[-1]['date']
            if last_tencent == last_cache:
                suspended += 1
                print(f'  {code}: suspended/delisted (no newer data, last={last_cache})')
            else:
                print(f'  {code}: strange - tencent last={last_tencent}, cache last={last_cache}')
    else:
        suspended += 1
        print(f'  {code}: no data from tencent')
    time.sleep(0.05)

print(f'\nUpdated: {updated}, Suspended/Delisted: {suspended}')

# Save
with open(CACHE_PATH, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False)
print('Saved!')

# Final check
still_need = sum(1 for code in cache if cache[code] and cache[code][-1].get('date', '') < '2026-05-06')
up_to_date = sum(1 for code in cache if cache[code] and cache[code][-1].get('date', '') >= '2026-05-06')
print(f'Final: {up_to_date} up-to-date, {still_need} still need update (suspended/delisted)')

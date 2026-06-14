"""QA Cross-Validation: compare local cache with Tencent real-time quotes"""
import json, random, time, urllib.request, ssl
from collections import Counter

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

# Get all stocks with last date = 2026-06-12
valid_stocks = [k for k, v in cache.items() if v and v[-1]['date'] == '2026-06-12']
print(f'Stocks with data up to 2026-06-12: {len(valid_stocks)}')

# Random sample 30
random.seed(42)
sample = random.sample(valid_stocks, min(30, len(valid_stocks)))
print(f'Sampled {len(sample)} stocks for cross-validation')
print()

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get_tencent_quote(code):
    url = f'https://qt.gtimg.cn/q={code}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    return resp.read().decode('gbk')

matched = 0
mismatched = 0
errors = 0
mismatches = []

for i, code in enumerate(sample):
    try:
        content = get_tencent_quote(code)
        parts = content.split('~')
        if len(parts) < 35:
            print(f'[{i+1:2d}] {code}: parse failed ({len(parts)} parts)')
            errors += 1
            continue

        name = parts[1]
        tencent_close = float(parts[3])
        tencent_open = float(parts[5])
        tencent_high = float(parts[33])
        tencent_low = float(parts[34])
        tencent_date = parts[30][:8] if len(parts[30]) >= 8 else ''

        # Get cache data
        cache_recs = cache[code]
        cache_last = cache_recs[-1]
        cache_close = float(cache_last['close'])
        cache_open = float(cache_last['open'])
        cache_high = float(cache_last['high'])
        cache_low = float(cache_last['low'])
        cache_date = cache_last['date'].replace('-', '')

        # Compare
        close_match = abs(tencent_close - cache_close) < 0.02
        date_match = tencent_date.startswith(cache_date) or cache_date in tencent_date
        open_match = abs(tencent_open - cache_open) < 0.02
        high_match = abs(tencent_high - cache_high) < 0.02
        low_match = abs(tencent_low - cache_low) < 0.02

        all_match = close_match and date_match and open_match and high_match and low_match

        if all_match:
            matched += 1
            status = 'OK'
        else:
            mismatched += 1
            status = 'MISMATCH'
            mismatches.append({
                'code': code, 'name': name,
                'tencent': {'close': tencent_close, 'open': tencent_open, 'high': tencent_high, 'low': tencent_low, 'date': tencent_date},
                'cache': {'close': cache_close, 'open': cache_open, 'high': cache_high, 'low': cache_low, 'date': cache_date},
                'checks': {'close': close_match, 'date': date_match, 'open': open_match, 'high': high_match, 'low': low_match}
            })

        detail = f"close T={tencent_close} C={cache_close} | date T={tencent_date} C={cache_date}"
        print(f'[{i+1:2d}] {code} {name}: {detail} | {status}')

        time.sleep(0.15)

    except Exception as e:
        print(f'[{i+1:2d}] {code}: ERROR - {e}')
        errors += 1

print()
print('=' * 70)
print('QA CROSS-VALIDATION REPORT')
print('=' * 70)
total_compared = matched + mismatched
print(f'Stocks sampled: {len(sample)}')
print(f'Successfully compared: {total_compared}')
print(f'Errors (API failures): {errors}')
print(f'Matched: {matched}')
print(f'Mismatched: {mismatched}')
if total_compared > 0:
    accuracy = matched / total_compared * 100
    print(f'Accuracy: {accuracy:.1f}%')
else:
    accuracy = 0
    print('Accuracy: N/A (no comparisons)')

if mismatches:
    print()
    print('=== MISMATCH DETAILS ===')
    for m in mismatches:
        print(f'{m["code"]} {m["name"]}:')
        print(f'  Tencent: close={m["tencent"]["close"]} open={m["tencent"]["open"]} high={m["tencent"]["high"]} low={m["tencent"]["low"]} date={m["tencent"]["date"]}')
        print(f'  Cache:   close={m["cache"]["close"]} open={m["cache"]["open"]} high={m["cache"]["high"]} low={m["cache"]["low"]} date={m["cache"]["date"]}')
        print(f'  Checks:  {m["checks"]}')

print()
if accuracy >= 99.0:
    print('FINAL VERDICT: PASS')
else:
    print('FINAL VERDICT: FAIL')

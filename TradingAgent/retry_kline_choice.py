"""重试失败的40只股票"""
import json, os, sys, time
from collections import Counter

TRADING_SHARED = r"D:\GitHub\TradingAgents\TradingShared"
API_DIR = os.path.join(TRADING_SHARED, "api")
CACHE_FILE = os.path.join(TRADING_SHARED, "data", "kline_cache", "kline_full_latest.json")

sys.path.insert(0, TRADING_SHARED)
sys.path.insert(0, API_DIR)

from get_choice_data import setup_choice_dll_path, login_callback

setup_choice_dll_path()
from EmQuantAPI import c
from config import CHOICE_USERNAME, CHOICE_PASSWORD

result = c.start(f"USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD},ForceLogin=1", login_callback)
time.sleep(3)
print(f"Login: {result.ErrorCode}")

with open(CACHE_FILE, 'r', encoding='utf-8') as f:
    cache = json.load(f)

# Find lagging stocks
lagging = []
for key, records in cache.items():
    if records and records[-1].get("date", "") < "2026-05-06":
        lagging.append(key)

print(f"Lagging stocks: {len(lagging)}")

def cache_key_to_choice(key):
    if key.startswith("sh"): return key[2:] + ".SH"
    elif key.startswith("sz"): return key[2:] + ".SZ"
    return None

updated = 0
errors = 0

for key in lagging:
    cc = cache_key_to_choice(key)
    if not cc: continue
    
    for attempt in range(3):
        try:
            csd = c.csd(cc, "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-04-25", "2026-05-06", "")
            if csd.ErrorCode == 0 and cc in csd.Data:
                dates = csd.Dates
                arrays = csd.Data[cc]
                existing_dates = {r["date"] for r in cache[key]}
                added = 0
                for i in range(len(dates)):
                    from datetime import datetime as dt
                    raw_date = dates[i]
                    if '/' in raw_date:
                        parsed = dt.strptime(raw_date, '%Y/%m/%d')
                        norm_date = parsed.strftime('%Y-%m-%d')
                    else:
                        norm_date = raw_date
                    if norm_date not in existing_dates:
                        try:
                            o, h, l, cl, v = arrays[0][i], arrays[1][i], arrays[2][i], arrays[3][i], arrays[4][i]
                            if o is None and h is None and l is None and cl is None:
                                continue
                            cache[key].append({
                                "date": norm_date,
                                "open": float(o) if o else None,
                                "high": float(h) if h else None,
                                "low": float(l) if l else None,
                                "close": float(cl) if cl else None,
                                "volume": float(v) if v else 0.0
                            })
                            added += 1
                        except: pass
                if added:
                    cache[key].sort(key=lambda x: x["date"])
                updated += 1
                print(f"  [OK] {key} +{added}")
                break
            else:
                print(f"  [RETRY {attempt+1}] {key}: {csd.ErrorCode}")
                time.sleep(2)
        except Exception as e:
            print(f"  [ERR] {key}: {e}")
            time.sleep(2)
    else:
        errors += 1
    
    time.sleep(0.5)

with open(CACHE_FILE, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False)

# Verify
last_dates = Counter()
for key, records in cache.items():
    if records:
        last_dates[records[-1].get("date","")] += 1
up = sum(cnt for dt, cnt in last_dates.items() if dt >= "2026-05-06")
print(f"\nUpdated: {updated}, Errors: {errors}")
print(f"Coverage: {up}/{len(cache)} ({up*100//len(cache)}%)")
for dt, cnt in sorted(last_dates.items()):
    print(f"  {dt}: {cnt}")

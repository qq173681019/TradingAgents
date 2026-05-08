"""
Choice API K线增量更新 v3 - 一次性处理所有需要更新的股票
"""
import json, os, sys, time
from datetime import datetime
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

# Login
print("Logging in...")
result = c.start(f"USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD},ForceLogin=1", login_callback)
time.sleep(3)
print(f"Login: ErrorCode={result.ErrorCode}")

# Load cache
print("Loading cache...")
with open(CACHE_FILE, 'r', encoding='utf-8') as f:
    cache = json.load(f)
print(f"Total stocks: {len(cache)}")

# Check CSD with a known good date
print("Testing CSD...")
test = c.csd("000001.SZ", "CLOSE", "2026-04-24", "2026-04-24", "")
csd_ok = test.ErrorCode == 0
print(f"CSD available: {csd_ok} (test ErrorCode={test.ErrorCode})")

if not csd_ok:
    print("CSD not available, cannot proceed. Aborting.")
    sys.exit(1)

# Find stocks that need updating
TARGET = "2026-05-06"
needs_update = []
for key, records in cache.items():
    if not records or records[-1].get("date", "") < TARGET:
        needs_update.append(key)

print(f"Stocks needing update: {len(needs_update)}")

def cache_key_to_choice(key):
    if key.startswith("sh"): return key[2:] + ".SH"
    elif key.startswith("sz"): return key[2:] + ".SZ"
    elif key.startswith("bj"): return key[2:] + ".BJ"
    return None

def normalize_date(dt_str):
    """Normalize date to YYYY-MM-DD"""
    if '/' in dt_str:
        return datetime.strptime(dt_str, '%Y/%m/%d').strftime('%Y-%m-%d')
    return dt_str

# Process in batches of 10 (conservative for stability)
BATCH = 10
total_updated = 0
total_new = 0
errors = 0

for i in range(0, len(needs_update), BATCH):
    batch_keys = needs_update[i:i+BATCH]
    codes = []
    key_map = {}
    for key in batch_keys:
        cc = cache_key_to_choice(key)
        if cc:
            codes.append(cc)
            key_map[cc] = key
    
    if not codes:
        continue
    
    codes_str = ",".join(codes)
    
    try:
        csd = c.csd(codes_str, "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-04-25", "2026-05-06", "")
        
        if csd.ErrorCode == 0:
            dates = [normalize_date(d) for d in csd.Dates]
            for cc in codes:
                key = key_map[cc]
                if cc in csd.Data:
                    arrays = csd.Data[cc]
                    existing_dates = {r["date"] for r in cache[key]}
                    added = 0
                    for j in range(len(dates)):
                        if dates[j] not in existing_dates:
                            try:
                                o, h, l, cl, v = arrays[0][j], arrays[1][j], arrays[2][j], arrays[3][j], arrays[4][j]
                                if o is None and h is None and l is None and cl is None:
                                    continue
                                cache[key].append({
                                    "date": dates[j],
                                    "open": float(o) if o is not None else None,
                                    "high": float(h) if h is not None else None,
                                    "low": float(l) if l is not None else None,
                                    "close": float(cl) if cl is not None else None,
                                    "volume": float(v) if v is not None else 0.0
                                })
                                added += 1
                            except (IndexError, TypeError, ValueError):
                                pass
                    if added:
                        cache[key].sort(key=lambda x: x["date"])
                        total_new += added
                    total_updated += 1
                else:
                    errors += 1
        elif csd.ErrorCode == 10002003:
            # Network timeout, retry individual stock
            print(f"  Timeout on batch at {i}, retrying individually...")
            for cc in codes:
                key = key_map[cc]
                try:
                    csd2 = c.csd(cc, "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-04-25", "2026-05-06", "")
                    if csd2.ErrorCode == 0 and cc in csd2.Data:
                        dates2 = [normalize_date(d) for d in csd2.Dates]
                        arrays = csd2.Data[cc]
                        existing = {r["date"] for r in cache[key]}
                        added = 0
                        for j in range(len(dates2)):
                            if dates2[j] not in existing:
                                try:
                                    o, h, l, cl, v = arrays[0][j], arrays[1][j], arrays[2][j], arrays[3][j], arrays[4][j]
                                    if o is None and h is None and l is None and cl is None:
                                        continue
                                    cache[key].append({"date": dates2[j], "open": float(o) if o else None, "high": float(h) if h else None, "low": float(l) if l else None, "close": float(cl) if cl else None, "volume": float(v) if v else 0.0})
                                    added += 1
                                except: pass
                        if added:
                            cache[key].sort(key=lambda x: x["date"])
                            total_new += added
                        total_updated += 1
                    else:
                        errors += 1
                except:
                    errors += 1
                time.sleep(0.3)
        else:
            print(f"  CSD error {csd.ErrorCode}: {csd.ErrorMsg}")
            errors += len(codes)
    except Exception as e:
        print(f"  Exception: {e}")
        errors += len(codes)
    
    # Progress
    processed = min(i + BATCH, len(needs_update))
    if processed % 100 < BATCH or processed == len(needs_update):
        pct = processed * 100 // len(needs_update)
        print(f"  [{pct:3d}%] {processed}/{len(needs_update)} | updated: {total_updated} | new: {total_new} | err: {errors}")
    
    # Save every 500
    if total_updated > 0 and total_updated % 500 < BATCH:
        print(f"  [SAVE] {total_updated} stocks...")
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    
    time.sleep(0.3)

# Final save
print("\nFinal save...")
with open(CACHE_FILE, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False)

# Verify
last_dates = Counter()
for key, records in cache.items():
    if records:
        last_dates[records[-1].get("date","")] += 1

up = sum(cnt for dt, cnt in last_dates.items() if dt >= TARGET)
print(f"\n=== RESULT ===")
print(f"Total: {len(cache)}")
print(f"Coverage {TARGET}: {up}/{len(cache)} ({up*100//len(cache)}%)")
print(f"Updated: {total_updated}, New records: {total_new}, Errors: {errors}")
print("Date distribution:")
for dt, cnt in sorted(last_dates.items()):
    tag = "OK" if dt >= TARGET else "OLD"
    print(f"  {dt}: {cnt} [{tag}]")

"""
更新K线缓存 - 使用Tushare批量获取
从2026-04-25到2026-05-06（增量更新）
优化: 使用ThreadPoolExecutor加速, 中间保存断点
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')
START_DATE = '20260425'
END_DATE = '20260506'

import tushare as ts
ts.set_token('4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28')
pro = ts.pro_api()

def main():
    t0 = time.time()
    print("=" * 60)
    print("  K线缓存增量更新 (Tushare)")
    print(f"  日期范围: {START_DATE} ~ {END_DATE}")
    print("=" * 60, flush=True)
    
    # 1. Load existing cache
    print("\n[1] Loading existing cache...", flush=True)
    with open(LATEST_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"  {len(cache)} stocks loaded", flush=True)
    
    # 2. Prepare stock list
    codes = list(cache.keys())
    print(f"  Updating {len(codes)} stocks", flush=True)
    
    updated = 0
    failed = 0
    new_records_total = 0
    no_new = 0
    
    # 3. Fetch and merge
    print(f"\n[2] Fetching klines...", flush=True)
    for i, cache_key in enumerate(codes):
        # Convert: sh600000 -> 600000.SH, sz000001 -> 000001.SZ
        if cache_key.startswith('sh'):
            ts_code = cache_key[2:] + '.SH'
        elif cache_key.startswith('sz'):
            ts_code = cache_key[2:] + '.SZ'
        else:
            continue
        
        try:
            df = pro.daily(ts_code=ts_code, start_date=START_DATE, end_date=END_DATE)
            if df is not None and len(df) > 0:
                new_records = []
                for _, r in df.iterrows():
                    date_str = str(r['trade_date'])
                    formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    new_records.append({
                        'date': formatted,
                        'open': float(r['open']),
                        'high': float(r['high']),
                        'low': float(r['low']),
                        'close': float(r['close']),
                        'volume': float(r['vol']),
                    })
                
                # Merge with existing
                existing_dates = set(r['date'] for r in cache[cache_key])
                added = 0
                for r in new_records:
                    if r['date'] not in existing_dates:
                        cache[cache_key].append(r)
                        added += 1
                if added > 0:
                    cache[cache_key].sort(key=lambda x: x['date'])
                    new_records_total += added
                    updated += 1
                else:
                    no_new += 1
            else:
                no_new += 1
                
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  FAILED {ts_code}: {e}", flush=True)
        
        # Progress report every 200 stocks
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(codes) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(codes)}] updated={updated} failed={failed} new={new_records_total} | {rate:.0f}/s ETA:{eta:.0f}s", flush=True)
            # Intermediate save
            with open(LATEST_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        
        # Tushare rate limit: respect it
        time.sleep(0.15)
    
    # 4. Final save
    print(f"\n[3] Final save...", flush=True)
    with open(LATEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    elapsed = time.time() - t0
    
    print(f"\n{'='*60}")
    print(f"  DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Cache: {sz:.1f}MB, {len(cache)} stocks")
    print(f"  Updated: {updated}, No new data: {no_new}, Failed: {failed}")
    print(f"  New records: {new_records_total}")
    print(f"{'='*60}")
    
    # 5. Verify
    print("\n[4] Verification:")
    for k in list(cache.keys())[:5]:
        recs = cache[k]
        print(f"  {k}: {recs[0]['date']} ~ {recs[-1]['date']}, {len(recs)} records")
    
    # Check last date distribution
    from collections import Counter
    last_dates = {}
    for k, recs in cache.items():
        last_dates[k] = recs[-1]['date']
    c = Counter(last_dates.values())
    print("\n  Last date distribution (top 5):")
    for d, cnt in c.most_common(5):
        print(f"    {d}: {cnt} stocks")

if __name__ == '__main__':
    main()

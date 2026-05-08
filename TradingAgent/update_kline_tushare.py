"""
更新K线缓存 - 用Tushare (不受东方财富代理限制)
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

import tushare as ts
ts.set_token('4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28')
pro = ts.pro_api()

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')
START_DATE = '20260425'
END_DATE = time.strftime('%Y%m%d')

def main():
    print("=" * 50, flush=True)
    print("K线缓存更新 (Tushare)", flush=True)
    print(f"日期范围: {START_DATE} ~ {END_DATE}", flush=True)
    print("=" * 50, flush=True)
    
    # Load existing
    print("\nLoading existing cache...", flush=True)
    with open(LATEST_FILE, 'r') as f:
        cache = json.load(f)
    print(f"  {len(cache)} stocks", flush=True)
    
    # Load existing and use its stock list (no need to call stock_basic)
    print("\nUsing existing stock codes...", flush=True)
    codes = list(cache.keys())  # e.g. ['sh600000', 'sz000001', ...]
    print(f"  {len(codes)} stocks to update", flush=True)
    
    updated = 0
    failed = 0
    new_records_total = 0
    
    for i, cache_key in enumerate(codes):
        # Convert cache_key (sh600000/sz000001) to tushare ts_code (600000.SH/000001.SZ)
        if cache_key.startswith('sh'):
            ts_code = cache_key[2:] + '.SH'
            symbol = cache_key[2:]
        elif cache_key.startswith('sz'):
            ts_code = cache_key[2:] + '.SZ'
            symbol = cache_key[2:]
        else:
            continue
        
        try:
            df = pro.daily(ts_code=ts_code, start_date=START_DATE, end_date=END_DATE)
            if df is not None and len(df) > 0:
                new_records = []
                for _, r in df.iterrows():
                    date_str = r['trade_date']  # YYYYMMDD
                    formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    new_records.append({
                        'date': formatted,
                        'open': float(r['open']),
                        'high': float(r['high']),
                        'low': float(r['low']),
                        'close': float(r['close']),
                        'volume': float(r['vol']),
                    })
                
                # Merge
                if cache_key in cache:
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
                    cache[cache_key] = new_records
                    new_records_total += len(new_records)
                    updated += 1
                    
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  FAILED {ts_code}: {e}")
        
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(codes)} ({(i+1)*100//len(codes)}%) updated={updated} failed={failed} new={new_records_total}", flush=True)
            # Intermediate save
            with open(LATEST_FILE, 'w') as f:
                json.dump(cache, f)
        
        # Tushare rate limit: 50 calls/min for daily
        if (i + 1) % 45 == 0:
            print("  Rate limit pause 65s...", flush=True)
            time.sleep(65)
        else:
            time.sleep(1.5)
    
    # Final save
    print(f"\nSaving final cache...")
    with open(LATEST_FILE, 'w') as f:
        json.dump(cache, f)
    
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    print(f"Done! {sz:.1f}MB, {len(cache)} stocks, {updated} updated, {failed} failed, {new_records_total} new records")
    
    # Verify
    for k in list(cache.keys())[:3]:
        records = cache[k]
        print(f"  {k}: {records[0]['date']} ~ {records[-1]['date']}, {len(records)} days")

if __name__ == '__main__':
    main()

"""
批量更新K线缓存 - 使用AKShare腾讯数据源(不受代理限制)
只更新数据截止日期 < 2026-05-06 的股票
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')
START_DATE = '20260425'
END_DATE = '20260506'

import akshare as ak
import pandas as pd

def main():
    t0 = time.time()
    print("=" * 60)
    print("  K-line cache update (Tencent via AKShare)")
    print(f"  Date range: {START_DATE} ~ {END_DATE}")
    print("=" * 60, flush=True)
    
    # 1. Load existing cache
    print("\n[1] Loading existing cache...", flush=True)
    with open(LATEST_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"  {len(cache)} stocks loaded", flush=True)
    
    # Build existing dates lookup
    existing_dates = {}
    for code, recs in cache.items():
        existing_dates[code] = set(r['date'] for r in recs)
    
    # 2. Find stocks that need updating
    need_update = []
    for code, recs in cache.items():
        last_date = recs[-1]['date']
        if last_date < '2026-05-06':
            need_update.append(code)
    
    print(f"  {len(need_update)} stocks need update", flush=True)
    
    if not need_update:
        print("  All stocks already up to date!")
        return
    
    # 3. Fetch and merge
    updated = 0
    failed = 0
    new_records_total = 0
    no_new = 0
    
    print(f"\n[2] Fetching klines...", flush=True)
    for i, cache_key in enumerate(need_update):
        # cache_key format: sh600000 or sz000001
        # Tencent symbol format: sh600000, sz000001 (same!)
        
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=cache_key,
                start_date=START_DATE,
                end_date=END_DATE,
                adjust='qfq'
            )
            
            if df is not None and len(df) > 0:
                new_records = []
                for _, r in df.iterrows():
                    date_str = str(r['date'])[:10]
                    new_records.append({
                        'date': date_str,
                        'open': float(r['open']),
                        'high': float(r['high']),
                        'low': float(r['low']),
                        'close': float(r['close']),
                        'volume': float(r['amount']),
                    })
                
                # Merge with existing
                added = 0
                for r in new_records:
                    if r['date'] not in existing_dates[cache_key]:
                        cache[cache_key].append(r)
                        existing_dates[cache_key].add(r['date'])
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
            if failed <= 10:
                print(f"  FAILED {cache_key}: {e}", flush=True)
        
        # Progress report every 100 stocks
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(need_update) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(need_update)}] updated={updated} failed={failed} new={new_records_total} | {rate:.1f}/s ETA:{eta:.0f}s", flush=True)
            # Intermediate save
            with open(LATEST_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        
        # Rate limit: be nice to Tencent
        time.sleep(0.3)
    
    # 4. Final save
    print(f"\n[3] Final save...", flush=True)
    with open(LATEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    elapsed = time.time() - t0
    
    print(f"\n{'='*60}")
    print(f"  DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Cache: {sz:.1f}MB, {len(cache)} stocks")
    print(f"  Updated: {updated}, No new: {no_new}, Failed: {failed}")
    print(f"  New records: {new_records_total}")
    print(f"{'='*60}")
    
    # 5. Verify
    print("\n[4] Verification:")
    for k in list(cache.keys())[:5]:
        recs = cache[k]
        print(f"  {k}: {recs[0]['date']} ~ {recs[-1]['date']}, {len(recs)} records")
    
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

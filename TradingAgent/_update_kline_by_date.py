"""
高效更新K线缓存 - Tushare按日期批量获取
策略: 按交易日获取全市场数据(每天一次API调用)
只需要7次API调用(7个交易日) vs 3192次(逐股票)
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')

import tushare as ts
ts.set_token('4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28')
pro = ts.pro_api()

# Trading days from 2026-04-25 to 2026-05-06
# Need to figure out which days were trading days
# Possible: Apr 25, 28, 29, 30 / May 5, 6 (五一假期: May 1-4 likely holiday)
CANDIDATE_DATES = [
    '20260425',  # Friday
    '20260428',  # Monday
    '20260429',  # Tuesday
    '20260430',  # Wednesday
    '20260505',  # Monday (after labor day holiday)
    '20260506',  # Tuesday
]

def main():
    t0 = time.time()
    print("=" * 60)
    print("  K-line cache update (Tushare - by trade date)")
    print(f"  Candidate dates: {CANDIDATE_DATES}")
    print("=" * 60, flush=True)
    
    # 1. Load existing cache
    print("\n[1] Loading existing cache...", flush=True)
    with open(LATEST_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"  {len(cache)} stocks loaded", flush=True)
    
    # Build lookup: existing dates per stock
    existing_dates = {}
    for code, recs in cache.items():
        existing_dates[code] = set(r['date'] for r in recs)
    
    # 2. Fetch by trade date
    total_new = 0
    total_updated_stocks = set()
    actual_trading_days = []
    
    print(f"\n[2] Fetching daily data...", flush=True)
    for trade_date in CANDIDATE_DATES:
        try:
            df = pro.daily(trade_date=trade_date)
            if df is None or len(df) == 0:
                print(f"  {trade_date}: No data (holiday?)", flush=True)
                continue
            
            formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
            actual_trading_days.append(formatted_date)
            
            day_new = 0
            day_stocks = 0
            
            for _, r in df.iterrows():
                ts_code = str(r['ts_code'])  # e.g. 600000.SH
                # Convert to cache key format
                parts = ts_code.split('.')
                if len(parts) == 2:
                    code_num = parts[0]
                    market = parts[1]
                    cache_key = f'sh{code_num}' if market == 'SH' else f'sz{code_num}'
                else:
                    continue
                
                record = {
                    'date': formatted_date,
                    'open': float(r['open']),
                    'high': float(r['high']),
                    'low': float(r['low']),
                    'close': float(r['close']),
                    'volume': float(r['vol']),
                }
                
                if cache_key in cache:
                    if formatted_date not in existing_dates[cache_key]:
                        cache[cache_key].append(record)
                        existing_dates[cache_key].add(formatted_date)
                        day_new += 1
                        total_updated_stocks.add(cache_key)
                    day_stocks += 1
                # Stock not in cache, skip (we only update existing)
            
            total_new += day_new
            print(f"  {trade_date}: {len(df)} stocks, {day_new} new records added", flush=True)
            
        except Exception as e:
            print(f"  {trade_date}: FAILED - {e}", flush=True)
            if 'frequency' in str(e).lower() or 'rate' in str(e).lower():
                print(f"  Rate limited! Waiting 70s...", flush=True)
                time.sleep(70)
                # Retry
                try:
                    df = pro.daily(trade_date=trade_date)
                    if df is not None and len(df) > 0:
                        formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                        actual_trading_days.append(formatted_date)
                        day_new = 0
                        for _, r in df.iterrows():
                            ts_code = str(r['ts_code'])
                            parts = ts_code.split('.')
                            if len(parts) == 2:
                                code_num = parts[0]
                                market = parts[1]
                                cache_key = f'sh{code_num}' if market == 'SH' else f'sz{code_num}'
                            else:
                                continue
                            record = {
                                'date': formatted_date,
                                'open': float(r['open']),
                                'high': float(r['high']),
                                'low': float(r['low']),
                                'close': float(r['close']),
                                'volume': float(r['vol']),
                            }
                            if cache_key in cache:
                                if formatted_date not in existing_dates[cache_key]:
                                    cache[cache_key].append(record)
                                    existing_dates[cache_key].add(formatted_date)
                                    day_new += 1
                                    total_updated_stocks.add(cache_key)
                        total_new += day_new
                        print(f"  {trade_date} (retry): {len(df)} stocks, {day_new} new records", flush=True)
                except Exception as e2:
                    print(f"  {trade_date} (retry): FAILED - {e2}", flush=True)
        
        # Rate limit: wait between calls
        time.sleep(3)
    
    # 3. Sort all records by date
    print(f"\n[3] Sorting records...", flush=True)
    for code in cache:
        cache[code].sort(key=lambda x: x['date'])
    
    # 4. Save
    print(f"\n[4] Saving...", flush=True)
    with open(LATEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    elapsed = time.time() - t0
    
    print(f"\n{'='*60}")
    print(f"  DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Cache: {sz:.1f}MB, {len(cache)} stocks")
    print(f"  Trading days found: {actual_trading_days}")
    print(f"  Stocks updated: {len(total_updated_stocks)}")
    print(f"  New records: {total_new}")
    print(f"{'='*60}")
    
    # 5. Verify
    print("\n[5] Verification:")
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

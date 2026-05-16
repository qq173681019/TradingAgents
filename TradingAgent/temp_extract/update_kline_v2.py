"""
更新K线缓存 - 简化版
直接用现有缓存的股票列表，逐个获取增量数据
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

# Patch requests
import requests
_orig_send = requests.Session.send
def _no_proxy_send(self, *a, **kw):
    self.trust_env = False
    return _orig_send(self, *a, **kw)
requests.Session.send = _no_proxy_send

import akshare as ak

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')
START_DATE = '20260425'
END_DATE = time.strftime('%Y%m%d')

def main():
    print("Loading existing cache...")
    with open(LATEST_FILE, 'r') as f:
        cache = json.load(f)
    print(f"  {len(cache)} stocks loaded")
    
    # Convert code format: sh600000 -> 600000, sz000001 -> 000001
    codes = []
    for code in list(cache.keys()):
        if code.startswith('sh') or code.startswith('sz'):
            codes.append(code[2:])
        else:
            codes.append(code)
    
    print(f"Updating {len(codes)} stocks from {START_DATE} to {END_DATE}...")
    
    updated = 0
    failed = 0
    new_records_total = 0
    
    for i, code in enumerate(codes):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=START_DATE,
                end_date=END_DATE,
                adjust="qfq"
            )
            if df is not None and len(df) > 0:
                # Convert to our format
                new_records = []
                for _, row in df.iterrows():
                    new_records.append({
                        'date': str(row['日期'])[:10],
                        'open': float(row['开盘']),
                        'high': float(row['最高']),
                        'low': float(row['最低']),
                        'close': float(row['收盘']),
                        'volume': float(row['成交量']),
                    })
                
                # Merge with existing
                key = f'sh{code}' if code.startswith('6') else f'sz{code}'
                if key not in cache:
                    key = code  # fallback
                
                if key in cache:
                    existing_dates = set(r['date'] for r in cache[key])
                    added = 0
                    for r in new_records:
                        if r['date'] not in existing_dates:
                            cache[key].append(r)
                            added += 1
                    if added > 0:
                        cache[key].sort(key=lambda x: x['date'])
                        new_records_total += added
                    updated += 1
                else:
                    cache[key] = new_records
                    new_records_total += len(new_records)
                    updated += 1
                    
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  FAILED {code}: {e}")
        
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{len(codes)} ({(i+1)*100//len(codes)}%), updated={updated}, failed={failed}, new_records={new_records_total}")
            # Intermediate save
            with open(LATEST_FILE, 'w') as f:
                json.dump(cache, f)
            print(f"  Intermediate save done")
        
        time.sleep(0.3)  # Rate limit
    
    # Final save
    print(f"\nFinal save...")
    with open(LATEST_FILE, 'w') as f:
        json.dump(cache, f)
    
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    print(f"Done! {sz:.1f}MB, {len(cache)} stocks, {updated} updated, {failed} failed, {new_records_total} new records")
    
    # Verify
    sample = list(cache.keys())[:3]
    for k in sample:
        records = cache[k]
        print(f"  {k}: {records[0]['date']} ~ {records[-1]['date']}, {len(records)} days")

if __name__ == '__main__':
    main()

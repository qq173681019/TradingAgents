#!/usr/bin/env python3
"""Full A-share K-line fetcher via Sina API - Resume support"""
import os, json, time, sys, glob

# Disable proxy
for k in ['HTTP_PROXY','http_proxy','HTTPS_PROXY','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

import urllib.request

KLINE_CACHE = os.path.join(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache')
os.makedirs(KLINE_CACHE, exist_ok=True)

START = '20251001'
END = '20260425'
OUTPUT = os.path.join(KLINE_CACHE, f'kline_full_{START}_{END}.json')
BATCH_FILE = os.path.join(KLINE_CACHE, f'kline_full_{START}_{END}.batch.json')

def fetch_stock_sina(symbol, datalen=300):
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={datalen}"
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    try:
        resp = opener.open(req, timeout=15)
        text = resp.read().decode('utf-8')
        if not text or text.startswith('null') or len(text) < 10:
            return []
        data = json.loads(text)
        records = []
        for item in data:
            d = item.get('day', '')
            if d >= START and d <= END:
                records.append({
                    'date': d,
                    'open': float(item.get('open', 0)),
                    'high': float(item.get('high', 0)),
                    'low': float(item.get('low', 0)),
                    'close': float(item.get('close', 0)),
                    'volume': float(item.get('volume', 0)),
                })
        return records
    except:
        return []

def fetch_index_sina(symbol='sh000001', datalen=300):
    return fetch_stock_sina(symbol, datalen=datalen)

if __name__ == '__main__':
    sys.stdout.reconfigure(line_buffering=True)
    
    print("=" * 60)
    print("Sina API K-line Fetcher (Resume Support)")
    print(f"Range: {START} ~ {END}")
    print("=" * 60)
    
    # Generate stock list
    stock_list = []
    for prefix in ['sh600', 'sh601', 'sh602', 'sh603', 'sh605',
                    'sz000', 'sz001', 'sz002', 'sz003']:
        for i in range(1000):
            stock_list.append(f"{prefix}{i:03d}")
    print(f"Total stocks to scan: {len(stock_list)}")
    
    # Load existing data (resume)
    all_data = {}
    start_idx = 0
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
            print(f"Loaded existing data: {len(all_data)} stocks")
        except:
            pass
    
    if os.path.exists(BATCH_FILE):
        try:
            with open(BATCH_FILE, 'r') as f:
                state = json.load(f)
                start_idx = state.get('last_idx', 0) + 1
                print(f"Resuming from index {start_idx}")
        except:
            pass
    
    # Save empty codes that returned nothing
    empty_codes = set()
    if os.path.exists(BATCH_FILE):
        try:
            with open(BATCH_FILE, 'r') as f:
                state = json.load(f)
                empty_codes = set(state.get('empty_codes', []))
        except:
            pass
    
    success = len(all_data)
    empty = len(empty_codes)
    failed = 0
    BATCH_SIZE = 500  # Save every 500 stocks
    last_save = start_idx
    
    print(f"\nStarting from {start_idx}/{len(stock_list)}...")
    print(f"Already have {success} valid stocks, {empty} known-empty")
    
    for i in range(start_idx, len(stock_list)):
        code = stock_list[i]
        
        # Skip known empty
        if code in empty_codes:
            continue
        
        records = fetch_stock_sina(code, datalen=300)
        if len(records) >= 20:
            all_data[code] = records
            success += 1
        else:
            empty_codes.add(code)
            empty += 1
        
        # Save batch progress
        if (i + 1) % 100 == 0:
            elapsed = i - start_idx + 1
            print(f"  [{i+1}/{len(stock_list)}] valid={success} empty={empty} elapsed={elapsed}")
            time.sleep(0.3)
        
        # Save checkpoint every BATCH_SIZE
        if (i + 1) % BATCH_SIZE == 0:
            with open(OUTPUT, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False)
            with open(BATCH_FILE, 'w') as f:
                json.dump({'last_idx': i, 'empty_codes': list(empty_codes)}, f)
            latest = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
            with open(latest, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False)
            sz = os.path.getsize(OUTPUT) / 1024 / 1024
            print(f"  [CHECKPOINT] {len(all_data)} stocks, {sz:.1f} MB")
            time.sleep(1)
    
    # Final save
    print(f"\nFinal save...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    latest = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    
    # Fetch index
    print(f"\nFetching SH index...")
    idx_records = fetch_index_sina('sh000001', datalen=300)
    if idx_records:
        n = len(idx_records)
        index_data = {
            'date': {str(i): idx_records[i]['date'] for i in range(n)},
            'open': {str(i): idx_records[i]['open'] for i in range(n)},
            'high': {str(i): idx_records[i]['high'] for i in range(n)},
            'low': {str(i): idx_records[i]['low'] for i in range(n)},
            'close': {str(i): idx_records[i]['close'] for i in range(n)},
            'volume': {str(i): idx_records[i]['volume'] for i in range(n)},
        }
        idx_file = os.path.join(KLINE_CACHE, f'index_full_{START}_{END}.json')
        with open(idx_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False)
        latest_idx = os.path.join(KLINE_CACHE, 'index_full_latest.json')
        with open(latest_idx, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False)
        print(f"  Index: {len(idx_records)} days ({idx_records[0]['date']} ~ {idx_records[-1]['date']})")
    
    # Cleanup batch file
    if os.path.exists(BATCH_FILE):
        os.remove(BATCH_FILE)
    
    # Verify
    sh = sum(1 for c in all_data if c.startswith('sh'))
    sz_count = sum(1 for c in all_data if c.startswith('sz'))
    lens = [len(v) for v in all_data.values()]
    sz_mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"DONE! {len(all_data)} stocks (SH:{sh} SZ:{sz_count})")
    print(f"Records per stock: min={min(lens)}, max={max(lens)}, avg={sum(lens)//len(lens)}")
    print(f"File: {OUTPUT} ({sz_mb:.1f} MB)")
    print(f"{'='*60}")

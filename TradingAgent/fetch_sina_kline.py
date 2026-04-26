#!/usr/bin/env python3
"""Full A-share K-line fetcher via Sina Finance API"""
import os, json, time, sys
from collections import defaultdict

# Disable proxy
for k in ['HTTP_PROXY','http_proxy','HTTPS_PROXY','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

import urllib.request

KLINE_CACHE = os.path.join(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache')
os.makedirs(KLINE_CACHE, exist_ok=True)

START = '20251001'
END = '20260425'

def fetch_stock_sina(symbol, scale=240, datalen=200):
    """Fetch stock K-line from Sina.
    symbol: sh600519, sz000001 etc.
    scale: 240=daily
    datalen: number of records to fetch (max ~800)
    """
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    try:
        resp = opener.open(req, timeout=15)
        text = resp.read().decode('utf-8')
        if not text or text.startswith('null') or len(text) < 10:
            return []
        import json as j
        data = j.loads(text)
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
    except Exception as e:
        return []

def fetch_index_sina(symbol='sh000001', datalen=200):
    """Fetch index K-line"""
    return fetch_stock_sina(symbol, scale=240, datalen=datalen)

if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(line_buffering=True)
    print("=" * 60)
    print("Sina API K-line Fetcher")
    print(f"Range: {START} ~ {END}")
    print("=" * 60)
    
    # Generate stock list: main board SH600xxx, SH601xxx, SH603xxx, SH605xxx
    # + SZ000xxx, SZ001xxx, SZ002xxx, SZ003xxx
    stock_list = []
    for prefix in ['sh600', 'sh601', 'sh602', 'sh603', 'sh605',
                    'sz000', 'sz001', 'sz002', 'sz003']:
        for i in range(1000):
            stock_list.append(f"{prefix}{i:03d}")
    print(f"\nStocks to scan: {len(stock_list)}")
    
    print(f"\n[1/3] Fetching stock K-line data...")
    all_data = {}
    success = 0
    empty = 0
    
    for i, code in enumerate(stock_list):
        records = fetch_stock_sina(code, datalen=300)
        if len(records) >= 20:
            all_data[code] = records
            success += 1
        else:
            empty += 1
        
        if (i + 1) % 200 == 0:
            print(f"  [{i+1}/{len(stock_list)}] valid={success}, empty={empty}")
            time.sleep(0.5)  # Be polite
    
    print(f"  Done: {success} stocks, {empty} empty/suspended")
    
    # 2. Fetch index
    print(f"\n[2/3] Fetching SH index...")
    idx_records = fetch_index_sina('sh000001', datalen=300)
    if idx_records:
        print(f"  Index: {len(idx_records)} days ({idx_records[0]['date']} ~ {idx_records[-1]['date']})")
    else:
        print("  Index: EMPTY!")
    
    # 3. Save
    print(f"\n[3/3] Saving...")
    kline_file = os.path.join(KLINE_CACHE, f'kline_full_{START}_{END}.json')
    with open(kline_file, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    size_mb = os.path.getsize(kline_file) / 1024 / 1024
    print(f"  K-line: {kline_file} ({size_mb:.1f} MB, {len(all_data)} stocks)")
    
    latest = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    
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
        print(f"  Index: saved")
    
    # Verify
    sh = sum(1 for c in all_data if c.startswith('sh'))
    sz = sum(1 for c in all_data if c.startswith('sz'))
    lens = [len(v) for v in all_data.values()]
    print(f"\nVerify: {len(all_data)} stocks (SH:{sh} SZ:{sz})")
    print(f"Records per stock: min={min(lens)}, max={max(lens)}, avg={sum(lens)//len(lens)}")
    print(f"Done!")

#!/usr/bin/env python3
"""Fetch stock data via Tencent API (no proxy issues)"""
import os
for k in ['HTTP_PROXY','http_proxy','HTTPS_PROXY','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

import json, time, urllib.request
from collections import defaultdict

KLINE_CACHE = os.path.join(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache')
os.makedirs(KLINE_CACHE, exist_ok=True)

# Use Tencent API - no auth needed, no proxy issues
# qfq daily: https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,1,qfq

def fetch_stock_kline_tencent(code, start='20251001', end='20260425'):
    """Fetch single stock K-line via Tencent API.
    code: like 'sh600519' or 'sz000001'
    """
    # Tencent API format
    market = code[:2]  # sh or sz
    stock_num = code[2:]
    param = f"{market}{stock_num},day,{start},{end},1,qfq"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={param}"
    
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', 'https://gu.qq.com/')
    
    try:
        resp = opener.open(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        day_data = data.get('data', {})
        for market_key, qfq_data in day_data.items():
            if qfq_data and 'day' in qfq_data and qfq_data['day']:
                klines = qfq_data['day']
                records = []
                for line in klines:
                    parts = line.split(',')
                    if len(parts) >= 6:
                        records.append({
                            'date': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5]),
                        })
                return records
    except Exception as e:
        pass
    return None

def fetch_index_tencent(code='sh000001', start='20251001', end='20260425'):
    """Fetch index K-line via Tencent API"""
    market = code[:2]
    stock_num = code[2:]
    param = f"{market}{stock_num},day,{start},{end},1,"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={param}&_var=kline_dayqfq{code}"
    
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    try:
        resp = opener.open(req, timeout=15)
        text = resp.read().decode('utf-8')
        # Remove JSONP prefix
        if text.startswith('kline_dayqfq'):
            text = text.split('=', 1)[1].strip()
        data = json.loads(text)
        for market_key, kline_data in data.get('data', {}).items():
            if kline_data and 'qfqday' in kline_data:
                klines = kline_data['qfqday']
                records = []
                for line in klines:
                    parts = line.split(',')
                    if len(parts) >= 6:
                        records.append({
                            'date': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5]),
                        })
                return records
    except Exception as e:
        print(f"  Index fetch failed: {e}")
    return None

# Get all A-share stock list via Tencent
def get_stock_list():
    """Get stock list - use a known list of SH+SZ stocks"""
    # Fetch from Tencent
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/rank/rankKline/getRankKline?type=1&market=0&order=1&sort=3&begin=0&count=6000"
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    try:
        resp = opener.open(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        stocks = []
        for item in data.get('data', {}).get('rank', []):
            code = item.get('code', '')
            market = item.get('market', '')
            if code:
                stocks.append(f"{market}{code}")
        return stocks
    except:
        pass
    
    # Fallback: use SH600000-SH605000 + SZ000001-SZ005000 ranges (roughly covers main board)
    stocks = []
    for prefix in ['sh600', 'sh601', 'sh602', 'sh603', 'sh605', 'sz000', 'sz001', 'sz002', 'sz003']:
        for i in range(1000):
            code = f"{prefix}{i:03d}"
            stocks.append(code)
    return stocks


if __name__ == '__main__':
    START = '20251001'
    END = '20260425'
    
    print("=" * 60)
    print("Full A-share K-line fetcher (Tencent API)")
    print(f"Range: {START} ~ {END}")
    print("=" * 60)
    
    # 1. Get stock list
    print("\n[1/3] Getting stock list...")
    stock_list = get_stock_list()
    print(f"  Total stocks to fetch: {len(stock_list)}")
    
    if len(stock_list) > 5000:
        stock_list = stock_list[:5000]
        print(f"  Limited to: {len(stock_list)}")
    
    # 2. Fetch K-line for each stock
    print(f"\n[2/3] Fetching K-line data...")
    all_data = {}
    success = 0
    failed = 0
    empty = 0
    
    for i, code in enumerate(stock_list):
        records = fetch_stock_kline_tencent(code, START, END)
        if records and len(records) >= 20:
            all_data[code] = records
            success += 1
        elif records:
            empty += 1
        else:
            failed += 1
        
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{len(stock_list)} (success={success}, empty={empty}, failed={failed})")
            time.sleep(1)  # Rate limit
    
    print(f"  Done: {success} stocks with data, {empty} empty, {failed} failed")
    
    # 3. Fetch index
    print(f"\n[3/3] Fetching index data...")
    idx_records = fetch_index_tencent('sh000001', START, END)
    if idx_records:
        print(f"  Index: {len(idx_records)} days ({idx_records[0]['date']} ~ {idx_records[-1]['date']})")
    
    # 4. Save
    import pandas as pd
    
    # Save kline
    kline_file = os.path.join(KLINE_CACHE, f'kline_full_{START}_{END}.json')
    with open(kline_file, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    size_mb = os.path.getsize(kline_file) / 1024 / 1024
    print(f"\n  K-line saved: {kline_file} ({size_mb:.1f} MB)")
    
    latest = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)
    print(f"  Latest: {latest}")
    
    # Save index in backtest format
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
        print(f"  Index saved: {idx_file}")
    
    print(f"\nDone!")

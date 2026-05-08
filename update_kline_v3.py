#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线缓存快速增量更新 v3
优化：跳过已更新的股票、减少延迟
"""
import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import os
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]

import urllib.request
urllib.request.getproxies = lambda: {}

import requests
import json
import time
from datetime import datetime, timedelta

DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
INDEX_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_FILE = os.path.join(DATA_DIR, 'kline_full_latest.json')
INDEX_FILE = os.path.join(INDEX_DIR, 'index_shanghai_full.json')
STATUS_FILE = os.path.join(INDEX_DIR, 'kline_update_status.json')

END_DATE = datetime.now().strftime('%Y-%m-%d')
BATCH_SIZE = 50
SLEEP_REQ = 0.05  # Very short sleep between requests
SLEEP_BATCH = 0.3  # Short sleep between batches
SAVE_EVERY = 10
TARGET_DATE = '2026-05-06'  # Only update stocks before this date


def create_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://stockapp.finance.qq.com/'
    })
    return session


def convert_code(code):
    pure = code.split('.')[0] if '.' in code else code
    if pure.startswith('6'):
        return f'sh{pure}'
    elif pure.startswith(('0', '3')):
        return f'sz{pure}'
    return f'sz{pure}'


def fetch_kline(session, code, start_date):
    tc = convert_code(code)
    try:
        url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
        params = {
            '_var': 'kline_day',
            'param': f'{tc},day,{start_date},{END_DATE},320,qfq',
            'r': str(time.time())
        }
        resp = session.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        
        text = resp.text
        if '=' in text:
            text = text.split('=', 1)[1].strip()
        if text.endswith(';'):
            text = text[:-1]
        
        data = json.loads(text)
        if data.get('code') != 0:
            return None
        
        sd = data.get('data', {}).get(tc, {})
        klines = sd.get('qfqday', []) or sd.get('day', [])
        if not klines:
            return None
        
        result = []
        for row in klines:
            if len(row) < 6:
                continue
            try:
                result.append({
                    'date': row[0],
                    'open': float(row[1]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[2]),
                    'volume': float(row[5]),
                })
            except (ValueError, IndexError):
                continue
        return result if result else None
    except Exception:
        return None


def main():
    print(f'[v3] K线快速增量更新', flush=True)
    print(f'目标日期: {TARGET_DATE}', flush=True)
    
    # Load
    t = time.time()
    with open(KLINE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f'[INFO] 加载完成: {len(data)} 只 ({time.time()-t:.1f}s)', flush=True)
    
    # Filter stocks that need update
    codes_to_update = []
    for code, klines in data.items():
        if isinstance(klines, list) and len(klines) > 0:
            last_date = klines[-1].get('date', '')
            if last_date < TARGET_DATE:
                codes_to_update.append((code, last_date))
    
    print(f'[INFO] 需更新: {len(codes_to_update)} 只', flush=True)
    
    if not codes_to_update:
        print('[INFO] 所有股票已是最新!', flush=True)
        return
    
    session = create_session()
    updated = 0
    failed = 0
    total = len(codes_to_update)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    start_time = time.time()
    
    for batch_idx in range(total_batches):
        bs_idx = batch_idx * BATCH_SIZE
        be_idx = min(bs_idx + BATCH_SIZE, total)
        batch = codes_to_update[bs_idx:be_idx]
        
        batch_updated = 0
        for code, last_date in batch:
            fetch_start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
            
            new_rows = fetch_kline(session, code, fetch_start)
            
            if new_rows:
                existing = data[code]
                existing_dates = {r.get('date') for r in existing}
                added = 0
                for row in new_rows:
                    if row['date'] not in existing_dates:
                        existing.append(row)
                        added += 1
                if added > 0:
                    existing.sort(key=lambda x: x.get('date', ''))
                    data[code] = existing
                    updated += 1
                    batch_updated += 1
            
            time.sleep(SLEEP_REQ)
        
        if batch_idx < total_batches - 1:
            time.sleep(SLEEP_BATCH)
        
        elapsed = time.time() - start_time
        pct = (batch_idx + 1) / total_batches * 100
        eta = elapsed / (batch_idx + 1) * (total_batches - batch_idx - 1)
        print(f'[批次 {batch_idx+1}/{total_batches}] {be_idx}/{total} 更新{batch_updated}只 | {pct:.0f}% ETA:{eta:.0f}s', flush=True)
        
        if (batch_idx + 1) % SAVE_EVERY == 0:
            with open(KLINE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print(f'  [已保存]', flush=True)
    
    # Final save
    with open(KLINE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    print(f'\n{"="*50}', flush=True)
    print(f'[完成] 更新{updated}只, 失败{total-updated}只, 耗时{elapsed:.0f}s', flush=True)
    
    # Update index
    print(f'\n[INFO] 更新上证指数...', flush=True)
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        idx = json.load(f)
    
    last_idx_date = idx[-1].get('date', '') if isinstance(idx, list) and idx else ''
    if last_idx_date < END_DATE:
        fetch_start = (datetime.strptime(last_idx_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        rows = fetch_kline(session, 'sh000001', fetch_start)
        if rows:
            existing_dates = {r.get('date') for r in idx}
            for r in rows:
                if r['date'] not in existing_dates:
                    idx.append(r)
            idx.sort(key=lambda x: x.get('date', ''))
            with open(INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(idx, f, ensure_ascii=False)
            print(f'[OK] 指数更新: {idx[-1].get("date")}', flush=True)
    
    # Verify
    print(f'\n[验证]', flush=True)
    date_counts = {}
    for code, klines in data.items():
        if isinstance(klines, list) and klines:
            ld = klines[-1].get('date', '')
            date_counts[ld] = date_counts.get(ld, 0) + 1
    
    for d_str, c in sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:5]:
        print(f'  {d_str}: {c} 只', flush=True)
    
    # Status
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'last_update_date': END_DATE,
            'last_update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'update_type': 'incremental_tencent_http_v3',
            'total_stocks': len(data),
            'updated_stocks': updated,
            'data_source': 'tencent_http'
        }, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

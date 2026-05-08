#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线缓存增量更新脚本 v2
使用腾讯HTTP API（绕过HTTPS代理问题）
从 2026-04-25 补全到最新日期
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

# ===== 关键：在所有网络相关import之前禁用代理 =====
for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import urllib.request
urllib.request.getproxies = lambda: {}

import requests

# ===== 路径配置 =====
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
INDEX_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_FILE = os.path.join(DATA_DIR, 'kline_full_latest.json')
INDEX_FILE = os.path.join(INDEX_DIR, 'index_shanghai_full.json')
STATUS_FILE = os.path.join(INDEX_DIR, 'kline_update_status.json')

# ===== 参数 =====
START_DATE = '2026-04-20'  # 多取几天确保衔接
END_DATE = datetime.now().strftime('%Y-%m-%d')
BATCH_SIZE = 30  # 每批30只，避免限流
SLEEP_BETWEEN_REQUESTS = 0.12
SLEEP_BETWEEN_BATCHES = 1.0
MAX_RETRIES = 2
SAVE_EVERY_N_BATCHES = 5


def create_session():
    """创建无代理的HTTP session"""
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://stockapp.finance.qq.com/'
    })
    return session


def convert_code_for_tencent(code: str) -> str:
    """股票代码转腾讯格式"""
    pure = code.split('.')[0] if '.' in code else code
    if pure.startswith('6'):
        return f'sh{pure}'
    elif pure.startswith(('0', '3')):
        return f'sz{pure}'
    else:
        return f'sz{pure}'


def fetch_kline_tencent(session, code: str, start_date: str, end_date: str):
    """从腾讯API获取单只股票K线，返回统一格式列表"""
    tencent_code = convert_code_for_tencent(code)
    
    for attempt in range(MAX_RETRIES):
        try:
            url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
            params = {
                '_var': 'kline_day',
                'param': f'{tencent_code},day,{start_date},{end_date},320,qfq',
                'r': str(time.time())
            }
            
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                continue
            
            text = resp.text
            if '=' in text:
                text = text.split('=', 1)[1].strip()
            if text.endswith(';'):
                text = text[:-1]
            
            data = json.loads(text)
            if data.get('code') != 0:
                continue
            
            stock_data = data.get('data', {}).get(tencent_code, {})
            # Try multiple possible keys
            klines = None
            for key in ['qfqday', 'day', 'kline']:
                if key in stock_data and stock_data[key]:
                    klines = stock_data[key]
                    break
            
            if not klines:
                return None
            
            # 转换为统一格式: {date, open, high, low, close, volume}
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
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)
            continue
    
    return None


def load_kline_cache():
    """加载现有K线缓存"""
    print(f'[INFO] 加载K线缓存: {KLINE_FILE}')
    with open(KLINE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f'[INFO] 已加载 {len(data)} 只股票')
    
    # 检查日期范围
    sample_code = list(data.keys())[0]
    sample = data[sample_code]
    if isinstance(sample, list) and len(sample) > 0:
        last_date = sample[-1].get('date', '未知')
        first_date = sample[0].get('date', '未知')
        print(f'[INFO] 示例 {sample_code}: {first_date} ~ {last_date}')
    return data


def update_kline_data():
    """增量更新K线数据"""
    data = load_kline_cache()
    codes = list(data.keys())
    total = len(codes)
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    new_record_count = 0
    
    session = create_session()
    start_time = time.time()
    
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f'\n[INFO] 开始更新，共 {total} 只股票，分 {total_batches} 批')
    print(f'[INFO] 日期范围: {START_DATE} ~ {END_DATE}')
    
    for batch_idx in range(total_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_codes = codes[batch_start:batch_end]
        
        print(f'\n[批次 {batch_idx+1}/{total_batches}] 股票 {batch_start+1}-{batch_end}/{total}')
        
        for i, code in enumerate(batch_codes):
            try:
                existing = data[code]
                if isinstance(existing, list) and len(existing) > 0:
                    last_date = existing[-1].get('date', '')
                    if last_date >= END_DATE:
                        skipped_count += 1
                        continue
                    
                    if last_date >= START_DATE:
                        fetch_start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                    else:
                        fetch_start = START_DATE
                else:
                    fetch_start = START_DATE
                
                new_rows = fetch_kline_tencent(session, code, fetch_start, END_DATE)
                
                if new_rows:
                    existing_dates = set()
                    if isinstance(existing, list):
                        existing_dates = {r.get('date') for r in existing}
                    
                    added = 0
                    for row in new_rows:
                        if row['date'] not in existing_dates:
                            existing.append(row)
                            added += 1
                    
                    if added > 0:
                        existing.sort(key=lambda x: x.get('date', ''))
                        data[code] = existing
                        updated_count += 1
                        new_record_count += added
                    else:
                        skipped_count += 1
                else:
                    failed_count += 1
                
            except Exception:
                failed_count += 1
                continue
            
            # 请求间休息
            time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        # 批次间休息
        if batch_idx < total_batches - 1:
            time.sleep(SLEEP_BETWEEN_BATCHES)
        
        # 定期保存
        if (batch_idx + 1) % SAVE_EVERY_N_BATCHES == 0 or batch_idx == total_batches - 1:
            print(f'[INFO] 保存中间进度 ({batch_idx+1}/{total_batches} 批)...')
            with open(KLINE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    
    print(f'\n{"="*60}')
    print(f'[完成] K线数据更新')
    print(f'  总股票数: {total}')
    print(f'  更新成功: {updated_count} (新增 {new_record_count} 条记录)')
    print(f'  已是最新: {skipped_count}')
    print(f'  获取失败: {failed_count}')
    print(f'  耗时: {elapsed:.1f}秒')
    print(f'{"="*60}')
    
    return True


def update_index_data():
    """更新上证指数数据"""
    print(f'\n[INFO] 更新上证指数数据...')
    
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    if isinstance(index_data, list) and len(index_data) > 0:
        last_date = index_data[-1].get('date', '')
        print(f'[INFO] 当前指数: {index_data[0].get("date")} ~ {last_date}, {len(index_data)} 条')
        
        if last_date >= END_DATE:
            print(f'[INFO] 指数已是最新')
            return True
        
        fetch_start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        fetch_start = START_DATE
    
    session = create_session()
    
    # 腾讯API获取指数 - 上证指数代码 sh000001
    tencent_code = 'sh000001'
    
    for attempt in range(MAX_RETRIES):
        try:
            url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
            params = {
                '_var': 'kline_day',
                'param': f'{tencent_code},day,{fetch_start},{END_DATE},320,qfq',
                'r': str(time.time())
            }
            
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                continue
            
            text = resp.text
            if '=' in text:
                text = text.split('=', 1)[1].strip()
            if text.endswith(';'):
                text = text[:-1]
            
            data = json.loads(text)
            if data.get('code') != 0:
                continue
            
            stock_data = data.get('data', {}).get(tencent_code, {})
            klines = stock_data.get('qfqday', []) or stock_data.get('day', [])
            
            if klines:
                existing_dates = {r.get('date') for r in index_data}
                added = 0
                for row in klines:
                    if len(row) < 6:
                        continue
                    try:
                        record = {
                            'date': row[0],
                            'open': float(row[1]),
                            'high': float(row[3]),
                            'low': float(row[4]),
                            'close': float(row[2]),
                            'volume': float(row[5]),
                        }
                        if record['date'] not in existing_dates:
                            index_data.append(record)
                            added += 1
                    except (ValueError, IndexError):
                        continue
                
                if added > 0:
                    index_data.sort(key=lambda x: x.get('date', ''))
                    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
                        json.dump(index_data, f, ensure_ascii=False)
                    print(f'[OK] 指数新增 {added} 条: {index_data[-1].get("date") if index_data else "?"}')
                else:
                    print(f'[INFO] 指数无新数据')
            else:
                print(f'[WARN] 指数API返回空数据')
            
            return True
            
        except Exception as e:
            print(f'[WARN] 指数更新尝试 {attempt+1} 失败: {e}')
            time.sleep(1)
    
    print(f'[ERROR] 指数更新失败')
    return False


def verify_data():
    """验证更新后的数据"""
    print(f'\n[验证] 检查更新结果...')
    
    with open(KLINE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    date_counts = {}
    min_date = None
    max_date = None
    
    for code, klines in data.items():
        if isinstance(klines, list) and len(klines) > 0:
            first_d = klines[0].get('date', '')
            last_d = klines[-1].get('date', '')
            if not min_date or first_d < min_date:
                min_date = first_d
            if not max_date or last_d > max_date:
                max_date = last_d
            date_counts[last_d] = date_counts.get(last_d, 0) + 1
    
    print(f'  股票总数: {total}')
    print(f'  数据范围: {min_date} ~ {max_date}')
    print(f'  最新日期分布 (Top 5):')
    for d, c in sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:5]:
        pct = c / total * 100
        print(f'    {d}: {c} 只 ({pct:.1f}%)')
    
    # 验证指数
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    if isinstance(index_data, list) and len(index_data) > 0:
        print(f'  上证指数: {index_data[0].get("date")} ~ {index_data[-1].get("date")}, {len(index_data)} 条')
    
    # 更新状态文件
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'last_update_date': END_DATE,
            'last_update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'update_type': 'incremental_tencent_http',
            'total_stocks': total,
            'data_range': f'{min_date} ~ {max_date}',
            'data_source': 'tencent_http'
        }, f, ensure_ascii=False, indent=2)
    print(f'  状态文件已更新')


if __name__ == '__main__':
    print(f'K线缓存增量更新 v2 (腾讯HTTP API)')
    print(f'日期范围: {START_DATE} ~ {END_DATE}')
    print(f'{"="*60}')
    
    ok = update_kline_data()
    if ok:
        update_index_data()
        verify_data()
    else:
        print('[ERROR] 更新失败')
        sys.exit(1)

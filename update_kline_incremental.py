#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线缓存增量更新脚本
从 2026-04-25 补全到最新日期
数据源：BaoStock（免费稳定）
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

# 禁用代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

import baostock as bs
import pandas as pd

# 路径配置
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
INDEX_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_FILE = os.path.join(DATA_DIR, 'kline_full_latest.json')
INDEX_FILE = os.path.join(INDEX_DIR, 'index_shanghai_full.json')

# 更新参数
START_DATE = '2026-04-20'  # 多取几天确保衔接
END_DATE = datetime.now().strftime('%Y-%m-%d')
BATCH_SIZE = 50  # 每批50只
SLEEP_BETWEEN = 0.15  # 批次间休息


def format_code_for_baostock(code: str) -> str:
    """将 sh600000 格式转为 sh.600000"""
    if '.' in code:
        return code
    if code.startswith('6'):
        return f'sh.{code}'
    elif code.startswith(('0', '3')):
        return f'sz.{code}'
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


def fetch_kline_baostock(code: str, start_date: str, end_date: str):
    """从BaoStock获取单只股票K线"""
    bs_code = format_code_for_baostock(code)
    if not bs_code:
        return None
    
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            fields="date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
        )
        
        if rs.error_code != '0':
            return None
        
        rows = []
        while rs.next():
            row = rs.get_row_data()
            if len(row) >= 6 and row[0]:  # 确保有数据
                try:
                    rows.append({
                        'date': row[0],
                        'open': float(row[1]) if row[1] else 0,
                        'high': float(row[2]) if row[2] else 0,
                        'low': float(row[3]) if row[3] else 0,
                        'close': float(row[4]) if row[4] else 0,
                        'volume': float(row[5]) if row[5] else 0,
                    })
                except (ValueError, IndexError):
                    continue
        
        return rows if rows else None
    except Exception as e:
        return None


def update_kline_data():
    """更新K线数据"""
    # 加载现有数据
    data = load_kline_cache()
    codes = list(data.keys())
    total = len(codes)
    
    # 统计需要更新的股票
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
    # 连接BaoStock
    print(f'\n[INFO] 连接BaoStock...')
    lg = bs.login()
    if lg.error_code != '0':
        print(f'[ERROR] BaoStock登录失败: {lg.error_msg}')
        return False
    print(f'[INFO] BaoStock登录成功')
    
    start_time = time.time()
    
    try:
        # 分批处理
        for batch_start in range(0, total, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total)
            batch_codes = codes[batch_start:batch_end]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f'\n[批次 {batch_num}/{total_batches}] 处理 {len(batch_codes)} 只股票 ({batch_start+1}-{batch_end}/{total})')
            
            for code in batch_codes:
                try:
                    # 获取已有数据最后日期
                    existing = data[code]
                    if isinstance(existing, list) and len(existing) > 0:
                        last_date = existing[-1].get('date', '')
                        # 如果最后日期 >= END_DATE，跳过
                        if last_date >= END_DATE:
                            skipped_count += 1
                            continue
                        # 从最后日期的下一天开始获取
                        if last_date >= START_DATE:
                            fetch_start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                        else:
                            fetch_start = START_DATE
                    else:
                        fetch_start = START_DATE
                    
                    # 获取新数据
                    new_rows = fetch_kline_baostock(code, fetch_start, END_DATE)
                    
                    if new_rows:
                        # 合并数据：去重（基于日期）
                        existing_dates = set()
                        if isinstance(existing, list):
                            existing_dates = {r.get('date') for r in existing}
                        
                        new_count = 0
                        for row in new_rows:
                            if row['date'] not in existing_dates:
                                existing.append(row)
                                new_count += 1
                        
                        if new_count > 0:
                            # 按日期排序
                            existing.sort(key=lambda x: x.get('date', ''))
                            data[code] = existing
                            updated_count += 1
                        else:
                            skipped_count += 1
                    else:
                        failed_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    continue
            
            # 批次间休息
            if batch_end < total:
                time.sleep(SLEEP_BETWEEN)
            
            # 每5批保存一次（防止中断丢失）
            if batch_num % 5 == 0:
                print(f'[INFO] 保存中间结果 (第{batch_num}批)...')
                with open(KLINE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
        
        # 最终保存
        print(f'\n[INFO] 保存最终结果...')
        with open(KLINE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        
        elapsed = time.time() - start_time
        print(f'\n{"="*60}')
        print(f'[完成] K线数据更新')
        print(f'  总股票数: {total}')
        print(f'  更新成功: {updated_count}')
        print(f'  已是最新: {skipped_count}')
        print(f'  获取失败: {failed_count}')
        print(f'  耗时: {elapsed:.1f}秒')
        print(f'{"="*60}')
        
        return True
        
    finally:
        bs.logout()


def update_index_data():
    """更新上证指数数据"""
    print(f'\n[INFO] 更新上证指数数据...')
    
    # 加载现有数据
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    if isinstance(index_data, list) and len(index_data) > 0:
        last_date = index_data[-1].get('date', '')
        print(f'[INFO] 当前指数数据: {index_data[0].get("date")} ~ {last_date}, 共 {len(index_data)} 条')
        
        if last_date >= END_DATE:
            print(f'[INFO] 指数数据已是最新')
            return True
        
        fetch_start = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        fetch_start = START_DATE
    
    # 连接BaoStock获取指数
    lg = bs.login()
    if lg.error_code != '0':
        print(f'[ERROR] BaoStock登录失败: {lg.error_msg}')
        return False
    
    try:
        rs = bs.query_history_k_data_plus(
            'sh.000001',
            fields="date,open,high,low,close,volume",
            start_date=fetch_start,
            end_date=END_DATE,
            frequency="d",
            adjustflag="3"
        )
        
        if rs.error_code != '0':
            print(f'[ERROR] 获取指数数据失败: {rs.error_msg}')
            return False
        
        new_rows = []
        while rs.next():
            row = rs.get_row_data()
            if len(row) >= 6 and row[0]:
                try:
                    new_rows.append({
                        'date': row[0],
                        'open': float(row[1]) if row[1] else 0,
                        'high': float(row[2]) if row[2] else 0,
                        'low': float(row[3]) if row[3] else 0,
                        'close': float(row[4]) if row[4] else 0,
                        'volume': float(row[5]) if row[5] else 0,
                    })
                except (ValueError, IndexError):
                    continue
        
        if new_rows:
            existing_dates = {r.get('date') for r in index_data}
            added = 0
            for row in new_rows:
                if row['date'] not in existing_dates:
                    index_data.append(row)
                    added += 1
            
            index_data.sort(key=lambda x: x.get('date', ''))
            
            with open(INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False)
            
            print(f'[OK] 指数数据更新完成，新增 {added} 条')
            print(f'     新范围: {index_data[0].get("date")} ~ {index_data[-1].get("date")}, 共 {len(index_data)} 条')
        else:
            print(f'[INFO] 无新增指数数据')
        
        return True
        
    finally:
        bs.logout()


def verify_data():
    """验证更新后的数据"""
    print(f'\n[验证] 检查更新结果...')
    
    # 验证K线
    with open(KLINE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    
    # 检查各股票的最后日期分布
    date_counts = {}
    min_dates = []
    max_dates = []
    
    for code, klines in data.items():
        if isinstance(klines, list) and len(klines) > 0:
            first_d = klines[0].get('date', '')
            last_d = klines[-1].get('date', '')
            min_dates.append(first_d)
            max_dates.append(last_d)
            date_counts[last_d] = date_counts.get(last_d, 0) + 1
    
    if min_dates and max_dates:
        min_dates.sort()
        max_dates.sort()
        print(f'  股票总数: {total}')
        print(f'  最早数据: {min_dates[0]}')
        print(f'  最晚数据: {max_dates[-1]}')
        
        # 显示最新日期分布
        print(f'  最新日期分布 (Top 5):')
        sorted_dates = sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:5]
        for d, c in sorted_dates:
            print(f'    {d}: {c} 只')
    
    # 验证指数
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    if isinstance(index_data, list) and len(index_data) > 0:
        print(f'  上证指数: {index_data[0].get("date")} ~ {index_data[-1].get("date")}, 共 {len(index_data)} 条')
    
    # 更新状态文件
    status_file = os.path.join(INDEX_DIR, 'kline_update_status.json')
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump({
            'last_update_date': END_DATE,
            'last_update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'update_type': 'incremental_baostock',
            'total_stocks': total,
            'data_source': 'baostock'
        }, f, ensure_ascii=False, indent=2)
    print(f'  状态文件已更新')


if __name__ == '__main__':
    print(f'K线缓存增量更新')
    print(f'更新范围: {START_DATE} ~ {END_DATE}')
    print(f'{"="*60}')
    
    # 1. 更新K线数据
    ok = update_kline_data()
    
    if ok:
        # 2. 更新指数数据
        update_index_data()
        
        # 3. 验证
        verify_data()
    else:
        print('[ERROR] K线更新失败')
        sys.exit(1)

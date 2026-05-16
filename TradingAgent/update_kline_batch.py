"""
K线批量更新 - 自动检测日期，使用腾讯接口
替代原来硬编码日期的版本，每次运行自动更新到最新
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['NO_PROXY'] = '*'

import requests

SESSION = requests.Session()
SESSION.trust_env = False

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'


def get_latest_trade_date():
    """动态获取最近交易日（跳过周末）"""
    today = datetime.now()
    # 如果是周六，回退到周五；周日回退到周五
    if today.weekday() == 5:  # Saturday
        return (today - timedelta(days=1)).strftime('%Y-%m-%d')
    elif today.weekday() == 6:  # Sunday
        return (today - timedelta(days=2)).strftime('%Y-%m-%d')
    # 工作日但还没收盘(15:00前)，用前一天数据
    if today.hour < 16:
        target = today - timedelta(days=1)
        if target.weekday() == 5:  # Saturday -> Friday
            target = target - timedelta(days=1)
        elif target.weekday() == 6:  # Sunday -> Friday
            target = target - timedelta(days=2)
        return target.strftime('%Y-%m-%d')
    return today.strftime('%Y-%m-%d')


def get_kline_tencent(code, count=10):
    """从腾讯获取K线数据"""
    url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{code},day,,,{count},qfq'}
    
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        
        stock_data = data.get('data', {}).get(code, {})
        klines = stock_data.get('qfqday', []) or stock_data.get('day', [])
        
        records = []
        for k in klines:
            try:
                records.append({
                    'date': k[0],
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]),
                })
            except (IndexError, ValueError, TypeError):
                continue
        return records
    except Exception:
        return []


def main():
    target_date = get_latest_trade_date()
    
    print("=" * 60)
    print("K线批量更新 (腾讯接口)")
    print(f"目标日期: {target_date}")
    print("=" * 60)

    # 加载缓存
    if not os.path.exists(CACHE_PATH):
        print(f"[错误] 缓存文件不存在: {CACHE_PATH}")
        sys.exit(1)
        
    print("\n[1] 加载现有缓存...")
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"  缓存中共 {len(cache)} 只股票")

    # 找出需要更新的
    needs_update = []
    for code in cache:
        records = cache[code]
        if not records:
            needs_update.append(code)
            continue
        last_date = records[-1].get('date', '')
        if last_date < target_date:
            needs_update.append(code)

    print(f"  需要更新: {len(needs_update)} 只股票")

    if not needs_update:
        print("\n所有股票已是最新！无需更新。")
        return

    # 批量获取
    KLINE_COUNT = 15  # 多取几条确保覆盖
    SAVE_INTERVAL = 300
    DELAY = 0.05
    
    total_updated = 0
    total_new_records = 0
    total_failed = 0
    processed = 0
    failed_codes = []

    t0 = time.time()
    
    for code in needs_update:
        klines = get_kline_tencent(code, KLINE_COUNT)
        
        if klines:
            existing = cache[code]
            existing_dates = {r['date'] for r in existing}
            added = 0
            for rec in klines:
                if rec['date'] not in existing_dates:
                    existing.append(rec)
                    existing_dates.add(rec['date'])
                    added += 1
            
            if added > 0:
                existing.sort(key=lambda x: x['date'])
                total_new_records += added
            total_updated += 1
        else:
            total_failed += 1
            failed_codes.append(code)
        
        processed += 1
        
        if processed % 200 == 0:
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(needs_update) - processed) / rate if rate > 0 else 0
            print(f"  进度: {processed}/{len(needs_update)} ({processed*100//len(needs_update)}%) | "
                  f"更新: {total_updated} | 失败: {total_failed} | 新增: {total_new_records} | "
                  f"速率: {rate:.0f}/s | ETA: {eta:.0f}s")

        if processed % SAVE_INTERVAL == 0 and processed > 0:
            print(f"  [保存中间结果] 已处理 {processed} 只...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        time.sleep(DELAY)

    # 最终保存
    print(f"\n[2] 保存最终结果...")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"  已保存到: {CACHE_PATH}")

    elapsed = time.time() - t0
    print(f"  耗时: {elapsed:.1f}s")

    # 统计
    print("\n" + "=" * 60)
    print("更新完成！")
    print(f"  更新股票数: {total_updated}")
    print(f"  失败股票数: {total_failed}")
    print(f"  新增记录数: {total_new_records}")
    
    up_to_date = 0
    still_need = 0
    for code in cache:
        if cache[code] and cache[code][-1].get('date', '') >= target_date:
            up_to_date += 1
        else:
            still_need += 1
    print(f"  已到最新日期({target_date}): {up_to_date}")
    print(f"  仍需更新: {still_need}")
    
    if failed_codes[:20]:
        print(f"  失败代码示例: {failed_codes[:20]}")
    print("=" * 60)


if __name__ == '__main__':
    main()

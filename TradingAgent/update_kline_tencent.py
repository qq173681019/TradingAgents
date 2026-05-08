"""
使用腾讯股票接口更新K线缓存
Choice API token过期 + push2his被拦截的备选方案
腾讯接口: web.ifzq.gtimg.cn
格式: [date, open, close, high, low, volume]
"""
import json
import os
import sys
import time
from datetime import datetime

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
TARGET_DATE = '2026-05-06'

import requests


def get_kline_tencent(code, count=10):
    """从腾讯获取K线数据
    
    Args:
        code: sh600000 或 sz000001
        count: 获取最近N条
    
    Returns:
        list of kline records, or empty list
    """
    # 腾讯接口格式: sh600000,day,,,count,qfq
    url = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{code},day,,,{count},qfq'}
    
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        
        stock_data = data.get('data', {}).get(code, {})
        # qfqday = 前复权日线
        klines = stock_data.get('qfqday', [])
        if not klines:
            # 有些股票可能用day
            klines = stock_data.get('day', [])
        
        records = []
        for k in klines:
            # [date, open, close, high, low, volume]
            try:
                rec = {
                    'date': k[0],
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]),
                }
                records.append(rec)
            except (IndexError, ValueError, TypeError):
                continue
        
        return records
    except Exception:
        return []


def main():
    # 禁用代理
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''
    os.environ['NO_PROXY'] = '*'
    
    global SESSION
    SESSION = requests.Session()
    SESSION.trust_env = False
    
    print("=" * 60)
    print("腾讯接口 K线缓存更新")
    print(f"目标日期: {TARGET_DATE}")
    print("=" * 60)

    # ── 1. 加载现有缓存 ──
    print("\n[1] 加载现有缓存...")
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    print(f"  缓存中共 {len(cache)} 只股票")

    # ── 2. 找出需要更新的股票 ──
    needs_update = []
    for code in cache:
        records = cache[code]
        if not records:
            needs_update.append(code)
            continue
        last_date = records[-1].get('date', '')
        if last_date < TARGET_DATE:
            needs_update.append(code)

    print(f"  需要更新: {len(needs_update)} 只股票")

    if not needs_update:
        print("\n所有股票已是最新！无需更新。")
        return

    # ── 3. 批量获取 ──
    # 每只股票获取最近10条日线就够了（覆盖4/25-5/6约6个交易日）
    KLINE_COUNT = 10
    SAVE_INTERVAL = 300
    DELAY = 0.05  # 50ms per request = 20 req/s, should be fine
    
    total_updated = 0
    total_new_records = 0
    total_failed = 0
    processed = 0
    failed_codes = []

    t0 = time.time()
    
    for code in needs_update:
        klines = get_kline_tencent(code, KLINE_COUNT)
        
        if klines:
            # 合并到缓存
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
        
        # 进度输出
        if processed % 200 == 0:
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(needs_update) - processed) / rate if rate > 0 else 0
            print(f"  进度: {processed}/{len(needs_update)} ({processed*100//len(needs_update)}%) | "
                  f"更新: {total_updated} | 失败: {total_failed} | 新增: {total_new_records} | "
                  f"速率: {rate:.0f}/s | ETA: {eta:.0f}s")

        # 中间保存
        if processed % SAVE_INTERVAL == 0 and processed > 0:
            print(f"  [保存中间结果] 已处理 {processed} 只...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        time.sleep(DELAY)

    # ── 4. 最终保存 ──
    print(f"\n[2] 保存最终结果...")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"  已保存到: {CACHE_PATH}")

    elapsed = time.time() - t0
    print(f"  耗时: {elapsed:.1f}s")

    # ── 5. 统计 ──
    print("\n" + "=" * 60)
    print("更新完成！")
    print(f"  更新股票数: {total_updated}")
    print(f"  失败股票数: {total_failed}")
    print(f"  新增记录数: {total_new_records}")
    
    # 验证
    up_to_date = 0
    still_need = 0
    for code in cache:
        if cache[code] and cache[code][-1].get('date', '') >= TARGET_DATE:
            up_to_date += 1
        else:
            still_need += 1
    print(f"  已到最新日期({TARGET_DATE}): {up_to_date}")
    print(f"  仍需更新: {still_need}")
    
    if failed_codes[:20]:
        print(f"  失败代码示例: {failed_codes[:20]}")
    print("=" * 60)


if __name__ == '__main__':
    main()

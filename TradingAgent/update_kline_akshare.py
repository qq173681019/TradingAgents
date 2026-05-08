"""
使用AKShare更新K线缓存（Choice API token过期的备选方案）
批量获取缺失的K线数据并合并到现有缓存
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
TARGET_DATE = '2026-05-06'

import akshare as ak
import pandas as pd


def convert_code_to_akshare(code):
    """sh600000 -> 600000, sz000001 -> 000001
    AKShare uses numeric codes, auto-detects exchange"""
    return code[2:]


def get_kline_batch_akshare(codes, start_date='20260425', end_date='20260506'):
    """批量获取K线数据
    
    AKShare没有真正的批量接口，但可以快速逐个获取
    """
    results = {}
    for code in codes:
        ak_code = convert_code_to_akshare(code)
        try:
            # ak.stock_zh_a_hist - A股历史行情
            df = ak.stock_zh_a_hist(
                symbol=ak_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=""
            )
            if df is not None and not df.empty:
                records = []
                for _, row in df.iterrows():
                    rec = {
                        'date': str(row['日期'])[:10] if hasattr(row, '日期') else str(row.name)[:10],
                        'open': float(row['开盘']) if pd.notna(row['开盘']) else None,
                        'high': float(row['最高']) if pd.notna(row['最高']) else None,
                        'low': float(row['最低']) if pd.notna(row['最低']) else None,
                        'close': float(row['收盘']) if pd.notna(row['收盘']) else None,
                        'volume': float(row['成交量']) if pd.notna(row['成交量']) else None,
                    }
                    if rec['close'] is not None:
                        records.append(rec)
                results[code] = records
        except Exception as e:
            pass  # silently skip errors
    
    return results


def main():
    print("=" * 60)
    print("AKShare K线缓存更新")
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

    # ── 3. 获取每只股票最后日期来确定起始日期 ──
    # 大部分是4月24日之后，用4月25日作为开始
    start_date_ak = '20260425'
    end_date_ak = TARGET_DATE.replace('-', '')

    # ── 4. 批量获取 ──
    print(f"\n[2] 使用AKShare批量获取 ({start_date_ak} ~ {end_date_ak})...")
    
    BATCH_SIZE = 20  # AKShare每批不要太大，避免频率限制
    SAVE_INTERVAL = 200
    DELAY_PER_BATCH = 1.0  # 每批之间延迟1秒
    
    total_updated = 0
    total_new_records = 0
    total_failed = 0
    processed = 0
    failed_codes = []

    for batch_start in range(0, len(needs_update), BATCH_SIZE):
        batch = needs_update[batch_start:batch_start + BATCH_SIZE]
        
        # 逐个获取（AKShare没有批量K线接口）
        results = get_kline_batch_akshare(batch, start_date_ak, end_date_ak)
        
        for code in batch:
            if code in results and results[code]:
                new_records = results[code]
                # 计算起始日期 - 从该股票最后日期的下一天开始
                existing = cache[code]
                existing_dates = {r['date'] for r in existing}
                added = 0
                for rec in new_records:
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

        processed += len(batch)

        # 进度输出
        if processed % 100 == 0 or processed == len(needs_update):
            print(f"  进度: {processed}/{len(needs_update)} ({processed*100//len(needs_update)}%) | 更新: {total_updated} | 失败: {total_failed} | 新增记录: {total_new_records}")

        # 中间保存
        if processed % SAVE_INTERVAL == 0 and processed > 0:
            print(f"  [保存中间结果] 已处理 {processed} 只...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        # 延迟避免频率限制
        time.sleep(DELAY_PER_BATCH)

    # ── 5. 最终保存 ──
    print("\n[3] 保存最终结果...")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"  已保存到: {CACHE_PATH}")

    # ── 6. 统计 ──
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
    print(f"  已到最新日期: {up_to_date}")
    print(f"  仍需更新: {still_need}")
    
    if failed_codes[:10]:
        print(f"  失败代码示例: {failed_codes[:10]}")
    print("=" * 60)


if __name__ == '__main__':
    main()

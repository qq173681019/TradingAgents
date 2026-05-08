"""
使用东方财富Choice API更新K线缓存
批量获取缺失的K线数据并合并到现有缓存
"""
import json
import os
import sys
import time
from datetime import datetime

# ── 路径设置 ──
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared\api')

CACHE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
TARGET_DATE = '2026-05-06'  # 目标最后日期

def convert_code_to_choice(code):
    """sh600000 -> 600000.SH, sz000001 -> 000001.SZ"""
    if code.startswith('sh'):
        return code[2:] + '.SH'
    elif code.startswith('sz'):
        return code[2:] + '.SZ'
    return code

def convert_code_from_choice(code):
    """600000.SH -> sh600000, 000001.SZ -> sz000001"""
    parts = code.split('.')
    if len(parts) == 2:
        return parts[1].lower() + parts[0]
    return code

def main():
    print("=" * 60)
    print("Choice API K线缓存更新")
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
            needs_update.append((code, last_date))

    # 过滤掉已包装的tuple，统一处理
    update_codes = []
    for item in needs_update:
        if isinstance(item, tuple):
            update_codes.append(item[0])
        else:
            update_codes.append(item)

    print(f"  需要更新: {len(update_codes)} 只股票")

    if not update_codes:
        print("\n所有股票已是最新！无需更新。")
        return

    # ── 3. 初始化Choice API ──
    print("\n[2] 初始化Choice API...")
    from get_choice_data import setup_choice_dll_path
    setup_choice_dll_path()
    from EmQuantAPI import c

    print("  正在登录...")
    ret = c.start("ForceLogin=1")
    print(f"  登录结果: ErrorCode={ret.ErrorCode}, Msg={ret.ErrorMsg}")
    if ret.ErrorCode != 0:
        print("  登录失败，退出！")
        return

    # 等待登录完成
    time.sleep(3)

    # ── 4. 检查CSD配额 ──
    print("\n[3] 检查CSD配额...")
    test_data = c.csd("000001.SZ", "CLOSE", "2026-05-06", "2026-05-06", "")
    use_csd = False
    if test_data.ErrorCode == 0:
        print("  [OK] CSD接口可用！")
        use_csd = True
    elif test_data.ErrorCode == 10001012:
        print(f"  [WARN] CSD配额不足 (ErrorCode={test_data.ErrorCode})")
        print("  将使用CSS接口作为备选（仅获取CLOSE数据）")
    else:
        print(f"  [WARN] CSD错误: {test_data.ErrorCode} - {test_data.ErrorMsg}")
        print("  将使用CSS接口作为备选")

    # ── 5. 批量获取数据 ──
    print(f"\n[4] 开始批量获取K线数据...")
    
    BATCH_SIZE = 50
    SAVE_INTERVAL = 500
    
    total_updated = 0
    total_new_records = 0
    total_failed = 0
    processed = 0

    for batch_start in range(0, len(update_codes), BATCH_SIZE):
        batch = update_codes[batch_start:batch_start + BATCH_SIZE]
        choice_codes = ','.join(convert_code_to_choice(code) for code in batch)

        try:
            if use_csd:
                # CSD批量获取OHLCV
                data = c.csd(choice_codes, "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-04-25", TARGET_DATE, "")
                
                if data.ErrorCode != 0:
                    # 可能某些批次有问题，逐个重试
                    print(f"  批次 {batch_start//BATCH_SIZE+1} CSD失败: {data.ErrorCode}, 逐个重试...")
                    for code in batch:
                        try:
                            single_result = _fetch_single_csd(c, code, "2026-04-25", TARGET_DATE)
                            if single_result:
                                new_records = _merge_records(cache[code], single_result)
                                added = len(new_records) - len(cache[code])
                                if added > 0:
                                    cache[code] = new_records
                                    total_new_records += added
                                total_updated += 1
                            else:
                                total_failed += 1
                        except Exception:
                            total_failed += 1
                    processed += len(batch)
                    continue

                dates = data.Dates if hasattr(data, 'Dates') else []
                indicators = data.Indicators if hasattr(data, 'Indicators') else []
                raw_data = data.Data if hasattr(data, 'Data') else {}

                # 解析指标索引
                idx_map = {}
                for i, ind in enumerate(indicators):
                    idx_map[ind] = i

                for code in batch:
                    choice_code = convert_code_to_choice(code)
                    if choice_code in raw_data:
                        stock_arrays = raw_data[choice_code]
                        new_records = []
                        for j, date_str in enumerate(dates):
                            try:
                                rec = {
                                    'date': date_str,
                                    'open': _safe_float(stock_arrays[idx_map.get('OPEN', 0)][j]),
                                    'high': _safe_float(stock_arrays[idx_map.get('HIGH', 1)][j]),
                                    'low': _safe_float(stock_arrays[idx_map.get('LOW', 2)][j]),
                                    'close': _safe_float(stock_arrays[idx_map.get('CLOSE', 3)][j]),
                                    'volume': _safe_float(stock_arrays[idx_map.get('VOLUME', 4)][j]),
                                }
                                # 跳过全为None的记录
                                if rec['close'] is not None:
                                    new_records.append(rec)
                            except (IndexError, TypeError):
                                continue

                        added = _merge_records(cache[code], new_records)
                        total_new_records += added
                        total_updated += 1
                    else:
                        total_failed += 1
            else:
                # CSS备选 - 逐只获取CLOSE数据
                for code in batch:
                    try:
                        choice_code = convert_code_to_choice(code)
                        existing = cache[code]
                        last_date = existing[-1]['date'] if existing else '2026-01-01'
                        # 从最后日期的下一天开始
                        from datetime import datetime, timedelta
                        start_dt = datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)
                        start_date_str = start_dt.strftime('%Y-%m-%d')

                        data = c.css(choice_code, "CLOSE", f"tradeDate={start_date_str}-{TARGET_DATE}")
                        if data.ErrorCode == 0 and choice_code in data.Data:
                            # CSS返回的数据格式不同，需要处理
                            # Data[choice_code] = [close_value]
                            close_val = data.Data[choice_code][0] if data.Data[choice_code] else None
                            if close_val is not None:
                                # CSS不能批量日期，逐日查询太慢
                                # 简化处理：如果只有1天数据
                                new_rec = {
                                    'date': TARGET_DATE,
                                    'close': _safe_float(close_val),
                                }
                                added = _merge_records_partial(cache[code], [new_rec])
                                total_new_records += added
                                total_updated += 1
                            else:
                                total_failed += 1
                        else:
                            total_failed += 1
                        time.sleep(0.05)
                    except Exception as e:
                        total_failed += 1

        except Exception as e:
            print(f"  批次 {batch_start//BATCH_SIZE+1} 异常: {e}")
            total_failed += len(batch)

        processed += len(batch)

        # 进度输出
        if processed % 200 == 0 or processed == len(update_codes):
            print(f"  进度: {processed}/{len(update_codes)} | 更新: {total_updated} | 失败: {total_failed} | 新增记录: {total_new_records}")

        # 中间保存
        if processed % SAVE_INTERVAL == 0:
            print(f"  [保存中间结果] 已处理 {processed} 只...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

    # ── 6. 最终保存 ──
    print("\n[5] 保存最终结果...")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"  已保存到: {CACHE_PATH}")

    # ── 7. 登出 ──
    print("\n[6] 登出Choice API...")
    c.stop()
    print("  已登出")

    # ── 8. 统计 ──
    print("\n" + "=" * 60)
    print("更新完成！")
    print(f"  更新股票数: {total_updated}")
    print(f"  失败股票数: {total_failed}")
    print(f"  新增记录数: {total_new_records}")
    
    # 验证
    still_need = 0
    for code in cache:
        if cache[code] and cache[code][-1].get('date', '') < TARGET_DATE:
            still_need += 1
    print(f"  仍需更新: {still_need}")
    print("=" * 60)


def _safe_float(val):
    """安全转换为float"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _merge_records(existing, new_records):
    """合并新记录到已有记录，返回新增记录数"""
    if not new_records:
        return 0
    
    existing_dates = {r['date'] for r in existing}
    added = 0
    for rec in new_records:
        if rec['date'] not in existing_dates:
            existing.append(rec)
            existing_dates.add(rec['date'])
            added += 1
    
    # 按日期排序
    existing.sort(key=lambda x: x['date'])
    return added


def _merge_records_partial(existing, new_records):
    """合并部分数据（CSS只有CLOSE）"""
    if not new_records:
        return 0
    
    existing_dates = {r['date'] for r in existing}
    added = 0
    for rec in new_records:
        if rec['date'] not in existing_dates:
            existing.append(rec)
            existing_dates.add(rec['date'])
            added += 1
    
    existing.sort(key=lambda x: x['date'])
    return added


def _fetch_single_csd(c, code, start_date, end_date):
    """单只股票CSD获取"""
    choice_code = convert_code_to_choice(code)
    data = c.csd(choice_code, "OPEN,HIGH,LOW,CLOSE,VOLUME", start_date, end_date, "")
    if data.ErrorCode != 0:
        return None
    
    dates = data.Dates if hasattr(data, 'Dates') else []
    indicators = data.Indicators if hasattr(data, 'Indicators') else []
    raw_data = data.Data if hasattr(data, 'Data') else {}
    
    idx_map = {}
    for i, ind in enumerate(indicators):
        idx_map[ind] = i
    
    if choice_code not in raw_data:
        return None
    
    stock_arrays = raw_data[choice_code]
    records = []
    for j, date_str in enumerate(dates):
        try:
            rec = {
                'date': date_str,
                'open': _safe_float(stock_arrays[idx_map.get('OPEN', 0)][j]),
                'high': _safe_float(stock_arrays[idx_map.get('HIGH', 1)][j]),
                'low': _safe_float(stock_arrays[idx_map.get('LOW', 2)][j]),
                'close': _safe_float(stock_arrays[idx_map.get('CLOSE', 3)][j]),
                'volume': _safe_float(stock_arrays[idx_map.get('VOLUME', 4)][j]),
            }
            if rec['close'] is not None:
                records.append(rec)
        except (IndexError, TypeError):
            continue
    
    return records


if __name__ == '__main__':
    main()

"""
K线批量更新 - 优先使用 Choice API，失败自动 fallback 到腾讯接口
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

TRADING_SHARED = r"D:\GitHub\TradingAgents\TradingShared"
API_DIR = os.path.join(TRADING_SHARED, "api")
CACHE_PATH = os.path.join(TRADING_SHARED, 'data', 'kline_cache', 'kline_full_latest.json')


# ============================================================
# 日期工具
# ============================================================

def get_latest_trade_date():
    """动态获取最近交易日（跳过周末）"""
    today = datetime.now()
    if today.weekday() == 5:  # Saturday
        return (today - timedelta(days=1)).strftime('%Y-%m-%d')
    elif today.weekday() == 6:  # Sunday
        return (today - timedelta(days=2)).strftime('%Y-%m-%d')
    if today.hour < 16:
        target = today - timedelta(days=1)
        if target.weekday() == 5:
            target = target - timedelta(days=1)
        elif target.weekday() == 6:
            target = target - timedelta(days=2)
        return target.strftime('%Y-%m-%d')
    return today.strftime('%Y-%m-%d')


# ============================================================
# Choice API 相关
# ============================================================

def init_choice(timeout=30):
    """初始化 Choice SDK，返回 (success, c_module, stop_func)
    使用线程+超时防止 c.start() 阻塞"""
    import threading

    try:
        sys.path.insert(0, TRADING_SHARED)
        sys.path.insert(0, API_DIR)

        from get_choice_data import setup_choice_dll_path, login_callback
        setup_choice_dll_path()
        from EmQuantAPI import c
        from config import CHOICE_USERNAME, CHOICE_PASSWORD

        print("[Choice] 正在登录...")

        login_result = {'done': False, 'result': None}

        def _do_login():
            try:
                result = c.start(
                    f"USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD},ForceLogin=1",
                    login_callback
                )
                login_result['result'] = result
            except Exception as e:
                login_result['result'] = e
            finally:
                login_result['done'] = True

        t = threading.Thread(target=_do_login, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if not login_result['done']:
            print(f"[Choice] 登录超时 ({timeout}s)，跳过 Choice")
            return False, None, None

        result = login_result['result']
        if isinstance(result, Exception):
            print(f"[Choice] 登录异常: {result}")
            return False, None, None

        if result is None or result.ErrorCode != 0:
            err_code = result.ErrorCode if result else 'unknown'
            err_msg = result.ErrorMsg if result else 'no result'
            print(f"[Choice] 登录失败: ErrorCode={err_code}, {err_msg}")
            return False, None, None

        time.sleep(2)
        print("[Choice] 登录成功")

        def stop_func():
            try:
                c.stop()
                print("[Choice] 已断开连接")
            except Exception:
                pass

        return True, c, stop_func

    except Exception as e:
        print(f"[Choice] 初始化失败: {e}")
        return False, None, None


def check_csd_available(c, timeout=20):
    """检查 CSD 接口是否可用（配额是否充足），带超时"""
    import threading

    print("[Choice] 检测 CSD 接口可用性...")
    test_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    result_box = {'done': False, 'data': None, 'error': None}

    def _do_check():
        try:
            result_box['data'] = c.csd("000001.SZ", "CLOSE", test_date, test_date, "")
        except Exception as e:
            result_box['error'] = e
        finally:
            result_box['done'] = True

    t = threading.Thread(target=_do_check, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if not result_box['done']:
        print(f"[Choice] CSD 检测超时 ({timeout}s)")
        return False

    if result_box['error']:
        print(f"[Choice] CSD 检测异常: {result_box['error']}")
        return False

    data = result_box['data']
    if data and data.ErrorCode == 0:
        print("[Choice] CSD 接口可用")
        return True
    else:
        ec = data.ErrorCode if data else 'unknown'
        em = data.ErrorMsg if data else 'no result'
        print(f"[Choice] CSD 接口不可用 (ErrorCode={ec}: {em})")
        return False


def cache_key_to_choice(key):
    """缓存键 -> Choice 代码 (sh600000 -> 600000.SH)"""
    if key.startswith("sh"):
        return key[2:] + ".SH"
    elif key.startswith("sz"):
        return key[2:] + ".SZ"
    elif key.startswith("bj"):
        return key[2:] + ".BJ"
    return None


def choice_to_cache_key(code):
    """Choice 代码 -> 缓存键 (600000.SH -> sh600000)"""
    if "." not in code:
        return None
    part, exchange = code.rsplit(".", 1)
    ex = exchange.lower()
    if ex in ("sh", "sz", "bj"):
        return f"{ex}{part}"
    return None


def normalize_choice_date(dt_str):
    """Choice 日期格式统一为 YYYY-MM-DD (零填充)"""
    if not dt_str:
        return dt_str
    # 处理斜杠分隔: 2026/6/1
    if '/' in dt_str:
        try:
            parts = dt_str.split('/')
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except (ValueError, IndexError):
            return dt_str
    # 处理不零填充的横杠分隔: 2026-6-1 → 2026-06-01
    if '-' in dt_str:
        parts = dt_str.split('-')
        if len(parts) == 3:
            try:
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            except (ValueError, IndexError):
                return dt_str
    return dt_str


def update_with_choice(c, cache, needs_update, target_date):
    """
    使用 Choice CSD 接口批量更新K线
    返回 (updated_keys, failed_keys)
    """
    updated_keys = []
    failed_keys = []
    total_new = 0

    BATCH = 50

    # 计算起始日期：取缓存中最大日期 + 1 天
    all_last_dates = []
    for key in needs_update:
        records = cache.get(key, [])
        if records:
            all_last_dates.append(records[-1].get("date", ""))
    if all_last_dates:
        global_start = min(all_last_dates)
    else:
        global_start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    for i in range(0, len(needs_update), BATCH):
        batch_keys = needs_update[i:i + BATCH]
        codes = []
        key_map = {}
        for key in batch_keys:
            cc = cache_key_to_choice(key)
            if cc:
                codes.append(cc)
                key_map[cc] = key

        if not codes:
            failed_keys.extend(batch_keys)
            continue

        codes_str = ",".join(codes)

        try:
            csd = c.csd(codes_str, "OPEN,HIGH,LOW,CLOSE,VOLUME",
                        global_start, target_date, "")

            if csd.ErrorCode == 0:
                dates = [normalize_choice_date(d) for d in csd.Dates]
                for cc in codes:
                    key = key_map[cc]
                    if cc in csd.Data:
                        arrays = csd.Data[cc]
                        # 归一化已有日期，防止格式不一致导致重复
                        existing_dates = {normalize_choice_date(r["date"]) for r in cache[key]}
                        added = 0
                        for j in range(len(dates)):
                            if dates[j] not in existing_dates:
                                try:
                                    o, h, l, cl, v = (
                                        arrays[0][j], arrays[1][j],
                                        arrays[2][j], arrays[3][j], arrays[4][j]
                                    )
                                    if o is None and h is None and l is None and cl is None:
                                        continue
                                    cache[key].append({
                                        "date": dates[j],
                                        "open": float(o) if o is not None else None,
                                        "high": float(h) if h is not None else None,
                                        "low": float(l) if l is not None else None,
                                        "close": float(cl) if cl is not None else None,
                                        "volume": float(v) if v is not None else 0.0,
                                    })
                                    added += 1
                                except (IndexError, TypeError, ValueError):
                                    pass
                        if added:
                            cache[key].sort(key=lambda x: x["date"])
                            total_new += added
                        updated_keys.append(key)
                    else:
                        failed_keys.append(key)

            elif csd.ErrorCode == 10002003:
                # 网络超时，逐个重试
                print(f"  [Choice] 批次超时 (offset={i})，逐个重试...")
                for cc in codes:
                    key = key_map[cc]
                    try:
                        csd2 = c.csd(cc, "OPEN,HIGH,LOW,CLOSE,VOLUME",
                                     global_start, target_date, "")
                        if csd2.ErrorCode == 0 and cc in csd2.Data:
                            dates2 = [normalize_choice_date(d) for d in csd2.Dates]
                            arrays = csd2.Data[cc]
                            existing = {r["date"] for r in cache[key]}
                            added = 0
                            for j in range(len(dates2)):
                                if dates2[j] not in existing:
                                    try:
                                        o, h, l, cl, v = (
                                            arrays[0][j], arrays[1][j],
                                            arrays[2][j], arrays[3][j], arrays[4][j]
                                        )
                                        if o is None and h is None and l is None and cl is None:
                                            continue
                                        cache[key].append({
                                            "date": dates2[j],
                                            "open": float(o) if o else None,
                                            "high": float(h) if h else None,
                                            "low": float(l) if l else None,
                                            "close": float(cl) if cl else None,
                                            "volume": float(v) if v else 0.0,
                                        })
                                        added += 1
                                    except Exception:
                                        pass
                            if added:
                                cache[key].sort(key=lambda x: x["date"])
                                total_new += added
                            updated_keys.append(key)
                        else:
                            failed_keys.append(key)
                    except Exception:
                        failed_keys.append(key)
                    time.sleep(0.3)
            else:
                print(f"  [Choice] CSD 错误 {csd.ErrorCode}: {csd.ErrorMsg}")
                failed_keys.extend(batch_keys)

        except Exception as e:
            print(f"  [Choice] 异常: {e}")
            failed_keys.extend(batch_keys)

        processed = min(i + BATCH, len(needs_update))
        if processed % 200 < BATCH or processed == len(needs_update):
            pct = processed * 100 // len(needs_update) if needs_update else 100
            print(f"  [Choice] 进度: {processed}/{len(needs_update)} ({pct}%) | "
                  f"已更新: {len(updated_keys)} | 失败: {len(failed_keys)} | 新增: {total_new}")

        # 定期保存
        if len(updated_keys) > 0 and len(updated_keys) % 500 < BATCH:
            print(f"  [Choice] 中间保存 ({len(updated_keys)} 只)...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        time.sleep(0.3)

    print(f"[Choice] 完成: 更新 {len(updated_keys)} 只, 失败 {len(failed_keys)} 只, 新增 {total_new} 条")
    return updated_keys, failed_keys


# ============================================================
# 腾讯接口 (fallback)
# ============================================================

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


def update_with_tencent(cache, needs_update, target_date):
    """
    使用腾讯接口更新K线（fallback 方案）
    返回 (updated_keys, failed_keys)
    """
    updated_keys = []
    failed_keys = []
    total_new_records = 0

    KLINE_COUNT = 15
    SAVE_INTERVAL = 300
    DELAY = 0.05

    t0 = time.time()

    for idx, code in enumerate(needs_update):
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
            updated_keys.append(code)
        else:
            failed_keys.append(code)

        processed = idx + 1
        if processed % 200 == 0:
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(needs_update) - processed) / rate if rate > 0 else 0
            print(f"  [腾讯] 进度: {processed}/{len(needs_update)} "
                  f"({processed*100//len(needs_update)}%) | "
                  f"更新: {len(updated_keys)} | 失败: {len(failed_keys)} | "
                  f"新增: {total_new_records} | ETA: {eta:.0f}s")

        if processed % SAVE_INTERVAL == 0 and processed > 0:
            print(f"  [腾讯] 中间保存 ({processed} 只)...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

        time.sleep(DELAY)

    print(f"[腾讯] 完成: 更新 {len(updated_keys)} 只, 失败 {len(failed_keys)} 只, 新增 {total_new_records} 条")
    return updated_keys, failed_keys


# ============================================================
# 主流程
# ============================================================

def main():
    target_date = get_latest_trade_date()

    print("=" * 60)
    print("K线批量更新 (Choice 优先 → 腾讯 fallback)")
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

    # ============================================================
    # Step 1: 尝试 Choice API
    # ============================================================
    choice_updated = []
    choice_failed = []
    remaining = list(needs_update)

    choice_ok, c_module, choice_stop = init_choice()

    if choice_ok:
        csd_ok = check_csd_available(c_module)
        if csd_ok:
            print(f"\n[2] 使用 Choice API 更新 {len(needs_update)} 只股票...")
            choice_updated, choice_failed = update_with_choice(
                c_module, cache, needs_update, target_date
            )

            # 中间保存
            print("\n[Choice] 保存 Choice 更新结果...")
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

            # 还需要腾讯补的 = Choice 失败的
            remaining = choice_failed
            if remaining:
                print(f"\n  Choice 失败 {len(remaining)} 只，将用腾讯接口补齐")
        else:
            print("\n  [Choice] CSD 不可用，全部使用腾讯接口")
        choice_stop()
    else:
        print("\n  [Choice] 初始化失败，全部使用腾讯接口")

    # ============================================================
    # Step 2: 腾讯接口补齐
    # ============================================================
    tencent_updated = []
    tencent_failed = []

    if remaining:
        print(f"\n[3] 使用腾讯接口更新 {len(remaining)} 只股票...")
        tencent_updated, tencent_failed = update_with_tencent(
            cache, remaining, target_date
        )
    else:
        print("\n[3] 无需腾讯接口（Choice 已全部完成）")

    # 最终保存
    print(f"\n[4] 保存最终结果...")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"  已保存到: {CACHE_PATH}")

    # 统计
    total_updated = len(choice_updated) + len(tencent_updated)
    total_failed = len(tencent_failed)

    print("\n" + "=" * 60)
    print("更新完成！")
    print(f"  Choice 更新: {len(choice_updated)} 只")
    print(f"  腾讯更新:    {len(tencent_updated)} 只")
    print(f"  总更新:      {total_updated} 只")
    print(f"  总失败:      {total_failed} 只")

    up_to_date = 0
    still_need = 0
    for code in cache:
        if cache[code] and cache[code][-1].get('date', '') >= target_date:
            up_to_date += 1
        else:
            still_need += 1
    print(f"  已到最新日期({target_date}): {up_to_date}")
    print(f"  仍需更新: {still_need}")

    if tencent_failed[:20]:
        print(f"  失败代码示例: {tencent_failed[:20]}")
    print("=" * 60)


if __name__ == '__main__':
    main()

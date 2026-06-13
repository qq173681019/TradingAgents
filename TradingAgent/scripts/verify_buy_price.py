#!/usr/bin/env python3
"""
buy_price 一致性验证脚本（封装版）
- 自动检测 cache 末条日期
- 4+1 级告警：✅/🟡/⚠️/🔴/🔴🔴
- 支持指定日期或自动找最新

用法：
  python3 scripts/verify_buy_price.py          # 验证最新推荐
  python3 scripts/verify_buy_price.py 20260603  # 验证指定日期
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows / WSL 路径兼容
BASE = Path(__file__).resolve().parent.parent
REC_DIR = BASE / 'recommendation_history'
KLINE = BASE.parent / 'TradingShared' / 'data' / 'kline_cache' / 'kline_full_latest.json'


def grade(days):
    if days is None:
        return '✗'
    if days <= 5:
        return '✅'
    elif days <= 10:
        return '🟡'
    elif days <= 30:
        return '⚠️'
    elif days <= 60:
        return '🔴'
    else:
        return '🔴🔴'


def find_latest_rec():
    """找最新推荐 JSON"""
    files = sorted(REC_DIR.glob('v28_recommendation_*_dryrun.json'), reverse=True)
    return files[0] if files else None


def main():
    # 1. 选文件
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
        rec_path = REC_DIR / f'v28_recommendation_{date_str}_dryrun.json'
    else:
        rec_path = find_latest_rec()
        if rec_path:
            # 从文件名提取日期
            date_str = rec_path.stem.replace('v28_recommendation_', '').replace('_dryrun', '')

    if not rec_path or not rec_path.exists():
        print(f'✗ 推荐文件不存在: {rec_path}')
        return 1

    print(f'=== buy_price 验证: {rec_path.name} ===')
    print()

    # 2. 加载数据
    with open(rec_path) as f:
        rec = json.load(f)
    with open(KLINE) as f:
        k = json.load(f)

    # 3. 找 cache 末条
    all_last_dates = []
    for code_key, arr in k.items():
        if arr and isinstance(arr, list) and 'date' in arr[-1]:
            all_last_dates.append(arr[-1]['date'])
    cache_last_date = max(all_last_dates)
    print(f'cache 末条: {cache_last_date} (共 {len(k)} 只股票)')
    print()

    # 4. 逐只验证
    results = []
    for r in rec.get('recommendations', []):
        code = r['code']
        target = r.get('buy_price')
        if target is None:
            results.append(('✗', code, 'buy_price=None', None, None, 0))
            continue
        matched = None
        arr_len = 0
        for prefix in ['sh', 'sz']:
            kc = f'{prefix}{code}'
            if kc in k and k[kc]:
                arr = k[kc]
                arr_len = len(arr)
                for row in arr:
                    for fld in ['open', 'high', 'low', 'close']:
                        if abs(row[fld] - target) < 0.01:
                            matched = (row['date'], fld, row[fld])
                            break
                    if matched:
                        break
                break
        if matched:
            d, fld, v = matched
            days_ago = (datetime.strptime(cache_last_date, '%Y-%m-%d')
                        - datetime.strptime(d, '%Y-%m-%d')).days
            flag = grade(days_ago)
            results.append((flag, code, f'buy={target:.3f} 匹配 {d} ({fld}={v})', days_ago, cache_last_date, arr_len))
        else:
            results.append(('✗', code, f'buy={target:.3f} 在 K线历史中找不到任何匹配 (cache 共 {arr_len} 条)', None, cache_last_date, arr_len))

    # 5. 输出
    print(f'--- 验证详情 ---')
    for flag, code, detail, days, cdate, arr_len in results:
        days_str = f' 距 cache 末条 {days} 天' if days is not None else ''
        print(f'  {flag} {code}: {detail}{days_str}')

    # 6. 分级统计
    from collections import Counter
    grades = [r[0] for r in results]
    print()
    print('--- 分级统计 ---')
    n_total = len(grades)
    for g in ['✅', '🟡', '⚠️', '🔴', '🔴🔴', '✗']:
        n = grades.count(g)
        if n:
            pct = 100.0 * n / n_total
            print(f'  {g}: {n} ({pct:.1f}%)')
    n_abnormal = sum(grades.count(g) for g in ['⚠️', '🔴', '🔴🔴', '✗'])
    pct = 100.0 * n_abnormal / n_total
    print(f'  异常率: {n_abnormal}/{n_total} ({pct:.1f}%)')

    return 0


if __name__ == '__main__':
    sys.exit(main())

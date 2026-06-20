#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 诊断脚本：检查V28数据基础问题"""
import json, glob, os

DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')

# 1. 检查评分文件
pattern = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
print("=== 评分文件 ===")
for f in files[:5]:
    sz = os.path.getsize(f)
    print(f"  {os.path.basename(f)}: {sz/1024:.0f}KB  mtime={os.path.getmtime(f)}")

if not files:
    print("  [ERROR] 没有找到评分文件!")
    exit(1)

score_file = files[0]
with open(score_file, 'r', encoding='utf-8') as fh:
    d = json.load(fh)

total = len(d)
empty_names = sum(1 for v in d.values() if not v.get('name', ''))
empty_industry = sum(1 for v in d.values() if not v.get('industry', '') or v.get('industry', '') in ('unknown', '未知'))
print(f"\n=== 评分数据统计 ===")
print(f"  总数: {total}")
print(f"  空名称: {empty_names} ({empty_names/total*100:.1f}%)")
print(f"  空行业: {empty_industry} ({empty_industry/total*100:.1f}%)")

# 检查PT/ST
pt_st = [(k, v.get('name', '')) for k, v in d.items() if any(kw in v.get('name', '') for kw in ['PT', 'ST', '*ST', '退'])]
print(f"  PT/ST: {len(pt_st)}")
for code, name in pt_st[:10]:
    print(f"    {code}: {name}")

# 检查特定问题股票
print(f"\n=== 问题股票检查 ===")
for code in ['000003', '000015', '600643', '600715', '002786', '600999']:
    if code in d:
        v = d[code]
        print(f"  {code}: name='{v.get('name','')}' industry='{v.get('industry','')}'")
    else:
        print(f"  {code}: 不在评分文件中")

# 2. 检查K线数据
print(f"\n=== K线数据 ===")
kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
if os.path.exists(kline_file):
    sz = os.path.getsize(kline_file)
    print(f"  文件: {os.path.basename(kline_file)} ({sz/1024/1024:.1f}MB)")
    with open(kline_file, 'r', encoding='utf-8') as fh:
        kdata = json.load(fh)
    print(f"  股票数: {len(kdata)}")
    # 检查最新日期
    max_dates = []
    for code, records in list(kdata.items())[:100]:
        if records:
            dates = [r.get('date', '') for r in records[-3:]]
            max_dates.extend(dates)
    if max_dates:
        print(f"  最新日期样本: {sorted(set(max_dates), reverse=True)[:5]}")
    # 检查000003是否在K线里
    for code in ['000003', '000015']:
        variants = [code, f'sz{code}', f'{code}.SZ']
        for v in variants:
            if v in kdata:
                recs = kdata[v]
                print(f"  {v} 在K线中: {len(recs)} 条记录, 最新={recs[-1].get('date','') if recs else '?'}")
                break
else:
    print("  [ERROR] kline_full_latest.json 不存在!")

# 3. 检查v19股票池
pool_file = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
print(f"\n=== V19股票池 ===")
if os.path.exists(pool_file):
    with open(pool_file, 'r', encoding='utf-8') as fh:
        pool = json.load(fh)
    print(f"  数量: {len(pool)}")
    # 检查PT股是否在池子里
    for code in ['000003', '000015']:
        if code in pool:
            print(f"  ⚠️ {code} (PT股) 在V19池中!")
        else:
            print(f"  ✅ {code} 不在V19池中")
else:
    print(f"  文件不存在: {pool_file}")

# 4. 检查sector_mapping
mapping_file = os.path.join(DATA_DIR, 'sector_cache', 'sector_mapping.json')
print(f"\n=== 行业映射 ===")
if os.path.exists(mapping_file):
    with open(mapping_file, 'r', encoding='utf-8') as fh:
        sm = json.load(fh)
    s2s = sm.get('stock_to_sector', {})
    print(f"  stock_to_sector: {len(s2s)} 条")
    # 检查覆盖率
    sample_codes = list(d.keys())[:200]
    has_sector = sum(1 for c in sample_codes if c in s2s or c.replace('.SZ','').replace('.SH','') in s2s)
    print(f"  覆盖率(前200): {has_sector}/200")
else:
    print(f"  文件不存在!")

# 5. 检查冷却期
cooldown_file = os.path.join(r'D:\GitHub\TradingAgents\TradingAgent', 'v28_cooldown.json')
print(f"\n=== 冷却期文件 ===")
if os.path.exists(cooldown_file):
    with open(cooldown_file, 'r', encoding='utf-8') as fh:
        cd = json.load(fh)
    last_recs = cd.get('last_rec_date', {})
    print(f"  记录数: {len(last_recs)}")
    # 检查银宝山新
    for code in ['002786', '600999', '603102']:
        if code in last_recs:
            print(f"  {code}: 最后推荐日={last_recs[code]}")
else:
    print(f"  文件不存在!")

print("\n=== 诊断完成 ===")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查基本面评分为什么都是6.3分
"""
import json
import os
from collections import Counter

# 读取评分文件
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
score_file = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')

with open(score_file, 'r', encoding='utf-8') as f:
    stocks = json.load(f)

print("="*80)
print("检查基本面评分来源")
print("="*80)

# 统计基本面评分分布
long_scores = [s.get('long_term_score', 5.0) for s in stocks.values()]
score_dist = Counter(long_scores)

print(f"\n总股票数: {len(long_scores)}")
print(f"\n基本面评分分布：")
for score in sorted(score_dist.keys()):
    count = score_dist[score]
    pct = count / len(long_scores) * 100
    bar = "█" * int(pct / 2)
    print(f"  {score:>6.1f}: {count:>3} 只 ({pct:>5.1f}%) {bar}")

# 抽样检查：每种评分选几只股票看看详细数据
print("\n" + "="*80)
print("抽样检查：不同评分的股票详细数据")
print("="*80)

# 按评分分组
score_groups = {}
for code, data in stocks.items():
    score = data.get('long_term_score', 5.0)
    if score not in score_groups:
        score_groups[score] = []
    score_groups[score].append((code, data))

# 每组抽查3只
for score in sorted(score_groups.keys()):
    print(f"\n【基本面评分 {score} 的股票】")
    print(f"  总数: {len(score_groups[score])}只")
    
    samples = score_groups[score][:3]
    for code, data in samples:
        print(f"\n  {code} {data.get('name', 'N/A')}:")
        print(f"    技术面: {data.get('short_term_score', 'N/A')}")
        print(f"    基本面: {data.get('long_term_score', 'N/A')}")
        print(f"    筹码面: {data.get('chip_score', 'N/A')}")
        print(f"    热门板块: {data.get('hot_sector_score', 'N/A')}")

# 检查是否有规律
print("\n" + "="*80)
print("分析评分规律")
print("="*80)

# 看看6.3分的股票是否有什么共同特征
score_63_stocks = score_groups.get(6.3, [])
if score_63_stocks:
    print(f"\n6.3分的股票（共{len(score_63_stocks)}只）的共同特征：")
    
    # 检查技术面评分分布
    tech_scores = [s[1].get('short_term_score', 0) for s in score_63_stocks]
    from collections import Counter
    tech_dist = Counter(tech_scores)
    print(f"\n  技术面评分分布：")
    for ts in sorted(tech_dist.keys())[:10]:
        print(f"    {ts:.1f}: {tech_dist[ts]}只")
    
    # 检查筹码面评分分布
    chip_scores = [s[1].get('chip_score', 0) for s in score_63_stocks]
    chip_dist = Counter(chip_scores)
    print(f"\n  筹码面评分分布：")
    for cs in sorted(chip_dist.keys())[:10]:
        print(f"    {cs:.1f}: {chip_dist[cs]}只")

# 检查数据来源
print("\n" + "="*80)
print("检查数据是否来自缓存")
print("="*80)

# 看看评分文件的生成时间
import time
file_mtime = os.path.getmtime(score_file)
file_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_mtime))
print(f"\n评分文件生成时间: {file_time}")

# 检查是否有其他评分文件
print(f"\n其他评分文件：")
for f in os.listdir(data_dir):
    if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json'):
        fpath = os.path.join(data_dir, f)
        ftime = os.path.getmtime(fpath)
        ftime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ftime))
        fsize = os.path.getsize(fpath)
        print(f"  {f} - {ftime_str} ({fsize} bytes)")

print("\n🔍 结论：")
print("  如果83只股票的基本面评分都是6.3，可能是：")
print("  1. 使用了某个默认值")
print("  2. 基本面数据缺失")
print("  3. 评分计算算法有bug")
print("  4. 或者是批量计算时使用了缓存/默认值")

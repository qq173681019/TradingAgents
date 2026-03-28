#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析主板评分数据
"""
import json
import os
from collections import Counter

# 读取评分数据
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
file_path = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"总股票数: {len(data)}")

# 统计成功匹配板块的股票
matched = [s for s in data.values() if s.get('matched_sector')]
print(f"成功匹配板块的股票: {len(matched)}/{len(data)}")

# 统计行业分布
industries = [s.get('industry', '未知') for s in data.values()]
top_industries = Counter(industries).most_common(20)
print(f"\n行业分布Top 20:")
for ind, count in top_industries:
    print(f"  {ind}: {count}只")

# 统计匹配的板块分布
matched_sectors = [s.get('matched_sector') for s in data.values() if s.get('matched_sector')]
top_sectors = Counter(matched_sectors).most_common(20)
print(f"\n匹配的板块分布Top 20:")
if top_sectors:
    for sec, count in top_sectors:
        print(f"  {sec}: {count}只")
else:
    print("  无匹配板块")

# 统计热门板块评分分布
hot_scores = [s.get('hot_sector_score', 5.0) for s in data.values()]
score_dist = Counter(hot_scores)
print(f"\n热门板块评分分布:")
for score in sorted(score_dist.keys()):
    print(f"  {score}: {score_dist[score]}只")

# 显示一些成功匹配的股票
if matched:
    print(f"\n前20个成功匹配的股票:")
    for s in matched[:20]:
        print(f"  {s['code']} {s['name']:10} 行业:{s['industry']:10} -> {s['matched_sector']:15} 涨幅:{s['sector_change']:+.1f}% 评分:{s['hot_sector_score']}")

# 分析问题股票
unknown_industry = [s for s in data.values() if s.get('industry') == '未知']
print(f"\n行业为'未知'的股票: {len(unknown_industry)}只")
if unknown_industry:
    print("前10只:")
    for s in unknown_industry[:10]:
        print(f"  {s['code']} {s['name']}")

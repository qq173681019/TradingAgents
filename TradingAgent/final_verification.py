#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证最终结果并生成报告
"""
import json
import os
from collections import Counter

# 读取更新后的数据
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 统计行业分布
industries = []
for code, stock in comp_data['stocks'].items():
    ind = stock['basic_info'].get('industry', '未知')
    industries.append(ind)

# 统计
total = len(industries)
known = len([i for i in industries if i != '未知'])
unknown = len([i for i in industries if i == '未知'])

print("="*70)
print("行业信息更新结果")
print("="*70)
print(f"总股票数: {total}")
print(f"已更新: {known} ({known/total*100:.1f}%)")
print(f"未更新: {unknown} ({unknown/total*100:.1f}%)")

# 行业分布Top 20
dist = Counter(industries)
print("\n行业分布Top 20:")
print("-"*70)
for i, (ind, count) in enumerate(dist.most_common(20), 1):
    pct = count / total * 100
    print(f"{i:>2}. {ind:<15} {count:>4} ({pct:>5.1f}%)")

print("\n" + "="*70)
print("✅ 行业信息更新完成！现在可以运行推荐生成了。")
print("="*70)

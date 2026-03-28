#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证更新后的行业信息
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 统计行业分布
industries = {}
for code, stock in comp_data['stocks'].items():
    ind = stock['basic_info'].get('industry', '未知')
    if ind not in industries:
        industries[ind] = 0
    industries[ind] += 1

print("行业分布统计:")
print("="*70)

# 排序并显示前20个行业
sorted_ind = sorted(industries.items(), key=lambda x: x[1], reverse=True)
for ind, count in sorted_ind[:20]:
    pct = count / len(comp_data['stocks']) * 100
    print(f"{ind:<15} {count:>4} ({pct:>5.1f}%)")

# 检查前10只股票
print("\n前10只股票的行业信息:")
print("="*70)
for code in list(comp_data['stocks'].keys())[:10]:
    stock = comp_data['stocks'][code]
    name = stock['basic_info'].get('name', 'N/A')
    industry = stock['basic_info'].get('industry', '未知')
    print(f"{code} {name:<10} -> {industry}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查为什么所有股票的基本面评分都是6.3
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 获取前10名股票的基本面详细数据
top_10_codes = ['600604', '600648', '600643', '600668', '600715', 
                '600692', '600717', '603936', '600609', '600657']

print("="*80)
print("检查前10名股票的基本面详细数据")
print("="*80)

for code in top_10_codes:
    if 'stocks' in comp_data and code in comp_data['stocks']:
        stock = comp_data['stocks'][code]
        
        # 获取基本面数据
        long_pred = stock.get('long_term_prediction', {})
        fundamental = long_pred.get('fundamental_analysis', {})
        
        print(f"\n{code} {stock.get('basic_info', {}).get('name', 'N/A')}:")
        print(f"  基本面评分: {long_pred.get('score', 'N/A')}")
        
        # 检查详细指标
        if fundamental:
            print(f"  PE市盈率: {fundamental.get('pe_ratio', 'N/A')}")
            print(f"  PB市净率: {fundamental.get('pb_ratio', 'N/A')}")
            print(f"  ROE: {fundamental.get('roe', 'N/A')}")
            print(f"  营收增长: {fundamental.get('revenue_growth', 'N/A')}")
            print(f"  利润增长: {fundamental.get('profit_growth', 'N/A')}")
        else:
            print("  [WARN] 没有基本面分析数据")
            print(f"  long_term_prediction keys: {list(long_pred.keys())[:10]}")
    else:
        print(f"\n{code}: 不在comprehensive_data中")

print("\n" + "="*80)
print("检查评分文件中的基本面数据")
print("="*80)

# 读取评分文件
score_file = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')
with open(score_file, 'r', encoding='utf-8') as f:
    score_data = json.load(f)

# 统计long_term_score
from collections import Counter
long_scores = [s.get('long_term_score', 5.0) for s in score_data.values()]
score_dist = Counter(long_scores)

print(f"\nlong_term_score分布:")
for score in sorted(score_dist.keys()):
    count = score_dist[score]
    print(f"  {score}: {count}只 ({count/len(score_data)*100:.1f}%)")

# 检查是否有详细的基本面数据
print(f"\n检查前5只股票的详细数据结构:")
for code in top_10_codes[:5]:
    if code in score_data:
        stock = score_data[code]
        print(f"\n{code}:")
        print(f"  Keys: {list(stock.keys())}")
        if 'fundamental_data' in stock:
            print(f"  fundamental_data: {stock['fundamental_data']}")

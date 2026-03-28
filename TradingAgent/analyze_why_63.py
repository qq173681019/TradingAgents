#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查为什么基本面6.3分的股票排前10，而不是更高的股票
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
score_file = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')

with open(score_file, 'r', encoding='utf-8') as f:
    stocks = json.load(f)

print("="*80)
print("分析：为什么前10名都是基本面6.3分的股票？")
print("="*80)

# 按长线评分排序
long_ranking = []
for code, data in stocks.items():
    tech = data.get('short_term_score', 5.0)
    fund = data.get('long_term_score', 5.0)
    chip = data.get('chip_score', 5.0)
    hot = data.get('hot_sector_score', 5.0)
    
    # 长线评分 = 技术15% + 基本面35% + 筹码35% + 热门板块15%
    long_score = tech * 0.15 + fund * 0.35 + chip * 0.35 + hot * 0.15
    
    long_ranking.append({
        'code': code,
        'name': data.get('name', 'N/A'),
        'long_score': long_score,
        'tech': tech,
        'fund': fund,
        'chip': chip,
        'hot': hot
    })

long_ranking.sort(key=lambda x: x['long_score'], reverse=True)

print("\n【长线推荐前20名】")
print("-"*80)
print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'综合':<6} {'技术':<6} {'基本':<6} {'筹码':<6} {'板块':<6}")
print("-"*80)

for i, stock in enumerate(long_ranking[:20], 1):
    print(f"{i:<4} {stock['code']:<8} {stock['name']:<10} {stock['long_score']:<6.2f} {stock['tech']:<6.1f} {stock['fund']:<6.1f} {stock['chip']:<6.1f} {stock['hot']:<6.1f}")

# 检查基本面评分分布
print("\n" + "="*80)
print("基本面评分分布分析")
print("="*80)

fund_dist = {}
for stock in stocks.values():
    fund = stock.get('long_term_score', 5.0)
    if fund not in fund_dist:
        fund_dist[fund] = []
    fund_dist[fund].append(stock)

print(f"\n基本面评分分组：")
for fund in sorted(fund_dist.keys()):
    count = len(fund_dist[fund])
    print(f"  {fund}: {count}只")

# 找出基本面评分最高的股票
print("\n" + "="*80)
print("基本面评分最高的股票（前20名）")
print("="*80)

by_fund = sorted(stocks.items(), key=lambda x: x[1].get('long_term_score', 5.0), reverse=True)

print(f"\n{'排名':<4} {'代码':<8} {'名称':<10} {'基本':<6} {'技术':<6} {'筹码':<6} {'长线综合':<8}")
print("-"*80)

for i, (code, data) in enumerate(by_fund[:20], 1):
    fund = data.get('long_term_score', 5.0)
    tech = data.get('short_term_score', 5.0)
    chip = data.get('chip_score', 5.0)
    hot = data.get('hot_sector_score', 5.0)
    long_score = tech * 0.15 + fund * 0.35 + chip * 0.35 + hot * 0.15
    
    print(f"{i:<4} {code:<8} {data.get('name', 'N/A'):<10} {fund:<6.1f} {tech:<6.1f} {chip:<6.1f} {long_score:<8.2f}")

# 关键分析
print("\n" + "="*80)
print("关键发现")
print("="*80)

# 计算相关性
fund_63_stocks = [s for s in stocks.values() if s.get('long_term_score') == 6.3]
fund_other_stocks = [s for s in stocks.values() if s.get('long_term_score') != 6.3]

if fund_63_stocks:
    avg_chip_63 = sum(s.get('chip_score', 5.0) for s in fund_63_stocks) / len(fund_63_stocks)
    avg_tech_63 = sum(s.get('short_term_score', 5.0) for s in fund_63_stocks) / len(fund_63_stocks)
    print(f"\n基本面6.3分的股票（{len(fund_63_stocks)}只）：")
    print(f"  平均筹码面评分: {avg_chip_63:.2f}")
    print(f"  平均技术面评分: {avg_tech_63:.2f}")

if fund_other_stocks:
    avg_chip_other = sum(s.get('chip_score', 5.0) for s in fund_other_stocks) / len(fund_other_stocks)
    avg_tech_other = sum(s.get('short_term_score', 5.0) for s in fund_other_stocks) / len(fund_other_stocks)
    print(f"\n其他评分的股票（{len(fund_other_stocks)}只）：")
    print(f"  平均筹码面评分: {avg_chip_other:.2f}")
    print(f"  平均技术面评分: {avg_tech_other:.2f}")

print("\n结论：")
print("  基本面6.3分的股票在筹码面和技术面评分上更高，")
print("  所以在长线综合评分中排名靠前（基本面35% + 筹码35% + 技术15% = 85%权重）")

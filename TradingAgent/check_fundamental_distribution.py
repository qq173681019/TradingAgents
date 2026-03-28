#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查所有股票的基本面评分分布
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
file_path = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')

with open(file_path, 'r', encoding='utf-8') as f:
    stocks = json.load(f)

print("="*80)
print("基本面评分分布分析")
print("="*80)

# 统计基本面评分分布
fund_scores = [s.get('long_term_score', 5.0) for s in stocks.values()]
fund_scores.sort(reverse=True)

print(f"\n总股票数: {len(fund_scores)}")
print(f"基本面评分范围: {min(fund_scores):.1f} - {max(fund_scores):.1f}")
print(f"基本面平均分: {sum(fund_scores)/len(fund_scores):.2f}")

# 分段统计
ranges = [
    (9.0, 10.0, "9.0-10.0 (优秀)"),
    (8.0, 9.0, "8.0-9.0 (良好)"),
    (7.0, 8.0, "7.0-8.0 (中等)"),
    (6.0, 7.0, "6.0-7.0 (及格)"),
    (5.0, 6.0, "5.0-6.0 (较差)"),
    (0.0, 5.0, "0-5.0 (极差)"),
]

print("\n基本面评分分段统计：")
print("-"*80)
for low, high, label in ranges:
    count = len([s for s in fund_scores if low <= s < high])
    pct = count / len(fund_scores) * 100
    bar = "█" * int(pct / 2)
    print(f"  {label:<20} {count:>4} 只 ({pct:>5.1f}%) {bar}")

# 列出基本面评分最高的20只股票
print("\n" + "="*80)
print("基本面评分最高的20只股票：")
print("-"*80)

stock_list = [(code, data.get('name', 'N/A'), data.get('long_term_score', 5.0), 
               data.get('short_term_score', 5.0), data.get('chip_score', 5.0))
              for code, data in stocks.items()]
stock_list.sort(key=lambda x: x[2], reverse=True)

print(f"{'代码':<8} {'名称':<12} {'基本面':<8} {'技术面':<8} {'筹码面':<8}")
print("-"*80)
for code, name, fund, tech, chip in stock_list[:20]:
    print(f"{code:<8} {name:<12} {fund:<8.1f} {tech:<8.1f} {chip:<8.1f}")

print("\n" + "="*80)
print("分析结论：")
print("="*80)
if max(fund_scores) <= 7.0:
    print("\n⚠️ 问题：所有股票的基本面评分都不超过7.0")
    print("   可能原因：")
    print("   1. 数据源质量问题")
    print("   2. 基本面分析算法过于保守")
    print("   3. 当前市场环境下，基本面普遍较差")
else:
    print(f"\n✓ 有{len([s for s in fund_scores if s >= 8.0])}只股票基本面评分>=8.0")
    print("  基本面权重应该能够起到区分作用")

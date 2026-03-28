#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比短线和长线推荐的差异
"""
import csv
import os

desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')

print("="*70)
print("对比短线和长线推荐差异")
print("="*70)

# 读取短线推荐
short_term = []
with open(os.path.join(desktop, '推荐_短线.csv'), 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        short_term.append(row)

# 读取长线推荐
long_term = []
with open(os.path.join(desktop, '推荐_长线.csv'), 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        long_term.append(row)

print(f"\n短线推荐前10名:")
print("-"*70)
print(f"{'排名':<4} {'代码':<8} {'名称':<12} {'综合':<6} {'技术':<6} {'基本':<6} {'筹码':<6} {'板块':<6}")
print("-"*70)
for i, stock in enumerate(short_term, 1):
    print(f"{i:<4} {stock['股票代码']:<8} {stock['股票名称']:<12} "
          f"{float(stock['综合评分']):<6.2f} {float(stock['技术面']):<6.1f} "
          f"{float(stock['基本面']):<6.1f} {float(stock['筹码面']):<6.1f} "
          f"{float(stock['热门板块']):<6.1f}")

print(f"\n长线推荐前10名:")
print("-"*70)
print(f"{'排名':<4} {'代码':<8} {'名称':<12} {'综合':<6} {'技术':<6} {'基本':<6} {'筹码':<6} {'板块':<6}")
print("-"*70)
for i, stock in enumerate(long_term, 1):
    print(f"{i:<4} {stock['股票代码']:<8} {stock['股票名称']:<12} "
          f"{float(stock['综合评分']):<6.2f} {float(stock['技术面']):<6.1f} "
          f"{float(stock['基本面']):<6.1f} {float(stock['筹码面']):<6.1f} "
          f"{float(stock['热门板块']):<6.1f}")

# 对比排名差异
print(f"\n排名对比:")
print("-"*70)
short_codes = [s['股票代码'] for s in short_term]
long_codes = [s['股票代码'] for s in long_term]

print(f"{'代码':<8} {'短线排名':<10} {'长线排名':<10} {'排名变化':<10}")
print("-"*70)
for code in set(short_codes[:10] + long_codes[:10]):
    short_rank = short_codes.index(code) + 1 if code in short_codes else '-'
    long_rank = long_codes.index(code) + 1 if code in long_codes else '-'
    if short_rank != '-' and long_rank != '-':
        change = short_rank - long_rank
        change_str = f"{change:+d}" if change != 0 else "0"
    else:
        change_str = '-'
    print(f"{code:<8} {short_rank:<10} {long_rank:<10} {change_str:<10}")

# 检查是否有差异
if short_codes[:10] == long_codes[:10]:
    print("\n❌ 问题：短线和长线前10名完全一样！")
    print("\n分析：虽然权重不同，但由于评分差异不够大，导致排序相同")
    print("\n建议：")
    print("  1. 当前数据质量差（行业都是'未知'，板块评分都是5.0）")
    print("  2. 即使权重不同，如果评分相同，排序也会相同")
    print("  3. 需要有真实的评分差异才能体现出权重的影响")
else:
    print("\n✅ 差异存在：短线和长线推荐不同！")
    print("\n短线独有：", [c for c in short_codes[:10] if c not in long_codes[:10]])
    print("长线独有：", [c for c in long_codes[:10] if c not in short_codes[:10]])

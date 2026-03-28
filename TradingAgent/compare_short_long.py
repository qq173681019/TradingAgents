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
    name = stock['股票名称']
    score = float(stock['综合评分'])
    tech = float(stock['技术面'])
    fund = float(stock['基本面'])
    chip = float(stock['筹码面'])
    hot = float(stock['热门板块'])
    print(f"{i:<4} {stock['股票代码']:<8} {name:<12} {score:<6.2f} {tech:<6.1f} {fund:<6.1f} {chip:<6.1f} {hot:<6.1f}")

print(f"\n长线推荐前10名:")
print("-"*70)
print(f"{'排名':<4} {'代码':<8} {'名称':<12} {'综合':<6} {'技术':<6} {'基本':<6} {'筹码':<6} {'板块':<6}")
print("-"*70)
for i, stock in enumerate(long_term, 1):
    name = stock['股票名称']
    score = float(stock['综合评分'])
    tech = float(stock['技术面'])
    fund = float(stock['基本面'])
    chip = float(stock['筹码面'])
    hot = float(stock['热门板块'])
    print(f"{i:<4} {stock['股票代码']:<8} {name:<12} {score:<6.2f} {tech:<6.1f} {fund:<6.1f} {chip:<6.1f} {hot:<6.1f}")

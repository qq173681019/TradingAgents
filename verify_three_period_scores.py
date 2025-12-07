#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
深度验证000001的三期评分计算逻辑
对比批量评分保存的数据 vs 我们用缓存数据重新计算的结果
"""
import json
import sys

print("=" * 80)
print("深度验证000001三期评分的计算逻辑")
print("=" * 80)

# 1. 加载批量评分中保存的数据
print("\n1️⃣ 查看批量评分保存的数据:")
print("-" * 80)
with open('data/batch_stock_scores_none.json', 'r', encoding='utf-8') as f:
    batch_data = json.load(f)

if '000001' in batch_data['scores']:
    saved = batch_data['scores']['000001']
    print(f"✓ 找到000001")
    print(f"  综合评分: {saved.get('overall_score')}")
    print(f"  短期评分: {saved.get('short_term_score')}")
    print(f"  中期评分: {saved.get('medium_term_score')}")
    print(f"  长期评分: {saved.get('long_term_score')}")
    print(f"  数据来源: {saved.get('data_source')}")
    print(f"  分析类型: {saved.get('analysis_type')}")
else:
    print("✗ 未找到000001")
    sys.exit(1)

# 2. 从缓存加载原始技术和基本面数据
print("\n2️⃣ 加载缓存中的原始数据:")
print("-" * 80)
with open('data/comprehensive_stock_data_part_11.json', 'r', encoding='utf-8') as f:
    cache_data = json.load(f)

if '000001' in cache_data['stocks']:
    stock = cache_data['stocks']['000001']
    print(f"✓ 找到000001缓存数据")
    
    # 提取技术指标
    tech_ind = stock.get('technical_indicators', {})
    print(f"  technical_indicators: {tech_ind}")
    
    # 提取基本面数据
    fin_data = stock.get('financial_data', {})
    print(f"  financial_data keys: {list(fin_data.keys())}")
    print(f"    PE: {fin_data.get('pe_ratio', 'N/A')}")
    print(f"    PB: {fin_data.get('pb_ratio', 'N/A')}")
    print(f"    ROE: {fin_data.get('roe', 'N/A')}")
else:
    print("✗ 缓存中未找到000001")
    sys.exit(1)

# 3. 关键问题：检查三期分数是如何被计算出来的
print("\n3️⃣ 三期分数来源分析:")
print("-" * 80)

# 可能的来源1：直接保存在stock数据中
if 'short_term_score' in stock:
    print(f"✓ 发现stock中包含 short_term_score: {stock['short_term_score']}")
if 'medium_term_score' in stock:
    print(f"✓ 发现stock中包含 medium_term_score: {stock['medium_term_score']}")
if 'long_term_score' in stock:
    print(f"✓ 发现stock中包含 long_term_score: {stock['long_term_score']}")

# 可能的来源2：保存在其他字段中
if 'scores' in stock:
    print(f"✓ 发现stock中包含 scores: {stock['scores']}")
if 'analysis_data' in stock:
    print(f"✓ 发现stock中包含 analysis_data")

# 可能的来源3：需要从技术和基本面数据计算
print("\n4️⃣ 重新计算三期分数（使用缓存数据）:")
print("-" * 80)

# 模拟"开始分析"中的计算逻辑
def calculate_scores_from_cache(tech_ind, fin_data):
    """基于缓存数据重新计算三期分数"""
    
    # 简单规则：如果缓存中的指标都为0或None，则评分为基准分5.0
    tech_score = 0
    fund_score = 0
    
    # 检查是否有有效的技术数据
    if tech_ind and tech_ind.get('status') != 'failed':
        # 如果有技术数据，计算技术评分
        tech_score = 5 + (tech_ind.get('indicator_value', 0) * 0.1)
    else:
        tech_score = 5.0
    
    # 检查是否有有效的基本面数据
    if fin_data:
        pe = fin_data.get('pe_ratio', 0)
        pb = fin_data.get('pb_ratio', 0)
        roe = fin_data.get('roe', 0)
        
        # 简单评分规则
        if 5 <= pe <= 25:
            fund_score += 1
        if 0.5 <= pb <= 3:
            fund_score += 1
        if roe >= 10:
            fund_score += 1
        
        fund_score = 5.0 + fund_score  # 基础5分 + 加分
    else:
        fund_score = 5.0
    
    # 三期分数（通常是固定的加权）
    short = tech_score  # 短期偏技术面
    medium = (tech_score * 0.6 + fund_score * 0.4)  # 中期平衡
    long = fund_score  # 长期偏基本面
    
    return short, medium, long

short_calc, medium_calc, long_calc = calculate_scores_from_cache(tech_ind, fin_data)

print(f"重新计算结果:")
print(f"  短期分: {short_calc:.1f} (保存的: {saved.get('short_term_score')})")
print(f"  中期分: {medium_calc:.1f} (保存的: {saved.get('medium_term_score')})")
print(f"  长期分: {long_calc:.1f} (保存的: {saved.get('long_term_score')})")

# 比对
print("\n5️⃣ 比对分析:")
print("-" * 80)
short_match = abs(short_calc - saved.get('short_term_score', 0)) < 0.1
medium_match = abs(medium_calc - saved.get('medium_term_score', 0)) < 0.1
long_match = abs(long_calc - saved.get('long_term_score', 0)) < 0.1

print(f"短期分数匹配: {'✓' if short_match else '✗'}")
print(f"中期分数匹配: {'✓' if medium_match else '✗'}")
print(f"长期分数匹配: {'✓' if long_match else '✗'}")

if not (short_match and medium_match and long_match):
    print("\n⚠️ 发现不匹配！可能的原因:")
    print("  1. 批量评分使用了不同的计算逻辑")
    print("  2. 批量评分使用了不同的数据源（而不是缓存）")
    print("  3. 批量评分的三期分数来自generate_investment_advice()的实际返回值")
    print("\n🔍 需要检查 get_stock_score_for_batch() 中")
    print("   generate_investment_advice() 的返回值")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出完整的评分公式并验证计算
"""

# 当前权重配置
print("="*80)
print("完整的评分公式")
print("="*80)

print("\n【短线推荐】权重配置：")
print("-"*80)
print("  技术面权重:   30% (0.3)")
print("  基本面权重:   10% (0.1)")
print("  筹码面权重:   20% (0.2)")
print("  热门板块权重: 40% (0.4)")
print("  总权重: 1.0")
print()
print("  短线综合评分 = 技术面 × 0.30")
print("               + 基本面 × 0.10")
print("               + 筹码面 × 0.20")
print("               + 热门板块 × 0.40")

print("\n【长线推荐】权重配置：")
print("-"*80)
print("  技术面权重:   15% (0.15)")
print("  基本面权重:   35% (0.35)")
print("  筹码面权重:   35% (0.35)")
print("  热门板块权重: 15% (0.15)")
print("  总权重: 1.0")
print()
print("  长线综合评分 = 技术面 × 0.15")
print("               + 基本面 × 0.35")
print("               + 筹码面 × 0.35")
print("               + 热门板块 × 0.15")

# 验证前5名的计算
print("\n" + "="*80)
print("验证前5名的计算")
print("="*80)

stocks = [
    {'code': '600604', 'name': '市北高新', 'tech': 8.5, 'fund': 6.3, 'chip': 8.2, 'hot': 5.0},
    {'code': '600648', 'name': '外高桥', 'tech': 8.5, 'fund': 6.3, 'chip': 8.2, 'hot': 5.0},
    {'code': '600643', 'name': '爱建集团', 'tech': 8.5, 'fund': 6.3, 'chip': 8.0, 'hot': 5.0},
    {'code': '600668', 'name': '尖峰集团', 'tech': 9.0, 'fund': 6.3, 'chip': 7.0, 'hot': 5.0},
    {'code': '600715', 'name': '文投控股', 'tech': 9.0, 'fund': 6.3, 'chip': 7.0, 'hot': 5.0},
]

print("\n{:<8} {:<10} {:<6} {:<6} {:<6} {:<6} | {:<10} {:<10} {:<10} {:<10}".format(
    "代码", "名称", "技术", "基本", "筹码", "板块", 
    "技术贡献", "基本贡献", "筹码贡献", "板块贡献"))

for stock in stocks:
    print(f"\n{stock['code']} {stock['name']}:")
    
    # 短线计算
    print("\n  短线计算：")
    tech_contrib = stock['tech'] * 0.3
    fund_contrib = stock['fund'] * 0.1
    chip_contrib = stock['chip'] * 0.2
    hot_contrib = stock['hot'] * 0.4
    short_score = tech_contrib + fund_contrib + chip_contrib + hot_contrib
    
    print(f"    技术面 {stock['tech']} × 0.30 = {tech_contrib:.2f}")
    print(f"    基本面 {stock['fund']} × 0.10 = {fund_contrib:.2f}")
    print(f"    筹码面 {stock['chip']} × 0.20 = {chip_contrib:.2f}")
    print(f"    热门板块 {stock['hot']} × 0.40 = {hot_contrib:.2f}")
    print(f"    短线总分 = {tech_contrib:.2f} + {fund_contrib:.2f} + {chip_contrib:.2f} + {hot_contrib:.2f} = {short_score:.2f}")
    
    # 长线计算
    print("\n  长线计算：")
    tech_contrib = stock['tech'] * 0.15
    fund_contrib = stock['fund'] * 0.35
    chip_contrib = stock['chip'] * 0.35
    hot_contrib = stock['hot'] * 0.15
    long_score = tech_contrib + fund_contrib + chip_contrib + hot_contrib
    
    print(f"    技术面 {stock['tech']} × 0.15 = {tech_contrib:.2f}")
    print(f"    基本面 {stock['fund']} × 0.35 = {fund_contrib:.2f}")
    print(f"    筹码面 {stock['chip']} × 0.35 = {chip_contrib:.2f}")
    print(f"    热门板块 {stock['hot']} × 0.15 = {hot_contrib:.2f}")
    print(f"    长线总分 = {tech_contrib:.2f} + {fund_contrib:.2f} + {chip_contrib:.2f} + {hot_contrib:.2f} = {long_score:.2f}")
    
    print(f"\n  结论：短线 {short_score:.2f} vs 长线 {long_score:.2f}，差异 {abs(short_score - long_score):.2f}")

print("\n" + "="*80)
print("权重差异分析")
print("="*80)
print("\n短线强调：")
print("  ✓ 技术面 (30%) - 比长线多 15%")
print("  ✓ 热门板块 (40%) - 比长线多 25%")
print()
print("长线强调：")
print("  ✓ 基本面 (35%) - 比短线多 25%")
print("  ✓ 筹码面 (35%) - 比短线多 15%")
print()
print("当前数据问题：")
print("  ✗ 热门板块评分都是 5.0（默认值）")
print("  ✗ 无法体现热门板块的权重优势")
print("  ✗ 导致短线的热门板块权重（40%）没有起到区分作用")

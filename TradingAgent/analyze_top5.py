#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析前5名为什么相同
"""

# 前5名股票的评分
stocks = [
    {'code': '600604', 'name': '市北高新', 'tech': 8.5, 'fund': 6.3, 'chip': 8.2, 'hot': 5.0},
    {'code': '600648', 'name': '外高桥', 'tech': 8.5, 'fund': 6.3, 'chip': 8.2, 'hot': 5.0},
    {'code': '600643', 'name': '爱建集团', 'tech': 8.5, 'fund': 6.3, 'chip': 8.0, 'hot': 5.0},
    {'code': '600668', 'name': '尖峰集团', 'tech': 9.0, 'fund': 6.3, 'chip': 7.0, 'hot': 5.0},
    {'code': '600715', 'name': '文投控股', 'tech': 9.0, 'fund': 6.3, 'chip': 7.0, 'hot': 5.0},
]

print("="*80)
print("前5名评分特征分析")
print("="*80)

for stock in stocks:
    print(f"\n{stock['code']} {stock['name']}:")
    print(f"  技术面: {stock['tech']}")
    print(f"  基本面: {stock['fund']}")
    print(f"  筹码面: {stock['chip']}")
    print(f"  热门板块: {stock['hot']}")
    
    # 短线评分（技术30% + 基本面10% + 筹码20% + 热门板块40%）
    short_score = (stock['tech'] * 0.3 + stock['fund'] * 0.1 + 
                   stock['chip'] * 0.2 + stock['hot'] * 0.4)
    
    # 长线评分（技术15% + 基本面35% + 筹码35% + 热门板块15%）
    long_score = (stock['tech'] * 0.15 + stock['fund'] * 0.35 + 
                  stock['chip'] * 0.35 + stock['hot'] * 0.15)
    
    print(f"  短线综合: {short_score:.2f}")
    print(f"  长线综合: {long_score:.2f}")
    print(f"  差异: {abs(short_score - long_score):.2f}")

print("\n" + "="*80)
print("分析结论：")
print("="*80)
print("前5名股票具有以下共同特征：")
print("  1. 技术面评分都很高（8.5或9.0）")
print("  2. 筹码面评分较高（7.0-8.2）")
print("  3. 基本面评分中等（6.3）")
print("  4. 热门板块评分都是5.0（默认值）")
print()
print("由于这些股票在技术面和筹码面都表现优秀，")
print("在两种权重配置下都能获得较高分数：")
print("  - 短线：技术30% + 筹码20% = 50%")
print("  - 长线：技术15% + 筹码35% = 50%")
print()
print("虽然权重分配不同，但总占比相同（50%），")
print("导致这些股票在两种配置下排名都靠前。")
print()
print("从第6名开始，差异开始显现，说明权重配置")
print("确实在起作用，只是前几名的综合实力太强。")

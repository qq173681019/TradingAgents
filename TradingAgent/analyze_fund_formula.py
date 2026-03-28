#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查基本面评分计算逻辑
"""

print("="*80)
print("基本面评分计算公式分析")
print("="*80)

print("\n基本公式（来自a_share_gui_compatible.py第13246行）：")
print("  final_score = min(10.0, max(1.0, score / 10.0))")
print("\n其中score是原始总分（50分基础 + 各项加减分）")

print("\n" + "="*80)
print("模拟计算：什么情况下会得到6.3分？")
print("="*80)

# 6.3分对应的原始分
final_63 = 6.3
raw_63 = final_63 * 10
print(f"\n6.3分 = 原始分{raw_63}")

print("\n可能组合（基础分50）：")
print("  组合1: 50(基础) + 18(PE<20) + 9(ROE 10-15%) + 2(增长0-5%) - 12(利润负增长) + 5(医药) = 72 → 7.2分")
print("  组合2: 50(基础) + 18(PE<20) + 9(ROE 10-15%) + 2(增长0-5%) = 79 → 7.9分")
print("  组合3: 50(基础) + 9(PE<35) + 9(ROE 10-15%) - 12(增长负) - 12(利润负) = 44 → 4.4分")

print("\n⚠️ 6.3分不应该出现在83只股票上！")
print("   这说明基本面评分算法有bug或数据源有问题")

print("\n" + "="*80)
print("检查评分文件中long_term_score的来源")
print("="*80)

# 模拟几种可能的6.3分来源
scenarios = [
    ("技术面-10分回退", -10),
    ("综合评分默认值", 6.3),
    ("平均分", 5.0),
    ("数据缺失默认", 5.0),
]

print("\n可能的场景：")
for desc, score in scenarios:
    print(f"  {desc}: {score}")

print("\n🔍 最可能的原因：")
print("  1. 83只股票的基本面数据都缺失")
print("  2. 使用了某个默认值6.3")
print("  3. 或者计算逻辑有bug，导致大量股票得到相同分数")

print("\n" + "="*80)
print("建议检查generate_mainboard_scores.py中：")
print("="*80)
print("  1. 第4281行: fund_score = long_pred.get('score', long_pred.get('fundamental_score', 0))")
print("  2. 查看数据源是否完整")
print("  3. 检查是否使用了某个默认值")

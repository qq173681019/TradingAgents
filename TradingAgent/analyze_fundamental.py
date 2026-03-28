#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重新分析：基本面在长线推荐中的作用
"""
import csv
import os

desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')

# 读取长线推荐
long_term = []
with open(os.path.join(desktop, '推荐_长线.csv'), 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        long_term.append(row)

print("="*80)
print("长线推荐分析：基本面权重的体现")
print("="*80)

print("\n长线权重配置：")
print("  技术面:   15% (0.15)")
print("  基本面:   35% (0.35) <- 最高权重！")
print("  筹码面:   35% (0.35) <- 最高权重！")
print("  热门板块: 15% (0.15)")

print("\n长线推荐前10名的评分贡献分析：")
print("-"*80)
print(f"{'代码':<8} {'名称':<10} {'综合':<6} {'技术':<6} {'基本':<6} {'筹码':<6} {'板块':<6} | {'技贡':<6} {'基贡':<6} {'筹贡':<6} {'板贡':<6}")
print("-"*80)

for stock in long_term[:10]:
    tech = float(stock['技术面'])
    fund = float(stock['基本面'])
    chip = float(stock['筹码面'])
    hot = float(stock['热门板块'])
    total = float(stock['综合评分'])
    
    # 计算各维度贡献
    tech_contrib = tech * 0.15
    fund_contrib = fund * 0.35
    chip_contrib = chip * 0.35
    hot_contrib = hot * 0.15
    
    print(f"{stock['股票代码']:<8} {stock['股票名称']:<10} {total:<6.2f} {tech:<6.1f} {fund:<6.1f} {chip:<6.1f} {hot:<6.1f} | {tech_contrib:<6.2f} {fund_contrib:<6.2f} {chip_contrib:<6.2f} {hot_contrib:<6.2f}")

print("\n" + "="*80)
print("问题分析")
print("="*80)

# 检查基本面评分分布
fund_scores = [float(s['基本面']) for s in long_term[:10]]
print(f"\n前10名基本面评分：")
print(f"  最高：{max(fund_scores)}")
print(f"  最低：{min(fund_scores)}")
print(f"  平均：{sum(fund_scores)/len(fund_scores):.2f}")

# 检查筹码面评分分布
chip_scores = [float(s['筹码面']) for s in long_term[:10]]
print(f"\n前10名筹码面评分：")
print(f"  最高：{max(chip_scores)}")
print(f"  最低：{min(chip_scores)}")
print(f"  平均：{sum(chip_scores)/len(chip_scores):.2f}")

print("\n结论：")
print("  1. 前10名的基本面评分都很低（6.3），没有区分度")
print("  2. 筹码面评分较高（7.0-8.2），是主要区分因素")
print("  3. 基本面权重35%确实起作用，但数据质量差（都是6.3）")
print("  4. 如果有股票基本面是8.0、9.0，在长线配置下会排到前面")

# 模拟：如果有一只股票基本面9.0，会排第几？
print("\n" + "="*80)
print("模拟测试：基本面9.0的股票会排第几？")
print("="*80)

# 取第1名的其他维度评分
first = long_term[0]
tech = float(first['技术面'])  # 8.5
chip = float(first['筹码面'])  # 8.2
hot = float(first['热门板块'])  # 5.0

# 如果基本面是9.0
fund_9 = 9.0
long_score_fund9 = tech * 0.15 + fund_9 * 0.35 + chip * 0.35 + hot * 0.15
print(f"\n假设：600604 基本面从6.3提升到9.0")
print(f"  长线评分 = 8.5×0.15 + 9.0×0.35 + 8.2×0.35 + 5.0×0.15")
print(f"          = {tech*0.15:.2f} + {fund_9*0.35:.2f} + {chip*0.35:.2f} + {hot*0.15:.2f}")
print(f"          = {long_score_fund9:.2f}")
print(f"  原评分：7.10")
print(f"  提升：{long_score_fund9 - 7.10:.2f}")

# 对比：短线评分会提升多少？
short_score_fund9 = tech * 0.30 + fund_9 * 0.10 + chip * 0.20 + hot * 0.40
short_score_old = tech * 0.30 + 6.3 * 0.10 + chip * 0.20 + hot * 0.40
print(f"\n  短线评分变化：")
print(f"    基本面6.3: {short_score_old:.2f}")
print(f"    基本面9.0: {short_score_fund9:.2f}")
print(f"    提升：{short_score_fund9 - short_score_old:.2f}")

print(f"\n  结论：")
print(f"    长线提升 {long_score_fund9 - 7.10:.2f} 分（基本面权重35%）")
print(f"    短线提升 {short_score_fund9 - short_score_old:.2f} 分（基本面权重10%）")
print(f"    长线提升是短线的 {(long_score_fund9 - 7.10) / (short_score_fund9 - short_score_old):.1f} 倍！")
print(f"\n  所以：基本面权重确实起作用，只是当前数据没有高基本面评分的股票！")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算6.3分对应的原始分和可能组合
"""

print("="*80)
print("基本面评分6.3分是如何计算的？")
print("="*80)

# 评分公式：final_score = min(10.0, max(1.0, score / 10.0))
# 6.3分对应的原始分
final_63 = 6.3
raw_score_63 = final_63 * 10
print(f"\n6.3分 = 原始总分 {raw_score_63} 分")

print("\n" + "="*80)
print("原始分计算规则（基础分50）")
print("="*80)

scenarios = [
    {
        "name": "场景1：中等偏上",
        "pe": 18,  # PE < 20: +18
        "roe": 9,  # ROE 10-15%: +9
        "rev": 2,  # 增长0-5%: +2
        "profit": -12,  # 利润负增长: -12
        "other": 0,  # 其他
    },
    {
        "name": "场景2：数据不全",
        "pe": 9,  # PE 20-35: +9
        "roe": 9,  # ROE 10-15%: +9
        "rev": 0,  # 增长未知: 0
        "profit": 0,  # 利润未知: 0
        "other": -5,  # 数据缺失: -5
    },
    {
        "name": "场景3：默认值",
        "pe": 0,  # 使用默认
        "roe": 0,  # 使用默认
        "rev": 0,  # 使用默认
        "profit": 0,  # 使用默认
        "other": 13,  # 全部默认值累计
    },
]

for scenario in scenarios:
    base = 50
    total = base + scenario["pe"] + scenario["roe"] + scenario["rev"] + scenario["profit"] + scenario["other"]
    final = min(10.0, max(1.0, total / 10.0))
    
    print(f"\n{scenario['name']}:")
    print(f"  基础分: 50")
    print(f"  PE评分: {scenario['pe']:+3d}")
    print(f"  ROE评分: {scenario['roe']:+3d}")
    print(f"  营收增长: {scenario['rev']:+3d}")
    print(f"  利润增长: {scenario['profit']:+3d}")
    print(f"  其他: {scenario['other']:+3d}")
    print(f"  原始总分: {total}")
    print(f"  最终评分: {total}/10 = {total/10:.1f} → {final:.1f}")

print("\n" + "="*80)
print("分析结论")
print("="*80)

print("\n如果83只股票的基本面评分都是6.3分，可能的原因：")
print("\n1. 数据源问题：")
print("   - 这些股票的基本面数据缺失或不完整")
print("   - 使用了默认值（PE=20, ROE=10%）")
print("   - 导致计算出相似的原始分（约63分）")

print("\n2. 评分算法限制：")
print("   - 基础分50分起，上下浮动范围有限")
print("   - PE, ROE等指标的评分档位较少")
print("   - 缺少8分、9分、10分的高分档位")

print("\n3. A股市场特征：")
print("   - 主板股票的基本面普遍中等偏上")
print("   - 缺少真正优秀的成长股（ROE>15%, 增长>15%）")
print("   - 大部分股票的PE、ROE、增长率都在中等区间")

print("\n" + "="*80)
print("验证方法")
print("="*80)
print("\n可以检查：")
print("  1. 查看comprehensive_stock_data.json中这些股票的基本面数据")
print("  2. 检查PE、ROE、增长率等指标是否真实")
print("  3. 如果都是默认值，说明数据源有问题")

# 检查一个6.3分的股票的详细数据
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 找一只6.3分的股票
code_63 = '600604'  # 市北高新
if 'stocks' in comp_data and code_63 in comp_data['stocks']:
    stock = comp_data['stocks'][code_63]
    print(f"\n{code_63} 的详细数据：")
    print(f"  Keys: {list(stock.keys())}")
    
    # 检查是否有基本面数据
    if 'fundamental_data' in stock:
        print(f"\n  基本面数据: {stock['fundamental_data']}")
    else:
        print(f"\n  ⚠️ 没有fundamental_data字段")
    
    # 检查long_term_prediction
    if 'long_term_prediction' in stock:
        long_pred = stock['long_term_prediction']
        print(f"\n  长线预测keys: {list(long_pred.keys())}")
        if 'fundamental_analysis' in long_pred:
            fund_analysis = long_pred['fundamental_analysis']
            print(f"\n  基本面分析:")
            print(f"    PE: {fund_analysis.get('pe_ratio', 'N/A')}")
            print(f"    ROE: {fund_analysis.get('roe', 'N/A')}")
            print(f"    增长: {fund_analysis.get('revenue_growth', 'N/A')}")
        else:
            print(f"\n  ⚠️ 没有fundamental_analysis字段")
    else:
        print(f"\n  ⚠️ 没有long_term_prediction字段")

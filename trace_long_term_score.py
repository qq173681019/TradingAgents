#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
追踪000001长期分数 4.6 的来源
直接调用generate_investment_advice和相关函数进行深度诊断
"""
import json

print("=" * 80)
print("追踪000001三期分数的实际计算过程")
print("=" * 80)

# 加载缓存数据
with open('data/comprehensive_stock_data_part_11.json', 'r', encoding='utf-8') as f:
    cache_data = json.load(f)

stock = cache_data['stocks']['000001']
print(f"\n000001缓存数据中存储的原始字段:")
print(f"  {list(stock.keys())}")

# 关键：查看是否在缓存中已经存储了三期分数
print(f"\n查找三期分数的可能位置:")

# 位置1：直接在stock中
for field in ['short_term_score', 'medium_term_score', 'long_term_score', 
              'short_term_prediction', 'medium_term_prediction', 'long_term_prediction',
              'short_advice', 'medium_advice', 'long_advice',
              'analysis_results', 'scores', 'predictions']:
    if field in stock:
        value = stock[field]
        if isinstance(value, dict):
            print(f"  ✓ {field}: {list(value.keys())}")
        else:
            print(f"  ✓ {field}: {value}")

# 位置2：检查comprehensive_data中是否有
with open('data/batch_stock_scores_none.json', 'r', encoding='utf-8') as f:
    batch_data = json.load(f)

if '000001' in batch_data['scores']:
    saved = batch_data['scores']['000001']
    print(f"\n批量评分保存的000001数据:")
    print(f"  短期: {saved.get('short_term_score')}")
    print(f"  中期: {saved.get('medium_term_score')}")  
    print(f"  长期: {saved.get('long_term_score')}")
    print(f"  综合: {saved.get('overall_score')}")
    
    # 查看长期分数4.6是如何计算出来的
    print(f"\n关键问题：长期分数为什么是 4.6（而不是 5.0）?")
    print(f"  这个分数的来源可能是:")
    print(f"  1. get_long_term_prediction() 函数的返回值")
    print(f"  2. 基于ROE = 2.398701 的计算结果")
    
    # 反推：如果长期分数是4.6，那么基于什么计算的?
    # 通常长期分数 = 5.0 + 某个因子 * 某个值
    # 或者 = 基础分 + ROE相关的加/减分
    
    roe = stock.get('financial_data', {}).get('roe', 0)
    print(f"\n  ROE = {roe}")
    print(f"  如果 长期分数 = 5.0 + (ROE - 10) * 某个系数")
    print(f"  则: 4.6 = 5.0 + ({roe} - 10) * 系数")
    print(f"  系数 = (4.6 - 5.0) / ({roe} - 10) = {(4.6 - 5.0) / (roe - 10):.3f}")

print(f"\n建议：需要查看 get_long_term_prediction() 函数的实现")
print(f"      看看它是如何基于 ROE = 2.398701 计算出 4.6 分的")

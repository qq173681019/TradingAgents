#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析000001的批量评分数据，找出为什么是5.0而不是7.4
"""
import json
import os

batch_file = "data/batch_stock_scores_minimax.json"

print("=" * 80)
print("分析000001在批量评分文件中的数据")
print("=" * 80)

# 读取批量评分文件
with open(batch_file, 'r', encoding='utf-8') as f:
    batch_scores = json.load(f)

# 查找000001的数据
if '000001' in batch_scores:
    data = batch_scores['000001']
    print(f"\n000001 在批量评分文件中的完整数据:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    
    # 分析一下这个数据是如何得到5.0的
    if 'comprehensive_score' in data:
        print(f"\n综合评分: {data['comprehensive_score']}")
    
    if 'score_details' in data:
        details = data['score_details']
        print(f"\n评分详情: {json.dumps(details, ensure_ascii=False, indent=2)}")
        
        # 看一下是否有原始的三期分数
        if 'short_term_score' in details:
            print(f"  短期: {details.get('short_term_score')}")
        if 'medium_term_score' in details:
            print(f"  中期: {details.get('medium_term_score')}")
        if 'long_term_score' in details:
            print(f"  长期: {details.get('long_term_score')}")
        
        # 看一下是否有原始的三种预测
        if 'short_prediction' in details:
            short_pred = details.get('short_prediction')
            if isinstance(short_pred, dict):
                print(f"\n短期预测对象keys: {list(short_pred.keys())}")
                print(f"  technical_score: {short_pred.get('technical_score')}")
        
        if 'medium_prediction' in details:
            medium_pred = details.get('medium_prediction')
            if isinstance(medium_pred, dict):
                print(f"\n中期预测对象keys: {list(medium_pred.keys())}")
                print(f"  total_score: {medium_pred.get('total_score')}")
        
        if 'long_prediction' in details:
            long_pred = details.get('long_prediction')
            if isinstance(long_pred, dict):
                print(f"\n长期预测对象keys: {list(long_pred.keys())}")
                print(f"  fundamental_score: {long_pred.get('fundamental_score')}")

else:
    print("\n❌ 000001 不在批量评分文件中!")

# 也查看一下前几个股票的结构，了解数据格式
print("\n" + "=" * 80)
print("前3只股票的数据结构（用于理解格式）:")
print("=" * 80)
count = 0
for code, data in batch_scores.items():
    if count >= 3:
        break
    print(f"\n{code}:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:500] + "...")
    count += 1

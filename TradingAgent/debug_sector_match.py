#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试：为什么板块匹配全部失败？
"""
import json
import os

# 读取comprehensive数据
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 检查几个股票的行业信息
test_codes = ['600604', '600648', '600519', '000001', '002594']

print("="*80)
print("调试：comprehensive_stock_data.json 中的行业信息")
print("="*80)

for code in test_codes:
    if 'stocks' in comp_data and code in comp_data['stocks']:
        stock = comp_data['stocks'][code]
        
        # 尝试各种可能的位置获取行业信息
        industry_sources = []
        
        # 位置1: basic_info.industry
        basic_info = stock.get('basic_info', {})
        if basic_info and 'industry' in basic_info:
            industry_sources.append(f"basic_info.industry: {basic_info['industry']}")
        
        # 位置2: financial_data 中的行业
        financial_data = stock.get('financial_data', {})
        if financial_data:
            if 'industry' in financial_data:
                industry_sources.append(f"financial_data.industry: {financial_data['industry']}")
        
        # 位置3: tech_data 中的行业
        tech_data = stock.get('tech_data', {})
        if tech_data and 'industry' in tech_data:
            industry_sources.append(f"tech_data.industry: {tech_data['industry']}")
        
        print(f"\n{code}:")
        if industry_sources:
            for src in industry_sources:
                print(f"  {src}")
        else:
            print(f"  [!] 没有找到行业信息")
            print(f"  可用的keys: {list(stock.keys())}")

# 检查评分文件中的行业信息
print("\n" + "="*80)
print("检查评分文件中的行业信息")
print("="*80)

score_file = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')
with open(score_file, 'r', encoding='utf-8') as f:
    score_data = json.load(f)

for code in test_codes:
    if code in score_data:
        stock = score_data[code]
        industry = stock.get('industry', 'N/A')
        matched = stock.get('matched_sector', 'N/A')
        print(f"\n{code}:")
        print(f"  industry字段: {industry}")
        print(f"  matched_sector: {matched}")

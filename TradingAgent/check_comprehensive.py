#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查comprehensive_stock_data.json
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
f = os.path.join(data_dir, 'comprehensive_stock_data.json')

if not os.path.exists(f):
    print(f"文件不存在: {f}")
    exit(1)

with open(f, 'r', encoding='utf-8') as file:
    data = json.load(file)

print(f"comprehensive_stock_data.json 总数: {len(data)}")

if len(data) > 0:
    sample = list(data.values())[0]
    print(f"\n第一个股票示例:")
    print(f"  keys: {list(sample.keys())}")
    if 'industry_concept' in sample:
        ic = sample['industry_concept']
        print(f"  industry_concept.industry: {ic.get('industry', 'N/A')}")
        print(f"  industry_concept.industry_name: {ic.get('industry_name', 'N/A')}")
        print(f"  industry_concept keys: {list(ic.keys())}")
    if 'basic_info' in sample:
        bi = sample['basic_info']
        print(f"  basic_info.industry: {bi.get('industry', 'N/A')}")
        print(f"  basic_info keys: {list(bi.keys())}")

# 检查主板股票的行业信息
print("\n主板股票行业信息:")
for code, stock in list(data.items())[:20]:
    if code.startswith(('600', '601', '603', '000', '001', '002')):
        industry = '未知'
        if 'industry_concept' in stock:
            ic = stock['industry_concept']
            industry = ic.get('industry') or ic.get('industry_name') or industry
        print(f"  {code}: {industry}")

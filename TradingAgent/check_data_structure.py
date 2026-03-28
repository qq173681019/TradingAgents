#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 comprehensive_stock_data.json 的真实结构
"""
import json
import os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

# 检查第一只股票的结构
first_code = list(comp_data['stocks'].keys())[0]
first_stock = comp_data['stocks'][first_code]

print(f"第一只股票 {first_code} 的结构:")
print(f"顶层keys: {list(first_stock.keys())}")

if 'basic_info' in first_stock:
    print(f"\nbasic_info keys: {list(first_stock['basic_info'].keys())}")
    print(f"basic_info内容: {first_stock['basic_info']}")

if 'financial_data' in first_stock:
    print(f"\nfinancial_data keys: {list(first_stock['financial_data'].keys())[:10]}")

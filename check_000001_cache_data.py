#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接测试generate_investment_advice函数的改进
"""
import sys
sys.path.insert(0, '.')

# 使用直接代码片段，避免import整个文件
code = """
# 测试智能模拟数据生成
import json

# 先检查是否能从comprehensive_stock_data_part_11.json中读取000001的数据
with open('data/comprehensive_stock_data_part_11.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

if isinstance(data, dict):
    if 'data' in data:
        stocks = data['data']
    elif 'stocks' in data:
        stocks = data['stocks']
    else:
        stocks = data
else:
    stocks = {}

if '000001' in stocks:
    stock_data = stocks['000001']
    print('找到000001缓存数据:')
    print(json.dumps(stock_data, indent=2, ensure_ascii=False)[:1000])
    print('...(truncated)')
else:
    print('000001不在part_11中')
"""

# 执行代码
exec(code)

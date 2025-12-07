#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查000001的缓存数据结构
"""
import json

data = json.load(open('data/comprehensive_stock_data_part_11.json', encoding='utf-8'))
stocks = data['stocks']
stock_000001 = stocks['000001']

print("000001 所有顶级字段:")
for key in stock_000001.keys():
    val = stock_000001[key]
    print(f"  {key}: {type(val).__name__} ", end="")
    if isinstance(val, dict):
        print(f"(keys: {list(val.keys())[:5]}{'...' if len(val) > 5 else ''})")
    elif isinstance(val, list):
        print(f"(length: {len(val)})")
    elif val is None:
        print("(None)")
    else:
        print(f"(value: {str(val)[:50]}...)")

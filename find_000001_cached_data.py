#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单复现000001批量评分计算，不涉及GUI初始化
"""
import json
import sys

# 直接读取缓存数据，看看000001的原始tech和fund数据是什么
with open('data/comprehensive_stock_data_part_1.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 找000001
for stock_code, stock_data in data.items():
    if '000001' in stock_code:
        print(f"找到: {stock_code}")
        print(json.dumps(stock_data, ensure_ascii=False, indent=2))
        break
else:
    print("在part_1中未找到000001，尝试其他part...")
    
    # 尝试其他part文件
    for part_num in range(2, 25):
        try:
            filename = f'data/comprehensive_stock_data_part_{part_num}.json'
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for stock_code, stock_data in data.items():
                if '000001' in stock_code:
                    print(f"找到: {stock_code} (在{filename}中)")
                    print(json.dumps(stock_data, ensure_ascii=False, indent=2))
                    break
            else:
                continue
            break
        except FileNotFoundError:
            continue

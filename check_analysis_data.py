#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查分析结果文件结构
"""
import json
import os

data_dir = 'data'
found_000015 = False

for file in os.listdir(data_dir):
    if 'stock_analysis_results_part' in file and file.endswith('.json'):
        print(f'检查文件: {file}')
        try:
            with open(os.path.join(data_dir, file), 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f'  顶层键: {list(data.keys())}')
            
            # 查找000015数据
            if 'data' in data and '000015' in data['data']:
                print(f'  ✅ 找到000015数据！')
                stock_data = data['data']['000015']
                print(f'  000015的键: {list(stock_data.keys())}')
                
                # 查看期间数据
                if 'short_term' in stock_data:
                    print(f'    short_term: {stock_data["short_term"]}')
                else:
                    print(f'    ❌ 没有short_term字段')
                
                if 'medium_term' in stock_data:
                    print(f'    medium_term: {stock_data["medium_term"]}')
                else:
                    print(f'    ❌ 没有medium_term字段')
                
                if 'long_term' in stock_data:
                    print(f'    long_term: {stock_data["long_term"]}')
                else:
                    print(f'    ❌ 没有long_term字段')
                
                found_000015 = True
                break
        except Exception as e:
            print(f'  错误: {e}')

if not found_000015:
    print('❌ 在分析结果文件中没有找到000015数据')

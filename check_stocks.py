#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import json
import os

# 搜索所有数据文件中是否包含这些股票
search_codes = ['002917', '002918', '002919', '002920', '002921']
found_stocks = {}

part_files = glob.glob(os.path.join('data', 'comprehensive_stock_data_part_*.json'))
print(f'检查 {len(part_files)} 个数据文件...')

for path in part_files:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'stocks' in data:
            stocks = data['stocks']
            for code in search_codes:
                if code in stocks:
                    found_stocks[code] = {
                        'file': os.path.basename(path),
                        'name': stocks[code].get('basic_info', {}).get('name', '未知'),
                        'industry': stocks[code].get('basic_info', {}).get('industry', '未知')
                    }
    except Exception as e:
        print(f'读取文件失败 {path}: {e}')

print(f'\n搜索结果:')
for code in search_codes:
    if code in found_stocks:
        info = found_stocks[code]
        print(f'{code}: {info["name"]} ({info["industry"]}) - 在 {info["file"]}')
    else:
        print(f'{code}: 未找到')

print(f'\n总计找到: {len(found_stocks)}/{len(search_codes)} 只股票')
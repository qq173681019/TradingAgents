#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查所有comprehensive_stock_data_part文件中是否有000001
"""
import json
import glob
import os

data_dir = 'data'
base_name = 'comprehensive_stock_data'
part_pattern = os.path.join(data_dir, f"{base_name}_part_*.json")
part_files = sorted(glob.glob(part_pattern))

print(f"找到 {len(part_files)} 个分卷文件")
print("=" * 80)

total_stocks = 0
found_000001 = False

for filepath in part_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 处理可能包含的data或stocks键
        if isinstance(data, dict):
            if 'data' in data and isinstance(data['data'], dict):
                stocks = data['data']
            elif 'stocks' in data and isinstance(data['stocks'], dict):
                stocks = data['stocks']
            else:
                stocks = data
        else:
            stocks = {}
        
        stock_count = len(stocks)
        total_stocks += stock_count
        
        # 检查000001
        if '000001' in stocks:
            found_000001 = True
            print(f"✓ {os.path.basename(filepath)}: {stock_count} 只 【包含000001】")
            print(f"  000001数据长度: {len(str(stocks['000001']))}")
        else:
            # 显示第一只和最后一只股票代码
            codes = list(stocks.keys())
            if codes:
                print(f"  {os.path.basename(filepath)}: {stock_count} 只 (范围: {codes[0]} ~ {codes[-1]})")
            else:
                print(f"  {os.path.basename(filepath)}: {stock_count} 只")
    
    except Exception as e:
        print(f"✗ {os.path.basename(filepath)}: 加载失败 - {e}")

print("=" * 80)
print(f"总计: {total_stocks} 只股票")
if found_000001:
    print("✓ 000001 已找到！")
else:
    print("✗ 000001 未找到")

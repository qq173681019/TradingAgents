#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

files = ['data/batch_stock_scores_minimax.json', 'data/batch_stock_scores_none.json']

print("=" * 80)
print("检查批量评分文件中000001的数据")
print("=" * 80)

for f in files:
    try:
        print(f'\n检查文件: {f}')
        with open(f, encoding='utf-8') as file:
            data = json.load(file)
            scores = data.get('scores', {})
            if '000001' in scores:
                print(f'✓ 找到000001')
                d = scores['000001']
                print(f'  综合评分: {d.get("score", "N/A")}')
                print(f'  短期评分: {d.get("short_term_score", "N/A")}')
                print(f'  中期评分: {d.get("medium_term_score", "N/A")}')
                print(f'  长期评分: {d.get("long_term_score", "N/A")}')
                break
            else:
                print(f'  ✗ 未找到000001')
    except Exception as e:
        print(f'  读取失败: {e}')

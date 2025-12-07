#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查批量评分文件中000001的数据
"""

import json
import os

# 找到最新的评分文件
batch_files = [
    'data/batch_scores.json',
    'data/batch_scores_deepseek.json',
    'data/batch_scores_minimax.json',
    'data/batch_scores_openai.json'
]

print("=" * 80)
print("检查批量评分文件中000001的数据")
print("=" * 80)

for f in batch_files:
    if os.path.exists(f):
        print(f'\n检查文件: {f}')
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                scores = data.get('scores', {})
                if '000001' in scores:
                    print(f'✅ 找到000001!')
                    print(f'完整数据:')
                    import json
                    print(json.dumps(scores['000001'], indent=2, ensure_ascii=False))
                    
                    # 提取关键信息
                    score = scores['000001'].get('score', 'N/A')
                    short = scores['000001'].get('short_term_score', 'N/A')
                    medium = scores['000001'].get('medium_term_score', 'N/A')
                    long = scores['000001'].get('long_term_score', 'N/A')
                    
                    print(f'\n关键信息:')
                    print(f'  综合评分: {score}')
                    print(f'  短期评分: {short}')
                    print(f'  中期评分: {medium}')
                    print(f'  长期评分: {long}')
                    break
        except Exception as e:
            print(f'  读取失败: {e}')
else:
    print('\n❌ 在任何文件中都没有找到000001')
    print('\n检查是否存在这些文件:')
    for f in batch_files:
        exists = "✅" if os.path.exists(f) else "❌"
        print(f'  {exists} {f}')

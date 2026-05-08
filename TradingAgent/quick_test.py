#!/usr/bin/env python3
import json

print("开始快速测试...")

try:
    with open('batch_stock_scores_optimized_主板_20260504_192632.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"加载了 {len(data)} 只股票")
    
    # 找评分最高的3只股票
    stocks = []
    for code, info in data.items():
        score = info.get('short_term_score', 5.0)
        name = info.get('name', '')
        stocks.append({'code': code, 'name': name, 'score': score})
    
    stocks.sort(key=lambda x: x['score'], reverse=True)
    top3 = stocks[:3]
    
    print("TOP3 推荐股票:")
    for i, stock in enumerate(top3, 1):
        print(f"{i}. {stock['name']}({stock['code']}): {stock['score']:.2f}分")
        
except Exception as e:
    print(f"失败: {e}")
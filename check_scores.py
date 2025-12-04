import json

# 加载评分数据
with open('data/batch_stock_scores_none.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

scores = data['scores']

print(f"总股票数: {len(scores)}")
print(f"\n评分区间分布:")
print(f"=" * 50)

# 1-3分
range_1_3 = [s for s in scores.values() if 1 <= s.get('overall_score', 10) < 3]
print(f"1-3分:   {len(range_1_3):4d} 只股票")

# 3-6分
range_3_6 = [s for s in scores.values() if 3 <= s.get('overall_score', 10) < 6]
print(f"3-6分:   {len(range_3_6):4d} 只股票")

# 6-9分
range_6_9 = [s for s in scores.values() if 6 <= s.get('overall_score', 10) < 9]
print(f"6-9分:   {len(range_6_9):4d} 只股票")

# 9分以上
range_9_plus = [s for s in scores.values() if s.get('overall_score', 10) >= 9]
print(f"9分以上: {len(range_9_plus):4d} 只股票")

print(f"=" * 50)
print(f"合计:    {len(range_1_3) + len(range_3_6) + len(range_6_9) + len(range_9_plus):4d} 只股票")

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接调用get_stock_score_for_batch来看000001的DEBUG输出
"""
import sys
import json
sys.path.insert(0, r'c:\Users\龚若兰\Documents\GitHub\TradingAgents')

# 直接运行score计算
from a_share_gui_compatible import AShareAnalyzerGUI

# 创建分析器实例（无GUI模式）
analyzer = AShareAnalyzerGUI(root=None)

print("=" * 80)
print("直接测试000001的批量评分计算")
print("=" * 80)

# 直接调用generate_investment_advice看看返回值
print("\n1. 测试generate_investment_advice():")
print("-" * 80)

short_pred = analyzer.generate_investment_advice('000001', period_type='短期')
print(f"短期返回: {json.dumps(short_pred, ensure_ascii=False, indent=2)}")

medium_pred = analyzer.generate_investment_advice('000001', period_type='中期')
print(f"\n中期返回: {json.dumps(medium_pred, ensure_ascii=False, indent=2)}")

long_pred = analyzer.generate_investment_advice('000001', period_type='长期')
print(f"\n长期返回: {json.dumps(long_pred, ensure_ascii=False, indent=2)}")

print("\n2. 调用get_stock_score_for_batch():")
print("-" * 80)
score = analyzer.get_stock_score_for_batch('000001')
print(f"最终批量评分: {score}")

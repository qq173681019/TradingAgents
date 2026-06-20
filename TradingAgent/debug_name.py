#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug 688503 name issue"""
import json, os, sys
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingAgent')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')

# Load
scores = json.load(open(r'D:\GitHub\TradingAgents\TradingShared\data\batch_stock_scores_optimized_主板_20260601_204416.json', encoding='utf-8'))
name_map = json.load(open(r'D:\GitHub\TradingAgents\TradingShared\data\stock_info_fallback.json', encoding='utf-8'))

# Import the function
from daily_recommender_v28 import get_stock_name, load_stock_names

# Test
code = '688503'
print(f"scores has {code}: {code in scores}")
print(f"scores name: {scores.get(code, {}).get('name', 'N/A')}")
print(f"name_map has {code}: {code in name_map}")
print(f"name_map name: {name_map.get(code, {}).get('name', 'N/A')}")

# Use the actual function
nm = load_stock_names()
print(f"load_stock_names() count: {len(nm)}")
print(f"load_stock_names has {code}: {code in nm}")
result = get_stock_name(code, scores, nm)
print(f"get_stock_name result: '{result}'")

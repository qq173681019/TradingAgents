#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新stock_info_fallback.json - 用AKShare补全股票名称"""
import json, os
import akshare as ak

DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
fallback_file = os.path.join(DATA_DIR, 'stock_info_fallback.json')

# 加载现有数据
if os.path.exists(fallback_file):
    with open(fallback_file, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    print(f"现有记录: {len(existing)}")
else:
    existing = {}

# 从AKShare获取A股代码列表
try:
    df = ak.stock_info_a_code_name()
    print(f"AKShare返回: {len(df)} 只股票")
    
    added = 0
    updated = 0
    for _, row in df.iterrows():
        code = str(row.get('code', '')).strip()
        name = str(row.get('name', '')).strip()
        if not code or not name:
            continue
        
        if code in existing:
            if existing[code].get('name', '') != name:
                existing[code]['name'] = name
                updated += 1
        else:
            existing[code] = {'name': name, 'industry': '未知', 'concept': '未知', 'price': 0}
            added += 1
    
    print(f"新增: {added}, 更新: {updated}")
    print(f"总计: {len(existing)}")
    
    with open(fallback_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"已保存: {fallback_file}")
    
except Exception as e:
    print(f"AKShare失败: {e}")
    print("（东方财富API可能被封，稍后重试）")

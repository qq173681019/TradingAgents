#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复行业信息 - 更新 basic_info['industry']
"""
import json
import os
import time
import akshare as ak

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

stocks = comp_data['stocks']
test_codes = list(stocks.keys())[:100]  # 先测试100只

print(f'开始更新前100只股票的行业信息...')
print('='*70)

success = 0
failed = 0

for i, code in enumerate(test_codes, 1):
    try:
        # 获取个股信息
        df = ak.stock_individual_info_em(symbol=code)
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item = str(row.get('item', ''))
                if '行业' in item or '所属行业' in item or '申万行业' in item:
                    industry = row.get('value', '')
                    if industry and industry not in ['未知', '', 'None']:
                        # 更新 basic_info.industry
                        stocks[code]['basic_info']['industry'] = industry
                        success += 1
                        print(f'[OK] {code}: {industry}')
                        break
        
        time.sleep(0.1)  # 避免请求过快
        
        if i % 10 == 0:
            print(f'进度: {i}/100')
    
    except Exception as e:
        failed += 1
        if i <= 10:
            print(f'[WARN] {code}: {e}')

print(f'\n完成！成功: {success}/100, 失败: {failed}')

# 保存
with open(comp_file, 'w', encoding='utf-8') as f:
    json.dump(comp_data, f, ensure_ascii=False, indent=2)

print(f'\n已保存更新后的数据')

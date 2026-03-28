#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整更新所有股票的行业信息
预计耗时：30-40分钟
"""
import json
import os
import time
import akshare as ak
from datetime import datetime

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# 日志文件
log_file = os.path.join(os.path.dirname(__file__), 'industry_update_log.txt')

def log(msg):
    """记录日志"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

# 读取数据
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')

with open(comp_file, 'r', encoding='utf-8') as f:
    comp_data = json.load(f)

stocks = comp_data['stocks']
total = len(stocks)

log(f'开始更新 {total} 只股票的行业信息')
log('='*70)

success = 0
failed = 0
batch_size = 50

codes = list(stocks.keys())

for i in range(0, len(codes), batch_size):
    batch = codes[i:i+batch_size]
    
    for code in batch:
        try:
            # 获取个股信息
            df = ak.stock_individual_info_em(symbol=code)
            
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    item = str(row.get('item', ''))
                    if '行业' in item or '所属行业' in item or '申万行业' in item:
                        industry = row.get('value', '')
                        if industry and industry not in ['未知', '', 'None']:
                            # 更新
                            stocks[code]['basic_info']['industry'] = industry
                            success += 1
                            break
            
            time.sleep(0.08)  # 避免请求过快
        
        except Exception as e:
            failed += 1
    
    # 每批记录进度
    progress = min(i + batch_size, total)
    log(f'进度: {progress}/{total} ({progress/total*100:.1f}%) - 成功: {success}, 失败: {failed}')
    
    # 每200只保存一次
    if progress % 200 == 0:
        with open(comp_file, 'w', encoding='utf-8') as f:
            json.dump(comp_data, f, ensure_ascii=False, indent=2)
        log(f'已保存进度（每200只保存一次）')

# 最终保存
with open(comp_file, 'w', encoding='utf-8') as f:
    json.dump(comp_data, f, ensure_ascii=False, indent=2)

log('='*70)
log(f'完成！成功: {success}/{total}, 失败: {failed}')
log(f'数据已保存到: {os.path.basename(comp_file)}')

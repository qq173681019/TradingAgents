#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时脚本：使用之前的评分数据生成推荐
"""
import csv
import json
import os
import sys

# 读取之前成功生成的评分数据（209只股票）
data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
file_path = os.path.join(data_dir, 'batch_stock_scores_optimized_主板_20260327_015453.json')

print(f'使用评分文件: {os.path.basename(file_path)}')

with open(file_path, 'r', encoding='utf-8') as f:
    stocks = json.load(f)

print(f'股票总数: {len(stocks)}')

desktop_path = os.path.join(os.environ['USERPROFILE'], 'Desktop')

# 临时权重配置（数据缺失，只使用技术面+筹码面）
weight_configs = [
    {
        'name': '短线',
        'filename': '推荐_短线.csv',
        'desc': '技术面60% + 筹码40%（临时配置，数据缺失）',
        'tech': 0.6,
        'fund': 0.0,
        'chip': 0.4,
        'sector': 0.0
    },
    {
        'name': '长线',
        'filename': '推荐_长线.csv',
        'desc': '技术面40% + 筹码60%（临时配置，数据缺失）',
        'tech': 0.4,
        'fund': 0.0,
        'chip': 0.6,
        'sector': 0.0
    }
]

print('\n正在根据新权重配置计算综合评分...\n')

for config in weight_configs:
    print(f"【{config['name']}推荐】")
    print(f"  权重配置: {config['desc']}")
    
    # 计算所有股票的综合评分
    scored_stocks = []
    for code, data in stocks.items():
        tech_score = data.get('short_term_score', 5.0)
        fund_score = data.get('long_term_score', 5.0)
        chip_score = data.get('chip_score', 5.0)
        hot_sector_score = data.get('hot_sector_score', 5.0)
        industry = data.get('industry', '未知')
        
        # 归一化权重
        total_weight = config['tech'] + config['fund'] + config['chip'] + config['sector']
        tech_w = config['tech'] / total_weight
        fund_w = config['fund'] / total_weight
        chip_w = config['chip'] / total_weight
        sector_w = config['sector'] / total_weight
        
        # 计算加权评分
        score = (tech_score * tech_w + 
                fund_score * fund_w + 
                chip_score * chip_w + 
                hot_sector_score * sector_w)
        
        scored_stocks.append({
            'code': code,
            'name': data.get('name', 'N/A'),
            'score': round(score, 2),
            'tech': tech_score,
            'fund': fund_score,
            'chip': chip_score,
            'hot_sector': hot_sector_score,
            'industry': industry,
            'matched_sector': data.get('matched_sector', '-'),
            'sector_change': data.get('sector_change', 0)
        })
    
    # 按评分排序，取前10名
    scored_stocks.sort(key=lambda x: x['score'], reverse=True)
    top_10 = scored_stocks[:10]
    
    # 导出CSV到桌面
    csv_path = os.path.join(desktop_path, config['filename'])
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['股票代码', '股票名称', '综合评分', '技术面', '基本面', '筹码面', '热门板块', '所属行业', '匹配板块', '板块涨幅%'])
        for stock in top_10:
            writer.writerow([
                stock['code'],
                stock['name'],
                stock['score'],
                stock['tech'],
                stock['fund'],
                stock['chip'],
                stock['hot_sector'],
                stock['industry'],
                stock['matched_sector'],
                f"{stock['sector_change']:+.2f}" if stock['sector_change'] else '-'
            ])
    
    print(f"  [OK] 已导出前10名到桌面: {config['filename']}")
    print(f"  前5名: ", end='')
    for i, stock in enumerate(top_10[:5]):
        if i > 0:
            print(", ", end='')
        print(f"{stock['code']} {stock['name']}({stock['score']:.2f})", end='')
    print('\n')

print('='*50)
print('[OK] 全部导出任务完成！')
print(f'文件位置: {desktop_path}')
print('='*50)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
供 BAT 文件调用
"""
import csv
import json
import os
import sys
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if __name__ == '__main__':
    try:
        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        # 查找最新的主板评分文件
        score_files = sorted([f for f in os.listdir(data_dir) 
                             if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')], 
                            reverse=True)
        
        if not score_files:
            print('错误：未找到主板评分文件')
            sys.exit(1)
        
        latest_score_file = score_files[0]
        print(f'使用评分文件: {latest_score_file}')
        
        # 加载评分数据
        with open(os.path.join(data_dir, latest_score_file), 'r', encoding='utf-8') as f:
            scores = json.load(f)
        
        # 按综合评分排序，取前10只
        sorted_stocks = sorted(scores.items(), 
                             key=lambda x: x[1].get('score', 0) if isinstance(x[1], dict) else 0, 
                             reverse=True)[:10]
        
        # 导出CSV
        download_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
        csv_filename = f'主板推荐股票_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        csv_path = os.path.join(download_folder, csv_filename)
        
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['股票代码', '股票名称', '综合得分', '技术面评分', '基本面评分', '筹码评分'])
            
            for code, data in sorted_stocks:
                if isinstance(data, dict):
                    writer.writerow([
                        code,
                        data.get('name', ''),
                        round(data.get('score', 0), 2),
                        round(data.get('short_term_score', 0), 2) if data.get('short_term_score') else '',
                        round(data.get('long_term_score', 0), 2) if data.get('long_term_score') else '',
                        round(data.get('chip_score', 0), 2) if data.get('chip_score') else ''
                    ])
        
        print(f'CSV文件已导出到: {csv_path}')
        print(f'共导出 {len(sorted_stocks)} 只推荐股票')
        
    except Exception as e:
        print(f'导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

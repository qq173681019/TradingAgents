#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
供 BAT 文件调用 - 复用 a_share_gui_compatible.py 的导出逻辑
"""
import csv
import json
import os
import sys
from datetime import datetime

if __name__ == '__main__':
    try:
        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        # 查找最新的主板评分文件
        print('正在查找评分文件...')
        score_files = [f for f in os.listdir(data_dir) 
                      if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')]
        if not score_files:
            print('错误：未找到主板评分文件')
            sys.exit(1)
        
        latest_file = max(score_files)
        file_path = os.path.join(data_dir, latest_file)
        print(f'使用评分文件: {latest_file}')
        
        # 加载评分数据
        with open(file_path, 'r', encoding='utf-8') as f:
            scores = json.load(f)
        
        desktop_path = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        
        # 定义导出配置：(文件名, 排序字段, 显示名称)
        export_configs = [
            ('推荐_综合.csv', 'score', '综合评分'),
            ('推荐_筹码.csv', 'chip_score', '筹码评分'),
            ('推荐_技术.csv', 'short_term_score', '技术面评分')
        ]
        
        for filename, sort_key, display_name in export_configs:
            print(f'正在导出: {display_name}...')
            
            # 按对应字段排序，取前10只
            sorted_stocks = sorted(scores.items(), key=lambda x: x[1].get(sort_key, 0), reverse=True)[:10]
            
            # 转换为推荐格式
            recommendations = [{'code': code, **data} for code, data in sorted_stocks]
            
            # 导出CSV
            csv_path = os.path.join(desktop_path, filename)
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                for stock in recommendations:
                    writer.writerow([stock['code']])
            
            print(f'  ✅ {display_name}已导出到: {filename} (共 {len(recommendations)} 只)')
        
        print('\n全部导出任务完成！')
        
    except Exception as e:
        print(f'❌ 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

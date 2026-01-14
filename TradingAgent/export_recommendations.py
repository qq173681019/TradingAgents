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
        
        # 按综合评分排序，取前10只
        sorted_stocks = sorted(scores.items(), key=lambda x: x[1].get('score', 0), reverse=True)[:10]
        
        # 转换为推荐格式
        last_recommendations = [{'code': code, **data} for code, data in sorted_stocks]
        print(f'已选出前 {len(last_recommendations)} 只推荐股票')
        
        # 导出CSV - 复用 a_share_gui_compatible.py 中 export_last_recommendations_to_csv 的逻辑
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f'主板推荐股票_{timestamp}.csv'
        csv_path = os.path.join(data_dir, csv_filename)
        
        # 导出股票代码（与 GUI 的 export_last_recommendations_to_csv 方法完全一致）
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            # 只写入股票代码
            for stock in last_recommendations:
                writer.writerow([stock['code']])
        
        print(f'✅ CSV文件已导出到: {csv_path}')
        print(f'📊 共导出 {len(last_recommendations)} 只推荐股票')
        
    except Exception as e:
        print(f'❌ 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

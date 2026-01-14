#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板股票评分
供 BAT 文件调用 - 直接加载数据并计算评分
"""
import json
import os
import sys
import time
from datetime import datetime

# 导入主程序
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if __name__ == '__main__':
    try:
        print('[步骤 2/3] 正在生成主板评分...')
        
        # 加载综合股票数据
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        print('正在加载股票评分数据...')
        # 加载 batch_stock_scores_none.json（包含所有股票的评分数据）
        score_file = os.path.join(data_dir, 'batch_stock_scores_none.json')
        if not os.path.exists(score_file):
            score_file = os.path.join(data_dir, 'batch_stock_scores.json')
        
        if not os.path.exists(score_file):
            print('错误：没有找到股票评分数据文件')
            sys.exit(1)
        
        with open(score_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 处理可能的两种数据格式
            if isinstance(data, dict) and 'scores' in data:
                all_stocks = data['scores']
            else:
                all_stocks = data
        
        if not all_stocks:
            print('错误：没有找到股票数据')
            sys.exit(1)
        
        # 过滤主板股票
        main_board_stocks = {
            code: data for code, data in all_stocks.items()
            if code.startswith(('600', '601', '603', '000', '001', '002'))
        }
        print(f'主板股票总数: {len(main_board_stocks)} 只')
        
        # 导入评分函数（简化版，直接计算）
        from a_share_gui_compatible import AShareAnalyzerGUI

        # 创建临时实例用于访问静态计算方法
        print('正在计算综合评分...')
        count = 0
        start_time = time.time()
        
        # 权重配置（与 GUI 默认值一致）
        tech_weight = 0.3
        fund_weight = 0.3
        chip_weight = 0.3
        hot_sector_weight = 0.1
        
        for code, data in main_board_stocks.items():
            # 提取各维度分数
            tech_score = data.get('short_term_score', 5.0)
            fund_score = data.get('long_term_score', 5.0)
            chip_score = data.get('chip_score', 5.0)
            hot_sector_score = data.get('hot_sector_score', 5.0)
            
            # 计算综合评分（使用简单加权平均）
            score = (tech_score * tech_weight + 
                    fund_score * fund_weight + 
                    chip_score * chip_weight + 
                    hot_sector_score * hot_sector_weight) / (tech_weight + fund_weight + chip_weight + hot_sector_weight)
            
            data['overall_score'] = round(score, 2)
            data['score'] = round(score, 2)
            count += 1
        
        elapsed = time.time() - start_time
        print(f'完成 {count} 只股票评分，耗时 {elapsed:.2f}秒')
        
        # 显示前5只股票的分数
        sorted_stocks = sorted(main_board_stocks.items(), key=lambda x: x[1].get('score', 0), reverse=True)[:5]
        print('\n前5只推荐股票:')
        for code, data in sorted_stocks:
            print(f"  {code}: {data.get('name', 'N/A')} - 综合分={data.get('score', 0):.2f}")
        
        # 保存主板评分结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(data_dir, f'batch_stock_scores_optimized_主板_{timestamp}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(main_board_stocks, f, ensure_ascii=False, indent=2)
        
        print(f'\n✅ 主板评分数据已保存到: {os.path.basename(output_file)}')
        print(f'📊 共评分 {len(main_board_stocks)} 只主板股票')
        
    except Exception as e:
        print(f'❌ 评分失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

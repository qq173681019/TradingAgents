#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
供 BAT 文件调用 - 根据4种权重配置计算综合评分，取前10名导出到桌面
"""
import csv
import json
import os
import sys
from datetime import datetime


def calculate_weighted_score(tech_score, fund_score, chip_score, hot_sector_score, 
                             tech_weight, fund_weight, chip_weight, hot_sector_weight):
    """
    计算加权综合评分
    
    Args:
        tech_score: 技术面评分 (1-10)
        fund_score: 基本面评分 (1-10)
        chip_score: 筹码面评分 (1-10)
        hot_sector_score: 热门板块评分 (1-10)
        tech_weight: 技术面权重
        fund_weight: 基本面权重
        chip_weight: 筹码面权重
        hot_sector_weight: 热门板块权重
    
    Returns:
        综合评分 (1-10分制)
    """
    try:
        # 确保分数在1-10范围内
        tech_score = max(1.0, min(10.0, float(tech_score)))
        fund_score = max(1.0, min(10.0, float(fund_score)))
        chip_score = max(1.0, min(10.0, float(chip_score)))
        hot_sector_score = max(1.0, min(10.0, float(hot_sector_score)))
        
        # 归一化权重
        total_weight = tech_weight + fund_weight + chip_weight + hot_sector_weight
        if total_weight > 0:
            tech_weight /= total_weight
            fund_weight /= total_weight
            chip_weight /= total_weight
            hot_sector_weight /= total_weight
        else:
            return 5.0
        
        # 计算加权评分
        score = (tech_score * tech_weight + 
                fund_score * fund_weight + 
                chip_score * chip_weight + 
                hot_sector_score * hot_sector_weight)
        
        # 确保结果在1-10范围内
        score = max(1.0, min(10.0, score))
        
        return round(score, 2)
    except Exception as e:
        print(f"评分计算错误: {e}")
        return 5.0


if __name__ == '__main__':
    try:
        print('[步骤 3/3] 正在根据不同权重配置生成推荐并导出到桌面...\n')
        
        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        # 查找最新的主板评分文件
        print('正在查找主板基础评分文件...')
        score_files = [f for f in os.listdir(data_dir) 
                      if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')]
        if not score_files:
            print('错误：未找到主板评分文件')
            print('请先运行「仅生成主板评分.bat」')
            sys.exit(1)
        
        latest_file = max(score_files)
        file_path = os.path.join(data_dir, latest_file)
        print(f'使用评分文件: {latest_file}\n')
        
        # 加载评分数据
        with open(file_path, 'r', encoding='utf-8') as f:
            stocks = json.load(f)
        
        desktop_path = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        
        # 定义4种权重配置
        weight_configs = [
            {
                'name': '综合',
                'filename': '推荐_综合.csv',
                'tech': 0.35,
                'fund': 0.2,
                'chip': 0.4,
                'hot': 0.05
            },
            {
                'name': '基本',
                'filename': '推荐_基本.csv',
                'tech': 0.1,
                'fund': 0.45,
                'chip': 0.4,
                'hot': 0.05
            },
            {
                'name': '筹码',
                'filename': '推荐_筹码.csv',
                'tech': 0.1,
                'fund': 0.1,
                'chip': 0.7,
                'hot': 0.1
            },
            {
                'name': '技术',
                'filename': '推荐_技术.csv',
                'tech': 0.8,
                'fund': 0.1,
                'chip': 0.1,
                'hot': 0.0
            }
        ]
        
        # 为每种权重配置计算评分并导出前10名
        for config in weight_configs:
            print(f"【{config['name']}配置】")
            print(f"  权重: 技术{config['tech']:.0%} + 基本{config['fund']:.0%} + "
                  f"筹码{config['chip']:.0%} + 热门板块{config['hot']:.0%}")
            
            # 计算所有股票的综合评分
            scored_stocks = []
            for code, data in stocks.items():
                tech_score = data.get('short_term_score', 5.0)
                fund_score = data.get('long_term_score', 5.0)
                chip_score = data.get('chip_score', 5.0)
                hot_sector_score = data.get('hot_sector_score', 5.0)
                
                # 计算该配置下的综合评分
                score = calculate_weighted_score(
                    tech_score, fund_score, chip_score, hot_sector_score,
                    config['tech'], config['fund'], config['chip'], config['hot']
                )
                
                scored_stocks.append({
                    'code': code,
                    'name': data.get('name', 'N/A'),
                    'score': score,
                    'tech': tech_score,
                    'fund': fund_score,
                    'chip': chip_score,
                    'hot': hot_sector_score
                })
            
            # 按评分排序，取前10名
            scored_stocks.sort(key=lambda x: x['score'], reverse=True)
            top_10 = scored_stocks[:10]
            
            # 导出CSV到桌面
            csv_path = os.path.join(desktop_path, config['filename'])
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                # 写入表头
                writer.writerow(['股票代码', '股票名称', '综合评分', '技术面', '基本面', '筹码面', '热门板块'])
                # 写入数据
                for stock in top_10:
                    writer.writerow([
                        stock['code'],
                        stock['name'],
                        stock['score'],
                        stock['tech'],
                        stock['fund'],
                        stock['chip'],
                        stock['hot']
                    ])
            
            print(f"  [OK] 已导出前10名到桌面: {config['filename']}")
            print(f"  前3名: ", end='')
            for i, stock in enumerate(top_10[:3]):
                if i > 0:
                    print(", ", end='')
                print(f"{stock['code']}({stock['score']:.2f})", end='')
            print('\n')
        
        print('='*50)
        print('[OK] 全部导出任务完成！')
        print(f'📁 文件位置: {desktop_path}')
        print('='*50)
        
    except Exception as e:
        print(f'[FAIL] 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

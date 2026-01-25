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
import csv
from datetime import datetime

# 导入主程序
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def calculate_weighted_score(tech_score, fund_score, chip_score, hot_sector_score, 
                             tech_weight, fund_weight, chip_weight, hot_sector_weight):
    """
    使用与 a_share_gui_compatible.py 一致的评分计算逻辑
    
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


def export_to_csv(stocks_data, output_file, weight_name):
    """
    导出股票数据到CSV文件
    
    Args:
        stocks_data: 股票数据字典 {code: data}
        output_file: 输出文件路径
        weight_name: 权重配置名称
    """
    try:
        # 按评分降序排序
        sorted_stocks = sorted(stocks_data.items(), 
                              key=lambda x: x[1].get('score', 0), 
                              reverse=True)
        
        # 写入CSV
        with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                '股票代码', '股票名称', '综合评分', 
                '技术面评分', '基本面评分', '筹码面评分', '热门板块评分',
                '权重配置'
            ])
            
            # 写入数据
            for code, data in sorted_stocks:
                writer.writerow([
                    code,
                    data.get('name', 'N/A'),
                    data.get('score', 0),
                    data.get('short_term_score', 5.0),
                    data.get('long_term_score', 5.0),
                    data.get('chip_score', 5.0),
                    data.get('hot_sector_score', 5.0),
                    weight_name
                ])
        
        print(f"  ✓ 已导出 {len(sorted_stocks)} 只股票到 {os.path.basename(output_file)}")
        
        # 显示前3只股票
        print(f"  前3名: ", end='')
        for i, (code, data) in enumerate(sorted_stocks[:3]):
            if i > 0:
                print(", ", end='')
            print(f"{code}({data.get('score', 0):.2f})", end='')
        print()
        
    except Exception as e:
        print(f"  ✗ CSV导出失败: {e}")
        import traceback
        traceback.print_exc()


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
        print(f'主板股票总数: {len(main_board_stocks)} 只\n')
        
        # 定义4种权重配置
        weight_configs = [
            {
                'name': '综合',
                'tech': 0.35,
                'fund': 0.2,
                'chip': 0.4,
                'hot': 0.05
            },
            {
                'name': '基本',
                'tech': 0.1,
                'fund': 0.45,
                'chip': 0.4,
                'hot': 0.05
            },
            {
                'name': '筹码',
                'tech': 0.1,
                'fund': 0.1,
                'chip': 0.7,
                'hot': 0.1
            },
            {
                'name': '技术',
                'tech': 0.8,
                'fund': 0.1,
                'chip': 0.1,
                'hot': 0.0
            }
        ]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 为每种权重配置计算评分并导出CSV
        for config in weight_configs:
            print(f"计算 [{config['name']}] 配置评分...")
            print(f"  权重: 技术{config['tech']:.0%}, 基本{config['fund']:.0%}, "
                  f"筹码{config['chip']:.0%}, 热门板块{config['hot']:.0%}")
            
            start_time = time.time()
            
            # 创建当前配置的股票数据副本
            config_stocks = {}
            
            for code, stock_data in main_board_stocks.items():
                # 复制股票数据
                config_stocks[code] = stock_data.copy()
                
                # 提取各维度分数
                tech_score = stock_data.get('short_term_score', 5.0)
                fund_score = stock_data.get('long_term_score', 5.0)
                chip_score = stock_data.get('chip_score', 5.0)
                hot_sector_score = stock_data.get('hot_sector_score', 5.0)
                
                # 使用与 GUI 一致的评分计算方法
                score = calculate_weighted_score(
                    tech_score, fund_score, chip_score, hot_sector_score,
                    config['tech'], config['fund'], config['chip'], config['hot']
                )
                
                config_stocks[code]['score'] = score
                config_stocks[code]['overall_score'] = score
            
            elapsed = time.time() - start_time
            print(f"  计算完成，耗时 {elapsed:.2f}秒")
            
            # 导出CSV
            csv_file = os.path.join(data_dir, f'主板推荐_{config["name"]}_{timestamp}.csv')
            export_to_csv(config_stocks, csv_file, config['name'])
            print()
        
        # 保存一份JSON格式（使用综合配置）
        print('保存JSON格式数据（综合配置）...')
        json_stocks = {}
        for code, stock_data in main_board_stocks.items():
            json_stocks[code] = stock_data.copy()
            tech_score = stock_data.get('short_term_score', 5.0)
            fund_score = stock_data.get('long_term_score', 5.0)
            chip_score = stock_data.get('chip_score', 5.0)
            hot_sector_score = stock_data.get('hot_sector_score', 5.0)
            
            score = calculate_weighted_score(
                tech_score, fund_score, chip_score, hot_sector_score,
                0.35, 0.2, 0.4, 0.05  # 综合配置
            )
            json_stocks[code]['score'] = score
            json_stocks[code]['overall_score'] = score
        
        output_file = os.path.join(data_dir, f'batch_stock_scores_optimized_主板_{timestamp}.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_stocks, f, ensure_ascii=False, indent=2)
        
        print(f'✅ JSON数据已保存到: {os.path.basename(output_file)}')
        print(f'\n📊 完成！共处理 {len(main_board_stocks)} 只主板股票')
        print(f'📁 输出文件位置: {data_dir}')
        
    except Exception as e:
        print(f'❌ 评分失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

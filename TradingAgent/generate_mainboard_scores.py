#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板股票基础评分数据  
供 BAT 文件调用 - 基于第1步已更新的数据重新计算评分
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
        print('[步骤 2/3] 正在重新计算主板股票基础评分...')
        print('说明：基于第1步更新的数据，重新计算技术面、基本面、筹码面评分')
        print('注意：使用已缓存的数据进行计算，不重新获取数据\n')
        
        # 导入主程序类
        print('正在初始化分析器...')
        # 创建分析器实例（无GUI）
        import tkinter as tk

        from a_share_gui_compatible import AShareAnalyzerGUI
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        analyzer = AShareAnalyzerGUI(root)
        
        # 加载综合股票数据
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        print('正在加载股票列表...')
        # 加载所有股票代码
        score_file = os.path.join(data_dir, 'batch_stock_scores_none.json')
        if not os.path.exists(score_file):
            score_file = os.path.join(data_dir, 'batch_stock_scores.json')
        
        if not os.path.exists(score_file):
            print('错误：没有找到股票数据文件')
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
        main_board_codes = [
            code for code in all_stocks.keys()
            if code.startswith(('600', '601', '603', '000', '001', '002'))
        ]
        print(f'主板股票总数: {len(main_board_codes)} 只\n')
        
        # 加载热门板块列表（从第1步保存的数据中）
        print('正在加载热门板块数据...')
        hot_sectors_list = set()
        if 'hot_sectors' in data:
            hot_sectors_list = set(data.get('hot_sectors', []))
            print(f'热门板块数量: {len(hot_sectors_list)} 个')
            if hot_sectors_list:
                print(f'热门板块: {", ".join(list(hot_sectors_list)[:10])}{"..." if len(hot_sectors_list) > 10 else ""}')
        else:
            print('⚠️  未找到热门板块数据，将使用默认评分5.0')
        
        # 重新计算每只股票的基础评分
        print('\n' + '='*60)
        print('开始重新计算评分（基于缓存数据）...')
        print('='*60)
        
        main_board_stocks = {}
        success_count = 0
        failed_count = 0
        start_time = time.time()
        
        for i, code in enumerate(main_board_codes, 1):
            try:
                # 显示进度
                if i % 50 == 0 or i == 1:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    print(f'进度: {i}/{len(main_board_codes)} ({i/len(main_board_codes)*100:.1f}%) '
                          f'- 速度: {rate:.1f}只/秒 - 成功: {success_count}, 失败: {failed_count}')
                
                # 获取股票名称
                stock_name = all_stocks[code].get('name', analyzer.get_stock_name(code) or 'N/A')
                
                # 调用完整的评分算法（使用缓存数据，即第1步更新的数据）
                # use_cache=True 表示使用第1步已经更新好的K线和基本面数据
                # 1. 技术面和基本面评分
                short_prediction, medium_prediction, long_prediction = analyzer.generate_investment_advice(code, use_cache=True)
                
                # 检查是否失败
                if short_prediction.get('failure_reason'):
                    failed_count += 1
                    if i % 100 == 0:
                        print(f'  {code} 失败: {short_prediction.get("failure_reason")}')
                    continue
                
                # 提取技术面和基本面评分
                tech_score = short_prediction.get('score', short_prediction.get('technical_score', 5.0))
                fund_score = long_prediction.get('score', long_prediction.get('fundamental_score', 5.0))
                
                # 2. 筹码面评分
                chip_score = 5.0  # 默认值
                if analyzer.chip_analyzer:
                    try:
                        chip_result = analyzer.chip_analyzer.analyze_stock(code)
                        if not chip_result.get('error') and chip_result.get('health_score', 0) > 0:
                            chip_score = chip_result.get('health_score', 5.0)
                    except Exception:
                        pass
                
                # 3. 热门板块评分（优化：不调用API，直接判断）
                hot_sector_score = 5.0  # 默认值
                if hot_sectors_list:
                    # 从第1步保存的数据中读取股票所属板块
                    stock_industry = all_stocks[code].get('industry', '')
                    # 判断股票所属板块是否在热门板块列表中
                    if stock_industry and any(hot in stock_industry for hot in hot_sectors_list):
                        hot_sector_score = 8.0  # 属于热门板块
                        if i <= 5:  # 前5个显示日志
                            print(f'  {code} 属于热门板块: {stock_industry}')
                    else:
                        hot_sector_score = 5.0  # 不属于热门板块
                
                # 保存详细评分数据
                stock_data = {
                    'code': code,
                    'name': stock_name,
                    'short_term_score': round(float(tech_score), 2),
                    'long_term_score': round(float(fund_score), 2),
                    'chip_score': round(float(chip_score), 2),
                    'hot_sector_score': round(float(hot_sector_score), 2),
                    'industry': all_stocks[code].get('industry', '')  # 保留板块信息
                }
                
                main_board_stocks[code] = stock_data
                success_count += 1
                
            except Exception as e:
                if i % 100 == 0:
                    print(f'  {code} 异常: {e}')
                failed_count += 1
                continue
        
        elapsed = time.time() - start_time
        print('\n' + '='*60)
        print(f'计算完成！耗时 {elapsed:.2f}秒')
        print(f'成功: {success_count} 只, 失败: {failed_count} 只')
        print(f'平均速度: {success_count/elapsed:.2f} 只/秒')
        print('='*60)
        
        # 显示评分分布统计
        if main_board_stocks:
            tech_scores = [s.get('short_term_score', 5.0) for s in main_board_stocks.values()]
            fund_scores = [s.get('long_term_score', 5.0) for s in main_board_stocks.values()]
            chip_scores = [s.get('chip_score', 5.0) for s in main_board_stocks.values()]
            
            print(f'\n评分统计:')
            print(f'  技术面: 平均 {sum(tech_scores)/len(tech_scores):.2f}')
            print(f'  基本面: 平均 {sum(fund_scores)/len(fund_scores):.2f}')
            print(f'  筹码面: 平均 {sum(chip_scores)/len(chip_scores):.2f}')
        
        # 保存主板基础评分数据
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(data_dir, f'batch_stock_scores_optimized_主板_{timestamp}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(main_board_stocks, f, ensure_ascii=False, indent=2)
        
        print(f'\n✅ 主板基础评分数据已保存到: {os.path.basename(output_file)}')
        print(f'📊 共计算 {len(main_board_stocks)} 只主板股票的基础评分数据')
        print(f'💡 下一步将根据不同权重配置计算综合评分并导出CSV到桌面')
        
        # 清理
        root.destroy()
        
    except Exception as e:
        print(f'❌ 评分计算失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f'❌ 评分失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

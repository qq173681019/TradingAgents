#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据批量更新脚本
供 BAT 文件调用
"""
import json
import os
import sys
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from TradingShared.api.comprehensive_data_collector import \
    ComprehensiveDataCollector

if __name__ == '__main__':
    collector = ComprehensiveDataCollector()
    collector.update_kline_data_only(batch_size=100, stock_type='主板', exclude_st=True)
    
    # 更新热门板块列表到 batch_stock_scores_none.json
    print('\n正在获取并保存热门板块信息...')
    try:
        # 获取热门板块
        import tkinter as tk

        from a_share_gui_compatible import AShareAnalyzerGUI
        
        root = tk.Tk()
        root.withdraw()
        analyzer = AShareAnalyzerGUI(root)
        
        # 获取热门板块列表（只获取一次）
        hot_sectors = []
        try:
            hot_sectors_data = analyzer._get_hot_sectors_from_tencent()
            if hot_sectors_data and 'sectors' in hot_sectors_data:
                hot_sectors = [s['name'] for s in hot_sectors_data['sectors'][:20]]  # 取前20个热门板块
                print(f'✓ 获取到 {len(hot_sectors)} 个热门板块')
        except Exception as e:
            print(f'⚠️  获取热门板块失败: {e}')
        
        # 加载并更新 batch_stock_scores_none.json
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        score_file = os.path.join(data_dir, 'batch_stock_scores_none.json')
        
        if os.path.exists(score_file):
            with open(score_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 添加热门板块信息
            data['hot_sectors'] = hot_sectors
            data['hot_sectors_update_time'] = datetime.now().isoformat()
            
            # 保存回文件
            with open(score_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f'✓ 热门板块信息已保存到 batch_stock_scores_none.json')
            if hot_sectors:
                print(f'  热门板块: {", ".join(hot_sectors[:5])}{"..." if len(hot_sectors) > 5 else ""}')
        else:
            print(f'⚠️  未找到 {score_file}')
        
        root.destroy()
        
    except Exception as e:
        print(f'⚠️  保存热门板块信息失败: {e}')
        import traceback
        traceback.print_exc()
    
    print('\nK线数据更新完成')
    print('\nK线数据更新完成')

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试股票获取和选择功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def test_stock_selection():
    """测试股票选择功能"""
    print("=" * 50)
    print("测试股票获取和质量排序功能")
    print("=" * 50)
    
    # 创建GUI实例
    root = tk.Tk()
    root.withdraw()  # 隐藏GUI窗口
    analyzer = AShareAnalyzerGUI(root)
    
    print("\n1. 测试主板股票获取...")
    try:
        main_board_stocks = analyzer.get_main_board_stocks_multi_source()
        print(f"✅ 获取到主板股票数量: {len(main_board_stocks)}")
        print(f"🔸 前10只股票: {main_board_stocks[:10]}")
        print(f"🔸 是否按质量排序: 前面的股票应该是大市值蓝筹股")
        
        # 验证前几只股票是否是知名大盘股
        top_stocks = main_board_stocks[:5]
        famous_stocks = ["600519", "600036", "000858", "601318", "000002"]  # 茅台、招行、五粮液、平安、万科
        overlap = set(top_stocks) & set(famous_stocks)
        print(f"🔸 前5只中的知名大盘股: {overlap}")
        
    except Exception as e:
        print(f"❌ 主板股票获取失败: {e}")
    
    print("\n2. 测试科创板股票获取...")
    try:
        kcb_stocks = analyzer.get_kcb_stocks_multi_source()
        print(f"✅ 获取到科创板股票数量: {len(kcb_stocks)}")
        print(f"🔸 前5只股票: {kcb_stocks[:5]}")
    except Exception as e:
        print(f"❌ 科创板股票获取失败: {e}")
    
    print("\n3. 测试创业板股票获取...")
    try:
        cyb_stocks = analyzer.get_cyb_stocks_multi_source()
        print(f"✅ 获取到创业板股票数量: {len(cyb_stocks)}")
        print(f"🔸 前5只股票: {cyb_stocks[:5]}")
    except Exception as e:
        print(f"❌ 创业板股票获取失败: {e}")
    
    print("\n4. 测试ETF获取...")
    try:
        etf_stocks = analyzer.get_etf_stocks_multi_source()
        print(f"✅ 获取到ETF数量: {len(etf_stocks)}")
        print(f"🔸 前5只ETF: {etf_stocks[:5]}")
    except Exception as e:
        print(f"❌ ETF获取失败: {e}")
    
    print("\n5. 测试总体股票池...")
    try:
        # 测试不同类型的股票获取
        main_stocks = analyzer.fetch_stock_list_from_api("main_board")
        print(f"✅ 主板股票池: {len(main_stocks)}只")
        
        kcb_stocks = analyzer.fetch_stock_list_from_api("kcb") 
        print(f"✅ 科创板股票池: {len(kcb_stocks)}只")
        
        cyb_stocks = analyzer.fetch_stock_list_from_api("cyb")
        print(f"✅ 创业板股票池: {len(cyb_stocks)}只")
        
        etf_stocks = analyzer.fetch_stock_list_from_api("etf")
        print(f"✅ ETF股票池: {len(etf_stocks)}只")
        
        total_stocks = len(main_stocks) + len(kcb_stocks) + len(cyb_stocks) + len(etf_stocks)
        print(f"🔸 总股票池大小: {total_stocks}只")
        
    except Exception as e:
        print(f"❌ 总体股票池获取失败: {e}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
    
    root.destroy()

if __name__ == "__main__":
    test_stock_selection()
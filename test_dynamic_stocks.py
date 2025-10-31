#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试动态股票池获取功能
"""

import sys
import time

# 导入主程序
sys.path.append('.')
from a_share_gui_compatible import AShareAnalyzerGUI

def test_dynamic_stock_pool():
    """测试动态股票池获取"""
    print("🔬 测试动态股票池获取系统")
    print("=" * 50)
    
    # 创建GUI实例（但不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    app = AShareAnalyzerGUI(root)
    
    # 测试不同类型的股票池
    test_types = ["60/00", "68科创板", "30创业板", "ETF"]
    
    for stock_type in test_types:
        print(f"\n📊 测试 {stock_type} 股票池:")
        print("-" * 30)
        
        # 获取股票池
        start_time = time.time()
        stock_pool = app.get_stock_pool_by_type(stock_type)
        end_time = time.time()
        
        print(f"✅ 获取成功，耗时: {end_time - start_time:.2f}秒")
        print(f"📈 股票数量: {len(stock_pool)}")
        print(f"📋 前10只股票: {stock_pool[:10]}")
        
        # 测试动态信息获取
        if stock_pool:
            test_ticker = stock_pool[0]
            print(f"\n🔍 测试股票 {test_ticker} 的动态信息获取:")
            
            info_start = time.time()
            stock_info = app.get_dynamic_stock_info(test_ticker)
            info_end = time.time()
            
            if stock_info:
                print(f"✅ 信息获取成功，耗时: {info_end - info_start:.2f}秒")
                print(f"📰 股票名称: {stock_info.get('name', 'N/A')}")
                print(f"🏭 所属行业: {stock_info.get('industry', 'N/A')}")
                print(f"💡 相关概念: {stock_info.get('concept', 'N/A')}")
                print(f"💰 当前价格: {stock_info.get('price', 'N/A')}")
            else:
                print(f"❌ 信息获取失败")
        
        time.sleep(1)  # 避免请求过快
    
    print("\n" + "=" * 50)
    print("🏁 动态股票池测试完成")
    
    root.destroy()

if __name__ == "__main__":
    test_dynamic_stock_pool()
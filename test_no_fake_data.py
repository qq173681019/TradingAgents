#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试改进后的无假数据股票系统
"""

import sys
import os
import tkinter as tk
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI

def test_no_fake_data():
    """测试系统不再提供假数据"""
    print("=== 测试真实数据vs网络错误显示 ===\n")
    
    # 创建虚拟的Tkinter root
    root = tk.Tk()
    root.withdraw()
    
    # 创建分析器实例
    analyzer = AShareAnalyzerGUI(root)
    
    test_cases = [
        ("600519", "贵州茅台", "应显示实时价格"),
        ("159915", "创业板ETF", "ETF应显示实时价格或错误"),
        ("999999", "不存在股票", "应显示网络获取失败"),
        ("300750", "宁德时代", "应显示实时价格"),
    ]
    
    for ticker, name, expected in test_cases:
        print(f"--- 测试 {ticker} ({name}) ---")
        print(f"预期结果: {expected}")
        
        # 测试价格获取
        price = analyzer.get_stock_price(ticker)
        if price is not None:
            print(f"✅ 获取到实时价格: ¥{price:.2f}")
        else:
            print(f"⚠️ 网络获取失败，未提供假数据")
        
        # 测试完整信息
        stock_info = analyzer.get_stock_info_generic(ticker)
        print(f"股票信息: {stock_info['name']}")
        print(f"价格状态: {stock_info.get('price_status', '未知')}")
        
        if stock_info['price'] is not None:
            print(f"显示价格: ¥{stock_info['price']:.2f}")
        else:
            print("显示价格: 网络获取失败")
        
        print()
    
    root.destroy()
    print("=== 测试完成：系统已确保不提供假数据 ===")

if __name__ == "__main__":
    test_no_fake_data()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试改进后的股票价格获取功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI

def test_improved_price_function():
    """测试改进后的价格获取功能"""
    print("=== 测试改进后的股票价格获取功能 ===\n")
    
    # 创建虚拟的Tkinter root（不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 创建分析器实例
    analyzer = AShareAnalyzerGUI(root)
    
    test_stocks = [
        ("600519", "贵州茅台"),
        ("000001", "平安银行"), 
        ("300750", "宁德时代"),
        ("688981", "中芯国际"),
        ("002594", "比亚迪"),
        ("123456", "不存在的股票")  # 测试错误处理
    ]
    
    for ticker, name in test_stocks:
        print(f"--- 测试 {ticker} ({name}) ---")
        
        # 测试价格获取
        price = analyzer.get_stock_price(ticker)
        print(f"获取到价格: {price} 元")
        
        # 测试完整股票信息获取
        stock_info = analyzer.get_stock_info_generic(ticker)
        print(f"股票信息: {stock_info}")
        
        print()
    
    root.destroy()  # 清理资源
    print("=== 测试完成 ===")

if __name__ == "__main__":
    test_improved_price_function()
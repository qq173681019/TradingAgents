#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票类型过滤功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def test_stock_type_filter():
    """测试股票类型过滤功能"""
    print("🧪 测试股票类型过滤功能...")
    
    # 创建测试窗口
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    # 创建分析器实例
    analyzer = AShareAnalyzerGUI(root)
    
    # 测试数据
    test_codes = [
        "600519",  # 贵州茅台 - 60开头
        "000858",  # 五粮液 - 00开头
        "002415",  # 海康威视 - 002开头
        "300750",  # 宁德时代 - 300开头
        "688981",  # 中芯国际 - 688开头
        "510300",  # 沪深300ETF - ETF
        "159915",  # 创业板ETF - ETF
    ]
    
    # 测试各种股票类型过滤
    stock_types = ["全部", "60/00", "68科创板", "30创业板", "ETF"]
    
    for stock_type in stock_types:
        print(f"\n📊 测试类型: {stock_type}")
        
        # 测试每个代码
        for code in test_codes:
            is_match = analyzer.is_stock_type_match(code, stock_type)
            status = "✅" if is_match else "❌"
            print(f"  {status} {code}: {is_match}")
        
        # 测试获取股票代码列表
        try:
            codes = analyzer.get_all_stock_codes(stock_type)
            print(f"  📈 获取到 {len(codes)} 只{stock_type}股票")
            if codes:
                print(f"     前5只: {codes[:5]}")
        except Exception as e:
            print(f"  ❌ 获取股票代码失败: {e}")
    
    print("\n✅ 股票类型过滤测试完成！")
    root.destroy()

if __name__ == "__main__":
    test_stock_type_filter()
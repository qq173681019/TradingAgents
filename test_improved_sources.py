#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试改进后的多数据源系统
"""

import sys
import os
import tkinter as tk
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_improved_data_sources():
    """测试改进后的多数据源"""
    print("=== 多数据源价格获取测试 ===\n")
    
    from a_share_gui_compatible import AShareAnalyzerGUI
    
    # 创建虚拟GUI
    root = tk.Tk()
    root.withdraw()
    app = AShareAnalyzerGUI(root)
    
    test_stocks = [
        ("600519", "贵州茅台"),
        ("000001", "平安银行"),
        ("300750", "宁德时代"),
        ("159915", "创业板ETF")
    ]
    
    success_count = 0
    
    for ticker, name in test_stocks:
        print(f"--- 测试 {ticker} ({name}) ---")
        
        start_time = time.time()
        price = app.get_stock_price(ticker)
        elapsed = time.time() - start_time
        
        if price is not None:
            print(f"✅ 成功获取价格: ¥{price:.2f} (耗时: {elapsed:.2f}秒)")
            success_count += 1
        else:
            print(f"❌ 所有数据源都失败 (耗时: {elapsed:.2f}秒)")
        
        print()
        time.sleep(0.5)  # 避免请求过快
    
    print(f"=== 测试完成 ===")
    print(f"成功率: {success_count}/{len(test_stocks)} ({success_count/len(test_stocks)*100:.1f}%)")
    
    if success_count > 0:
        print("✅ 数据源可用，系统正常工作")
    else:
        print("❌ 所有数据源都失败，可能是网络问题")
    
    root.destroy()

if __name__ == "__main__":
    test_improved_data_sources()
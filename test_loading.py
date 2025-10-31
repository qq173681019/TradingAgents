#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试进度条和智能缓存功能
"""

import sys
import os
import tkinter as tk
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_loading_and_cache():
    """测试loading和缓存功能"""
    print("=== 测试loading进度条和智能缓存 ===\n")
    
    # 直接启动GUI进行实际测试
    from a_share_gui_compatible import AShareAnalyzerGUI
    
    root = tk.Tk()
    app = AShareAnalyzerGUI(root)
    
    print("✅ GUI已启动，包含以下改进:")
    print("1. ⏳ 详细的5步骤进度条显示")
    print("2. 🚫 连续失败2次的股票名称不再重复获取")
    print("3. 📊 推荐分析时显示每只股票的处理进度")
    print("4. ✨ 实时价格获取状态显示")
    print("\n请在GUI中:")
    print("- 输入股票代码(如600519)点击'开始分析'查看进度条")
    print("- 点击'股票推荐'查看股票池分析进度")
    print("- 观察价格获取的真实性")
    
    # 测试缓存功能
    print("\n=== 测试智能缓存功能 ===")
    
    test_ticker = "999999"  # 不存在的股票
    print(f"测试不存在的股票: {test_ticker}")
    
    # 第一次尝试
    result1 = app.get_stock_name_from_sina(test_ticker)
    print(f"第1次获取结果: {result1}")
    print(f"当前尝试次数: {app.stock_name_attempts.get(test_ticker, 0)}")
    
    # 第二次尝试
    result2 = app.get_stock_name_from_sina(test_ticker)
    print(f"第2次获取结果: {result2}")
    print(f"当前尝试次数: {app.stock_name_attempts.get(test_ticker, 0)}")
    
    # 第三次尝试（应该被跳过）
    result3 = app.get_stock_name_from_sina(test_ticker)
    print(f"第3次获取结果: {result3}")
    print(f"是否在失败列表中: {test_ticker in app.failed_stock_names}")
    
    print("\n✅ 智能缓存测试完成！")
    
    root.mainloop()

if __name__ == "__main__":
    test_loading_and_cache()
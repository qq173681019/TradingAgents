#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试改进后的多源API获取系统
"""

import sys
import time

# 导入主程序
sys.path.append('.')
from a_share_gui_compatible import AShareAnalyzerGUI

def test_improved_api():
    """测试改进后的API获取"""
    print("🔬 测试改进后的多源API获取系统")
    print("=" * 60)
    
    # 创建GUI实例（但不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    app = AShareAnalyzerGUI(root)
    
    # 测试不同类型的股票池
    test_types = ["60/00", "68科创板", "30创业板", "ETF"]
    
    for stock_type in test_types:
        print(f"\n📊 测试 {stock_type} 股票池:")
        print("-" * 40)
        
        # 获取股票池
        start_time = time.time()
        stock_pool = app.get_stock_pool_by_type(stock_type)
        end_time = time.time()
        
        if stock_pool:
            print(f"✅ 获取成功，耗时: {end_time - start_time:.2f}秒")
            print(f"📈 股票数量: {len(stock_pool)}")
            print(f"📋 股票代码: {stock_pool}")
            
            # 验证前3只股票的价格获取
            print(f"\n🔍 验证前3只股票的价格获取:")
            for i, ticker in enumerate(stock_pool[:3], 1):
                try:
                    price = app.try_get_real_price_tencent(ticker)
                    if price:
                        print(f"  {i}. {ticker}: ¥{price}")
                    else:
                        print(f"  {i}. {ticker}: 价格获取失败")
                except Exception as e:
                    print(f"  {i}. {ticker}: 错误 - {e}")
        else:
            print(f"❌ 获取失败，耗时: {end_time - start_time:.2f}秒")
        
        time.sleep(1)  # 避免请求过快
    
    print("\n" + "=" * 60)
    print("🏁 改进后的API获取测试完成")
    
    root.destroy()

if __name__ == "__main__":
    test_improved_api()
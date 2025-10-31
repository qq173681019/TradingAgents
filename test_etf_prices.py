#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试ETF价格获取
"""

import sys

# 导入主程序
sys.path.append('.')
from a_share_gui_compatible import AShareAnalyzerGUI

def test_etf_prices():
    """测试ETF价格获取"""
    print("🔬 测试ETF价格获取")
    print("=" * 40)
    
    # 创建GUI实例（但不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    app = AShareAnalyzerGUI(root)
    
    # 测试ETF代码
    etf_codes = ["510050", "510300", "510500", "159919", "159915"]
    
    for ticker in etf_codes:
        print(f"\n🔍 测试 {ticker}:")
        
        # 测试腾讯财经
        price = app.try_get_real_price_tencent(ticker)
        if price:
            print(f"✅ 获取成功: ¥{price}")
        else:
            print(f"❌ 获取失败")
    
    print("\n" + "=" * 40)
    print("🏁 ETF价格测试完成")
    
    root.destroy()

if __name__ == "__main__":
    test_etf_prices()
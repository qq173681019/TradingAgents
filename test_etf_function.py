#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试ETF获取功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def test_etf_function():
    """测试ETF获取功能"""
    print("=" * 50)
    print("🧪 测试ETF获取功能")
    print("=" * 50)
    
    # 创建GUI实例
    root = tk.Tk()
    root.withdraw()  # 隐藏GUI窗口
    analyzer = AShareAnalyzerGUI(root)
    
    try:
        print("\n1️⃣ 测试ETF股票获取...")
        etf_stocks = analyzer.get_etf_stocks_multi_source()
        
        if etf_stocks:
            print(f"✅ ETF获取成功: {len(etf_stocks)}只")
            print(f"🔸 前10只ETF: {etf_stocks[:10]}")
            print(f"🔸 ETF代码示例:")
            
            # 检查不同类型的ETF
            etf_51 = [code for code in etf_stocks if code.startswith('51')]
            etf_15 = [code for code in etf_stocks if code.startswith('15')]
            etf_16 = [code for code in etf_stocks if code.startswith('16')]
            
            print(f"     51开头(沪市ETF): {len(etf_51)}只")
            print(f"     15开头(深市ETF): {len(etf_15)}只")
            print(f"     16开头(深市ETF): {len(etf_16)}只")
            
            if etf_51:
                print(f"     沪市ETF示例: {etf_51[:3]}")
            if etf_15:
                print(f"     深市ETF示例: {etf_15[:3]}")
        else:
            print("❌ ETF获取失败")
    
    except Exception as e:
        print(f"❌ ETF测试出错: {e}")
    
    try:
        print("\n2️⃣ 测试ETF价格获取...")
        # 测试几个常见ETF的价格获取
        test_etfs = ["510050", "510300", "159001", "159005"]  # 50ETF、沪深300ETF等
        
        for etf_code in test_etfs:
            try:
                price = analyzer.get_stock_price(etf_code)
                if price:
                    print(f"✅ {etf_code}: ¥{price:.2f}")
                else:
                    print(f"❌ {etf_code}: 价格获取失败")
            except Exception as e:
                print(f"❌ {etf_code}: {e}")
    
    except Exception as e:
        print(f"❌ ETF价格测试出错: {e}")
    
    try:
        print("\n3️⃣ 测试fetch_stock_list_from_api...")
        # 测试通过API接口获取ETF
        etf_list = analyzer.fetch_stock_list_from_api("etf")
        if etf_list:
            print(f"✅ API获取ETF成功: {len(etf_list)}只")
        else:
            print("❌ API获取ETF失败")
    
    except Exception as e:
        print(f"❌ API测试出错: {e}")
    
    print("\n" + "=" * 50)
    print("✅ ETF功能测试完成")
    print("=" * 50)
    
    root.destroy()

if __name__ == "__main__":
    test_etf_function()
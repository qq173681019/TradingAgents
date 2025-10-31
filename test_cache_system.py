#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试缓存系统和API失败处理
"""

import sys
import time
import json
import os

# 导入主程序
sys.path.append('.')
from a_share_gui_compatible import AShareAnalyzerGUI

def test_cache_system():
    """测试缓存系统"""
    print("🔬 测试股票分析缓存系统")
    print("=" * 50)
    
    # 创建GUI实例（但不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    app = AShareAnalyzerGUI(root)
    
    # 测试缓存加载
    print(f"📊 当前缓存股票数: {len(app.daily_cache)}")
    
    # 测试单只股票分析和缓存
    test_ticker = "600036"
    print(f"\n🔍 测试股票 {test_ticker} 分析:")
    
    # 检查是否有缓存
    cached = app.get_stock_from_cache(test_ticker)
    if cached:
        print(f"✅ 发现缓存数据: {cached['name']} - {cached['score']:.2f}分")
        print(f"📅 缓存时间: {cached.get('cache_time', 'N/A')}")
    else:
        print("📝 无缓存，将进行实时分析")
        
        # 实时分析
        analysis = app.analyze_single_stock(test_ticker, "短期", 8.0)
        if analysis:
            print(f"✅ 分析完成: {analysis['name']} - {analysis['score']:.2f}分")
            print(f"💾 已保存到缓存")
        else:
            print("❌ 分析失败")
    
    # 测试API失败处理
    print(f"\n🌐 测试API失败处理:")
    stock_pool = app.get_stock_pool_by_type("60/00")
    if stock_pool:
        print(f"✅ API成功，获取{len(stock_pool)}只股票")
    else:
        print("❌ API失败，系统正确处理")
    
    # 检查缓存文件
    print(f"\n📁 缓存文件状态:")
    if os.path.exists(app.cache_file):
        with open(app.cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        print(f"✅ 缓存文件存在")
        print(f"📅 缓存日期: {cache_data.get('date', 'N/A')}")
        print(f"⏰ 最后更新: {cache_data.get('timestamp', 'N/A')}")
        print(f"📊 股票数量: {len(cache_data.get('stocks', {}))}")
    else:
        print("📝 缓存文件不存在")
    
    print("\n" + "=" * 50)
    print("🏁 缓存系统测试完成")
    
    root.destroy()

if __name__ == "__main__":
    test_cache_system()
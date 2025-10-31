#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试股票获取数量统计
"""

import sys
import time

# 导入主程序
sys.path.append('.')
from a_share_gui_compatible import AShareAnalyzerGUI

def test_stock_count():
    """测试股票获取数量统计"""
    print("🔬 测试股票获取数量统计")
    print("=" * 60)
    
    # 创建GUI实例（但不显示界面）
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    
    app = AShareAnalyzerGUI(root)
    
    # 测试不同类型的股票池获取数量
    test_types = ["60/00", "68科创板", "30创业板", "ETF"]
    
    total_summary = {}
    
    for stock_type in test_types:
        print(f"\n📊 测试 {stock_type} 股票池获取:")
        print("-" * 40)
        
        # 模拟设置
        app.stock_type_var = type('MockVar', (), {'get': lambda: stock_type})()
        
        # 获取股票池
        start_time = time.time()
        stock_pool = app.get_stock_pool_by_type(stock_type)
        end_time = time.time()
        
        if stock_pool:
            print(f"✅ 获取成功，耗时: {end_time - start_time:.2f}秒")
            print(f"📈 股票总数: {len(stock_pool)}只")
            print(f"📋 前10只: {stock_pool[:10]}")
            
            # 验证股票有效性（检查前5只）
            valid_count = 0
            print(f"\n🔍 验证前5只股票:")
            for i, ticker in enumerate(stock_pool[:5], 1):
                try:
                    price = app.try_get_real_price_tencent(ticker)
                    if price and price > 0:
                        valid_count += 1
                        print(f"  ✅ {i}. {ticker}: ¥{price}")
                    else:
                        print(f"  ❌ {i}. {ticker}: 无法获取价格")
                except Exception as e:
                    print(f"  ❌ {i}. {ticker}: 错误 - {e}")
            
            print(f"📊 验证结果: {valid_count}/{min(5, len(stock_pool))} 只股票有效")
            
            total_summary[stock_type] = {
                'total': len(stock_pool),
                'valid_sample': valid_count,
                'sample_size': min(5, len(stock_pool))
            }
        else:
            print(f"❌ 获取失败，耗时: {end_time - start_time:.2f}秒")
            total_summary[stock_type] = {
                'total': 0,
                'valid_sample': 0,
                'sample_size': 0
            }
        
        time.sleep(1)  # 避免请求过快
    
    # 总结报告
    print("\n" + "=" * 60)
    print("📊 股票获取数量总结:")
    print("=" * 60)
    
    total_stocks = 0
    for stock_type, stats in total_summary.items():
        total_stocks += stats['total']
        validity_rate = (stats['valid_sample'] / stats['sample_size'] * 100) if stats['sample_size'] > 0 else 0
        print(f"📈 {stock_type:8s}: {stats['total']:2d}只股票  (验证率: {validity_rate:.0f}%)")
    
    print(f"\n🎯 总计可获取股票: {total_stocks}只")
    print(f"💡 这就是你在推荐分析中能看到的股票总数")
    
    print("\n📝 说明:")
    print("• 验证率基于前5只股票的价格获取成功率")
    print("• 实际分析时会对所有股票进行验证")
    print("• API失败时部分类型会使用备用股票池")
    
    print("\n🏁 股票数量统计测试完成")
    
    root.destroy()

if __name__ == "__main__":
    test_stock_count()
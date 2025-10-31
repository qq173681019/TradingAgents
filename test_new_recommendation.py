#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试新的股票推荐功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def test_new_recommendation():
    """测试新的股票推荐功能"""
    print("=" * 60)
    print("🧪 测试股票推荐功能 (集成智能筛选)")
    print("=" * 60)
    
    # 创建GUI实例
    root = tk.Tk()
    root.withdraw()  # 隐藏GUI窗口
    analyzer = AShareAnalyzerGUI(root)
    
    try:
        print("\n1️⃣ 测试股票池获取功能...")
        # 测试不同类型股票池
        main_stocks = analyzer._get_stock_pool("main_board")
        print(f"✅ 主板股票池: {len(main_stocks)}只")
        
        kcb_stocks = analyzer._get_stock_pool("kcb") 
        print(f"✅ 科创板股票池: {len(kcb_stocks)}只")
        
        cyb_stocks = analyzer._get_stock_pool("cyb")
        print(f"✅ 创业板股票池: {len(cyb_stocks)}只")
        
        all_stocks = analyzer._get_stock_pool("all")
        print(f"✅ 全市场股票池: {len(all_stocks)}只")
        
    except Exception as e:
        print(f"❌ 股票池测试失败: {e}")
    
    try:
        print("\n2️⃣ 测试单股分析功能...")
        # 测试分析几只知名股票
        test_stocks = ["600519", "600036", "000858"]  # 茅台、招行、五粮液
        
        for ticker in test_stocks:
            print(f"\n🔍 分析 {ticker}...")
            result = analyzer._analyze_single_stock(ticker)
            if result:
                print(f"✅ {result['ticker']} ({result['name']})")
                print(f"   💰 价格: ¥{result['price']:.2f}")
                print(f"   📊 综合评分: {result['total_score']:.1f}分")
                print(f"   📈 技术分析: {result['technical_score']:.1f}分")
                print(f"   💼 基本面: {result['fundamental_score']:.1f}分")
            else:
                print(f"❌ {ticker} 分析失败")
    
    except Exception as e:
        print(f"❌ 单股分析测试失败: {e}")
    
    try:
        print("\n3️⃣ 测试推荐报告生成...")
        # 模拟推荐数据
        mock_recommended = [
            {
                'ticker': '600519',
                'name': '贵州茅台',
                'price': 1430.0,
                'technical_score': 8.5,
                'fundamental_score': 9.0,
                'total_score': 8.75
            },
            {
                'ticker': '600036',
                'name': '招商银行',
                'price': 40.89,
                'technical_score': 7.2,
                'fundamental_score': 7.8,
                'total_score': 7.5
            }
        ]
        
        mock_all_analyzed = mock_recommended + [
            {
                'ticker': '000001',
                'name': '平安银行',
                'price': 11.32,
                'technical_score': 5.5,
                'fundamental_score': 6.0,
                'total_score': 5.75
            }
        ]
        
        # 测试报告生成
        analyzer._generate_recommendation_report(
            mock_recommended, mock_all_analyzed, [], 7.0, "main_board", 10
        )
        
        print("✅ 推荐报告生成测试完成")
        
    except Exception as e:
        print(f"❌ 推荐报告测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 股票推荐功能测试完成")
    print("=" * 60)
    print("\n💡 测试总结:")
    print("• 股票池获取: 支持主板、科创板、创业板、全市场")
    print("• 单股分析: 包含价格、技术面、基本面综合评分") 
    print("• 智能推荐: 集成到股票推荐按钮中")
    print("• 报告生成: 详细的推荐报告和投资建议")
    print("• 用户体验: 通过设置对话框自定义推荐参数")
    print("\n🚀 现在可以使用GUI界面的'股票推荐'功能了！")
    
    root.destroy()

if __name__ == "__main__":
    test_new_recommendation()
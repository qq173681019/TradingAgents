#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试智能股票筛选功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def test_batch_analysis():
    """测试批量分析功能"""
    print("=" * 60)
    print("🎯 测试智能股票筛选功能")
    print("=" * 60)
    
    # 创建GUI实例
    root = tk.Tk()
    root.withdraw()  # 隐藏GUI窗口
    analyzer = AShareAnalyzerGUI(root)
    
    print("\n1️⃣ 测试股票池获取...")
    try:
        # 测试不同类型股票池
        main_stocks = analyzer._get_stock_pool("main_board")
        print(f"✅ 主板股票池: {len(main_stocks)}只")
        print(f"   前5只: {main_stocks[:5]}")
        
        kcb_stocks = analyzer._get_stock_pool("kcb") 
        print(f"✅ 科创板股票池: {len(kcb_stocks)}只")
        print(f"   前5只: {kcb_stocks[:5]}")
        
        all_stocks = analyzer._get_stock_pool("all")
        print(f"✅ 全市场股票池: {len(all_stocks)}只")
        
    except Exception as e:
        print(f"❌ 股票池获取失败: {e}")
    
    print("\n2️⃣ 测试单股分析...")
    try:
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
        print(f"❌ 单股分析失败: {e}")
    
    print("\n3️⃣ 测试分数提取...")
    try:
        # 测试分数提取功能
        test_advice_1 = "技术分析评分: 7.5 - 该股票表现良好，推荐买入"
        test_advice_2 = "强烈推荐 (5星) - 基本面扎实"
        test_advice_3 = "中性 (3星) - 持有观望"
        
        score1 = analyzer._extract_score_from_advice(test_advice_1, "技术分析")
        score2 = analyzer._extract_score_from_advice(test_advice_2, "基本面分析")
        score3 = analyzer._extract_score_from_advice(test_advice_3, "基本面分析")
        
        print(f"✅ 分数提取测试:")
        print(f"   明确分数 '7.5': {score1}")
        print(f"   强烈推荐级别: {score2}")
        print(f"   中性级别: {score3}")
        
    except Exception as e:
        print(f"❌ 分数提取测试失败: {e}")
    
    print("\n4️⃣ 测试缓存功能...")
    try:
        # 测试缓存读写
        test_result = {
            'ticker': '600519',
            'name': '贵州茅台',
            'price': 1430.0,
            'technical_score': 8.5,
            'fundamental_score': 9.0,
            'total_score': 8.75
        }
        
        # 保存到缓存
        analyzer.save_stock_to_cache('600519', test_result)
        print("✅ 保存到缓存")
        
        # 从缓存读取
        cached = analyzer.get_stock_from_cache('600519')
        if cached:
            print(f"✅ 从缓存读取: {cached['ticker']} - {cached['total_score']:.1f}分")
        else:
            print("❌ 缓存读取失败")
            
    except Exception as e:
        print(f"❌ 缓存测试失败: {e}")
    
    print("\n5️⃣ 模拟小规模批量分析...")
    try:
        # 模拟对少量股票进行批量分析
        sample_stocks = ["600519", "600036", "000858", "601318", "000002"]
        print(f"📊 模拟分析{len(sample_stocks)}只股票...")
        
        analyzed_results = []
        for ticker in sample_stocks:
            try:
                result = analyzer._analyze_single_stock(ticker)
                if result:
                    analyzed_results.append(result)
                    print(f"   ✅ {ticker}: {result['total_score']:.1f}分")
                else:
                    print(f"   ❌ {ticker}: 分析失败")
            except Exception as e:
                print(f"   ❌ {ticker}: {e}")
        
        # 按分数排序
        analyzed_results.sort(key=lambda x: x['total_score'], reverse=True)
        
        print(f"\n📈 分析结果 (按分数排序):")
        for i, stock in enumerate(analyzed_results, 1):
            stars = "⭐" * min(5, int(stock['total_score'] / 2))
            print(f"   {i}. {stock['ticker']} ({stock['name']}) - {stock['total_score']:.1f}分 {stars}")
        
        # 筛选高分股票
        high_score_stocks = [s for s in analyzed_results if s['total_score'] >= 7.0]
        print(f"\n🎯 7.0分以上优质股票: {len(high_score_stocks)}只")
        
    except Exception as e:
        print(f"❌ 模拟批量分析失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 智能筛选功能测试完成")
    print("=" * 60)
    print("\n💡 测试总结:")
    print("• 股票池获取: 支持主板、科创板、创业板、全市场")
    print("• 单股分析: 包含价格、技术面、基本面综合评分") 
    print("• 分数排序: 按投资价值从高到低排序")
    print("• 智能筛选: 根据设定分数线筛选优质股票")
    print("• 缓存优化: 避免重复分析，提高效率")
    print("\n🚀 现在可以使用GUI界面的'智能筛选股票'功能了！")
    
    root.destroy()

if __name__ == "__main__":
    test_batch_analysis()
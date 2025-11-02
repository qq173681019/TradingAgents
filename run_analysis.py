#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股智能分析系统 - 命令行版本
适用于没有GUI环境的情况
"""

import sys
import os

# 添加主程序路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_stock_analysis():
    """运行股票分析"""
    print("🚀 启动A股智能分析系统 (命令行版)")
    print("=" * 60)
    
    try:
        # 导入主程序的核心功能
        from a_share_gui_compatible import StockAnalyzer
        
        # 创建分析器实例 (不使用GUI)
        print("📊 初始化分析系统...")
        analyzer = StockAnalyzer()
        
        # 测试股票列表
        test_stocks = [
            "600519",  # 贵州茅台
            "600036",  # 招商银行  
            "000858",  # 五粮液
            "601318",  # 中国平安
            "000002",  # 万科A
        ]
        
        print(f"🎯 开始分析 {len(test_stocks)} 只股票...")
        print("=" * 60)
        
        results = []
        
        for i, ticker in enumerate(test_stocks, 1):
            print(f"\n📈 [{i}/{len(test_stocks)}] 分析股票: {ticker}")
            print("-" * 40)
            
            try:
                # 执行单只股票分析
                result = analyzer.analyze_single_stock(ticker, period="短期")
                
                if result:
                    results.append(result)
                    
                    # 显示分析结果
                    print(f"✅ 股票名称: {result.get('name', '未知')}")
                    print(f"💰 当前价格: ¥{result.get('price', 0):.2f}")
                    print(f"📊 技术分析: {result.get('technical_score', 0):.1f}/10")
                    print(f"💼 基本面分析: {result.get('fundamental_score', 0):.1f}/10")
                    print(f"🎯 综合评分: {result.get('total_score', 0):.1f}/10")
                    print(f"📋 投资期限: {result.get('period', '未知')}")
                else:
                    print(f"❌ {ticker} 分析失败")
                    
            except Exception as e:
                print(f"❌ {ticker} 分析出错: {e}")
        
        # 显示汇总结果
        print("\n" + "=" * 60)
        print("📊 分析结果汇总")
        print("=" * 60)
        
        if results:
            print("排名   股票代码   股票名称        综合评分   技术分   基本面分")
            print("-" * 60)
            
            # 按综合评分排序
            results.sort(key=lambda x: x.get('total_score', 0), reverse=True)
            
            for i, result in enumerate(results, 1):
                ticker = result.get('ticker', '未知')
                name = result.get('name', '未知')
                total_score = result.get('total_score', 0)
                tech_score = result.get('technical_score', 0)
                fund_score = result.get('fundamental_score', 0)
                
                print(f" {i:2d}    {ticker}      {name:10s}   {total_score:6.1f}/10   {tech_score:5.1f}    {fund_score:6.1f}")
            
            # 显示投资建议
            print("\n💡 投资建议:")
            best_stock = results[0]
            if best_stock.get('total_score', 0) >= 7.0:
                print(f"🔥 推荐关注: {best_stock.get('name')} ({best_stock.get('ticker')})")
                print(f"   综合评分: {best_stock.get('total_score', 0):.1f}/10")
            elif best_stock.get('total_score', 0) >= 6.0:
                print(f"👀 可以关注: {best_stock.get('name')} ({best_stock.get('ticker')})")
                print(f"   综合评分: {best_stock.get('total_score', 0):.1f}/10")
            else:
                print("⚠️ 当前市场环境下，建议谨慎投资")
        else:
            print("❌ 没有成功分析任何股票")
        
        print("\n✅ 分析完成!")
        print("💡 这是基于模拟数据的分析结果，仅供参考，不构成投资建议")
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("💡 请检查程序文件是否完整")
    except Exception as e:
        print(f"❌ 程序运行失败: {e}")
        print("💡 请检查运行环境和依赖")

def interactive_analysis():
    """交互式分析"""
    print("\n🎮 进入交互模式")
    print("输入股票代码进行分析，输入 'quit' 退出")
    
    try:
        from a_share_gui_compatible import StockAnalyzer
        analyzer = StockAnalyzer()
        
        while True:
            ticker = input("\n请输入股票代码 (如: 600519): ").strip()
            
            if ticker.lower() in ['quit', 'exit', 'q']:
                print("👋 退出程序")
                break
            
            if not ticker:
                continue
            
            if not ticker.isdigit() or len(ticker) != 6:
                print("❌ 请输入6位数字的股票代码")
                continue
            
            print(f"\n🔍 分析股票 {ticker}...")
            try:
                result = analyzer.analyze_single_stock(ticker, period="短期")
                
                if result:
                    print(f"✅ 分析完成!")
                    print(f"📊 股票名称: {result.get('name', '未知')}")
                    print(f"💰 当前价格: ¥{result.get('price', 0):.2f}")
                    print(f"🎯 综合评分: {result.get('total_score', 0):.1f}/10")
                else:
                    print("❌ 分析失败，请重试")
            except Exception as e:
                print(f"❌ 分析出错: {e}")
    
    except Exception as e:
        print(f"❌ 交互模式启动失败: {e}")

if __name__ == "__main__":
    # 显示欢迎信息
    print("🎉 欢迎使用A股智能分析系统!")
    print("📝 注意: 由于运行环境限制，使用命令行版本")
    
    # 运行批量分析
    run_stock_analysis()
    
    # 询问是否进入交互模式
    choice = input("\n是否进入交互模式? (y/n): ").strip().lower()
    if choice in ['y', 'yes']:
        interactive_analysis()
    
    print("\n🙏 感谢使用A股智能分析系统!")
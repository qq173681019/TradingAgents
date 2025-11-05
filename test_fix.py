#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股分析系统 - GUI测试脚本
测试股票推荐功能是否正常工作
"""

import sys
import os

# 添加当前路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_gui_recommendations():
    """测试GUI推荐功能"""
    print("🔍 测试GUI股票推荐功能...")
    
    try:
        # 检查是否有tkinter
        try:
            import tkinter as tk
            print("✅ tkinter可用")
            tkinter_available = True
        except ImportError:
            print("❌ tkinter不可用，跳过GUI测试")
            return
        
        # 导入GUI类
        from a_share_gui_compatible import AShareAnalyzerGUI
        
        # 创建测试实例（不显示窗口）
        root = tk.Tk()
        root.withdraw()  # 隐藏窗口
        
        print("📊 创建分析器实例...")
        analyzer = AShareAnalyzerGUI(root)
        
        # 测试推荐功能的核心方法
        print("🔄 测试短期推荐...")
        short_recs = analyzer.get_recommended_stocks_by_period('short', 5)
        print(f"   短期推荐结果: {len(short_recs)}只股票")
        
        if short_recs:
            for i, stock in enumerate(short_recs[:3], 1):
                print(f"   {i}. {stock.get('name', '未知')} ({stock.get('code', '未知')}) - 评分: {stock.get('score', 0)}")
        
        print("🔄 测试中期推荐...")
        medium_recs = analyzer.get_recommended_stocks_by_period('medium', 5)
        print(f"   中期推荐结果: {len(medium_recs)}只股票")
        
        print("🔄 测试长期推荐...")
        long_recs = analyzer.get_recommended_stocks_by_period('long', 5)
        print(f"   长期推荐结果: {len(long_recs)}只股票")
        
        # 测试格式化报告
        print("📄 测试报告格式化...")
        if short_recs and medium_recs and long_recs:
            report = analyzer.format_stock_recommendations(short_recs, medium_recs, long_recs)
            print("✅ 报告格式化成功")
            print(f"   报告长度: {len(report)}字符")
        else:
            print("⚠️ 部分推荐数据为空，无法生成完整报告")
        
        root.destroy()
        print("✅ GUI推荐功能测试完成")
        
    except Exception as e:
        print(f"❌ GUI测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_cli_fallback():
    """测试命令行版本作为备用"""
    print("\n🔍 测试命令行版本推荐功能...")
    
    try:
        from cli_launcher import AShareAnalyzerCLI
        
        cli = AShareAnalyzerCLI()
        print("📊 命令行分析器创建成功")
        
        # 测试推荐功能
        short_recs = cli.get_recommendations('short', 3)
        print(f"✅ 命令行短期推荐: {len(short_recs)}只股票")
        
        if short_recs:
            for i, stock in enumerate(short_recs, 1):
                print(f"   {i}. {stock.get('name', '未知')} ({stock.get('code', '未知')}) - 评分: {stock.get('score', 0)}")
        
    except Exception as e:
        print(f"❌ 命令行测试失败: {e}")

def main():
    """主函数"""
    print("🚀 A股分析系统 - 推荐功能测试")
    print("=" * 50)
    
    # 测试GUI版本
    test_gui_recommendations()
    
    # 测试命令行版本
    test_cli_fallback()
    
    print("\n📋 测试总结:")
    print("=" * 30)
    print("如果看到'✅ GUI推荐功能测试完成'，说明ticker错误已修复")
    print("如果仍有错误，请检查错误信息并继续修复")

if __name__ == "__main__":
    main()
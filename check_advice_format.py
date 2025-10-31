#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
查看投资建议格式
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from a_share_gui_compatible import AShareAnalyzerGUI
import tkinter as tk

def check_advice_format():
    """查看投资建议格式"""
    print("=" * 50)
    print("查看投资建议输出格式")
    print("=" * 50)
    
    # 创建GUI实例
    root = tk.Tk()
    root.withdraw()  # 隐藏GUI窗口
    analyzer = AShareAnalyzerGUI(root)
    
    try:
        # 生成投资建议
        short_advice, long_advice = analyzer.generate_investment_advice('600519')
        
        print("\n📈 短期投资建议:")
        print("-" * 30)
        print(short_advice)
        
        print("\n💼 长期投资建议:")
        print("-" * 30)  
        print(long_advice)
        
        # 测试分数提取
        print("\n🔍 分数提取测试:")
        print("-" * 30)
        tech_score = analyzer._extract_score_from_advice(short_advice, "技术分析")
        fund_score = analyzer._extract_score_from_advice(long_advice, "基本面分析")
        
        print(f"技术分析分数: {tech_score}")
        print(f"基本面分析分数: {fund_score}")
        print(f"综合分数: {(tech_score + fund_score) / 2}")
        
    except Exception as e:
        print(f"❌ 出错: {e}")
    
    root.destroy()

if __name__ == "__main__":
    check_advice_format()
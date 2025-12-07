import json
import os
import sys
import time

# 添加项目根目录到 Python 路径
sys.path.append(os.getcwd())

from a_share_gui_compatible import AShareAnalyzerGUI as Analyzer


def verify_stock(ticker):
    print(f"Headless verification for {ticker}")
    
    # 初始化分析器 (无GUI模式)
    analyzer = Analyzer(root=None)
    analyzer.llm_model = 'none'
    
    # 1. 生成预测 (Generate Investment Advice)
    print("\n-- Generating investment advice (predictions) --")
    try:
        short_p, medium_p, long_p = analyzer.generate_investment_advice(ticker)
        
        # 提取分数
        short_tech = short_p.get('technical_score', 0)
        short_score = short_p.get('score', 5.0)
        
        medium_total = medium_p.get('total_score', 0)
        medium_score = medium_p.get('score', 5.0)
        
        long_fund = long_p.get('fundamental_score', 0)
        long_score = long_p.get('score', 5.0)
        
        print(f"Short prediction: {short_p}")
        print(f"Medium prediction: {medium_p}")
        print(f"Long prediction: {long_p}")
        
        print(f"\nExtracted values:")
        print(f" short_tech={short_tech} (norm:{short_score})")
        print(f" medium_total={medium_total} (norm:{medium_score})")
        print(f" long_fund={long_fund} (norm:{long_score})")
        
        # 手动计算综合评分
        comp_from_raw = analyzer.calculate_comprehensive_score(short_tech, medium_total, long_fund, input_type='raw')
        comp_from_norm = analyzer.calculate_comprehensive_score(short_score, medium_score, long_score, input_type='normalized')
        
        print(f"\nCalculated comprehensive scores:")
        print(f" - from_raw (raw->1-10 internally): {comp_from_raw}")
        print(f" - from_norm (direct 1-10): {comp_from_norm}")
        
    except Exception as e:
        print(f"Error generating advice: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_stock("600591")

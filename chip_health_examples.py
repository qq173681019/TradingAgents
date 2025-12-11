#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筹码健康度分析工具 v2.0 - 快速入门示例
演示所有新增功能的使用方法
"""

import numpy as np
import pandas as pd

from chip_health_analyzer import ChipHealthAnalyzer


def example_1_basic_usage():
    """示例1：基础使用"""
    print("\n" + "="*70)
    print("示例1：基础使用")
    print("="*70)
    
    # 创建分析器
    analyzer = ChipHealthAnalyzer()
    
    # 分析股票
    result = analyzer.analyze_stock('600519')
    
    # 打印关键信息
    print(f"\n【关键指标】")
    print(f"健康度评分: {result['health_score']:.1f}/10.0")
    print(f"健康度等级: {result['health_level']}")
    print(f"SCR集中度: {result['scr']:.2f}%")
    print(f"筹码乖离率: {result['chip_bias']:+.2f}%")
    print(f"筹码峰型: {result['peak_type']}")
    
    return result


def example_2_bull_market_mode():
    """示例2：牛市模式 - 重视形态和集中度"""
    print("\n" + "="*70)
    print("示例2：牛市模式分析")
    print("="*70)
    
    # 创建牛市模式分析器
    analyzer = ChipHealthAnalyzer(market_condition='bull')
    
    # 分析同一只股票，对比评分差异
    result = analyzer.analyze_stock('600519')
    
    print(f"\n【牛市模式评分】")
    print(f"健康度评分: {result['health_score']:.1f}/10.0")
    print(f"使用权重: 集中度30% 形态25%（较高）")
    
    return result


def example_3_bear_market_mode():
    """示例3：熊市模式 - 重视风险控制"""
    print("\n" + "="*70)
    print("示例3：熊市模式分析")
    print("="*70)
    
    # 创建熊市模式分析器
    analyzer = ChipHealthAnalyzer(market_condition='bear')
    
    result = analyzer.analyze_stock('600519')
    
    print(f"\n【熊市模式评分】")
    print(f"健康度评分: {result['health_score']:.1f}/10.0")
    print(f"使用权重: 盈亏比25% 乖离率25%（较高）")
    
    return result


def example_4_ml_enhanced():
    """示例4：机器学习增强模式（需要先训练模型）"""
    print("\n" + "="*70)
    print("示例4：机器学习增强模式")
    print("="*70)
    
    try:
        # 创建ML增强分析器
        analyzer = ChipHealthAnalyzer(use_ml=True, market_condition='bull')
        
        # 生成模拟训练数据（实际使用时应该用真实历史数据）
        print("\n生成模拟训练数据...")
        training_data = pd.DataFrame({
            'scr': np.random.uniform(5, 40, 50),
            'chip_bias': np.random.uniform(-20, 30, 50),
            'profit_ratio': np.random.uniform(20, 90, 50),
            'turnover_rate': np.random.uniform(0.5, 15, 50),
            'hhi': np.random.uniform(0.1, 0.4, 50),
            'gini_coefficient': np.random.uniform(0.3, 0.7, 50),
            'target_score': np.random.uniform(3, 9, 50)
        })
        
        # 训练模型
        success = analyzer.train_ml_model(training_data)
        
        if success:
            # 使用ML增强分析
            result = analyzer.analyze_stock('600519')
            
            print(f"\n【ML增强评分】")
            print(f"健康度评分: {result['health_score']:.1f}/10.0")
            print(f"评分策略: 70%传统算法 + 30%机器学习")
            
            return result
        else:
            print("❌ ML模型训练失败")
            
    except Exception as e:
        print(f"❌ ML增强功能异常: {e}")
        print("提示: 需要安装 scikit-learn: pip install scikit-learn")
    
    return None


def example_5_export_report():
    """示例5：导出分析报告"""
    print("\n" + "="*70)
    print("示例5：导出分析报告")
    print("="*70)
    
    analyzer = ChipHealthAnalyzer(market_condition='bull')
    result = analyzer.analyze_stock('600519')
    
    # 导出报告
    filename = analyzer.export_analysis_report(result, filename='茅台筹码分析.txt')
    
    if filename:
        print(f"\n✓ 报告已导出: {filename}")
        print(f"可以在文本编辑器中查看详细分析结果")
    
    return result


def example_6_batch_analysis():
    """示例6：批量分析多只股票"""
    print("\n" + "="*70)
    print("示例6：批量分析多只股票")
    print("="*70)
    
    analyzer = ChipHealthAnalyzer(market_condition='bull')
    
    # 要分析的股票列表
    stock_codes = ['600519', '000858', '600036']
    
    print("\n开始批量分析...")
    results = []
    
    for code in stock_codes:
        try:
            print(f"\n分析 {code}...")
            result = analyzer.analyze_stock(code)
            results.append({
                'code': code,
                'score': result['health_score'],
                'level': result['health_level'],
                'scr': result['scr'],
                'signal': result['signal_strength']
            })
        except Exception as e:
            print(f"❌ {code} 分析失败: {e}")
    
    # 打印汇总表
    print("\n" + "="*70)
    print("【批量分析汇总】")
    print("="*70)
    print(f"{'股票代码':<10} {'评分':<10} {'等级':<20} {'SCR':<10} {'信号'}")
    print("-"*70)
    
    for r in results:
        print(f"{r['code']:<10} {r['score']:<10.1f} {r['level']:<20} {r['scr']:<10.2f} {r['signal']}")
    
    # 按评分排序
    results_sorted = sorted(results, key=lambda x: x['score'], reverse=True)
    print(f"\n🏆 健康度最高: {results_sorted[0]['code']} ({results_sorted[0]['score']:.1f}分)")
    
    return results


def example_7_compare_modes():
    """示例7：对比不同模式的评分差异"""
    print("\n" + "="*70)
    print("示例7：对比不同市场环境下的评分")
    print("="*70)
    
    stock_code = '600519'
    modes = {
        'normal': '震荡市',
        'bull': '牛市',
        'bear': '熊市'
    }
    
    print(f"\n分析股票: {stock_code}")
    print("="*70)
    
    results = {}
    for mode, name in modes.items():
        analyzer = ChipHealthAnalyzer(market_condition=mode)
        result = analyzer.analyze_stock(stock_code)
        results[mode] = result
        
        print(f"\n【{name}模式】")
        print(f"  健康度评分: {result['health_score']:.1f}/10.0")
        print(f"  信号强度: {result['signal_strength']}")
    
    # 打印对比表
    print("\n" + "="*70)
    print("【评分对比】")
    print("="*70)
    print(f"{'模式':<10} {'评分':<10} {'信号强度':<10} {'建议'}")
    print("-"*70)
    
    for mode, name in modes.items():
        r = results[mode]
        print(f"{name:<10} {r['health_score']:<10.1f} {r['signal_strength']:<10} ", end='')
        
        # 简化建议
        if '强烈看涨' in r['trading_suggestion']:
            print("🟢 看涨")
        elif '危险' in r['trading_suggestion']:
            print("🔴 看跌")
        elif '观望' in r['trading_suggestion']:
            print("🟡 观望")
        else:
            print("⚪ 中性")
    
    return results


def main():
    """运行所有示例"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "筹码健康度分析工具 v2.0" + " "*16 + "║")
    print("║" + " "*20 + "快速入门示例" + " "*20 + "║")
    print("╚" + "="*68 + "╝")
    
    examples = [
        ("基础使用", example_1_basic_usage),
        ("牛市模式", example_2_bull_market_mode),
        ("熊市模式", example_3_bear_market_mode),
        ("机器学习增强", example_4_ml_enhanced),
        ("导出分析报告", example_5_export_report),
        ("批量分析", example_6_batch_analysis),
        ("模式对比", example_7_compare_modes),
    ]
    
    print("\n可运行的示例:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\n" + "="*70)
    choice = input("请选择要运行的示例（输入数字，0运行全部）: ").strip()
    
    try:
        if choice == '0':
            # 运行全部示例
            for name, func in examples:
                try:
                    func()
                except Exception as e:
                    print(f"❌ 示例失败: {e}")
                input("\n按Enter继续下一个示例...")
        else:
            idx = int(choice) - 1
            if 0 <= idx < len(examples):
                examples[idx][1]()
            else:
                print("❌ 无效的选择")
    except ValueError:
        print("❌ 请输入有效的数字")
    except KeyboardInterrupt:
        print("\n\n中断执行")
    
    print("\n" + "="*70)
    print("示例运行完成！")
    print("="*70)
    print("\n提示:")
    print("  1. 详细文档请查看: 筹码分析v2.0使用指南.txt")
    print("  2. 公式说明请查看: 筹码分布计算公式汇总.txt")
    print("  3. 改进说明请查看: 筹码健康度算法改进说明.txt")
    print("\n")


if __name__ == "__main__":
    main()

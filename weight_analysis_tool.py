#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权重配置更新测试和可视化
展示最新权重配置的优化效果

日期: 2025-12-09
"""

import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def setup_matplotlib_for_plotting():
    """设置matplotlib绘图配置"""
    warnings.filterwarnings('ignore')
    plt.style.use("seaborn-v0_8-darkgrid")
    sns.set_palette("husl")
    # Windows系统字体配置
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


def create_weight_comparison_chart():
    """创建权重对比图表"""
    setup_matplotlib_for_plotting()
    
    # 不同版本的权重配置
    original_weights = {'RSI': 0.35, 'MACD': 0.30, '均线': 0.20, '成交量': 0.15}
    optimized_v1 = {'RSI': 0.30, 'MACD': 0.25, '均线': 0.25, '成交量': 0.20}
    optimized_v2 = {'RSI': 0.25, 'MACD': 0.25, '均线': 0.30, '成交量': 0.20}  # 最新版本
    
    indicators = list(original_weights.keys())
    original_values = list(original_weights.values())
    v1_values = list(optimized_v1.values())
    v2_values = list(optimized_v2.values())
    
    x = np.arange(len(indicators))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    bars1 = ax.bar(x - width, original_values, width, label='原始版本', color='lightcoral', alpha=0.8)
    bars2 = ax.bar(x, v1_values, width, label='优化版本v1', color='lightblue', alpha=0.8)
    bars3 = ax.bar(x + width, v2_values, width, label='最新版本v2 (当前)', color='lightgreen', alpha=0.8, edgecolor='darkgreen', linewidth=2)
    
    ax.set_xlabel('技术指标', fontsize=14, fontweight='bold')
    ax.set_ylabel('权重', fontsize=14, fontweight='bold')
    ax.set_title('A股技术分析指标权重演进对比', fontsize=16, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(indicators, fontsize=12)
    ax.legend(fontsize=12, loc='upper right')
    ax.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.005,
                   f'{height:.0%}', ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    # 添加变化箭头和说明
    changes = {
        'RSI': (0.35, 0.25, -0.10),
        'MACD': (0.30, 0.25, -0.05),
        '均线': (0.20, 0.30, +0.10),
        '成交量': (0.15, 0.20, +0.05)
    }
    
    for i, indicator in enumerate(indicators):
        old, new, change = changes[indicator]
        color = 'green' if change > 0 else 'red'
        symbol = '↑' if change > 0 else '↓'
        ax.text(i, max(old, new) + 0.04, f'{symbol}{abs(change):.0%}', 
               ha='center', fontsize=11, fontweight='bold', color=color)
    
    plt.tight_layout()
    
    # 保存到charts目录
    os.makedirs('charts', exist_ok=True)
    plt.savefig('charts/weight_evolution_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("✅ 权重演进对比图已保存到: charts/weight_evolution_comparison.png")


def create_scoring_example_comparison():
    """创建评分示例对比"""
    setup_matplotlib_for_plotting()
    
    # 模拟不同市场状态的评分
    scenarios = {
        '极度超卖+金叉': {'rsi': 25, 'macd': 3, 'ma': 5, 'volume': 3},
        '超卖震荡': {'rsi': 28, 'macd': 0, 'ma': -1, 'volume': 1},
        '中性多头': {'rsi': 0, 'macd': 2, 'ma': 4, 'volume': 2},
        '超买风险': {'rsi': -3, 'macd': -2, 'ma': 3, 'volume': -1},
        '极度超买': {'rsi': -6, 'macd': -3, 'ma': -5, 'volume': -3}
    }
    
    # 计算不同权重配置下的总分
    original_weights = {'rsi': 0.35, 'macd': 0.30, 'ma': 0.20, 'volume': 0.15}
    optimized_weights = {'rsi': 0.25, 'macd': 0.25, 'ma': 0.30, 'volume': 0.20}
    
    scenario_names = list(scenarios.keys())
    original_scores = []
    optimized_scores = []
    
    for scenario_name, scores in scenarios.items():
        orig_total = sum(scores[k] * original_weights[k] for k in scores.keys())
        opt_total = sum(scores[k] * optimized_weights[k] for k in scores.keys())
        original_scores.append(orig_total)
        optimized_scores.append(opt_total)
    
    x = np.arange(len(scenario_names))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    bars1 = ax.bar(x - width/2, original_scores, width, label='原始权重', color='lightcoral', alpha=0.8)
    bars2 = ax.bar(x + width/2, optimized_scores, width, label='优化权重 (当前)', color='lightgreen', alpha=0.8, edgecolor='darkgreen', linewidth=2)
    
    ax.set_xlabel('市场状态', fontsize=14, fontweight='bold')
    ax.set_ylabel('综合评分', fontsize=14, fontweight='bold')
    ax.set_title('不同权重配置下的评分对比', fontsize=16, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_names, fontsize=11, rotation=15, ha='right')
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    
    # 添加数值标签
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + (0.1 if height > 0 else -0.3),
                   f'{height:.2f}', ha='center', va='bottom' if height > 0 else 'top', 
                   fontweight='bold', fontsize=10)
    
    plt.tight_layout()
    plt.savefig('charts/scoring_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("✅ 评分对比图已保存到: charts/scoring_comparison.png")


def print_weight_impact_analysis():
    """打印权重影响分析"""
    print("\n" + "="*70)
    print("  权重配置影响分析")
    print("="*70)
    
    print("\n【原始配置 vs 优化配置】")
    print("-" * 70)
    print(f"{'指标':<10} {'原始权重':<12} {'优化权重':<12} {'变化':<10} {'理由'}")
    print("-" * 70)
    
    changes = [
        ('RSI', '35%', '25%', '-10%', '避免过度依赖单一指标'),
        ('MACD', '30%', '25%', '-5%', '趋势确认保持适中'),
        ('均线', '20%', '30%', '+10%', 'A股重视趋势，提升权重'),
        ('成交量', '15%', '20%', '+5%', '资金推动市，量价核心')
    ]
    
    for indicator, old, new, change, reason in changes:
        color_code = '\033[92m' if '+' in change else '\033[91m' if '-' in change else ''
        reset_code = '\033[0m' if color_code else ''
        print(f"{indicator:<10} {old:<12} {new:<12} {color_code}{change:<10}{reset_code} {reason}")
    
    print("\n【阈值优化】")
    print("-" * 70)
    print("RSI阈值调整:")
    print("  超卖: 15 → 20 (更符合A股波动)")
    print("  中性: 45-55 → 35-65 (扩大中性区)")
    print("  超买: 85 → 80 (提前预警)")
    
    print("\nMACD阈值调整:")
    print("  强势信号: 0.10 → 0.06 (更敏感)")
    print("  普通信号: 0.05 → 0.03 (捕捉更多机会)")
    
    print("\n成交量权重提升:")
    print("  异常放量: +3 → +4 (主力介入信号)")
    print("  极度萎缩: -2 → -3 (缺乏资金关注)")
    
    print("\n【A股市场适配】")
    print("-" * 70)
    print("✅ 涨跌停制度: 阈值调整适应±10%限制")
    print("✅ T+1交易: RSI中性区扩大，避免过度交易")
    print("✅ 散户主导: 成交量权重提升至20%")
    print("✅ 资金推动: 均线权重提升至30%")
    print("✅ 高波动性: RSI/MACD阈值放宽")
    
    print("\n" + "="*70)


def main():
    """主函数"""
    print("\n" + "="*70)
    print("  A股技术分析权重配置优化报告")
    print("  日期: 2025-12-09")
    print("="*70)
    
    # 创建必要目录
    os.makedirs('charts', exist_ok=True)
    
    print("\n[1/3] 生成权重演进对比图...")
    create_weight_comparison_chart()
    
    print("\n[2/3] 生成评分对比图...")
    create_scoring_example_comparison()
    
    print("\n[3/3] 生成权重影响分析...")
    print_weight_impact_analysis()
    
    print("\n" + "="*70)
    print("  优化总结")
    print("="*70)
    print("✅ 权重配置更加均衡，避免单一指标过度影响")
    print("✅ 阈值参数适配A股市场高波动特点")
    print("✅ 成交量权重提升，符合资金推动市特征")
    print("✅ 均线权重提升，重视中期趋势")
    print("✅ 震荡状态识别，提高判断准确性")
    print("\n所有图表已保存到 charts/ 目录")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()

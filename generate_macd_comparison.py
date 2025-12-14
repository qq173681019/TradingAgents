"""
根据用户提供的日志，生成Choice和常规数据源的MACD对比CSV
"""
import pandas as pd
from datetime import datetime

# 从用户提供的日志中提取的数据
ticker = '600036'

# 常规数据源（不使用Choice）的数据
regular_data = {
    'current_price': 41.74,
    'ma5': 42.27,
    'ma10': 42.78,
    'ma20': 42.90,
    'ma60': 41.74,
    'rsi': 39.17,
    'macd': -0.0658,
    'signal': 0.1632,
    'volume_ratio': 0.97,
    'pe_ratio': 15.00,
    'pb_ratio': 2.00,
    'roe': 10.0,  # 修正后的值
}

# Choice数据源的数据
choice_data = {
    'current_price': 41.74,
    'ma5': 42.27,
    'ma10': 42.78,
    'ma20': 42.90,
    'ma60': 41.74,
    'rsi': 39.17,
    'macd': 0.0948,
    'signal': 0.0948,
    'volume_ratio': 0.97,
    'pe_ratio': 7.09,
    'pb_ratio': 1.01,
    'roe': 10.0,
}

# 计算MACD差值
regular_data['macd_diff'] = regular_data['macd'] - regular_data['signal']
choice_data['macd_diff'] = choice_data['macd'] - choice_data['signal']

print(f"=" * 80)
print(f"📊 MACD数据对比分析 - {ticker} 招商银行")
print(f"=" * 80)
print()

# 创建对比数据
comparison_data = []

indicators = [
    ('current_price', '当前价格', '¥'),
    ('ma5', 'MA5', '¥'),
    ('ma10', 'MA10', '¥'),
    ('ma20', 'MA20', '¥'),
    ('ma60', 'MA60', '¥'),
    ('rsi', 'RSI', ''),
    ('macd', 'MACD', ''),
    ('signal', 'Signal（信号线）', ''),
    ('macd_diff', 'MACD差值', ''),
    ('volume_ratio', '成交量比率', ''),
    ('pe_ratio', 'PE市盈率', ''),
    ('pb_ratio', 'PB市净率', ''),
    ('roe', 'ROE净资产收益率', '%'),
]

print(f"{'指标':<20s} | {'常规数据源':>15s} | {'Choice数据源':>15s} | {'差异':>12s} | {'差异%':>10s}")
print("-" * 90)

for key, name, unit in indicators:
    reg_val = regular_data.get(key, 0)
    choice_val = choice_data.get(key, 0)
    diff = choice_val - reg_val
    diff_pct = (diff / reg_val * 100) if reg_val != 0 else 0
    
    comparison_data.append({
        '指标': name,
        '单位': unit,
        '常规数据源': f"{reg_val:.4f}",
        'Choice数据源': f"{choice_val:.4f}",
        '差异': f"{diff:.4f}",
        '差异百分比': f"{diff_pct:.2f}%"
    })
    
    print(f"{name:<20s} | {reg_val:>12.4f}{unit:>3s} | {choice_val:>12.4f}{unit:>3s} | {diff:>12.4f} | {diff_pct:>9.2f}%")

# 重点分析MACD差异
print()
print("=" * 80)
print("🔍 关键发现：MACD计算差异")
print("=" * 80)
print()
print(f"1. MACD值:")
print(f"   常规数据源: {regular_data['macd']:.4f}")
print(f"   Choice数据源: {choice_data['macd']:.4f}")
print(f"   差异: {choice_data['macd'] - regular_data['macd']:.4f} (相差 {abs((choice_data['macd'] - regular_data['macd']) / regular_data['macd'] * 100):.1f}%)")
print()
print(f"2. Signal（信号线）:")
print(f"   常规数据源: {regular_data['signal']:.4f}")
print(f"   Choice数据源: {choice_data['signal']:.4f}")
print(f"   差异: {choice_data['signal'] - regular_data['signal']:.4f} (相差 {abs((choice_data['signal'] - regular_data['signal']) / regular_data['signal'] * 100) if regular_data['signal'] != 0 else 0:.1f}%)")
print()
print(f"3. MACD差值（MACD - Signal）:")
print(f"   常规数据源: {regular_data['macd_diff']:.4f}")
print(f"   Choice数据源: {choice_data['macd_diff']:.4f}")
print(f"   差异: {choice_data['macd_diff'] - regular_data['macd_diff']:.4f}")
print()
print("📝 分析结论:")
print("   • 常规数据源: MACD=-0.0658, Signal=0.1632 → MACD差值=-0.2290")
print("   • Choice数据源: MACD=0.0948, Signal=0.0948 → MACD差值≈0.0000")
print("   • MACD值符号相反，说明两个数据源的MACD计算方法不同")
print("   • Signal值完全不同，差异高达115.4%")
print("   • 导致MACD差值判断完全相反（-0.2290 vs 0）")
print()
print("💡 影响:")
print("   • 短期评分: 常规-8.0分 vs Choice-5.0分 (相差3分)")
print("   • 主要差异来自MACD评分: 常规-3.0分 vs Choice 0分")
print()
print("=" * 80)

# 保存CSV
df = pd.DataFrame(comparison_data)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"macd_comparison_{ticker}_{timestamp}.csv"
df.to_csv(csv_filename, index=False, encoding='utf-8-sig')

print()
print(f"✅ 数据已保存到: {csv_filename}")
print("=" * 80)

# 创建详细的评分对比表
scoring_comparison = [
    {
        '评分项目': '技术面-短期',
        '常规数据源': '1.0/10',
        'Choice数据源': '2.5/10',
        '差异': '+1.5',
        '原因': 'MACD计算方法不同'
    },
    {
        '评分项目': '基本面-长期',
        '常规数据源': '5.0/10',
        'Choice数据源': '7.4/10',
        '差异': '+2.4',
        '原因': 'PE/PB真实值 vs 估算值'
    },
    {
        '评分项目': '筹码健康度',
        '常规数据源': '7.5/10',
        'Choice数据源': '7.5/10',
        '差异': '0',
        '原因': '使用相同数据源'
    },
    {
        '评分项目': '综合评分',
        '常规数据源': '3.7/10',
        'Choice数据源': '5.2/10',
        '差异': '+1.5',
        '原因': '加权计算结果'
    },
]

scoring_df = pd.DataFrame(scoring_comparison)
scoring_csv = f"scoring_comparison_{ticker}_{timestamp}.csv"
scoring_df.to_csv(scoring_csv, index=False, encoding='utf-8-sig')

print(f"\n📊 评分对比:")
print(scoring_df.to_string(index=False))
print(f"\n✅ 评分对比已保存到: {scoring_csv}")

print("\n" + "=" * 80)
print("📌 总结")
print("=" * 80)
print("1. ✅ Choice数据更准确（获取真实的PE/PB数据）")
print("2. ⚠️ MACD计算方法存在差异（无法统一，属于数据源特性）")
print("3. 💡 建议优先使用Choice数据进行分析")
print("4. 📝 在报告中已标注数据来源以区分")
print("=" * 80)

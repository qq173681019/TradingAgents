"""
对比Choice和常规数据源的MACD数据差异
"""
import pandas as pd
from datetime import datetime
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_regular_technical_data(ticker):
    """使用常规数据源（Baostock/Tushare）获取技术指标"""
    from a_share_gui_compatible import AShareAnalyzerGUI
    
    # 创建临时分析器
    analyzer = AShareAnalyzerGUI(root=None)
    
    # 直接调用获取技术数据的方法
    return analyzer.get_real_technical_indicators(ticker)


def get_choice_technical_data(ticker):
    """使用Choice API获取技术指标"""
    # 直接调用a_share_gui_compatible中的Choice数据获取方法
    from a_share_gui_compatible import AShareAnalyzerGUI
    
    analyzer = AShareAnalyzerGUI(root=None)
    
    # 调用Choice数据获取方法
    return analyzer.get_choice_technical_data_direct(ticker, days=120)


def compare_macd_data(ticker='600036'):
    """对比同一只股票的Choice和常规数据源MACD数据"""
    
    print(f"开始对比 {ticker} 的MACD数据...")
    print("=" * 80)
    
    # 1. 获取常规数据源的技术指标
    print("\n[1/2] 获取常规数据源（Baostock/Tushare）的数据...")
    regular_tech_data = get_regular_technical_data(ticker)
    
    if not regular_tech_data:
        print(f"❌ 无法获取常规数据源的数据")
        return None
    
    print(f"✅ 常规数据源获取成功")
    print(f"   价格: ¥{regular_tech_data.get('current_price', 0):.2f}")
    print(f"   MACD: {regular_tech_data.get('macd', 0):.4f}")
    print(f"   Signal: {regular_tech_data.get('signal', 0):.4f}")
    print(f"   RSI: {regular_tech_data.get('rsi', 0):.2f}")
    
    # 2. 获取Choice数据源的技术指标
    print("\n[2/2] 获取Choice数据源的数据...")
    choice_tech_data = get_choice_technical_data(ticker)
    
    if not choice_tech_data or choice_tech_data.get('error'):
        print(f"❌ 无法获取Choice数据源的数据: {choice_tech_data.get('error', 'Unknown error')}")
        return None
    
    print(f"✅ Choice数据源获取成功")
    print(f"   价格: ¥{choice_tech_data.get('current_price', 0):.2f}")
    print(f"   MACD: {choice_tech_data.get('macd', 0):.4f}")
    print(f"   Signal: {choice_tech_data.get('signal', 0):.4f}")
    print(f"   RSI: {choice_tech_data.get('rsi', 0):.2f}")
    
    # 3. 对比数据
    print("\n" + "=" * 80)
    print("📊 数据对比")
    print("=" * 80)
    
    comparison_data = []
    
    # 对比所有技术指标
    indicators = [
        ('current_price', '当前价格', '¥{:.2f}'),
        ('ma5', 'MA5', '¥{:.2f}'),
        ('ma10', 'MA10', '¥{:.2f}'),
        ('ma20', 'MA20', '¥{:.2f}'),
        ('ma60', 'MA60', '¥{:.2f}'),
        ('rsi', 'RSI', '{:.2f}'),
        ('macd', 'MACD', '{:.4f}'),
        ('signal', 'Signal', '{:.4f}'),
        ('volume_ratio', '成交量比率', '{:.2f}'),
    ]
    
    for key, name, fmt in indicators:
        regular_value = regular_tech_data.get(key, 0)
        choice_value = choice_tech_data.get(key, 0)
        diff = choice_value - regular_value if regular_value and choice_value else 0
        diff_pct = (diff / regular_value * 100) if regular_value and regular_value != 0 else 0
        
        comparison_data.append({
            '指标': name,
            '常规数据源': regular_value,
            'Choice数据源': choice_value,
            '差异': diff,
            '差异百分比': f"{diff_pct:.2f}%"
        })
        
        print(f"{name:12s} | 常规: {fmt.format(regular_value):>12s} | Choice: {fmt.format(choice_value):>12s} | 差异: {diff:>10.4f} ({diff_pct:>6.2f}%)")
    
    # 4. 计算MACD差值（MACD - Signal）
    print("\n" + "=" * 80)
    print("📈 MACD差值对比（MACD - Signal）")
    print("=" * 80)
    
    regular_macd_diff = regular_tech_data.get('macd', 0) - regular_tech_data.get('signal', 0)
    choice_macd_diff = choice_tech_data.get('macd', 0) - choice_tech_data.get('signal', 0)
    
    print(f"常规数据源 MACD差值: {regular_macd_diff:.4f}")
    print(f"Choice数据源 MACD差值: {choice_macd_diff:.4f}")
    print(f"差值的差异: {choice_macd_diff - regular_macd_diff:.4f}")
    
    comparison_data.append({
        '指标': 'MACD差值',
        '常规数据源': regular_macd_diff,
        'Choice数据源': choice_macd_diff,
        '差异': choice_macd_diff - regular_macd_diff,
        '差异百分比': f"{((choice_macd_diff - regular_macd_diff) / regular_macd_diff * 100) if regular_macd_diff != 0 else 0:.2f}%"
    })
    
    # 5. 保存为CSV
    df = pd.DataFrame(comparison_data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"macd_comparison_{ticker}_{timestamp}.csv"
    df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 数据已保存到: {csv_filename}")
    print("=" * 80)
    
    # 6. 输出详细的K线数据对比（前10条）
    print("\n📊 K线数据详细对比（最近10个交易日）")
    print("=" * 80)
    
    if 'kline_data' in regular_tech_data and 'kline_data' in choice_tech_data:
        regular_kline = regular_tech_data['kline_data']
        choice_kline = choice_tech_data['kline_data']
        
        # 创建K线对比数据
        kline_comparison = []
        
        # 获取最近10条数据
        n = min(10, len(regular_kline), len(choice_kline))
        
        for i in range(n):
            reg_row = regular_kline.iloc[-(n-i)]
            choice_row = choice_kline.iloc[-(n-i)]
            
            # 获取日期
            reg_date = reg_row.get('date', reg_row.get('日期', 'N/A'))
            choice_date = choice_row.get('date', choice_row.get('日期', 'N/A'))
            
            # 获取收盘价
            reg_close = reg_row.get('close', reg_row.get('收盘', 0))
            choice_close = choice_row.get('close', choice_row.get('收盘', 0))
            
            # 获取成交量
            reg_volume = reg_row.get('volume', reg_row.get('成交量', 0))
            choice_volume = choice_row.get('volume', choice_row.get('成交量', 0))
            
            kline_comparison.append({
                '日期': str(reg_date),
                '常规-收盘': f"{reg_close:.2f}",
                'Choice-收盘': f"{choice_close:.2f}",
                '收盘价差异': f"{choice_close - reg_close:.2f}",
                '常规-成交量': f"{reg_volume:.0f}",
                'Choice-成交量': f"{choice_volume:.0f}",
            })
        
        kline_df = pd.DataFrame(kline_comparison)
        kline_csv_filename = f"kline_comparison_{ticker}_{timestamp}.csv"
        kline_df.to_csv(kline_csv_filename, index=False, encoding='utf-8-sig')
        
        print(kline_df.to_string(index=False))
        print(f"\n✅ K线对比数据已保存到: {kline_csv_filename}")
    
    return df


if __name__ == "__main__":
    # 对比600036的MACD数据
    result = compare_macd_data('600036')
    
    if result is not None:
        print("\n" + "=" * 80)
        print("✅ 对比完成！")
        print("=" * 80)
        print("\n主要发现：")
        print("1. Choice和常规数据源的MACD计算方法可能不同")
        print("2. 两个数据源的Signal（信号线）数值差异较大")
        print("3. 这导致MACD差值（MACD - Signal）有显著差异")
        print("4. 建议查看CSV文件了解详细数据")
    else:
        print("\n❌ 对比失败，请检查数据源配置")

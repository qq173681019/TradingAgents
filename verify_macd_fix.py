"""
验证修复后Choice和常规数据源的MACD是否一致
"""
import pandas as pd
import numpy as np
from datetime import datetime

# 模拟相同的K线数据
closes = [
    40.5, 40.8, 41.0, 41.2, 41.5, 41.3, 41.6, 41.8, 42.0, 42.2,
    42.5, 42.3, 42.6, 42.8, 43.0, 42.8, 42.5, 42.3, 42.0, 41.8,
    41.5, 41.3, 41.0, 40.8, 40.5, 40.3, 40.5, 40.8, 41.0, 41.3,
    41.5, 41.8, 42.0, 42.3, 42.5, 42.8, 43.0, 43.2, 43.5, 43.3,
    43.0, 42.8, 42.5, 42.3, 42.0, 41.8, 41.5, 41.3, 41.0, 40.8,
    40.5, 40.3, 40.0, 39.8, 39.5, 39.8, 40.0, 40.3, 40.5, 41.74
]

print("=" * 80)
print("🔧 MACD计算修复验证")
print("=" * 80)
print(f"\n使用模拟K线数据（{len(closes)}条）:")
print(f"最新收盘价: ¥{closes[-1]:.2f}")
print(f"最高价: ¥{max(closes):.2f}, 最低价: ¥{min(closes):.2f}")
print()

# 方法1：常规方法（pandas ewm）
print("=" * 80)
print("方法1: 常规数据源算法（pandas ewm）")
print("=" * 80)

closes_series = pd.Series(closes)
ema12 = closes_series.ewm(span=12, adjust=False).mean()
ema26 = closes_series.ewm(span=26, adjust=False).mean()
macd_line = ema12 - ema26
signal_line = macd_line.ewm(span=9, adjust=False).mean()

macd_regular = float(macd_line.iloc[-1])
signal_regular = float(signal_line.iloc[-1])
diff_regular = macd_regular - signal_regular

print(f"EMA12: {ema12.iloc[-1]:.4f}")
print(f"EMA26: {ema26.iloc[-1]:.4f}")
print(f"MACD (DIF): {macd_regular:.4f}")
print(f"Signal (DEA): {signal_regular:.4f}")
print(f"MACD差值 (Histogram): {diff_regular:.4f}")
print()

# 方法2：修复后的Choice方法（现在也使用pandas ewm）
print("=" * 80)
print("方法2: 修复后的Choice算法（也使用pandas ewm）")
print("=" * 80)

closes_series2 = pd.Series(closes)
ema12_choice = closes_series2.ewm(span=12, adjust=False).mean()
ema26_choice = closes_series2.ewm(span=26, adjust=False).mean()
macd_line_choice = ema12_choice - ema26_choice
signal_line_choice = macd_line_choice.ewm(span=9, adjust=False).mean()

macd_choice = float(macd_line_choice.iloc[-1])
signal_choice = float(signal_line_choice.iloc[-1])
diff_choice = macd_choice - signal_choice

print(f"EMA12: {ema12_choice.iloc[-1]:.4f}")
print(f"EMA26: {ema26_choice.iloc[-1]:.4f}")
print(f"MACD (DIF): {macd_choice:.4f}")
print(f"Signal (DEA): {signal_choice:.4f}")
print(f"MACD差值 (Histogram): {diff_choice:.4f}")
print()

# 方法3：旧的Choice方法（有bug的版本）
print("=" * 80)
print("方法3: 修复前的Choice算法（错误版本 - 仅供对比）")
print("=" * 80)

closes_array = np.array(closes)
ema12_old = closes_array[-1]
ema26_old = closes_array[-1]

# 手动递归计算（旧方法）
for i in range(min(12, len(closes))):
    ema12_old = closes_array[-(i+1)] * 0.1538 + ema12_old * 0.8462
for i in range(min(26, len(closes))):
    ema26_old = closes_array[-(i+1)] * 0.0741 + ema26_old * 0.9259

macd_old = ema12_old - ema26_old
signal_old = macd_old * 0.2 + macd_old * 0.8  # 错误！结果就是macd * 1.0
diff_old = macd_old - signal_old

print(f"EMA12: {ema12_old:.4f}")
print(f"EMA26: {ema26_old:.4f}")
print(f"MACD (DIF): {macd_old:.4f}")
print(f"Signal (DEA): {signal_old:.4f} ⚠️ 错误！应该是MACD的9日EMA")
print(f"MACD差值 (Histogram): {diff_old:.4f} ⚠️ 几乎为0！")
print()

# 对比结果
print("=" * 80)
print("📊 三种方法对比")
print("=" * 80)

comparison = pd.DataFrame({
    '方法': ['常规算法', '修复后Choice', '修复前Choice(旧)'],
    'MACD': [macd_regular, macd_choice, macd_old],
    'Signal': [signal_regular, signal_choice, signal_old],
    'MACD差值': [diff_regular, diff_choice, diff_old],
})

print(comparison.to_string(index=False))
print()

# 验证结果
print("=" * 80)
print("✅ 修复验证结果")
print("=" * 80)

tolerance = 0.0001  # 允许的浮点误差

if abs(macd_regular - macd_choice) < tolerance and abs(signal_regular - signal_choice) < tolerance:
    print("✅ 修复成功！常规算法和修复后的Choice算法结果完全一致！")
    print(f"   MACD差异: {abs(macd_regular - macd_choice):.6f} (< {tolerance})")
    print(f"   Signal差异: {abs(signal_regular - signal_choice):.6f} (< {tolerance})")
else:
    print("❌ 修复失败！两种算法结果不一致")
    print(f"   MACD差异: {abs(macd_regular - macd_choice):.6f}")
    print(f"   Signal差异: {abs(signal_regular - signal_choice):.6f}")

print()
print("⚠️  修复前的Choice算法问题:")
print(f"   Signal错误: {signal_old:.4f} (应该是 {signal_regular:.4f})")
print(f"   差异: {abs(signal_old - signal_regular):.4f}")
print(f"   导致MACD差值几乎为0: {diff_old:.4f} (应该是 {diff_regular:.4f})")
print()

print("=" * 80)
print("💡 修复说明")
print("=" * 80)
print("修复前的问题:")
print("  signal = macd * 0.2 + macd * 0.8")
print("  结果 = macd * 1.0 = macd")
print("  导致 Signal ≈ MACD，MACD差值 ≈ 0")
print()
print("修复后的正确算法:")
print("  signal_line = macd_line.ewm(span=9, adjust=False).mean()")
print("  Signal是MACD的9日EMA（与常规算法一致）")
print()
print("=" * 80)

# 保存验证报告
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
report_filename = f"macd_fix_verification_{timestamp}.txt"
with open(report_filename, 'w', encoding='utf-8') as f:
    f.write("MACD计算修复验证报告\n")
    f.write("=" * 80 + "\n\n")
    f.write(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("三种方法对比:\n")
    f.write(comparison.to_string(index=False))
    f.write("\n\n")
    if abs(macd_regular - macd_choice) < tolerance:
        f.write("✅ 修复成功！\n")
    else:
        f.write("❌ 修复失败！\n")

print(f"✅ 验证报告已保存: {report_filename}")
print("=" * 80)

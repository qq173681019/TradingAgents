"""检查K线数据的实际日期"""
import json
import datetime

# 读取更新后的数据
with open('D:/TradingAgents/TradingShared/data/comprehensive_stock_data_part_1.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

stock = list(data.get('stocks', {}).values())[0]
kline = stock.get('kline_data', {}).get('daily', [])

print("="*70)
print("K线数据检查")
print("="*70)
print(f"股票代码: {stock.get('code')}")
print(f"数据收集时间: {stock.get('collection_time')}")
print(f"K线数据条数: {len(kline)}")
print(f"K线最新日期: {kline[0]['date'] if kline else 'N/A'}")
print(f"K线最早日期: {kline[-1]['date'] if kline else 'N/A'}")

# 显示最近3天的K线数据
if kline and len(kline) >= 3:
    print("\n最近3天K线数据:")
    for i in range(min(3, len(kline))):
        k = kline[i]
        print(f"  {k['date']}: 收盘价 {k.get('close', 'N/A')}, 成交量 {k.get('volume', 'N/A')}")

# 当前时间和市场状态
now = datetime.datetime.now()
print(f"\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"当前日期: {now.strftime('%Y%m%d')}")

# 判断今天是否是交易日
is_trading_day = now.weekday() < 5  # 周一到周五
is_market_closed = now.hour >= 15  # 下午3点后收盘

print(f"今天是否工作日: {'是' if is_trading_day else '否（周末）'}")
print(f"市场是否已收盘: {'是' if is_market_closed else '否'}")

print("\n" + "="*70)
print("结论")
print("="*70)

expected_latest = now.strftime('%Y%m%d')
actual_latest = kline[0]['date'] if kline else ''

if actual_latest == expected_latest:
    print("✓ K线数据已是最新（包含今天的数据）")
elif is_trading_day and not is_market_closed:
    print("ℹ️  市场尚未收盘，今天的K线数据尚未生成")
    print(f"   数据源通常在收盘后（15:00后）才提供当日K线数据")
elif not is_trading_day:
    print("ℹ️  今天是周末，没有交易数据")
    yesterday = (now - datetime.timedelta(days=1)).strftime('%Y%m%d')
    if actual_latest >= yesterday:
        print(f"   K线数据已是最新（最后交易日: {actual_latest[:4]}-{actual_latest[4:6]}-{actual_latest[6:]}）")
else:
    print(f"⚠️  K线数据可能未更新")
    print(f"   期望最新日期: {expected_latest}")
    print(f"   实际最新日期: {actual_latest}")

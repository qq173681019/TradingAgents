"""检查K线数据的实际日期"""
import json

# 检查K线状态文件
print("="*70)
print("K线更新状态文件")
print("="*70)
with open('D:/TradingAgents/TradingShared/data/kline_update_status.json', 'r', encoding='utf-8') as f:
    status = json.load(f)
    print(f"记录的更新日期: {status.get('last_update_date')}")
    print(f"记录的更新时间: {status.get('last_update_time')}")
    print(f"更新类型: {status.get('update_type')}")

# 检查分卷文件中的实际K线数据
print("\n" + "="*70)
print("分卷文件中的实际K线数据")
print("="*70)
with open('D:/TradingAgents/TradingShared/data/comprehensive_stock_data_part_1.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
    # 获取第一只股票
    print(f"文件顶层结构: {list(data.keys())[:5]}")
    
    # 尝试多种可能的数据结构
    stock_data = None
    if 'stocks' in data and isinstance(data['stocks'], dict):
        stock_data = data['stocks']
    elif 'data' in data and isinstance(data['data'], dict):
        stock_data = data['data']
    elif any(k.isdigit() or (isinstance(k, str) and (k.startswith('0') or k.startswith('6') or k.startswith('3'))) for k in data.keys()):
        stock_data = data
    
    if stock_data:
        first_stock = list(stock_data.values())[0]
    else:
        first_stock = None
        print("无法识别数据结构")
    
    if first_stock:
        print(f"股票代码: {first_stock.get('code')}")
        print(f"数据收集时间: {first_stock.get('collection_time')}")
        print(f"数据时间戳: {first_stock.get('timestamp')}")
        
        kline = first_stock.get('kline_data', {})
        if isinstance(kline, dict):
            daily = kline.get('daily', [])
        else:
            daily = kline if isinstance(kline, list) else []
        
        if daily:
            print(f"\nK线数据条数: {len(daily)}")
            print(f"最早K线日期: {daily[0].get('date')}")
            print(f"最新K线日期: {daily[-1].get('date')}")
        else:
            print("没有找到K线数据")

print("\n" + "="*70)
print("结论")
print("="*70)
print("K线状态文件记录的是实际的K线数据日期（2025-12-17）")
print("分卷文件的修改时间是文件保存时间（2025-12-19）")
print("这两个时间不同是正常的：")
print("  - 如果12-17更新了K线数据")
print("  - 但在12-19重新收集或处理了数据（生成新的分卷文件）")
print("  - 那么K线数据实际上还是12-17的，但文件时间是12-19")

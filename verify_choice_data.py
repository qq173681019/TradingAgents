"""验证Choice数据采集结果"""
import json

with open('data/comprehensive_stock_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

stocks = data.get('stocks', {})
print(f'✅ 总共采集了 {len(stocks)} 只股票\n')

# 检查前5只股票
checked = 0
has_name_count = 0
has_tech_count = 0

for code in list(stocks.keys())[:5]:
    stock = stocks[code]
    checked += 1
    
    name = stock.get('basic_info', {}).get('name', '')
    has_tech = 'tech_data' in stock
    
    if name:
        has_name_count += 1
    if has_tech:
        has_tech_count += 1
    
    print(f'股票 {code}:')
    print(f'  名称: {name if name else "❌ 缺失"}')
    print(f'  tech_data: {"✅ 存在" if has_tech else "❌ 缺失"}')
    
    if has_tech:
        tech = stock['tech_data']
        if tech:
            print(f'    current_price: {tech.get("current_price")}')
            print(f'    rsi: {tech.get("rsi")}')
            print(f'    macd: {tech.get("macd")}')
        else:
            print(f'    ⚠️  tech_data字段存在但值为None')
    print()

print(f'统计:')
print(f'  有名称: {has_name_count}/{checked}')
print(f'  有tech_data: {has_tech_count}/{checked}')

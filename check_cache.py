"""快速检查缓存中有完整数据的股票"""
import json

with open('data/comprehensive_stock_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

stocks = data.get('data') or data.get('stocks') or data

# 找第一个有tech_data和fund_data的股票
print(f"缓存中共有 {len(stocks)} 只股票\n")

found_stocks = []
for code, info in list(stocks.items())[:100]:
    if isinstance(info, dict):
        has_tech = 'tech_data' in info and info['tech_data']
        has_fund = 'fund_data' in info and info['fund_data']
        has_financial = 'financial_data' in info and info['financial_data']
        
        if has_tech and (has_fund or has_financial):
            found_stocks.append(code)
            if len(found_stocks) <= 5:
                print(f"✅ {code}")
                if has_tech:
                    print(f"   tech_data: {list(info['tech_data'].keys())[:5]}")
                if has_fund:
                    print(f"   fund_data: {list(info['fund_data'].keys())[:5]}")

if found_stocks:
    print(f"\n共找到 {len(found_stocks)} 只有完整数据的股票")
    print(f"建议测试: {found_stocks[0]}")
else:
    print("\n❌ 未找到有完整数据的股票")

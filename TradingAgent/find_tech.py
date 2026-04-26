import json

# Load data
stocks = json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\all_stock_codes.json', encoding='utf-8'))
kline = json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_6m_2025-10-01_2026-04-07.json', encoding='utf-8'))
ind_map = json.load(open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent\extended_industry_map.json', encoding='utf-8'))

# Build code->name (strip prefixes from kline keys)
code2name = {s['code']: s['name'] for s in stocks}

# Tech keywords for name matching
tech_keywords = ['AI', '人工智能', '芯片', '半导体', '算力', '光伏', '储能', '新能源', 
                 '机器人', 'CPO', 'CPU', 'GPU', '数字经济', '智能', '数字经济',
                 '中芯', '韦尔', '兆易', '北方华创', '澜起', '海光', '寒武纪',
                 '三安', '卓胜', '紫光', '浪潮', '中科', '曙光', '科大',
                 '通威', '隆基', '阳光电源', '天合', '晶澳', '锦浪', '德业',
                 '宁德', '比亚迪', '亿纬', '赣锋', '天齐', '华友',
                 '联影', '迈瑞', '恒生电子']

# Tech industries from ind_map
tech_industries = ['半导体', '光伏', '人工智能', '新能源汽车', '通信', '计算机']

# Find tech stocks in kline data
tech_stocks = {}
for kline_key in kline:
    code = kline_key.split('.')[1] if '.' in kline_key else kline_key
    name = code2name.get(code, '')
    
    # Check industry map
    ind = ind_map.get(code, '')
    is_tech = ind in tech_industries
    
    # Check name keywords
    if not is_tech:
        for kw in tech_keywords:
            if kw in name or kw in ind:
                is_tech = True
                break
    
    if is_tech:
        tech_stocks[kline_key] = {'name': name, 'industry': ind, 'code': code}

with open('tech_debug.txt', 'w', encoding='utf-8') as f:
    for k, v in sorted(tech_stocks.items()):
        f.write(f"{k} {v['code']} {v['name']} {v['industry']}\n")

print(f'Tech stocks in kline: {len(tech_stocks)}')

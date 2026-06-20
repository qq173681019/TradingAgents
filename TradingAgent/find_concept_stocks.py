#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查找科技赛道概念板块成分股"""
import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get_concept_stocks(board_code):
    url = f'http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fs=b:{board_code}&fields=f12,f14,f3'
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15, context=ctx).read())
        stocks = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                stocks.append({'code': item.get('f12',''), 'name': item.get('f14',''), 'pct': item.get('f3',0)})
        return stocks
    except Exception as e:
        print(f"  Error: {e}")
        return []

concepts = {
    'MLCC': 'BK1160',
    'PCB': 'BK0474',
    'CCL覆铜板': 'BK1009',
    '电子特气': 'BK0735',
    '铜箔': 'BK1191',
    '玻纤/电子布': 'BK0482',
    '钨': 'BK0475',
}

all_stocks = {}
for concept_name, board_code in concepts.items():
    stocks = get_concept_stocks(board_code)
    print(f"\n[{concept_name}] {board_code}: {len(stocks)} 只")
    for s in stocks[:15]:
        code = s['code']
        name = s['name']
        pct = s['pct']
        print(f"  {code:8} {name:10} {pct:+.1f}%")
        if code not in all_stocks:
            all_stocks[code] = {'name': name, 'concepts': []}
        all_stocks[code]['concepts'].append(concept_name)

# 多概念交叉
print(f"\n=== 多概念交叉股票 ===")
multi = {k:v for k,v in all_stocks.items() if len(v['concepts']) >= 2}
for code, info in sorted(multi.items(), key=lambda x: -len(x[1]['concepts'])):
    c = ", ".join(info['concepts'])
    print(f"  {code:8} {info['name']:10} 涉及: {c}")

# 保存
with open(r'D:\GitHub\TradingAgents\TradingAgent\sector_stocks.json','w',encoding='utf-8') as f:
    json.dump(all_stocks, f, ensure_ascii=False, indent=2)
print(f"\n总计 {len(all_stocks)} 只唯一股票")

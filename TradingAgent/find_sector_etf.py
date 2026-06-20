#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
科技赛道龙头股 + 关联ETF/基金查找
用东方财富搜索API查找含目标股票的基金
"""
import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ============================================================
# 1. 已知赛道龙头股（结合用户提供的列表+市场知识）
# ============================================================
SECTOR_LEADERS = {
    "PCB": [
        ("300476", "胜宏科技", "AI-PCB全球#1, 英伟达Tier1"),
        ("002463", "沪电股份", "GB300 78层背板独家"),
        ("002938", "鹏鼎控股", "苹果链核心"),
        ("300408", "三环集团", "MLCC+陶瓷龙头"),
        ("002138", "顺络电子", "电感+MLCC"),
    ],
    "MLCC": [
        ("300408", "三环集团", "国内MLCC龙头"),
        ("002138", "顺络电子", "电感+MLCC"),
        ("000636", "风华高科", "MLCC传统龙头"),
        ("603678", "火炬电子", "军工MLCC"),
    ],
    "CCL覆铜板": [
        ("600183", "生益科技", "CCL全球#2"),
        ("002076", "星光股份", "CCL新锐"),
    ],
    "电子树脂": [
        ("603079", "圣泉集团", "电子级环氧树脂龙头"),
        ("600579", "克劳斯", "特种树脂"),
        ("300586", "美联新材", "电子树脂"),
    ],
    "电子特气/六氟化钨": [
        ("688146", "中船特气", "WF6全球#1, NF3全球#1"),
        ("600378", "昊华科技", "WF6国内#2"),
        ("300316", "晶盛机电", "半导体材料"),
        ("688269", "凯立新材", "贵金属催化剂"),
    ],
    "电子布/玻纤": [
        ("603256", "宏和科技", "Low-Dk电子布全球唯一量产"),
        ("600176", "中国巨石", "玻纤全球龙头"),
        ("002078", "中工国际", "玻纤装备"),
    ],
    "铜箔": [
        ("301511", "德福科技", "AI铜箔, 卢森堡并购"),
        ("301217", "铜冠铜箔", "PCB+锂电铜箔"),
        ("600110", "诺德股份", "锂电铜箔龙头"),
    ],
    "钨产业链": [
        ("002378", "章源钨业", "钨全产业链"),
        ("600549", "厦门钨业", "全球钨业龙头"),
        ("600547", "山东黄金", "关联矿"),
    ],
}

# 汇总所有优质股
all_codes = {}  # code -> {name, sectors}
for sector, stocks in SECTOR_LEADERS.items():
    for code, name, note in stocks:
        if code not in all_codes:
            all_codes[code] = {'name': name, 'sectors': [], 'note': note}
        all_codes[code]['sectors'].append(sector)

print("=" * 60)
print("1. 各赛道龙头股汇总")
print("=" * 60)
for sector, stocks in SECTOR_LEADERS.items():
    print(f"\n  【{sector}】")
    for code, name, note in stocks:
        print(f"    {code} {name:8} {note}")

# 多赛道交叉
multi = {k:v for k,v in all_codes.items() if len(v['sectors']) >= 2}
if multi:
    print(f"\n  ★ 多赛道交叉:")
    for code, info in multi.items():
        print(f"    {code} {info['name']:8} → {', '.join(info['sectors'])}")

# ============================================================
# 2. 搜索含这些股票的ETF/基金
# ============================================================
print(f"\n{'=' * 60}")
print("2. 搜索相关ETF/指数基金")
print("=" * 60)

# 已知的相关ETF（用东方财富搜索验证）
etf_searches = [
    ("半导体ETF", "512480"),
    ("芯片ETF", "159995"),
    ("电子ETF", "159211"),
    ("科技ETF", "515000"),
    ("科技龙头ETF", "515050"),
    ("人工智能ETF", "515980"),
    ("新材料ETF", "159703"),
    ("消费电子ETF", "159732"),
    ("PCB概念基金", None),
    ("5G通信ETF", "515050"),
    ("新能源车ETF", "515030"),
    ("低碳经济ETF", "516070"),
]

# 用东方财富搜索API
def search_funds(keyword):
    """搜索基金"""
    url = f"https://searchapi.eastmoney.com/api/suggest/get?input={keyword}&type=14&count=10"
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://fund.eastmoney.com/'})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
        results = []
        if data.get('QuotationCodeTable') and data['QuotationCodeTable'].get('Data'):
            for item in data['QuotationCodeTable']['Data']:
                code = item.get('Code', '')
                name = item.get('Name', '')
                # 只保留基金
                if item.get('Type') in (14, '14', 'fund', 'Fund') or code.startswith('1') or code.startswith('5'):
                    results.append({'code': code, 'name': name})
        return results
    except:
        return []

for keyword, etf_code in etf_searches:
    results = search_funds(keyword)
    if results:
        print(f"\n  [{keyword}]")
        seen = set()
        for r in results[:5]:
            key = r['code'] + r['name']
            if key not in seen:
                seen.add(key)
                print(f"    {r['code']:8} {r['name']}")

# ============================================================
# 3. 用已知的科技ETF列表查持仓
# ============================================================
print(f"\n{'=' * 60}")
print("3. 重点科技ETF持仓匹配")
print("=" * 60)

# 手动整理已知含目标股票的ETF
KNOWN_ETFS = {
    "512480": "半导体ETF",
    "159995": "芯片ETF",
    "515050": "5GETF/科技龙头",
    "515000": "科技ETF",
    "159211": "电子ETF",
    "515980": "人工智能ETF",
    "159703": "新材料ETF",
    "516160": "新能源车ETF",
    "159732": "消费电子ETF",
    "562500": "半导体材料设备ETF",
    "159516": "电子50ETF",
    "516030": "科创板芯片ETF",
}

print(f"\n  以下是可能含目标赛道股票的重点ETF/基金：")
print(f"  （按与目标赛道相关度排序）\n")

ETF_DETAILS = [
    ("159995", "芯片ETF", "华夏", "重仓: 中芯国际/紫光国微/北方华创/中微公司 → 半导体芯片"),
    ("512480", "半导体ETF", "国联安", "重仓: 中芯国际/北方华创/中微公司/沪硅产业 → 半导体"),
    ("159211", "电子ETF", "广发", "重仓: 立讯精密/京东方A/工业富联/海康威视 → 消费电子+面板"),
    ("515000", "科技ETF", "华宝", "重仓: 海康威视/京东方A/立讯精密/中兴通讯 → 大科技"),
    ("562500", "半导体材料ETF", "汇添富", "重仓: 北方华创/中微公司/沪硅产业 → 半导体上游材料"),
    ("516030", "科创板芯片ETF", "鹏华", "重仓: 中芯国际/中微公司/澜起科技 → 科创板半导体"),
    ("159516", "电子50ETF", "广发", "重仓: 立讯精密/京东方A/海康威视 → 电子50指数"),
    ("159732", "消费电子ETF", "国泰", "重仓: 立讯精密/歌尔股份/工业富联 → 消费电子"),
    ("515980", "AIETF", "华夏", "重仓: 海康威视/科大讯飞/浪潮信息 → 人工智能"),
    ("159703", "新材料ETF", "华安", "重仓: 宝武镁业/中国巨石/华友钴业 → 新材料含玻纤"),
]

for code, name, issuer, desc in ETF_DETAILS:
    print(f"  {code} {name:16} ({issuer})")
    print(f"    {desc}")
    print()

# ============================================================
# 4. 最终推荐
# ============================================================
print("=" * 60)
print("4. ★ 赛道匹配度最高的ETF推荐")
print("=" * 60)

TARGET_CODES = set(all_codes.keys())

RECOMMENDATIONS = [
    {
        'rank': 1,
        'code': '562500',
        'name': '半导体材料设备ETF',
        'match': '★★★★★',
        'reason': '最纯正的半导体上游材料ETF，重仓股覆盖中微公司/北方华创/沪硅产业等，与电子特气/电子树脂/PCB赛道高度吻合',
        'target_stocks': '中微公司(688012), 中芯国际(688981)',
    },
    {
        'rank': 2,
        'code': '159995',
        'name': '芯片ETF(华夏)',
        'match': '★★★★☆',
        'reason': '覆盖半导体全产业链，含中芯国际/紫光国微/澜起科技，与PCB+半导体赛道交叉',
        'target_stocks': '中芯国际, 紫光国微, 中微公司, 澜起科技',
    },
    {
        'rank': 3,
        'code': '159211',
        'name': '电子ETF(广发)',
        'match': '★★★★☆',
        'reason': '大电子板块宽基ETF，含立讯精密/歌尔股份等消费电子龙头，也覆盖部分PCB/铜箔',
        'target_stocks': '立讯精密(002475), 歌尔股份(002241)',
    },
    {
        'rank': 4,
        'code': '159703',
        'name': '新材料ETF(华安)',
        'match': '★★★★☆',
        'reason': '含中国巨石(电子布/玻纤)，也覆盖其他新材料企业',
        'target_stocks': '中国巨石(600176)',
    },
    {
        'rank': 5,
        'code': '515000',
        'name': '科技ETF(华宝)',
        'match': '★★★☆☆',
        'reason': '大科技宽基，分散但覆盖面广，含海康/京东方/立讯等',
        'target_stocks': '立讯精密, 歌尔股份',
    },
]

for r in RECOMMENDATIONS:
    print(f"\n  #{r['rank']} {r['code']} {r['name']}")
    print(f"     匹配度: {r['match']}")
    print(f"     理由: {r['reason']}")
    print(f"     覆盖标的: {r['target_stocks']}")

# 保存
output = {
    'sector_leaders': {k: [{'code':c,'name':n,'note':nt} for c,n,nt in v]} for k,v in SECTOR_LEADERS.items()},
    'etf_recommendations': RECOMMENDATIONS,
    'all_target_codes': list(TARGET_CODES),
}
with open(r'D:\GitHub\TradingAgents\TradingAgent\sector_etf_match.json','w',encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: sector_etf_match.json")

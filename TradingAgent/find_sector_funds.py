#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查找科技赛道概念板块成分股 + 关联基金"""
import os, sys, json

DLL_DIR = r'D:\GitHub\TradingAgents\TradingShared\libs\windows'
DLL_PATH = os.path.join(DLL_DIR, 'EmQuantAPI_x64.dll')
API_DIR = r'D:\GitHub\TradingAgents\TradingShared\api'
SHARED_DIR = r'D:\GitHub\TradingAgents\TradingShared'
os.add_dll_directory(DLL_DIR)
import ctypes
ctypes.CDLL(DLL_PATH, winmode=0x00000008)
sys.path.insert(0, API_DIR)
sys.path.insert(0, SHARED_DIR)
from EmQuantAPI import c

c.start("USERNAME=hczq2048,PASSWORD=yo336999")

# ============================================================
# 1. 查概念板块
# ============================================================
print("=" * 60)
print("1. 搜索相关概念板块")
print("=" * 60)

keywords = ["MLCC", "电子树脂", "六氟化钨", "电子布", "PCB", "铜箔", 
            "印制电路", "覆铜板", "电子特气", "玻纤"]

# 用cses搜概念板块
for kw in keywords:
    ret = c.cses(kw, "INDICID,INDICNAME,SECUCODE,SECURITYSHORTNAME,PCRP", 
                  "Type=802,Sort=PCRP,Order=1,Field=SECUCODE,Field=SECURITYSHORTNAME")
    if ret.ErrorCode == 0 and ret.Data:
        print(f"\n  [{kw}] 找到 {len(ret.Data.get('Codes', []))} 个板块")
        codes = ret.Data.get('Codes', [])[:3]
        names = ret.Data.get('SecurityShortNames', [])[:3] if 'SecurityShortNames' in ret.Data else []
        for i, code in enumerate(codes):
            name = names[i] if i < len(names) else '?'
            print(f"    {code} {name}")
    else:
        print(f"\n  [{kw}] 无结果 ({ret.ErrorMsg[:30]})")

# ============================================================
# 2. 直接用已知概念板块代码查成分股
# ============================================================
print("\n" + "=" * 60)
print("2. 概念板块成分股")
print("=" * 60)

# 东方财富已知概念板块代码
CONCEPT_CODES = {
    "MLCC": "BK1160",      # MLCC概念
    "PCB": "BK0474",       # 印制电路板
    "覆铜板": "BK1009",     # 覆铜板
    "电子特气": "BK0735",   # 电子特气
    "铜箔": "BK1191",       # 铜箔概念
    "玻璃纤维": "BK0482",   # 玻璃纤维
    "电子树脂": "BK1051",   # 电子树脂/环氧树脂
    "钨": "BK0475",         # 钨
}

all_concept_stocks = {}

for concept_name, concept_code in CONCEPT_CODES.items():
    ret = c.cses(concept_code, "SECUCODE,SECURITYSHORTNAME,PCRP",
                 "Type=801,Sort=PCRP,Order=1")
    if ret.ErrorCode == 0:
        codes = ret.Data.get('Codes', [])
        names = ret.Data.get('SecurityShortNames', [])
        pcrps = ret.Data.get('PCRPs', [])
        print(f"\n  [{concept_name}] {concept_code}: {len(codes)} 只")
        for i, (code, name) in enumerate(zip(codes[:10], names[:10])):
            pct = pcrps[i] if i < len(pcrps) and pcrps[i] else '?'
            print(f"    {code:12} {name:10} 涨跌:{pct}")
            clean = code.replace('.SZ', '').replace('.SH', '')
            all_concept_stocks[clean] = {'name': name, 'concept': concept_name}
    else:
        print(f"\n  [{concept_name}] {concept_code}: 查询失败 {ret.ErrorMsg[:40]}")

# ============================================================
# 3. 统计重复出现的股票（多概念交集）
# ============================================================
print("\n" + "=" * 60)
print("3. 多概念交叉股票（优质标的）")
print("=" * 60)

# 用css查这些股票属于哪些概念
target_stocks = list(all_concept_stocks.keys())[:50]
if target_stocks:
    code_str = ",".join([f"{s}.SZ" if not s.startswith('6') else f"{s}.SH" for s in target_stocks[:30]])
    ret = c.css(code_str, "Name", "")
    if ret.ErrorCode == 0:
        for code in list(ret.Data.keys())[:20]:
            data = ret.Data[code]
            print(f"  {code}: {data}")

# ============================================================
# 4. 查找相关ETF/基金
# ============================================================
print("\n" + "=" * 60)
print("4. 搜索相关ETF/基金")
print("=" * 60)

# 搜索关键词相关ETF
etf_keywords = ["半导体", "芯片", "电子", "PCB", "铜箔", "新材料", "科技", "人工智能"]

for kw in etf_keywords:
    ret = c.cses(kw, "SECUCODE,SECURITYSHORTNAME,PCRP,FSR",
                 "Type=440,Sort=FSR,Order=1")
    if ret.ErrorCode == 0 and ret.Data:
        codes = ret.Data.get('Codes', [])[:5]
        names = ret.Data.get('SecurityShortNames', [])[:5]
        if codes:
            print(f"\n  [{kw}ETF]")
            for i, (code, name) in enumerate(zip(codes, names)):
                print(f"    {code:12} {name}")
    else:
        print(f"\n  [{kw}ETF] 无结果")

c.stop()
print("\n完成")

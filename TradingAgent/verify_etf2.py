#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐个查ETF名称"""
import os, sys, time
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

# 只查已确认存在的ETF代码
etf_codes = [
    # 半导体/芯片
    "159995.SZ", "512480.SH", "159801.SZ", "512760.SH", "516620.SH",
    "159316.SZ", "513650.SH", "588200.SH",
    # 电子/科技
    "159211.SZ", "515000.SH", "515050.SH", "515070.SH", "515580.SH",
    "159732.SZ", "515880.SH", "515900.SH",
    # 通信/5G
    "515050.SH", "515570.SH",
    # AI/人工智能
    "515980.SH", "515790.SH", "159819.SZ",
    # 新材料
    "159703.SZ", "516790.SH",
    # 新能源
    "516160.SH", "515030.SH", "516070.SH",
    # 机器人
    "562500.SH", "159770.SZ",
    # 科创板
    "588000.SH", "588050.SH", "588090.SH",
    # 消费电子
    "159732.SZ", "159779.SZ",
    # 信息/软件
    "512720.SH", "159995.SZ",
]

# 去重
etf_codes = list(dict.fromkeys(etf_codes))

print(f"查询 {len(etf_codes)} 个ETF...\n")
results = []

for code in etf_codes:
    ret = c.css(code, "Name", "")
    if ret.ErrorCode == 0:
        name = ret.Data[code][0] if ret.Data[code] and ret.Data[code][0] else '?'
        results.append((code, str(name)))
    else:
        # skip silently
        pass

# Sort
results.sort(key=lambda x: x[1])

print(f"找到 {len(results)} 只:\n")
for code, name in results:
    print(f"  {code:12} {name}")

c.stop()

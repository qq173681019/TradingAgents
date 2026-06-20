#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug Choice CSD return format"""
import os, sys
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

# Test with 300476
ret = c.csd("300476.SZ", "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-06-10", "2026-06-16", "Period=1,Adjustflag=2")
print(f"ErrorCode: {ret.ErrorCode}")
print(f"ErrorMsg: {ret.ErrorMsg}")
print(f"Dates: {ret.Dates}")
print(f"Indicators: {ret.Indicators}")
print(f"Codes: {ret.Codes}")
print(f"Data type: {type(ret.Data)}")
print(f"Data keys: {ret.Data.keys() if isinstance(ret.Data, dict) else 'N/A'}")
if isinstance(ret.Data, dict):
    for k, v in ret.Data.items():
        print(f"  Data['{k}'] type={type(v)}, len={len(v) if isinstance(v, list) else 'N/A'}")
        if isinstance(v, list):
            for j, inner in enumerate(v):
                print(f"    [{j}] (indicator={ret.Indicators[j] if j < len(ret.Indicators) else '?'}): len={len(inner) if isinstance(inner, list) else 'N/A'}, sample={inner[:3] if isinstance(inner, list) else inner}")

c.stop()

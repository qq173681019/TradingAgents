#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查ETF前十大持仓，匹配目标股票"""
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

# 目标股票（用户关心的赛道龙头）
TARGET_STOCKS = {
    '300476': '胜宏科技', '002463': '沪电股份', '002938': '鹏鼎控股',
    '300408': '三环集团', '002138': '顺络电子', '000636': '风华高科',
    '603678': '火炬电子', '600183': '生益科技', '603079': '圣泉集团',
    '688146': '中船特气', '600378': '昊华科技', '603256': '宏和科技',
    '600176': '中国巨石', '301511': '德福科技', '301217': '铜冠铜箔',
    '002378': '章源钨业', '600549': '厦门钨业',
    # 扩展：半导体
    '688981': '中芯国际', '002049': '紫光国微', '688012': '中微公司',
    '688008': '澜起科技', '603986': '兆易创新',
    # 光模块
    '300308': '中际旭创', '300502': '新易盛',
    # 消费电子
    '002475': '立讯精密', '002241': '歌尔股份',
    # AI算力
    '000977': '浪潮信息',
}

# ETF列表
ETFS = [
    ("159995.SZ", "芯片ETF华夏"),
    ("512480.SH", "半导体ETF国联安"),
    ("512760.SH", "芯片ETF国泰"),
    ("159801.SZ", "芯片ETF广发"),
    ("588200.SH", "科创芯片ETF嘉实"),
    ("515000.SH", "科技ETF华宝"),
    ("515580.SH", "科技100ETF华泰柏瑞"),
    ("159211.SZ", "深证100ETF富国"),
    ("159732.SZ", "消费电子ETF华夏"),
    ("159779.SZ", "消费电子ETF招商"),
    ("515050.SH", "通信ETF华夏"),
    ("515880.SH", "通信ETF国泰"),
    ("515980.SH", "人工智能ETF华富"),
    ("515070.SH", "人工智能ETF华夏"),
    ("159819.SZ", "人工智能ETF易方达"),
    ("159703.SZ", "新材料ETF天弘"),
    ("516160.SH", "新能源ETF南方"),
    ("515030.SH", "新能源车ETF华夏"),
    ("562500.SH", "机器人ETF华夏"),
    ("159770.SZ", "机器人ETF天弘"),
    ("588000.SH", "科创50ETF华夏"),
    ("512720.SH", "计算机ETF国泰"),
]

print(f"查询 {len(ETFS)} 只ETF的持仓，匹配 {len(TARGET_STOCKS)} 只目标股...\n")

# 用css查询ETF持仓权重（前十大）
# Choice指标: F10_FUND_TOP10STOCKS 返回基金前十大持仓
# 或者用 FUND_TOPHOLDINGS
for etf_code, etf_name in ETFS:
    # 尝试获取基金持仓
    ret = c.css(etf_code, "F10_FUND_TOP10STOCKNAME,F10_FUND_TOP10STOCKCODE,F10_FUND_TOP10STOCKRATIO", "")
    if ret.ErrorCode == 0:
        data = ret.Data.get(etf_code, [])
        if data and len(data) >= 3:
            names = data[0] if isinstance(data[0], list) else [data[0]]
            codes = data[1] if isinstance(data[1], list) else [data[1]]
            ratios = data[2] if isinstance(data[2], list) else [data[2]]
            
            # 匹配目标股票
            matched = []
            for i in range(min(len(names), len(codes), 10)):
                stock_name = str(names[i]) if names[i] else ''
                stock_code = str(codes[i]) if codes[i] else ''
                ratio = ratios[i] if i < len(ratios) and ratios[i] else 0
                
                # 清理代码
                clean = stock_code.replace('.SZ','').replace('.SH','').strip()
                if clean in TARGET_STOCKS:
                    matched.append(f"{TARGET_STOCKS[clean]}({ratio:.1f}%)" if isinstance(ratio, (int,float)) else f"{TARGET_STOCKS[clean]}")
            
            if matched:
                print(f"★ {etf_code} {etf_name}")
                print(f"  匹配: {', '.join(matched)}")
            else:
                # 显示前5大持仓
                top5 = []
                for i in range(min(5, len(names))):
                    sn = str(names[i]) if names[i] else '?'
                    r = ratios[i] if i < len(ratios) and isinstance(ratios[i], (int,float)) else 0
                    top5.append(f"{sn}({r:.1f}%)")
                print(f"  {etf_code} {etf_name}: {' | '.join(top5)}")
        else:
            print(f"  {etf_code} {etf_name}: 无持仓数据")
    else:
        print(f"  {etf_code} {etf_name}: 查询失败({ret.ErrorMsg[:30]})")

c.stop()

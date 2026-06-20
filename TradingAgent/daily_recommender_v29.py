#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V29 科技赛道增强选股引擎
========================
核心改进（vs V28）：
1. 科技赛道白名单 — 半导体/PCB/CCL/电子特气/电子布/钨/铜箔/AI算力等
2. 赛道增强评分 — 命中热门赛道 +15~25分，非赛道 -10~20分
3. Choice API实时数据 — 不依赖缓存K线，获取最新行情
4. 技术面买入信号 — RSI超卖/均线支撑/缩量回调/放量反弹
5. 7维评分体系 — 趋势/资金/赛道/相对强度/技术信号/量价/风险
6. 强制赛道集中 — 推荐结果至少2/3来自科技赛道

使用：
    python daily_recommender_v29.py             # 完整推荐
    python daily_recommender_v29.py --dry-run   # 不推送
    python daily_recommender_v29.py --debug     # 调试模式
"""

import json, os, sys, time, argparse, logging, functools
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger('V29')
print = functools.partial(print, flush=True)

# ============================================================
# Choice API 初始化
# ============================================================
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

CHOICE_USER = "hczq2048"
CHOICE_PASS = "yo336999"

# ============================================================
# Paths
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
SHARED_DIR_FULL = os.path.join(BASE_DIR, '..', 'TradingShared')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
RECOMMEND_COUNT = 3
COOLDOWN_DAYS = 5

# ============================================================
# ★ 核心创新：科技赛道白名单
# ============================================================

# 热门科技赛道关键词 → 赛道分类 + 加分权重
TECH_TRACKS = {
    # 赛道名称: (关键词列表, 加分权重)
    "AI-PCB": (["PCB", "印制电路", "覆铜板", "电路板"], 25),
    "AI-CCL": (["覆铜板", "CCL", "铜箔基板", "介质"], 22),
    "电子特气": (["特气", "氟化", "六氟化钨", "WF6", "NF3", "电子气体"], 22),
    "电子布": (["电子布", "玻纤", "玻璃纤维", "Low-Dk", "极薄布"], 22),
    "钨产业链": (["钨", "硬质合金", "APT"], 18),
    "AI铜箔": (["铜箔", "HVLP", "锂电池铜箔"], 20),
    "半导体芯片": (["半导体", "芯片", "集成电路", "晶圆", "封测", "光刻"], 25),
    "存储芯片": (["存储", "DRAM", "NAND", "Flash", "内存"], 23),
    "AI算力": (["算力", "服务器", "数据中心", "GPU", "AI芯片"], 25),
    "光模块": (["光模块", "光通信", "800G", "1.6T", "硅光"], 23),
    "消费电子": (["消费电子", "苹果链", "MR", "VR", "AR", "智能穿戴"], 18),
    "新能源电池": (["锂电池", "固态电池", "钠离子", "正极", "负极", "电解液"], 18),
    "机器人": (["机器人", "减速器", "伺服", "人形"], 20),
    "华为产业链": (["华为", "鸿蒙", "昇腾", "鲲鹏"], 20),
    "电力": (["电力", "电网", "配电", "输电", "变电站", "虚拟电厂", "电力设备"], 20),
    "商业航天": (["航天", "卫星", "火箭", "空间站", "遥感", "北斗", "商业航天"], 22),
    "电子树脂": (["电子树脂", "环氧树脂", "酚醛树脂", "马来酰亚胺", "BMI树脂"], 20),
    "MLCC": (["MLCC", "多层陶瓷电容", "陶瓷电容", "片式电容", "被动元件"], 22),
    "六氟化钨": (["六氟化钨", "WF6", "三氟化氮", "电子特气", "特种气体"], 22),
    "N1X概念": (["N1X", "N1X概念", "北斗一号"], 20),
    "SpaceX": (["SpaceX", "星链", "Starlink", "星舰", "猎鹰"], 22),
    "白酒": (["白酒", "茅台", "五粮液", "泸州老窖", "汾酒", "酒"], 18),
    "银行": (["银行", "银行股", "城商行", "农商行", "商业银行"], 18),
    # ★ 2026-06-20 新增三大赛道
    "CPO": (["CPO", "共封装", "硅光子", "铌酸锂", "光电共封"], 25),
    "液冷": (["液冷", "冷板", "浸没式", "氟化液", "数据中心冷却"], 23),
    "HBM": (["HBM", "高带宽内存", "TSV", "先进封装", "溅射靶材"], 25),
}

# 非科技行业关键词（降权）
NON_TECH_KEYWORDS = [
    '水务', '燃气', '公用', '证券', '保险', '房地产',
    '高速公路', '港口', '机场', '交通', '医药', '食品', '饮料',
    '纺织', '服装', '农业', '养殖', '林业', '钢铁', '煤炭',
]

# 科技龙头核心池（用户提供的12只 + 扩展）
# 格式: (代码, 赛道, 名称备注)
TECH_LEADER_POOL_RAW = [
    # PCB
    ("300476.SZ", "AI-PCB", "胜宏科技"),
    ("002463.SZ", "AI-PCB", "沪电股份"),
    ("002938.SZ", "AI-PCB", "鹏鼎控股"),
    ("300408.SZ", "AI-PCB", "三环集团"),
    ("002138.SZ", "AI-PCB", "顺络电子"),
    # CCL覆铜板
    ("600183.SH", "AI-CCL", "生益科技"),
    # 电子特气
    ("688146.SH", "电子特气", "中船特气"),
    ("600378.SH", "电子特气", "昊华科技"),
    # 电子布
    ("603256.SH", "电子布", "宏和科技"),
    ("600176.SH", "电子布", "中国巨石"),
    # 钨
    ("002378.SZ", "钨产业链", "章源钨业"),
    ("600549.SH", "钨产业链", "厦门钨业"),
    # 铜箔
    ("301511.SZ", "AI铜箔", "德福科技"),
    ("301217.SZ", "AI铜箔", "铜冠铜箔"),
    # 半导体
    ("688981.SH", "半导体芯片", "中芯国际"),
    ("002049.SZ", "半导体芯片", "紫光国微"),
    ("300661.SZ", "半导体芯片", "圣邦股份"),
    ("688012.SH", "半导体芯片", "中微公司"),
    ("688008.SH", "半导体芯片", "澜起科技"),
    # 存储
    ("603986.SH", "存储芯片", "兆易创新"),
    ("688521.SH", "存储芯片", "聚辰股份"),
    # 光模块
    ("300308.SZ", "光模块", "中际旭创"),
    ("300502.SZ", "光模块", "新易盛"),
    ("002281.SZ", "光模块", "光迅科技"),
    # AI算力
    ("000977.SZ", "AI算力", "浪潮信息"),
    ("603019.SH", "AI算力", "中科曙光"),
    # 消费电子
    ("002241.SZ", "消费电子", "歌尔股份"),
    ("002475.SZ", "消费电子", "立讯精密"),
    # 新能源
    ("300750.SZ", "新能源电池", "宁德时代"),
    ("002594.SZ", "新能源电池", "比亚迪"),
    # 机器人
    ("300024.SZ", "机器人", "机器人"),
    ("688169.SH", "机器人", "石头科技"),
    # 电力
    ("600406.SH", "电力", "国电南瑞"),
    ("600905.SH", "电力", "三峡能源"),
    ("002060.SZ", "电力", "江苏华辰"),
    ("601179.SH", "电力", "中国西电"),
    # 商业航天
    ("600118.SH", "商业航天", "中国卫星"),
    ("688515.SH", "商业航天", "航天南湖"),
    ("000901.SZ", "商业航天", "航天科技"),
    ("300034.SZ", "商业航天", "钢研高纳"),
    # MLCC（300408三环集团已在PCB池中，通过关键词匹配MLCC赛道）
    ("000636.SZ", "MLCC", "风华高科"),
    ("603678.SH", "MLCC", "火炬电子"),
    # 六氟化钨（688146/600378已在电子特气池中，通过关键词匹配六氟化钨赛道）
    ("688536.SH", "六氟化钨", "南大光电"),
    # 电子树脂
    ("603688.SH", "电子树脂", "圣泉集团"),
    # 白酒
    ("600519.SH", "白酒", "贵州茅台"),
    ("000858.SZ", "白酒", "五粮液"),
    ("000568.SZ", "白酒", "泸州老窖"),
    ("600809.SH", "白酒", "山西汾酒"),
    # 银行
    ("601398.SH", "银行", "工商银行"),
    ("600036.SH", "银行", "招商银行"),
    ("601288.SH", "银行", "农业银行"),
    # N1X（300034/600118已在商业航天池中，通过关键词匹配N1X/SpaceX赛道）

    # ★ 2026-06-20 补丁：CPO/液冷/HBM + 创业板龙头补充
    # CPO
    ("300620.SZ", "CPO", "光库科技"),       # 铌酸锂调制器,CPO核心器件
    ("300570.SZ", "CPO", "太辰光"),         # MPO连接器,CPO配套
    # 液冷
    ("300602.SZ", "液冷", "飞荣达"),         # 导热界面材料+液冷板
    ("300499.SZ", "液冷", "高澜股份"),       # 浸没式液冷先发者
    ("300037.SZ", "液冷", "新宙邦"),         # 氟化液国产替代
    # HBM产业链
    ("300666.SZ", "HBM", "江丰电子"),       # 高纯溅射靶材,先进封装
    ("300604.SZ", "HBM", "长川科技"),       # 半导体测试设备,HBM配套
    # 半导体补充
    ("300782.SZ", "半导体芯片", "卓胜微"),   # 射频芯片龙头
    ("300373.SZ", "半导体芯片", "扬杰科技"), # IGBT功率半导体
    # 存储补充
    ("300223.SZ", "存储芯片", "北京君正"),   # DRAM+SRAM,车规存储
    # 消费电子补充
    ("300433.SZ", "消费电子", "蓝思科技"),   # 玻璃盖板全球龙头
    ("300115.SZ", "消费电子", "长盈精密"),   # 精密结构件,苹果+华为
    # 新能源补充
    ("300014.SZ", "新能源电池", "亿纬锂能"), # 锂电二线龙头
    # 商业航天补充
    ("300053.SZ", "商业航天", "欧比特"),     # 宇航芯片+卫星星座
    ("300101.SZ", "商业航天", "振芯科技"),   # 北斗芯片+卫星导航
]

# 构建代码到赛道/名称的映射
TECH_LEADER_POOL = [item[0] for item in TECH_LEADER_POOL_RAW]
STOCK_META = {item[0]: {'track': item[1], 'name': item[2]} for item in TECH_LEADER_POOL_RAW}

# 指数代码（上证综指）
INDEX_CODE = "000001.SH"

# ============================================================
# 登录/登出 Choice
# ============================================================
def choice_login():
    ret = c.start(f"USERNAME={CHOICE_USER},PASSWORD={CHOICE_PASS}")
    if ret.ErrorCode != 0:
        print(f"[Choice] 登录失败: {ret.ErrorMsg}")
        sys.exit(1)
    print("[Choice] 登录成功")

def choice_logout():
    c.stop()
    print("[Choice] 已登出")

# ============================================================
# 数据获取 — Choice CSD
# ============================================================
def fetch_klines_batch(codes, days=150):
    """批量获取多只股票的日K线数据
    Returns: {code: [{'date','open','high','low','close','volume','pct'}, ...]}
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    code_str = ",".join(codes)
    
    result = {}
    try:
        ret = c.csd(code_str, "OPEN,HIGH,LOW,CLOSE,VOLUME,VOLUMEAMOUNT,PCTCHG,TURN",
                     start_date, end_date, "Period=1")
        if ret.ErrorCode != 0:
            print(f"[Choice] CSD错误: {ret.ErrorMsg}")
            return result
        
        for code in ret.Codes:
            stock_data = ret.Data.get(code, [])
            records = []
            for i, d in enumerate(ret.Dates):
                try:
                    def safe_float(val):
                        if val is None:
                            return 0.0
                        try:
                            return float(val)
                        except:
                            return 0.0
                    
                    rec = {
                        'date': d,
                        'open': safe_float(stock_data[0][i]),
                        'high': safe_float(stock_data[1][i]),
                        'low': safe_float(stock_data[2][i]),
                        'close': safe_float(stock_data[3][i]),
                        'volume': safe_float(stock_data[4][i]),
                        'amount': safe_float(stock_data[5][i]) if len(stock_data) > 5 else 0,
                        'pct': safe_float(stock_data[6][i]) if len(stock_data) > 6 else 0,
                        'turn': safe_float(stock_data[7][i]) if len(stock_data) > 7 else 0,
                    }
                    if rec['close'] > 0 and rec['volume'] > 0:
                        records.append(rec)
                except Exception:
                    continue
            if len(records) >= 30:
                result[code] = records
    except Exception as e:
        print(f"[Choice] 批量获取异常: {e}")
    
    return result

def fetch_index_data(days=200):
    """获取指数日K线"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        ret = c.csd(INDEX_CODE, "CLOSE,HLOSE,VOLUME",
                     start_date, end_date, "Period=1")
        if ret.ErrorCode != 0:
            print(f"[Choice] 指数获取失败: {ret.ErrorMsg}")
            return []
        
        records = []
        stock_data = ret.Data.get(INDEX_CODE, [])
        for i, d in enumerate(ret.Dates):
            try:
                cl = float(stock_data[0][i]) if stock_data[0][i] else 0
                if cl > 0:
                    records.append({'date': d, 'close': cl})
            except:
                continue
        return records
    except Exception as e:
        print(f"[Choice] 指数异常: {e}")
        return []

def fetch_stock_names(codes):
    """获取股票名称 — 用 'Name' 指标"""
    result = {}
    # 分批，每次30只
    for i in range(0, len(codes), 30):
        batch = codes[i:i+30]
        code_str = ",".join(batch)
        try:
            ret = c.css(code_str, "Name", "")
            if ret.ErrorCode == 0:
                for code in ret.Codes:
                    data = ret.Data.get(code, [''])
                    name = data[0] if isinstance(data, list) and data else str(data)
                    clean = code.replace('.SZ', '').replace('.SH', '')
                    result[clean] = str(name) if name else ''
        except Exception as e:
            print(f"  [Choice] 名称获取失败: {e}")
    return result

def fetch_sector_info(codes):
    """获取股票所属行业 — Choice css 不支持行业指标，用内置映射代替"""
    return {}

# ============================================================
# 技术指标
# ============================================================
def calc_ma(closes, period):
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    diffs = np.diff(closes[-(period + 1):])
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return 0.0, 0.0
    alpha_f = 2 / (fast + 1)
    alpha_s = 2 / (slow + 1)
    ema_f = float(np.mean(closes[:fast]))
    ema_s = float(np.mean(closes[:slow]))
    dif_series = []
    for i in range(slow, len(closes)):
        ema_f = alpha_f * closes[i] + (1 - alpha_f) * ema_f
        ema_s = alpha_s * closes[i] + (1 - alpha_s) * ema_s
        dif_series.append(ema_f - ema_s)
    if not dif_series:
        return 0.0, 0.0
    dif = dif_series[-1]
    if len(dif_series) >= signal:
        dea = float(np.mean(dif_series[-signal:]))
    else:
        dea = float(np.mean(dif_series))
    return dif, dea

# ============================================================
# 赛道分类
# ============================================================
def classify_tech_track(name, industry):
    """根据名称和行业判断所属科技赛道
    Returns: (track_name, bonus)
    """
    text = f"{name} {industry}"
    
    for track, (keywords, bonus) in TECH_TRACKS.items():
        for kw in keywords:
            if kw in text:
                return track, bonus
    
    # 检查是否非科技
    for kw in NON_TECH_KEYWORDS:
        if kw in text:
            return "非科技", -15
    
    return "其他", 0

# ============================================================
# 7维评分系统
# ============================================================
def score_trend(closes):
    """维度1: 多时间框架趋势评分 (0-100)"""
    n = len(closes)
    if n < 20:
        return 50
    
    score = 0
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if n >= 60 else ma20
    
    # 日线趋势
    if closes[-1] > ma5 > ma10 > ma20:
        score += 40
    elif closes[-1] > ma5 > ma10:
        score += 30
    elif closes[-1] > ma5:
        score += 15
    elif closes[-1] < ma5 < ma10 < ma20:
        score -= 40
    elif closes[-1] < ma5 < ma10:
        score -= 30
    elif closes[-1] < ma5:
        score -= 15
    
    # MA5斜率
    if n >= 6:
        ma5_slope = (ma5 - np.mean(closes[-6:-1])) / max(abs(np.mean(closes[-6:-1])), 0.01) * 100
        if ma5_slope > 1:
            score += 15
        elif ma5_slope > 0:
            score += 8
        elif ma5_slope < -1:
            score -= 15
        elif ma5_slope < 0:
            score -= 8
    
    # 周线/月线趋势
    if n >= 60:
        weekly = closes[::5]
        if len(weekly) >= 12:
            wma5 = np.mean(weekly[-5:])
            wma10 = np.mean(weekly[-10:])
            if weekly[-1] > wma5 > wma10:
                score += 20
            elif weekly[-1] > wma5:
                score += 10
            elif weekly[-1] < wma5 < wma10:
                score -= 20
    
    return max(0, min(100, (score + 100) / 2))

def score_money_flow(closes, volumes, highs, lows, turns):
    """维度2: 资金流向评分 (0-10)"""
    n = len(closes)
    if n < 10:
        return 5.0
    
    score = 5.0
    
    # 量价配合
    up_vols = [volumes[i] for i in range(-10, 0) if closes[i] > closes[i-1]]
    dn_vols = [volumes[i] for i in range(-10, 0) if closes[i] <= closes[i-1]]
    avg_up = np.mean(up_vols) if up_vols else 1
    avg_dn = np.mean(dn_vols) if dn_vols else 1
    vol_ratio = avg_up / max(avg_dn, 1)
    
    if vol_ratio > 2.0:
        score += 2.0
    elif vol_ratio > 1.5:
        score += 1.0
    elif vol_ratio < 0.5:
        score -= 2.5
    elif vol_ratio < 0.7:
        score -= 1.5
    
    # OBV趋势
    obv = [0]
    start = max(-20, -n)
    for i in range(start, 0):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    
    if obv[-1] == max(obv):
        score += 1.5
    if len(obv) >= 5 and obv[-1] < obv[-5]:
        score -= 1.0
    
    # 换手率分析
    if n >= 10 and turns[-1] > 0:
        turn_today = turns[-1]
        turn_avg5 = np.mean(turns[-6:-1])
        turn_ratio = turn_today / max(turn_avg5, 0.1)
        if turn_ratio > 2.0 and closes[-1] > closes[-2]:
            score += 1.5
        elif turn_ratio > 1.5 and closes[-1] > closes[-2]:
            score += 0.5
        elif turn_ratio > 2.0 and closes[-1] < closes[-2]:
            score -= 2.0
    
    return max(0, min(10, score))

def score_sector_momentum(track_name, track_stocks_data):
    """维度3: 赛道动量评分 (0-100)
    
    track_stocks_data: {track: [{'code','close','ret5','ret20'}, ...]}
    """
    if track_name not in track_stocks_data or not track_stocks_data[track_name]:
        return 50
    
    stocks = track_stocks_data[track_name]
    avg_ret5 = np.mean([s['ret5'] for s in stocks])
    avg_ret20 = np.mean([s['ret20'] for s in stocks])
    positive_rate = sum(1 for s in stocks if s['ret5'] > 0) / len(stocks)
    
    # 赛道热度 = 近期涨幅 + 正收益率
    heat = avg_ret5 * 3 + positive_rate * 30 + avg_ret20 * 0.5
    return max(0, min(100, 50 + heat))

def score_relative_strength(code, closes, peer_returns):
    """维度4: 相对强度排名 (0-100)"""
    if len(closes) < 6:
        return 50
    my_ret = (closes[-1] - closes[-6]) / closes[-6] * 100
    if not peer_returns:
        return 50
    percentile = sum(1 for r in peer_returns if r < my_ret) / len(peer_returns) * 100
    return percentile

def score_technical_signal(closes, volumes, rsi, ma20, ma60):
    """维度5: 技术买入信号 (0-100) — V29新增"""
    n = len(closes)
    if n < 20:
        return 50
    
    price = closes[-1]
    score = 50
    
    # RSI超卖反弹
    if rsi < 30:
        score += 20
    elif rsi < 40:
        score += 12
    elif rsi < 50:
        score += 5
    elif rsi > 80:
        score -= 15
    elif rsi > 70:
        score -= 8
    
    # 均线支撑
    if ma20 and ma60:
        price_vs_ma20 = (price - ma20) / ma20 * 100
        price_vs_ma60 = (price - ma60) / ma60 * 100
        
        # 回踩20日线 = 买入机会
        if -3 < price_vs_ma20 < 2:
            score += 15
        # 回踩60日线 = 强支撑
        if -3 < price_vs_ma60 < 2:
            score += 20
        # 远离均线 = 超买
        if price_vs_ma20 > 10:
            score -= 10
    
    # MACD金叉
    dif, dea = calc_macd(closes)
    if dif > dea and dif > 0:
        score += 10
    elif dif > dea:
        score += 5
    elif dif < dea and dif < 0:
        score -= 10
    
    # 缩量回调
    if n >= 10:
        recent_3_ret = (closes[-1] - closes[-4]) / closes[-4] * 100
        vol_ratio = np.mean(volumes[-3:]) / max(np.mean(volumes[-10:-3]), 1)
        if recent_3_ret < -3 and vol_ratio < 0.8:
            score += 15  # 缩量回调 = 好买点
        if recent_3_ret < -8:
            score -= 10  # 暴跌回避
    
    # 放量反弹
    if n >= 3:
        today_vol_ratio = volumes[-1] / max(np.mean(volumes[-5:-1]), 1)
        if closes[-2] < closes[-3] and closes[-1] > closes[-2] and today_vol_ratio > 1.3:
            score += 15  # 放量反弹
    
    return max(0, min(100, score))

def score_volume_health(closes, volumes):
    """维度6: 量价健康度 (0-100)"""
    n = len(closes)
    if n < 10:
        return 50
    
    score = 50
    for i in range(-5, 0):
        if closes[i] > closes[i-1] and volumes[i] > volumes[i-1]:
            score += 3  # 量价齐升
        elif closes[i] < closes[i-1] and volumes[i] < volumes[i-1]:
            score += 2  # 缩量回调
        elif closes[i] > closes[i-1] and volumes[i] < volumes[i-1]:
            score -= 1  # 缩量上涨
        elif closes[i] < closes[i-1] and volumes[i] > volumes[i-1]:
            score -= 3  # 放量下跌
    
    vol_cv = np.std(volumes[-10:]) / max(np.mean(volumes[-10:]), 1)
    if vol_cv < 0.3:
        score += 5
    elif vol_cv > 0.8:
        score -= 5
    
    return max(0, min(100, score))

def score_risk(industry, track_name, rsi, vol_cv):
    """维度7: 风险调整 (0-100)"""
    if track_name == "非科技":
        return 20
    if rsi > 75:
        return 25  # 超买
    if rsi > 65:
        return 40
    if rsi < 35:
        return 70  # 超卖机会
    return 55

# ============================================================
# 市场状态检测
# ============================================================
def detect_market_regime(index_records):
    """检测大盘状态"""
    if len(index_records) < 30:
        return 'range', 0.5, 3
    
    closes = np.array([r['close'] for r in index_records])
    n = len(closes)
    
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if n >= 60 else ma20
    
    trend = 0
    if closes[-1] > ma5: trend += 1
    if ma5 > ma10: trend += 1
    if ma10 > ma20: trend += 1
    if ma20 > ma60: trend += 1
    
    ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.5 + ret20 * 0.5
    
    if trend >= 3 and momentum > 2:
        return 'strong_bull', 0.8, 1
    elif trend >= 2 and momentum > 0:
        return 'bull', 0.6, 2
    elif trend <= 1 and momentum < -2:
        return 'bear', 0.7, 4
    elif trend == 0 and momentum < -3:
        return 'crisis', 0.8, 5
    else:
        return 'range', 0.4, 3

def detect_no_trade_signals(index_records):
    """检测不交易信号"""
    if len(index_records) < 10:
        return False, []
    
    closes = np.array([r['close'] for r in index_records])
    n = len(closes)
    signals = []
    
    # 冲高回落
    if n >= 2:
        prev_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if prev_ret > 3.0:
            signals.append(('冲高回落风险', 2))
    
    # 连涨疲劳
    consec_up = 0
    for i in range(n-1, max(0, n-8), -1):
        if closes[i] > closes[i-1]:
            consec_up += 1
        else:
            break
    if consec_up >= 4:
        signals.append(('连涨疲劳', 3))
    
    # 波动率急升
    if n >= 25:
        rets5 = np.diff(closes[-6:]) / closes[-6:-1] * 100
        rets20 = np.diff(closes[-21:]) / closes[-21:-1] * 100
        if np.std(rets20) > 0.001 and np.std(rets5) / np.std(rets20) > 2.0:
            signals.append(('波动率急升', 2))
    
    # 连跌
    consec_dn = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]:
            consec_dn += 1
        else:
            break
    if consec_dn >= 3:
        signals.append(('连跌3天+', 2))
    
    total_risk = sum(r for _, r in signals)
    return total_risk >= 3, signals

# ============================================================
# ★ V29 核心评分引擎
# ============================================================
def score_v29(klines_dict, names_dict, sectors_dict, index_records, debug=False):
    """V29 评分引擎
    
    Returns: {code: {所有评分 + track + final_score}}
    """
    regime, confidence, mkt_risk = detect_market_regime(index_records)
    print(f"\n  大盘: {regime} confidence={confidence:.2f} risk={mkt_risk}")
    
    # 1. 计算每只股票的基础数据
    stock_data = {}
    for code, records in klines_dict.items():
        clean_code = code.replace('.SZ', '').replace('.SH', '')
        # 先从内置META获取名称和赛道
        meta = STOCK_META.get(code, {})
        name = meta.get('name', '') or names_dict.get(clean_code, '')
        track_from_meta = meta.get('track', '')
        industry = sectors_dict.get(clean_code, '')
        
        # 赛道分类：优先用内置META
        if track_from_meta:
            track = track_from_meta
            track_bonus = TECH_TRACKS.get(track, ([], 0))[1] if track in TECH_TRACKS else 0
        else:
            track, track_bonus = classify_tech_track(name, industry)

        closes = np.array([r['close'] for r in records])
        volumes = np.array([r['volume'] for r in records])
        highs = np.array([r['high'] for r in records])
        lows = np.array([r['low'] for r in records])
        turns = np.array([r['turn'] for r in records])
        
        if len(closes) < 30:
            continue

        ret5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
        ret20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0
        
        ma20 = calc_ma(closes, 20)
        ma60 = calc_ma(closes, 60)
        rsi = calc_rsi(closes, 14)
        
        stock_data[clean_code] = {
            'code': clean_code, 'name': name, 'industry': industry,
            'track': track, 'track_bonus': track_bonus,
            'closes': closes, 'volumes': volumes, 'highs': highs,
            'lows': lows, 'turns': turns,
            'ret5': ret5, 'ret20': ret20,
            'ma20': ma20, 'ma60': ma60, 'rsi': rsi,
            'close': float(closes[-1]),
            'pct_today': records[-1].get('pct', 0),
            'records': records,
        }
    
    print(f"  有效股票: {len(stock_data)}")
    
    # 2. 按赛道分组，计算赛道动量
    track_groups = defaultdict(list)
    for code, sd in stock_data.items():
        track_groups[sd['track']].append({
            'code': code, 'ret5': sd['ret5'], 'ret20': sd['ret20'],
            'close': sd['close'],
        })
    
    print(f"  赛道分布: {', '.join(f'{t}({len(v)})' for t, v in sorted(track_groups.items(), key=lambda x: -len(x[1])))}")
    
    # 3. 计算各维度评分
    results = []
    for code, sd in stock_data.items():
        track = sd['track']
        closes, volumes = sd['closes'], sd['volumes']
        highs, lows, turns = sd['highs'], sd['lows'], sd['turns']
        rsi = sd['rsi']
        ma20, ma60 = sd['ma20'], sd['ma60']
        
        # 7维评分
        trend_s = score_trend(closes)
        money_s = score_money_flow(closes, volumes, highs, lows, turns)
        sector_s = score_sector_momentum(track, track_groups)
        
        # 同赛道peer returns
        peer_returns = [s['ret5'] for s in track_groups.get(track, []) if s['code'] != code]
        rs_s = score_relative_strength(code, closes, peer_returns)
        tech_s = score_technical_signal(closes, volumes, rsi, ma20, ma60)
        vol_s = score_volume_health(closes, volumes)
        
        vol_cv = float(np.std(volumes[-10:]) / max(np.mean(volumes[-10:]), 1))
        risk_s = score_risk(sd['industry'], track, rsi, vol_cv)
        
        # 权重（根据市场状态调整）
        if mkt_risk <= 2:
            w = [0.20, 0.12, 0.15, 0.10, 0.20, 0.10, 0.13]  # 牛市：趋势+技术信号+赛道
        elif mkt_risk >= 4:
            w = [0.15, 0.10, 0.10, 0.08, 0.15, 0.10, 0.32]  # 熊市：风险权重加大
        else:
            w = [0.18, 0.12, 0.13, 0.10, 0.18, 0.10, 0.19]  # 震荡
        
        final = (trend_s * w[0] + money_s * 10 * w[1] + sector_s * w[2] +
                 rs_s * w[3] + tech_s * w[4] + vol_s * w[5] + risk_s * w[6])
        
        # ★ 赛道增强/惩罚
        final += sd['track_bonus']
        
        # ★ V29: 近期涨幅过大惩罚
        if sd['ret5'] > 20:
            final -= 15  # 5日涨幅>20%，追高风险大
        elif sd['ret5'] > 15:
            final -= 8
        elif sd['ret5'] > 10:
            final -= 3
        
        if sd['ret20'] > 40:
            final -= 10  # 20日涨幅过大
        elif sd['ret20'] > 25:
            final -= 5
        
        results.append({
            'code': code,
            'name': sd['name'],
            'industry': sd['industry'],
            'track': track,
            'track_bonus': track_bonus,
            'final_score': final,
            'close': sd['close'],
            'pct_today': sd['pct_today'],
            'rsi': round(rsi, 1),
            'ma20': round(ma20, 2) if ma20 else None,
            'ma60': round(ma60, 2) if ma60 else None,
            'ret5': round(sd['ret5'], 2),
            'ret20': round(sd['ret20'], 2),
            'scores': {
                'trend': round(trend_s, 1),
                'money_flow': round(money_s, 1),
                'sector': round(sector_s, 1),
                'relative_strength': round(rs_s, 1),
                'technical_signal': round(tech_s, 1),
                'volume_health': round(vol_s, 1),
                'risk': round(risk_s, 1),
            },
        })
    
    # 排序
    results.sort(key=lambda x: x['final_score'], reverse=True)
    
    if debug:
        print(f"\n  === Top 15 调试 ===")
        for i, r in enumerate(results[:15], 1):
            print(f"  {i:2}. {r['code']} {r['name'][:8]:8} [{r['track']:8}] "
                  f"分:{r['final_score']:.1f} "
                  f"趋势:{r['scores']['trend']:.0f} 资金:{r['scores']['money_flow']:.1f} "
                  f"赛道:{r['scores']['sector']:.0f} 技术:{r['scores']['technical_signal']:.0f} "
                  f"RSI:{r['rsi']:.0f} 5日:{r['ret5']:+.1f}%")
    
    return results, regime, mkt_risk, confidence

# ============================================================
# 选择推荐（强制赛道集中）
# ============================================================
def select_v29(scored_stocks, cooldown_file=None, debug=False):
    """选择推荐，强制至少2/3来自科技赛道"""
    
    # 加载冷却期
    cooldown = {}
    if cooldown_file and os.path.exists(cooldown_file):
        try:
            with open(cooldown_file, 'r', encoding='utf-8') as f:
                cooldown = json.load(f).get('last_rec_date', {})
        except:
            pass
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    selected = []
    tech_count = 0
    non_tech_count = 0
    
    for s in scored_stocks:
        if len(selected) >= RECOMMEND_COUNT:
            break
        
        code = s['code']
        track = s['track']
        is_tech = track != "非科技" and track != "其他"
        
        # 冷却期检查
        if code in cooldown:
            last_date = cooldown[code]
            days_since = (datetime.now() - datetime.strptime(last_date, '%Y-%m-%d')).days
            if days_since < COOLDOWN_DAYS:
                continue
        
        # 强制赛道集中：非科技最多1只
        if not is_tech and non_tech_count >= 1:
            continue
        
        # 趋势强向下跳过
        if s['scores']['trend'] < 30:
            continue
        
        selected.append(s)
        if is_tech:
            tech_count += 1
        else:
            non_tech_count += 1
    
    # 更新冷却
    if cooldown_file:
        for s in selected:
            cooldown[s['code']] = today
        with open(cooldown_file, 'w', encoding='utf-8') as f:
            json.dump({'last_rec_date': cooldown, 'updated': today}, f, ensure_ascii=False, indent=2)
    
    return selected

# ============================================================
# 格式化输出
# ============================================================
def format_recommendations(selected, regime, mkt_risk, confidence):
    """格式化推荐结果"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"V29 科技赛道推荐 | {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 60)
    lines.append(f"大盘: {regime} (risk={mkt_risk}, conf={confidence:.2f})")
    lines.append("")
    
    for i, s in enumerate(selected, 1):
        sc = s['scores']
        lines.append(f"#{i} {s['name']}({s['code']}) [{s['track']}]")
        lines.append(f"  现价:{s['close']} 涨跌:{s['pct_today']:+.1f}% RSI:{s['rsi']}")
        lines.append(f"  综合评分:{s['final_score']:.1f} (赛道加成:{s['track_bonus']:+d})")
        lines.append(f"  趋势:{sc['trend']:.0f} 资金:{sc['money_flow']:.1f} 赛道:{sc['sector']:.0f} "
                      f"技术:{sc['technical_signal']:.0f} 量价:{sc['volume_health']:.0f}")
        lines.append(f"  MA20:{s['ma20']} MA60:{s['ma60']} 5日:{s['ret5']:+.1f}% 20日:{s['ret20']:+.1f}%")
        lines.append("")
    
    lines.append("⚠️ 仅供参考，不构成投资建议")
    return '\n'.join(lines)

# ============================================================
# 主函数
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    t0 = time.time()
    print("=" * 60)
    print(f"V29 科技赛道增强选股引擎 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 1. 登录Choice
    choice_login()
    
    # 2. 获取指数数据
    print("\n[1/4] 获取大盘指数...")
    index_records = fetch_index_data(days=200)
    print(f"  指数数据: {len(index_records)} 天")
    
    # 3. 不交易信号检测
    skip_day, no_trade_signals = detect_no_trade_signals(index_records)
    if skip_day:
        signal_str = ', '.join(f"{s[0]}({s[1]})" for s in no_trade_signals)
        print(f"\n  ⚠️ 不交易信号: {signal_str}")
        print(f"  今日建议空仓观望")
        choice_logout()
        result = {'date': datetime.now().strftime('%Y-%m-%d'), 'action': 'NO_TRADE',
                  'reason': signal_str, 'recommendations': []}
        _save_result(result)
        return result
    
    # 4. 获取股票K线数据（批量，每次最多50只）
    all_codes = TECH_LEADER_POOL
    print(f"\n[2/4] 获取 {len(all_codes)} 只科技股K线...")
    
    all_klines = {}
    batch_size = 50
    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i+batch_size]
        print(f"  批次 {i//batch_size + 1}/{(len(all_codes)-1)//batch_size + 1} ({len(batch)}只)...", end=" ")
        batch_data = fetch_klines_batch(batch, days=150)
        all_klines.update(batch_data)
        print(f"获取 {len(batch_data)} 只")
        time.sleep(0.5)
    
    print(f"  总计: {len(all_klines)} 只有效K线")
    
    # 5. 获取名称和行业
    print(f"\n[3/4] 获取股票名称和行业...")
    clean_codes = [c.replace('.SZ', '').replace('.SH', '') for c in all_codes]
    names_dict = fetch_stock_names(all_codes[:100])
    sectors_dict = fetch_sector_info(all_codes[:100])
    print(f"  名称: {len(names_dict)} 条, 行业: {len(sectors_dict)} 条")
    
    # 6. V29评分
    print(f"\n[4/4] V29 7维评分...")
    scored, regime, mkt_risk, confidence = score_v29(
        all_klines, names_dict, sectors_dict, index_records, debug=args.debug)
    
    # 7. 选择推荐
    cooldown_file = os.path.join(BASE_DIR, 'v29_cooldown.json')
    selected = select_v29(scored, cooldown_file=cooldown_file, debug=args.debug)
    
    # 8. 输出
    report = format_recommendations(selected, regime, mkt_risk, confidence)
    try:
        print(f"\n{report}")
    except UnicodeEncodeError:
        # Windows GBK fallback
        import sys as _sys
        _sys.stdout.buffer.write(report.encode('utf-8', errors='replace'))
        _sys.stdout.buffer.write(b'\n')
    
    # 9. 保存结果
    result = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'version': 'V29',
        'action': 'RECOMMEND' if selected else 'NO_MATCH',
        'market': {'regime': regime, 'risk': mkt_risk, 'confidence': round(confidence, 2)},
        'recommendations': [{
            'rank': i + 1,
            'code': s['code'],
            'name': s['name'],
            'track': s['track'],
            'final_score': round(s['final_score'], 1),
            'close': s['close'],
            'rsi': s['rsi'],
            'ret5': s['ret5'],
            'ret20': s['ret20'],
            'scores': s['scores'],
        } for i, s in enumerate(selected)],
    }
    _save_result(result)
    
    # 10. 登出
    choice_logout()
    
    elapsed = time.time() - t0
    print(f"\n  耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    
    return result


def _save_result(result):
    """保存推荐结果"""
    hist_dir = os.path.join(BASE_DIR, 'recommendation_history')
    os.makedirs(hist_dir, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    filepath = os.path.join(hist_dir, f'v29_recommendation_{today}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存: {filepath}")
    
    # Also save as last recommendation
    last_file = os.path.join(BASE_DIR, 'last_recommendation_v29.json')
    with open(last_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

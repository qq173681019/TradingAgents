#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
科技赛道买入监控 — V2 (Choice API版)
=====================================
使用Choice EmQuantAPI获取K线数据，检测买入信号。

买入信号逻辑：
  1. 均线支撑：价格回踩20日/60日均线附近（偏离<3%）
  2. RSI超卖：RSI(14)在30-45区间
  3. 缩量回调：连续下跌+成交量萎缩
  4. 放量反弹：前一天跌今天涨且放量
  5. 接近30日低点支撑

核心条件：20日均线在60日均线之上（中期趋势向上）

使用：python watch_tech_stocks_v2.py [--push]
"""

import json, os, sys, datetime, argparse
import numpy as np

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

USERNAME = "hczq2048"
PASSWORD = "yo336999"

# ============================================================
# 监控池
# ============================================================
WATCH_LIST = [
    {"code": "300476.SZ", "name": "胜宏科技", "sector": "AI-PCB",     "note": "全球PCB市占13.8%#1 英伟达Tier1 GB200占50%"},
    {"code": "002463.SZ", "name": "沪电股份", "sector": "AI-PCB",     "note": "英伟达GB300 78层背板独家 177亿扩产"},
    {"code": "002938.SZ", "name": "鹏鼎控股", "sector": "AI-PCB",     "note": "苹果链核心 1.6T光模块量产 AI端侧~50%"},
    {"code": "600183.SH", "name": "生益科技", "sector": "CCL",        "note": "CCL全球#2 M9级高端 英伟达/华为双供货"},
    {"code": "688146.SH", "name": "中船特气", "sector": "电子特气",    "note": "WF6全球#1 NF3全球#1 国内65%"},
    {"code": "600378.SH", "name": "昊华科技", "sector": "电子特气",    "note": "WF6国内#2 央企氟化工全产业链"},
    {"code": "603256.SH", "name": "宏和科技", "sector": "电子布",      "note": "Low-Dk二代布全球唯一量产 极薄布#1"},
    {"code": "600176.SH", "name": "中国巨石", "sector": "电子布",      "note": "玻纤全球龙头 7628布龙头 淮安3.9亿米"},
    {"code": "002378.SZ", "name": "章源钨业", "sector": "钨产业链",    "note": "钨全产业链 涨幅近3倍"},
    {"code": "600549.SH", "name": "厦门钨业", "sector": "钨产业链",    "note": "钨产能3.5万吨/年 全球钨业龙头"},
    {"code": "301511.SZ", "name": "德福科技", "sector": "AI铜箔",      "note": "31亿布局高端AI铜箔 卢森堡并购"},
    {"code": "301217.SZ", "name": "铜冠铜箔", "sector": "AI铜箔",      "note": "安徽国资 PCB+锂电铜箔 HVLP4领跑"},
]

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
    gains = np.where(diffs > 0, diffs, 0)
    losses = np.where(diffs < 0, -diffs, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd_dif(closes, fast=12, slow=26):
    if len(closes) < slow:
        return 0, 0
    alpha_f = 2 / (fast + 1)
    alpha_s = 2 / (slow + 1)
    ema_f = float(np.mean(closes[:fast]))
    ema_s = float(np.mean(closes[:slow]))
    for i in range(slow, len(closes)):
        ema_f = alpha_f * closes[i] + (1 - alpha_f) * ema_f
        ema_s = alpha_s * closes[i] + (1 - alpha_s) * ema_s
    dif = ema_f - ema_s
    return dif, ema_f

# ============================================================
# 数据获取 — Choice CSD
# ============================================================
def fetch_kline_choice(code: str, days: int = 150) -> dict:
    """通过Choice API获取日K线"""
    end_date = datetime.date.today().strftime("%Y-%m-%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        ret = c.csd(code, "OPEN,HIGH,LOW,CLOSE,VOLUME,VOLUMEAMOUNT,PCTCHG", 
                     start_date, end_date, "Period=1")
        if ret.ErrorCode != 0:
            return {'code': code, 'klines': [], 'error': ret.ErrorMsg}

        dates = ret.Dates
        stock_data = ret.Data.get(code, [])
        
        # Data格式: [[OPEN序列], [HIGH序列], [LOW序列], [CLOSE序列], [VOLUME序列], [AMOUNT序列], [PCTCHG序列]]
        records = []
        for i, d in enumerate(dates):
            try:
                rec = {
                    'date': d,
                    'open': float(stock_data[0][i]) if stock_data[0][i] is not None else 0,
                    'high': float(stock_data[1][i]) if stock_data[1][i] is not None else 0,
                    'low': float(stock_data[2][i]) if stock_data[2][i] is not None else 0,
                    'close': float(stock_data[3][i]) if stock_data[3][i] is not None else 0,
                    'volume': float(stock_data[4][i]) if stock_data[4][i] is not None else 0,
                    'amount': float(stock_data[5][i]) if len(stock_data) > 5 and stock_data[5][i] is not None else 0,
                    'pct': float(stock_data[6][i]) if len(stock_data) > 6 and stock_data[6][i] is not None else 0.0,
                }
                records.append(rec)
            except (ValueError, IndexError):
                continue

        return {'code': code, 'klines': records}
    except Exception as e:
        return {'code': code, 'klines': [], 'error': str(e)}

# ============================================================
# 买入信号检测
# ============================================================
def detect_buy_signals(stock_data) -> dict:
    klines = stock_data['klines']
    if len(klines) < 65:
        return {'signals': ['数据不足'], 'score': 0, 'trend_up': False}

    closes = np.array([k['close'] for k in klines])
    volumes = np.array([k['volume'] for k in klines])
    lows = np.array([k['low'] for k in klines])

    price = float(closes[-1])
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    rsi = calc_rsi(closes, 14)

    if ma20 is None or ma60 is None:
        return {'signals': ['均线数据不足'], 'score': 0, 'trend_up': False}

    trend_up = ma20 > ma60
    price_vs_ma20 = (price - ma20) / ma20 * 100
    price_vs_ma60 = (price - ma60) / ma60 * 100

    signals = []
    score = 0

    if not trend_up:
        return {'signals': ['⚠️ MA20在MA60下方，下降通道'], 'score': 0, 'trend_up': False,
                'price': round(price, 2), 'ma20': round(ma20, 2), 'ma60': round(ma60, 2),
                'rsi': round(rsi, 1), 'pct_today': klines[-1].get('pct', 0)}

    # 信号1: 回踩20日均线
    if -3 < price_vs_ma20 < 2:
        signals.append(f"📌 回踩20日线（偏离{price_vs_ma20:+.1f}%）")
        score += 3

    # 信号2: 回踩60日均线
    if -3 < price_vs_ma60 < 2:
        signals.append(f"📌 回踩60日线支撑（偏离{price_vs_ma60:+.1f}%）")
        score += 4

    # 信号3: RSI超卖
    if rsi < 35:
        signals.append(f"📉 RSI={rsi:.0f} 超卖")
        score += 3
    elif rsi < 45:
        signals.append(f"📉 RSI={rsi:.0f} 偏弱")
        score += 1

    # 信号4: 缩量回调
    if len(volumes) >= 10:
        recent_3_ret = (closes[-1] - closes[-4]) / closes[-4] * 100
        vol_ratio = float(np.mean(volumes[-3:])) / max(float(np.mean(volumes[-10:-3])), 1)
        if recent_3_ret < -3 and vol_ratio < 0.8:
            signals.append(f"🔍 缩量回调（3日跌{recent_3_ret:.1f}% 量比{vol_ratio:.1f}）")
            score += 3

    # 信号5: 放量反弹
    if len(klines) >= 3:
        yest_pct = klines[-2].get('pct', 0)
        today_pct = klines[-1].get('pct', 0)
        today_vol_ratio = float(volumes[-1]) / max(float(np.mean(volumes[-5:-1])), 1)
        if yest_pct < -1 and today_pct > 2 and today_vol_ratio > 1.2:
            signals.append(f"🔥 放量反弹（今+{today_pct:.1f}% 量比{today_vol_ratio:.1f}）")
            score += 4

    # 信号6: 接近30日低点
    if len(lows) >= 30:
        low_30 = float(np.min(lows[-30:]))
        price_vs_low30 = (price - low_30) / low_30 * 100
        if price_vs_low30 < 3:
            signals.append(f"📌 接近30日低点支撑（距低点{price_vs_low30:.1f}%）")
            score += 2

    # 排除：RSI偏高+远离均线
    if rsi > 65 and price_vs_ma20 > 8:
        signals.append("⚠️ RSI偏高且远离均线，追高风险大")
        score -= 3

    # 排除：5日大涨
    if len(closes) >= 6:
        recent_5_ret = (closes[-1] - closes[-6]) / closes[-6] * 100
        if recent_5_ret > 15:
            signals.append(f"⚠️ 5日大涨{recent_5_ret:.0f}%，获利盘多")
            score -= 2

    return {
        'signals': signals, 'score': score, 'trend_up': trend_up,
        'price': round(price, 2),
        'ma5': round(ma5, 2) if ma5 else None,
        'ma10': round(ma10, 2) if ma10 else None,
        'ma20': round(ma20, 2), 'ma60': round(ma60, 2),
        'rsi': round(rsi, 1),
        'pct_today': klines[-1].get('pct', 0),
        'vol_ratio': round(float(volumes[-1]) / max(float(np.mean(volumes[-5:-1])), 1), 2) if len(volumes) >= 6 else None,
    }

# ============================================================
# 格式化报告
# ============================================================
def format_report(all_results):
    alert_stocks = [r for r in all_results if r['score'] >= 3 and r.get('trend_up')]
    watch_stocks = [r for r in all_results if 0 < r['score'] < 3 and r.get('trend_up')]
    danger_stocks = [r for r in all_results if not r.get('trend_up')]

    lines = []
    lines.append("📡 科技赛道买入监控")
    lines.append(f"📅 {datetime.date.today().strftime('%Y-%m-%d')}")
    lines.append("")

    if alert_stocks:
        lines.append("🔴 买入信号（score≥3）")
        lines.append("─────────────")
        for r in sorted(alert_stocks, key=lambda x: -x['score']):
            lines.append(f"■ {r['name']}({r['code']}) [{r['sector']}]")
            lines.append(f"  现价:{r['price']} 涨跌:{r.get('pct_today',0):+.1f}% RSI:{r['rsi']} 评分:{r['score']}")
            lines.append(f"  MA20:{r['ma20']} MA60:{r['ma60']}")
            for s in r['signals']:
                lines.append(f"  {s}")
            lines.append(f"  📝 {r.get('note','')[:40]}")
            lines.append("")

    if watch_stocks:
        lines.append("🟡 观望（弱信号）")
        lines.append("─────────────")
        for r in sorted(watch_stocks, key=lambda x: -x['score']):
            lines.append(f"■ {r['name']}({r['code']}) 现价:{r['price']} RSI:{r['rsi']} 评分:{r['score']}")
            for s in r['signals']:
                lines.append(f"  {s}")
        lines.append("")

    if danger_stocks:
        lines.append("⚫ 下降通道（暂回避）")
        for r in danger_stocks:
            sigs = r.get('signals', [''])
            lines.append(f"  {r['name']}({r['code']}) {sigs[0]}")
        lines.append("")

    no_signal = [r for r in all_results if r['score'] == 0 and r.get('trend_up')]
    if no_signal:
        lines.append("⚪ 暂无信号（趋势向上但未到买点）")
        for r in no_signal:
            lines.append(f"  {r['name']}({r['code']}) 现价:{r['price']} RSI:{r['rsi']}")
    
    lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议")
    return '\n'.join(lines)

# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()

    print(f"科技赛道买入监控(Choice API) — {datetime.date.today()}")
    print(f"监控 {len(WATCH_LIST)} 只股票\n")

    # 登录Choice
    print("[Choice] 登录中...", end=" ", flush=True)
    login = c.start(f"USERNAME={USERNAME},PASSWORD={PASSWORD}")
    if login.ErrorCode != 0:
        print(f"❌ 登录失败: {login.ErrorMsg}")
        sys.exit(1)
    print("✅")

    all_results = []
    for i, stock in enumerate(WATCH_LIST):
        code = stock['code']
        name = stock['name']
        sector = stock['sector']
        note = stock['note']

        print(f"[{i+1}/{len(WATCH_LIST)}] {name}({code})...", end=" ", flush=True)

        data = fetch_kline_choice(code, days=150)

        if data.get('error') or not data['klines']:
            print(f"❌ {data.get('error', '无数据')}")
            all_results.append({
                'code': code, 'name': name, 'sector': sector,
                'note': note, 'signals': ['数据获取失败'], 'score': 0, 'trend_up': False
            })
            continue

        result = detect_buy_signals(data)
        result['code'] = code
        result['name'] = name
        result['sector'] = sector
        result['note'] = note

        status = '🔴' if result['score'] >= 3 else ('🟡' if result['score'] > 0 else '⚪')
        if not result['trend_up']:
            status = '⚫'
        print(f"{status} 现价:{result.get('price','?')} RSI:{result.get('rsi','?')} 评分:{result['score']}")
        for s in result['signals']:
            print(f"    {s}")

        all_results.append(result)

    # 登出
    c.stop()
    print("\n[Choice] 已登出")

    # 输出报告
    print("\n" + "=" * 60)
    report = format_report(all_results)
    print(report)

    # 保存结果
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'TradingShared', 'data')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, 'tech_watch_result.json')
    save_data = [{
        'code': r['code'], 'name': r['name'], 'sector': r['sector'],
        'price': r.get('price'), 'rsi': r.get('rsi'),
        'ma20': r.get('ma20'), 'ma60': r.get('ma60'),
        'score': r['score'], 'trend_up': r.get('trend_up', False),
        'signals': r['signals'], 'note': r.get('note', ''),
        'date': datetime.date.today().isoformat(),
    } for r in all_results]
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")

    has_alert = any(r['score'] >= 3 and r.get('trend_up') for r in all_results)
    if args.push:
        if has_alert:
            print("\n[推送] 有买入信号！")
        else:
            print("\n[推送] 今日无买入信号，不推送")

if __name__ == '__main__':
    main()

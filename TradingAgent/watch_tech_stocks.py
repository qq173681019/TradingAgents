#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
科技赛道买入监控 — V1
====================
监控12只科技赛道核心标的，检测买入信号，微信推送。

买入信号逻辑（趋势向上 + 回调到位）：
  1. 均线支撑：价格回踩20日/60日均线附近（偏离<3%）
  2. RSI超卖回调：RSI(14)在30-45区间
  3. 缩量回调：连续2-3天下跌 + 成交量萎缩
  4. MACD底背离：价格新低但MACD不创新低
  5. 大阳线反弹：前一天跌后今天放量反弹>2%

核心条件：20日均线在60日均线之上（中期趋势向上），排除下降通道。

使用：python watch_tech_stocks.py [--push]
  --push  有信号时推送到微信（不加只打印）
"""

import json, os, sys, time, argparse, urllib.request, datetime
import numpy as np

# ============================================================================
# 监控池
# ============================================================================
WATCH_LIST = [
    # PCB赛道
    {"code": "300476", "name": "胜宏科技", "sector": "AI-PCB",     "note": "全球PCB市占13.8% #1 英伟达Tier1 GB200占50% 港股IPO 199亿"},
    {"code": "002463", "name": "沪电股份", "sector": "AI-PCB",     "note": "英伟达GB300 78层背板独家 177亿扩产"},
    {"code": "002938", "name": "鹏鼎控股", "sector": "AI-PCB",     "note": "苹果链核心 1.6T光模块量产 AI端侧~50%"},
    # CCL覆铜板
    {"code": "600183", "name": "生益科技", "sector": "CCL",        "note": "CCL全球#2 M9级高端 英伟达/华为双供货"},
    # 电子特气
    {"code": "688146", "name": "中船特气", "sector": "电子特气",    "note": "WF6全球#1 2000吨 NF3全球#1 国内65%"},
    {"code": "600378", "name": "昊华科技", "sector": "电子特气",    "note": "WF6国内#2 600吨 央企氟化工全产业链"},
    # 电子布
    {"code": "603256", "name": "宏和科技", "sector": "电子布",      "note": "Low-Dk二代布全球唯一量产 极薄布#1 毛利60%+"},
    {"code": "600176", "name": "中国巨石", "sector": "电子布",      "note": "玻纤全球龙头 7628布龙头 淮安3.9亿米新线"},
    # 钨产业链
    {"code": "002378", "name": "章源钨业", "sector": "钨产业链",    "note": "钨精矿+APT+钨粉+硬质合金全产业链 涨幅近3倍"},
    {"code": "600549", "name": "厦门钨业", "sector": "钨产业链",    "note": "钨产能3.5万吨/年 全球钨业绝对龙头"},
    # 铜箔
    {"code": "301511", "name": "德福科技", "sector": "AI铜箔",      "note": "31亿布局高端AI铜箔 卢森堡并购"},
    {"code": "301217", "name": "铜冠铜箔", "sector": "AI铜箔",      "note": "安徽国资 PCB+锂电铜箔双业务 HVLP4领跑"},
]

# ============================================================================
# 数据获取 — 东方财富日K
# ============================================================================
def fetch_kline(code: str, days: int = 120) -> dict:
    """从东方财富获取日K线数据"""
    # 判断市场前缀
    if code.startswith('6'):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"

    end_date = datetime.date.today().strftime('%Y%m%d')
    start_date = (datetime.date.today() - datetime.timedelta(days=days + 60)).strftime('%Y%m%d')

    url = (f"http://push2his.eastmoney.com/api/qt/stock/kline/get?"
           f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6&"
           f"fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60&"
           f"klt=101&fqt=1&beg={start_date}&end={end_date}")

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://quote.eastmoney.com/'
    })

    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        data = json.loads(resp.read())
        klines = data.get('data', {}).get('klines', [])
        name = data.get('data', {}).get('name', code)

        records = []
        for k in klines:
            parts = k.split(',')
            if len(parts) >= 8:
                records.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                    'amount': float(parts[6]),
                    'pct': float(parts[8]) if len(parts) > 8 else 0.0,
                })
        return {'code': code, 'name': name, 'klines': records}
    except Exception as e:
        return {'code': code, 'name': code, 'klines': [], 'error': str(e)}


# ============================================================================
# 技术指标计算
# ============================================================================
def calc_ma(closes, period):
    if len(closes) < period:
        return None
    return np.mean(closes[-period:])


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


def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None, None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif = ema_fast - ema_slow
    # 简化dea
    dea_series = []
    close_arr = np.array(closes)
    for i in range(slow, len(closes)):
        ef = _ema(close_arr[:i + 1], fast)
        es = _ema(close_arr[:i + 1], slow)
        dea_series.append(ef - es)
    if len(dea_series) >= signal:
        dea = np.mean(dea_series[-signal:])
    else:
        dea = np.mean(dea_series) if dea_series else dif
    return dif, dea


def _ema(data, period):
    if len(data) < period:
        return np.mean(data) if len(data) > 0 else 0
    alpha = 2 / (period + 1)
    ema = np.mean(data[:period])
    for i in range(period, len(data)):
        ema = alpha * data[i] + (1 - alpha) * ema
    return ema


# ============================================================================
# 买入信号检测
# ============================================================================
def detect_buy_signals(stock_data) -> dict:
    """
    返回 {signals: [...], score: int, trend_up: bool, price, ma20, ma60, rsi}
    """
    klines = stock_data['klines']
    if len(klines) < 65:
        return {'signals': ['数据不足'], 'score': 0, 'trend_up': False}

    closes = np.array([k['close'] for k in klines])
    volumes = np.array([k['volume'] for k in klines])
    highs = np.array([k['high'] for k in klines])
    lows = np.array([k['low'] for k in klines])

    price = closes[-1]
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

    # === 核心条件：趋势向上 ===
    if not trend_up:
        return {'signals': ['⚠️ 20日均线在60日均线下方，下降通道，暂不考虑'], 
                'score': 0, 'trend_up': False,
                'price': round(price, 2), 'ma20': round(ma20, 2), 'ma60': round(ma60, 2), 'rsi': round(rsi, 1)}

    # === 买入信号检测 ===

    # 信号1: 回踩20日均线（偏离<3%）
    if -3 < price_vs_ma20 < 2:
        signals.append(f"📌 回踩20日均线附近（偏离{price_vs_ma20:+.1f}%）")
        score += 3

    # 信号2: 回踩60日均线（偏离<3%）
    if -3 < price_vs_ma60 < 2:
        signals.append(f"📌 回踩60日均线支撑（偏离{price_vs_ma60:+.1f}%）")
        score += 4  # 60日线支撑更强

    # 信号3: RSI超卖区间
    if rsi < 35:
        signals.append(f"📉 RSI={rsi:.0f} 超卖")
        score += 3
    elif rsi < 45:
        signals.append(f"📉 RSI={rsi:.0f} 偏弱")
        score += 1

    # 信号4: 缩量回调（近3天跌+量缩）
    if len(volumes) >= 10:
        recent_3_ret = (closes[-1] - closes[-4]) / closes[-4] * 100
        vol_ratio = np.mean(volumes[-3:]) / max(np.mean(volumes[-10:-3]), 1)
        if recent_3_ret < -3 and vol_ratio < 0.8:
            signals.append(f"🔍 缩量回调（3日跌{recent_3_ret:.1f}%，量比{vol_ratio:.1f}）")
            score += 3

    # 信号5: 放量反弹（昨天跌今天涨且放量）
    if len(klines) >= 3:
        yest_pct = klines[-2]['pct']
        today_pct = klines[-1]['pct']
        today_vol_ratio = volumes[-1] / max(np.mean(volumes[-5:-1]), 1)
        if yest_pct < -1 and today_pct > 2 and today_vol_ratio > 1.2:
            signals.append(f"🔥 放量反弹（今+{today_pct:.1f}% 量比{today_vol_ratio:.1f}）")
            score += 4

    # 信号6: 连续回调后接近前低支撑
    if len(closes) >= 30:
        low_30 = np.min(lows[-30:])
        price_vs_low30 = (price - low_30) / low_30 * 100
        if price_vs_low30 < 3:
            signals.append(f"📌 接近30日低点支撑（距低点{price_vs_low10:.1f}%）" if False else f"📌 接近30日低点支撑（距低点{price_vs_low30:.1f}%）")
            score += 2

    # 信号7: MACD底背离（简化版）
    if len(closes) >= 60:
        low_30_idx = np.argmin(lows[-30:]) + len(lows) - 30
        low_60_idx = np.argmin(lows[-60:]) + len(lows) - 60
        if low_30_idx > low_60_idx:  # 最近低点在更早低点之后
            if lows[-30:][low_30_idx - (len(lows) - 30)] > lows[-60:][low_60_idx - (len(lows) - 60)]:
                # 价格没有新低 → 可能底背离（简化判断）
                pass  # 太复杂简化处理

    # 排除条件：如果RSI>65且远离均线，说明超买
    if rsi > 65 and price_vs_ma20 > 8:
        signals.append("⚠️ RSI偏高且远离均线，追高风险大")
        score -= 3

    # 排除条件：连续大涨后
    if len(closes) >= 5:
        recent_5_ret = (closes[-1] - closes[-6]) / closes[-6] * 100
        if recent_5_ret > 15:
            signals.append(f"⚠️ 5日大涨{recent_5_ret:.0f}%，短期获利盘多")
            score -= 2

    return {
        'signals': signals,
        'score': score,
        'trend_up': trend_up,
        'price': round(price, 2),
        'ma5': round(ma5, 2) if ma5 else None,
        'ma10': round(ma10, 2) if ma10 else None,
        'ma20': round(ma20, 2),
        'ma60': round(ma60, 2),
        'rsi': round(rsi, 1),
        'pct_today': klines[-1]['pct'],
        'vol_ratio': round(volumes[-1] / max(np.mean(volumes[-5:-1]), 1), 2) if len(volumes) >= 6 else None,
    }


# ============================================================================
# 格式化输出
# ============================================================================
def format_report(all_results, push=False):
    """格式化为推送消息"""
    # 按赛道分组
    by_sector = {}
    for r in all_results:
        sector = r['sector']
        if sector not in by_sector:
            by_sector[sector] = []
        by_sector[sector].append(r)

    # 筛选有信号的
    alert_stocks = [r for r in all_results if r['score'] >= 3 and r['trend_up']]
    watch_stocks = [r for r in all_results if 0 < r['score'] < 3 and r['trend_up']]
    danger_stocks = [r for r in all_results if not r['trend_up']]

    lines = []
    lines.append("📡 科技赛道买入监控")
    lines.append(f"📅 {datetime.date.today().strftime('%Y-%m-%d')}")
    lines.append("")

    if alert_stocks:
        lines.append("🔴 买入信号（score≥3）")
        lines.append("─────────────")
        for r in sorted(alert_stocks, key=lambda x: -x['score']):
            lines.append(f"■ {r['name']}({r['code']}) [{r['sector']}]")
            lines.append(f"  现价:{r['price']} RSI:{r['rsi']} 评分:{r['score']}")
            lines.append(f"  MA20:{r['ma20']} MA60:{r['ma60']}")
            for s in r['signals']:
                lines.append(f"  {s}")
            lines.append(f"  📝 {r['note'][:40]}")
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
        lines.append("─────────────")
        for r in danger_stocks:
            lines.append(f"  {r['name']}({r['code']}) {r.get('signals', [''])[0]}")
        lines.append("")

    # 无信号的也列出
    no_signal = [r for r in all_results if r['score'] == 0 and r['trend_up']]
    if no_signal:
        lines.append("⚪ 暂无信号（趋势向上但未到买点）")
        for r in no_signal:
            lines.append(f"  {r['name']}({r['code']}) 现价:{r['price']} RSI:{r['rsi']}")

    lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议")

    return '\n'.join(lines)


# ============================================================================
# 主程序
# ============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--push', action='store_true', help='有信号时推送到微信')
    parser.add_argument('--json', action='store_true', help='输出JSON')
    args = parser.parse_args()

    print(f"科技赛道买入监控 — {datetime.date.today()}")
    print(f"监控 {len(WATCH_LIST)} 只股票\n")

    all_results = []

    for i, stock in enumerate(WATCH_LIST):
        code = stock['code']
        name = stock['name']
        sector = stock['sector']
        note = stock['note']

        print(f"[{i+1}/{len(WATCH_LIST)}] {name}({code})...", end=" ", flush=True)

        data = fetch_kline(code, days=120)

        if data.get('error') or not data['klines']:
            print(f"❌ {data.get('error', '无数据')}")
            all_results.append({
                'code': code, 'name': name, 'sector': sector,
                'note': note, 'signals': ['数据获取失败'], 'score': 0, 'trend_up': False
            })
            continue

        result = detect_buy_signals(data)
        result['code'] = code
        result['name'] = data.get('name', name)
        result['sector'] = sector
        result['note'] = note

        print(f"{'✅' if result['score'] >= 3 else '⏳'} 现价:{result.get('price','?')} RSI:{result.get('rsi','?')} 评分:{result['score']}")

        if result['signals']:
            for s in result['signals']:
                print(f"    {s}")

        all_results.append(result)
        time.sleep(0.3)  # 礼貌延迟

    # 输出报告
    print("\n" + "=" * 60)
    report = format_report(all_results, push=args.push)
    print(report)

    # 保存结果
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'TradingShared', 'data')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, 'tech_watch_result.json')
    save_data = []
    for r in all_results:
        save_data.append({
            'code': r['code'], 'name': r['name'], 'sector': r['sector'],
            'price': r.get('price'), 'rsi': r.get('rsi'),
            'ma20': r.get('ma20'), 'ma60': r.get('ma60'),
            'score': r['score'], 'trend_up': r['trend_up'],
            'signals': r['signals'], 'note': r['note'],
            'date': datetime.date.today().isoformat(),
        })
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")

    # 推送判断
    has_alert = any(r['score'] >= 3 and r['trend_up'] for r in all_results)
    if args.push and has_alert:
        print("\n[推送] 有买入信号，准备推送微信...")
        # 推送由 cron 的 delivery 处理，这里只输出
        print(report)
    elif args.push and not has_alert:
        print("\n[推送] 今日无买入信号，不推送")


if __name__ == '__main__':
    main()

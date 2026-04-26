#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测脚本 V6 - 震荡市双策略优化
核心改进: Risk 3 (range market) 使用双策略选股
  策略A: resilient (强势抗跌) - 低波动 + 高相对强度 + 防御板块
  策略B: reversal (超跌反弹) - RSI超卖 + 均值回归 + 支撑位近
其他 Risk Level 与 V5 相同
"""

import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# Config - 调整评估区间
# ============================================================================
# 数据: 2026-01-05 ~ 2026-04-24 (73天)
# 特征期需要至少30天数据, 评估期用后面的交易日
FEATURE_MIN_DAYS = 30
EVAL_START = '2026-03-01'  # 给足2个月特征期
EVAL_END = '2026-04-24'
TOP_N = 3
MAX_INDUSTRY = 2

# 内存优化: 只加载有足够K线的股票
MIN_KLINE_DAYS = 40


# ============================================================================
# Data Loading - 适配新文件格式
# ============================================================================
def load_data():
    print("[1/3] Loading data...")
    
    # K-line: kline_full_latest.json - dict of list
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    if not os.path.exists(kline_file):
        # Try old format
        kline_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')
    
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    # 只保留必要列，大幅减少内存
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}
    kline = {}
    skipped = 0
    for code, records in raw.items():
        if len(records) < MIN_KLINE_DAYS:
            skipped += 1
            continue
        # 只保留需要的字段
        filtered = []
        for r in records:
            fr = {k: v for k, v in r.items() if k in NEED_COLS}
            filtered.append(fr)
        df = pd.DataFrame(filtered)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        clean = code
        if clean.startswith('sh') or clean.startswith('sz'):
            clean = clean[2:]
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # 转为 float32 减少内存
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = df[col].astype('float32')
        kline[clean] = df
    del raw, filtered
    import gc; gc.collect()
    print(f"  K-line: {len(kline)} stocks ({skipped} skipped < {MIN_KLINE_DAYS} days), date range: {df['date'].min().date()} ~ {df['date'].max().date()}")
    
    # Index: index_full_latest.json - dict of dict (key=field, value={0:x, 1:y})
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    if not os.path.exists(idx_file):
        idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)
    
    # Check format
    if 'date' in raw_idx and isinstance(raw_idx['date'], dict):
        # New format: {date: {0: x, 1: y}, close: {0: x, 1: y}}
        n = len(raw_idx['date'])
        idx_records = []
        for i in range(n):
            try:
                ds = str(raw_idx['date'].get(str(i), ''))
                cl = float(raw_idx['close'].get(str(i), 0))
                if ds and cl > 0:
                    idx_records.append({'date': ds, 'close': cl})
            except:
                continue
    elif isinstance(raw_idx, dict):
        # Old format: {date: {0: ts, ...}, close: {0: val, ...}}
        n = max(int(k) for k in raw_idx.get('date', {})) + 1
        idx_records = []
        for i in range(n):
            key = str(i)
            try:
                ts = raw_idx['date'][key]
                if isinstance(ts, (int, float)):
                    ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d')
                else:
                    ds = str(ts)
                cl = float(raw_idx['close'][key])
                idx_records.append({'date': ds, 'close': cl})
            except:
                continue
    else:
        raise ValueError(f"Unknown index format: {type(raw_idx)}")
    
    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index: {len(index_df)} days, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    
    # Scores (optional - if available)
    import glob
    sf = sorted(glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')))
    scores = {}
    # Use the 2805-stock file for industry info
    score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    if not os.path.exists(score_file):
        # Fallback: find biggest score file
        all_score_files = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
        if all_score_files:
            score_file = max(all_score_files, key=lambda x: os.path.getsize(x))
    if score_file and os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        # Only use industry info, NOT scores (scores are outdated from Jan 25)
        for code, s in sd.items():
            if not isinstance(s, dict):
                continue
            clean_code = code
            if clean_code.startswith('sh') or clean_code.startswith('sz'):
                clean_code = clean_code[2:]
            scores[clean_code] = {
                'tech': 5.0,  # neutral - don't use outdated scores
                'fund': 5.0,
                'chip': 5.0,
                'sector': 5.0,
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': 0.0,
            }
    print(f"  Scores: {len(scores)} stocks")
    
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: np.mean([v for v in vals if v is not None and not np.isnan(v)])
                  for ind, vals in sector_perf.items()}
    
    return kline, index_df, scores, sector_avg


# ============================================================================
# Feature Engineering (same as V4)
# ============================================================================
def calc_features(df, target_date):
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 20:
        return None
    
    c = hist['close'].values
    v = hist['volume'].values
    h = hist['high'].values if 'high' in hist.columns else c
    lo = hist['low'].values if 'low' in hist.columns else c
    turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
    pct = hist['pctChg'].values if 'pctChg' in hist.columns else np.zeros(len(c))
    
    n = len(c)
    f = {}
    
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0
    
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10
    
    f['close_ma5'] = c[-1] / ma5 - 1
    f['close_ma10'] = c[-1] / ma10 - 1
    f['close_ma20'] = c[-1] / ma20 - 1
    f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    f['ma10_slope'] = (ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1]) if n >= 11 else 0
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)
    
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)
    
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0
    
    if n >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        f['vol5'] = np.std(rets) * 100
    else:
        f['vol5'] = 0
    if n >= 11:
        rets10 = np.diff(c[-11:]) / c[-11:-1]
        f['vol10'] = np.std(rets10) * 100
    else:
        f['vol10'] = f.get('vol5', 0)
    
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    f['vol_trend'] = (v[-1] - np.mean(v[-5:])) / max(np.mean(v[-5:]), 1) if n >= 5 else 0
    
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_ratio'] = turn5 / max(turn10, 0.01)
        f['turn_avg'] = turn5
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_ratio'] = 1.0
        f['turn_avg'] = 0
        f['turn_spike'] = 1.0
    
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    if n >= 6:
        trs = []
        for i in range(-min(14, n-1), 0):
            tr = max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1]))
            trs.append(tr)
        f['atr_pct'] = np.mean(trs) / c[-1] * 100
    else:
        f['atr_pct'] = 0
    
    streak = 0
    for i in range(n-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak
    
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0
    
    if n >= 3 and not np.all(pct == 0):
        f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum'] = float(np.nansum(pct[-3:]))
        f['pct_5d_sum'] = float(np.nansum(pct[-5:])) if n >= 5 else f['pct_3d_sum']
    else:
        f['pct_1d'] = f['r1']
        f['pct_3d_sum'] = f['r3']
        f['pct_5d_sum'] = f['r5']
    
    if n >= 10:
        peak = c[-10]
        max_dd = 0
        for i in range(-9, 1):
            if c[i] > peak:
                peak = c[i]
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        f['max_dd_10d'] = max_dd
    else:
        f['max_dd_10d'] = 0
    
    f['dist_support'] = (c[-1] - np.min(c[-w20:])) / c[-1] * 100
    
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0
    
    return f


# ============================================================================
# Market State Detection
# ============================================================================
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]

def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)

def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


def detect_market_state(index_df, date):
    hist = index_df[index_df['date'] < date].copy()
    if len(hist) < 20:
        return 'range', 0, 'normal', 3
    
    closes = hist['close'].values
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]
    
    if current > ma20 * 1.02 and ma5 > ma20:
        regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20:
        regime = 'bear'
    else:
        regime = 'range'
    
    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    
    if n >= 10:
        idx_rets = np.diff(closes[-10:]) / closes[-10:-1] * 100
        idx_vol = np.std(idx_rets)
        if idx_vol > 1.5:
            vol_state = 'high'
        elif idx_vol > 0.8:
            vol_state = 'normal'
        else:
            vol_state = 'low'
    else:
        vol_state = 'normal'
    
    risk = 3
    consec_decline = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]:
            consec_decline += 1
        else:
            break
    
    if consec_decline >= 4:
        risk = 5
    elif consec_decline >= 3:
        risk = 4
    elif regime == 'bear' and vol_state == 'high':
        risk = 5
    elif regime == 'bear':
        risk = 4
    elif regime == 'bull' and vol_state == 'high':
        risk = 3
    elif regime == 'bull':
        risk = 2
    elif vol_state == 'high':
        risk = 4
    else:
        risk = 3
    
    if n >= 2:
        last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if last_ret < -2:
            risk = min(risk + 1, 5)
        elif last_ret > 2:
            risk = max(risk - 1, 1)
    
    return regime, momentum, vol_state, risk


# ============================================================================
# Scoring
# ============================================================================
def score_stock_v5(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level):
    if features is None:
        return -999, 'filtered'
    
    f = features
    
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return -999, 'limit'
    
    static_score = 0
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sector * 0.15) / 10 * 5
    
    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    
    vr = f.get('vol_ratio', 1)
    if 1.1 <= vr <= 2.0:
        vol_s = 3
    elif vr > 2.0:
        vol_s = 1
    else:
        vol_s = 2
    
    rsi = f.get('rsi', 50)
    if 40 <= rsi <= 60:
        rsi_s = 3
    elif 30 <= rsi < 40:
        rsi_s = 4
    elif 60 < rsi <= 70:
        rsi_s = 2
    else:
        rsi_s = 1
    
    vol5 = f.get('vol5', 2)
    if vol5 < 1.5:
        low_vol_s = 4
    elif vol5 < 2.5:
        low_vol_s = 3
    elif vol5 < 3.5:
        low_vol_s = 2
    else:
        low_vol_s = 1
    
    defense_s = 0
    industry = static_scores.get('industry', 'unknown') if static_scores else 'unknown'
    if is_defensive_industry(industry):
        defense_s += 3
    if is_high_beta_industry(industry):
        defense_s -= 2
    defense_s += low_vol_s
    
    rel_strength = f.get('rel_strength_5d', 0)
    rel_strength_3d = f.get('rel_strength_3d', 0)
    beta = f.get('beta_20d', 1.0)
    
    max_dd = f.get('max_dd_10d', 0)
    if max_dd < -15:
        defense_s -= 3
    elif max_dd < -10:
        defense_s -= 1
    
    sector_heat = sector_avg.get(industry, 0) * 0.1
    
    # V5 改进: 更激进的相对强度权重 + 反转加强
    if risk_level >= 4:
        score = (
            momentum_s * 0.02 +
            trend_s * 0.03 +
            mr_s * 0.12 +              # 均值回归权重增加
            vol_s * 0.03 +
            rsi_s * 0.08 +
            static_score * 0.12 +
            defense_s * 0.10 +
            sector_heat * 0.02 +
            low_vol_s * 0.05 +
            rel_strength * 0.18 +      # 相对强度 KEY (增加)
            rel_strength_3d * 0.12 +   # 短期相对强度 (增加)
            (2.0 - min(beta, 2.0)) * 0.10
        )
        
        if beta > 1.5:
            score *= 0.3
        elif beta > 1.2:
            score *= 0.6
        elif beta < 0.5:
            score *= 1.4
        
        if f.get('oversold', 0):
            score *= 1.2
        if f.get('overbought', 0):
            score *= 0.2
        
        if is_high_beta_industry(industry):
            score *= 0.3
        if is_defensive_industry(industry):
            score *= 1.3
        
        if rel_strength > 3:
            score *= 1.4
        if rel_strength > 5:
            score *= 1.2  # 二次加成
        
        if vol5 < 1.5:
            score *= 1.25
        
        # V5: 加强近期大跌惩罚
        if f.get('r1', 0) < -5:
            score *= 0.2
        if f.get('r3', 0) < -8:
            score *= 0.2
        
        # V5: 涨停后回调回避 (2天内涨超8%的回避)
        if f.get('pct_1d', 0) > 7:
            score *= 0.2
        if f.get('r3', 0) > 15:
            score *= 0.3
        
        # V5: 强势股连涨加分
        if f.get('streak', 0) >= 2 and rel_strength > 0:
            score *= 1.15
        
        strategy = 'defense'
        
    elif risk_level == 3:
        # V6b: 纯 resilient 策略 - 震荡市只选「跌不动」的强势股
        # 不做 reversal (超跌反弹在震荡市等于接飞刀)
        # 核心因子: 低波动 > 相对强度 > 防御板块 > 低beta
        score = (
            momentum_s * 0.05 +      # 几乎不看动量
            trend_s * 0.08 +          # 轻微趋势
            mr_s * 0.02 +             # 不做均值回归
            vol_s * 0.05 +
            rsi_s * 0.05 +
            static_score * 0.08 +
            defense_s * 0.12 +        # 防御性
            sector_heat * 0.03 +
            low_vol_s * 0.20 +        # 低波动 = 最核心
            rel_strength * 0.25 +     # 相对强度 = 核心
            rel_strength_3d * 0.07
        )
        
        # === 硬性过滤 ===
        # 高beta = 在震荡市风险大
        if beta > 1.5:
            score *= 0.2
        elif beta > 1.2:
            score *= 0.5
        elif beta < 0.7:
            score *= 1.4
        
        # 高波动 = 不稳
        if vol5 > 3.5:
            score *= 0.3
        elif vol5 < 1.5:
            score *= 1.4
        elif vol5 < 2.0:
            score *= 1.2
        
        # 相对强度 (核心信号)
        if rel_strength > 5:
            score *= 1.6
        elif rel_strength > 3:
            score *= 1.4
        elif rel_strength > 1:
            score *= 1.2
        elif rel_strength < -3:
            score *= 0.4   # 弱于大盘的不要
        
        # 防御板块加分
        if is_defensive_industry(industry):
            score *= 1.3
        # 高beta板块惩罚
        if is_high_beta_industry(industry):
            score *= 0.4
        
        # MA20 支撑
        if f.get('close_ma20', 0) > 0:    # 站在MA20上方
            score *= 1.25
        elif f.get('close_ma20', 0) < -0.03:  # 远离MA20
            score *= 0.6
        
        # 回撤控制
        if max_dd > -3:
            score *= 1.3
        elif max_dd > -5:
            score *= 1.1
        elif max_dd < -10:
            score *= 0.3
        
        # 超买回避
        if f.get('overbought', 0):
            score *= 0.3
        
        # 换手率稳定
        if f.get('turn_avg', 0) < 2:
            score *= 1.15
        
        # 硬性过滤: 近期跌幅过大可能有基本面问题
        if f.get('r1', 0) < -5:
            score *= 0.2
        if f.get('r3', 0) < -10:
            score *= 0.2
        
        strategy = 'resilient'
        
    else:
        score = (
            momentum_s * 0.25 +
            trend_s * 0.20 +
            mr_s * 0.05 +
            vol_s * 0.10 +
            rsi_s * 0.05 +
            static_score * 0.15 +
            defense_s * 0.05 +
            sector_heat * 0.10 +
            low_vol_s * 0.05
        )
        
        if f['r1'] > 5:
            score *= 0.5
        if f.get('overbought', 0):
            score *= 0.8
        
        strategy = 'momentum'
    
    return score, strategy


def get_adaptive_top_n(risk_level, base_n=3):
    if risk_level >= 5:
        return max(1, base_n - 2)
    elif risk_level >= 4:
        return max(2, base_n - 1)
    elif risk_level == 3:
        return 2  # V6c: Risk 3 选2只，兼顾集中和分散
    elif risk_level <= 1:
        return base_n + 1
    else:
        return base_n


def get_stock_return(df, date):
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None

def get_index_return(index_df, date):
    prev = index_df[index_df['date'] < date]
    day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None


def run_backtest(kline, index_df, scores, sector_avg, top_n=TOP_N, adaptive_n=True, label="V6"):
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = []
    for d in date_range:
        if get_index_return(index_df, d) is not None:
            valid_dates.append(d)
    
    print(f"\n  [{label}] Top-N: {top_n} (adaptive: {adaptive_n})")
    print(f"  Eval: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} days)")
    print(f"  Pool: {len(kline)} stocks")
    
    results = []
    wins = 0
    total = 0
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    stock_recent_perf = defaultdict(list)
    
    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        actual_n = get_adaptive_top_n(risk, top_n) if adaptive_n else top_n
        
        scored = []
        
        idx_hist = index_df[index_df['date'] < test_date]
        idx_closes = idx_hist['close'].values
        idx_n = len(idx_closes)
        if idx_n >= 22:
            idx_diff = np.diff(idx_closes[-21:])
            idx_base = idx_closes[-21:-1]
            idx_rets_20 = idx_diff[:len(idx_base)] / idx_base[:len(idx_diff)] * 100
        else:
            idx_rets_20 = None
        idx_ret_5d = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100 if idx_n >= 6 else 0
        idx_ret_3d = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100 if idx_n >= 4 else 0
        
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0:
                continue
            
            feats = calc_features(df, test_date)
            if feats is None:
                continue
            
            stock_hist = df[df['date'] < test_date]
            s_closes = stock_hist['close'].values
            s_n = len(s_closes)
            
            if idx_rets_20 is not None and s_n >= 23:
                s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
                sr_len = min(len(s_rets_20), len(idx_rets_20))
                if sr_len >= 10:
                    s_r = s_rets_20[-sr_len:]
                    i_r = idx_rets_20[-sr_len:]
                    idx_var = np.var(i_r)
                    if idx_var > 0.001:
                        cov = np.cov(s_r, i_r)[0, 1]
                        feats['beta_20d'] = cov / idx_var
            
            if s_n >= 6:
                s_ret_5d = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100
                feats['rel_strength_5d'] = s_ret_5d - idx_ret_5d
            if s_n >= 4:
                s_ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                feats['rel_strength_3d'] = s_ret_3d - idx_ret_3d
            
            static = scores.get(code, None)
            
            score, strategy = score_stock_v5(
                feats, static, sector_avg, regime, momentum, vol_state, risk
            )
            
            if score == -999:
                continue
            
            industry = static.get('industry', 'unknown') if static else 'unknown'
            scored.append({
                'code': code,
                'name': static.get('name', '') if static else '',
                'score': score,
                'industry': industry,
                'strategy': strategy,
            })
        
        blacklist = set()
        for code, rets in stock_recent_perf.items():
            if len(rets) >= 1 and rets[-1] < -3:
                blacklist.add(code)
            if risk >= 4 and rets[-1] > 6:
                blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        selected = []
        ind_count = defaultdict(int)
        for s in scored:
            if len(selected) >= actual_n:
                break
            if s['code'] in blacklist:
                continue
            ind = s['industry']
            if ind_count[ind] >= MAX_INDUSTRY:
                continue
            if risk >= 4 and s['score'] < 0.3:
                continue
            if risk == 3 and s['score'] < 0.3:  # V6: Risk 3 也要有最低分门槛
                continue
            if risk < 3 and s['score'] < 0.5:
                continue
            selected.append(s)
            ind_count[ind] += 1
        
        if not selected:
            non_bl = [s for s in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk >= 4 or risk == 3 else 2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected:
            continue
        
        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None:
            idx_ret = 0
        
        daily_wins = 0
        stock_rets = []
        for s in selected:
            sr = get_stock_return(kline[s['code']], test_date)
            if sr is not None:
                beat = sr > idx_ret
                stock_rets.append({
                    'code': s['code'],
                    'name': s['name'],
                    'ret': round(sr, 2),
                    'beat': beat,
                    'score': round(s['score'], 2),
                    'strategy': s['strategy'],
                })
                if beat:
                    daily_wins += 1
        
        for s in stock_rets:
            stock_recent_perf[s['code']].append(s['ret'])
            if len(stock_recent_perf[s['code']]) > 3:
                stock_recent_perf[s['code']] = stock_recent_perf[s['code']][-3:]
        
        if stock_rets:
            total += 1
            wr = daily_wins / len(stock_rets)
            is_win = wr > 0.5
            if is_win:
                wins += 1
            
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            
            results.append({
                'date': test_date.strftime('%Y-%m-%d'),
                'regime': regime,
                'risk': risk,
                'vol_state': vol_state,
                'n_stocks': len(stock_rets),
                'stocks': stock_rets,
                'idx_ret': round(idx_ret, 2),
                'avg_ret': round(avg_ret, 2),
                'wr': round(wr, 2),
                'win': is_win,
                'beat_idx': beat_idx,
            })
            
            stats_by_risk[risk]['total'] += 1
            if is_win:
                stats_by_risk[risk]['wins'] += 1
            if beat_idx:
                stats_by_risk[risk]['beat_idx'] += 1
            
            tag = 'W' if is_win else 'L'
            bi = '↑' if beat_idx else '↓'
            print(f"  [{test_date.strftime('%m-%d')}] {tag}{bi} avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% R{risk} [{regime[:4]}] n={len(stock_rets)}")
    
    accuracy = wins / total if total > 0 else 0
    beat_idx_days = sum(1 for r in results if r['beat_idx'])
    
    non_extreme = [r for r in results if r['risk'] < 5]
    ne_wins = sum(1 for r in non_extreme if r['win'])
    ne_beat = sum(1 for r in non_extreme if r['beat_idx'])
    ne_total = len(non_extreme)
    ne_acc = ne_wins / ne_total if ne_total > 0 else 0
    ne_beat_pct = ne_beat / ne_total if ne_total > 0 else 0
    
    print(f"\n  RESULT (all):    {wins}/{total} = {accuracy*100:.1f}% win, {beat_idx_days}/{total} = {beat_idx_days/total*100:.1f}% beat_idx")
    print(f"  RESULT (R1-R4):  {ne_wins}/{ne_total} = {ne_acc*100:.1f}% win, {ne_beat}/{ne_total} = {ne_beat_pct*100:.1f}% beat_idx")
    
    print(f"\n  By Risk Level:")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        acc = s['wins'] / s['total'] * 100 if s['total'] > 0 else 0
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"    Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    
    return {
        'accuracy': accuracy,
        'wins': wins,
        'total': total,
        'beat_idx_days': beat_idx_days,
        'beat_idx_pct': beat_idx_days / total if total > 0 else 0,
        'ne_accuracy': ne_acc,
        'ne_wins': ne_wins,
        'ne_total': ne_total,
        'ne_beat': ne_beat,
        'ne_beat_pct': ne_beat_pct,
        'results': results,
        'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()},
    }


def save_report(result, output_path, label="V5"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    lines = [
        "=" * 60,
        f"Backtest {label} Report",
        "=" * 60,
        f"Eval: {EVAL_START} ~ {EVAL_END}",
        "",
        f"Win Rate: {result['accuracy']*100:.1f}% ({result['wins']}/{result['total']})",
        f"Beat Index: {result['beat_idx_days']}/{result['total']} = {result['beat_idx_pct']*100:.1f}%",
        f"Beat Index (R1-R4): {result['ne_beat']}/{result['ne_total']} = {result['ne_beat_pct']*100:.1f}%",
        "",
        "By Risk Level:",
    ]
    
    for r in sorted(result['stats_by_risk'].keys()):
        s = result['stats_by_risk'][r]
        acc = s['wins'] / s['total'] * 100 if s['total'] > 0 else 0
        bi = s['beat_idx'] / s['total'] * 100 if s['total'] > 0 else 0
        lines.append(f"  Risk {r}: {s['wins']}/{s['total']} win={acc:.0f}% beat_idx={bi:.0f}%")
    
    lines.append(f"\n{'='*60}")
    lines.append("Daily Details")
    lines.append("="*60)
    
    for d in result['results']:
        tag = 'W' if d['win'] else 'L'
        bi = '↑IDX' if d['beat_idx'] else '↓IDX'
        lines.append(f"\n{d['date']} [{tag}][{bi}] avg={d['avg_ret']:+.2f}% idx={d['idx_ret']:+.2f}% "
                     f"wr={d['wr']*100:.0f}% R{d['risk']} [{d['regime'][:4]}] n={d['n_stocks']}")
        for s in d['stocks']:
            b = 'V' if s['beat'] else 'X'
            lines.append(f"  {s['code']} {s['name']}: {s['ret']:+.2f}% [{b}] ({s['strategy']})")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\nReport: {output_path}")


def main():
    t0 = time.time()
    
    print("=" * 60)
    print("Backtest V6 - Range Market Dual Strategy")
    print("=" * 60)
    
    kline, index_df, scores, sector_avg = load_data()
    
    # Run multiple configurations
    configs = [
        ('adaptive', 3, True),
    ]
    
    all_results = []
    for label, top_n, adaptive in configs:
        r = run_backtest(kline, index_df, scores, sector_avg, top_n=top_n, adaptive_n=adaptive, label=label)
        all_results.append((label, r))
    
    best_label, best = max(all_results, key=lambda x: x[1]['ne_beat_pct'])
    
    report_path = os.path.join(RESULT_DIR, f'backtest_v6_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    save_report(best, report_path, label=best_label)
    
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    for label, r in all_results:
        tag = ' <-- BEST' if label == best_label else ''
        print(f"  {label:10s}: win={r['accuracy']*100:.1f}% beat_idx={r['beat_idx_pct']*100:.1f}% "
              f"(R1-R4: beat={r['ne_beat_pct']*100:.1f}% {r['ne_wins']}/{r['ne_total']}){tag}")
    print(f"  Time: {elapsed:.0f}s")
    
    # Save JSON
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v6',
        'data_stocks': len(kline),
        'data_days': len(index_df),
        'eval_range': f'{EVAL_START} ~ {EVAL_END}',
        'results': {label: {
            'accuracy': r['accuracy'],
            'beat_idx_pct': r['beat_idx_pct'],
            'ne_beat_pct': r['ne_beat_pct'],
        } for label, r in all_results},
        'best': best_label,
    }
    fp = os.path.join(RESULT_DIR, 'final_result_v6.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    
    return best


if __name__ == '__main__':
    main()

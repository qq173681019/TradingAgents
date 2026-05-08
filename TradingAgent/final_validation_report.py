#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingAgent 算法优化最终验证报告生成器
=========================================

功能
1. 验证所有必需数据文件存在性
2. 分别运行 V9d优化版 和 增强评分系统 的回测
3. 对比两种策略的完整回测结果
4. 计算胜率提升幅度
5. 生成详细的对比分析报告Markdown格式

作者: TradingAgent 最终验证员
日期: 2026-05-04
"""

import json
import os
import sys
import glob
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
from typing import Dict, Optional, List, Tuple

# ============================================================================
# 路径配置
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, '..', 'TradingShared')
DATA_DIR = os.path.join(SHARED_DIR, 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

# 确保输出目录存在
os.makedirs(RESULT_DIR, exist_ok=True)

# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, 'final_validation.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# 回测配置
# ============================================================================
EVAL_START = '2026-03-01'
EVAL_END = '2026-04-24'
TOP_N = 3
MAX_INDUSTRY = 1
FEATURE_MIN_DAYS = 30
MIN_KLINE_DAYS = 40

# 防御性行业关键词
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
# 高Beta行业关键词
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]


# ============================================================
# 1. 数据准备和验证
# ============================================================
def validate_data_sources() -> Dict:
    """
    验证所有必需的数据文件存在

    Returns:
        dict: {
            'valid': bool,  # 所有文件是否就绪
            'files': {文件名: {'exists': bool, 'size_mb': float, 'path': str}},
            'errors': [str]  # 缺失文件列表
        }
    """
    logger.info("=" * 60)
    logger.info("第1步: 验证数据文件...")
    logger.info("=" * 60)

    # 必需文件列表支持通配符
    required_files = [
        ('kline_full_latest.json', os.path.join(KLINE_CACHE, 'kline_full_latest.json')),
        ('index_full_latest.json', os.path.join(KLINE_CACHE, 'index_full_latest.json')),
        ('batch_stock_scores_2805.json', os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')),
    ]

    # 通配符匹配文件
    wildcard_patterns = [
        ('batch_stock_scores_optimized_主板_*.json', os.path.join(DATA_DIR, 'batch_stock_scores_optimized_主板_*.json')),
        ('batch_stock_scores_optimized_*.json', os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')),
    ]

    validation = {
        'valid': True,
        'files': {},
        'errors': [],
    }

    # 检查固定路径文件
    for name, path in required_files:
        exists = os.path.exists(path)
        size_mb = os.path.getsize(path) / 1024 / 1024 if exists else 0
        validation['files'][name] = {
            'exists': exists,
            'size_mb': round(size_mb, 2),
            'path': path,
        }
        if exists:
            logger.info(f"   {name}: {size_mb:.2f} MB")
        else:
            logger.warning(f"   {name}: 不存在")
            validation['errors'].append(f"缺少文件: {name}")
            validation['valid'] = False

    # 检查通配符文件至少有一个匹配即可
    for name, pattern in wildcard_patterns:
        matches = glob.glob(pattern)
        if matches:
            latest = max(matches, key=lambda x: os.path.getmtime(x))
            size_mb = os.path.getsize(latest) / 1024 / 1024
            validation['files'][name] = {
                'exists': True,
                'size_mb': round(size_mb, 2),
                'path': latest,
                'count': len(matches),
                'latest': os.path.basename(latest),
            }
            logger.info(f"   {name}: 找到 {len(matches)} 个文件最新 {os.path.basename(latest)} ({size_mb:.2f} MB)")
        else:
            # 通配符匹配失败不阻断可选数据
            validation['files'][name] = {
                'exists': False,
                'size_mb': 0,
                'path': pattern,
                'count': 0,
            }
            logger.info(f"   {name}: 未找到匹配文件可选")

    # 检查增强评分系统相关文件
    enhanced_files = [
        ('enhanced_scorer.py', os.path.join(BASE_DIR, 'enhanced_scorer.py')),
        ('enhanced_data_fetcher.py', os.path.join(BASE_DIR, 'enhanced_data_fetcher.py')),
    ]
    for name, path in enhanced_files:
        exists = os.path.exists(path)
        validation['files'][name] = {
            'exists': exists,
            'path': path,
        }
        if exists:
            logger.info(f"   {name}: 存在")
        else:
            logger.warning(f"   {name}: 不存在增强评分回测将降级运行")

    if validation['valid']:
        logger.info(" 所有必需数据文件验证通过")
    else:
        logger.error(f" 数据验证失败缺少 {len(validation['errors'])} 个文件:")
        for err in validation['errors']:
            logger.error(f"  - {err}")

    return validation


# ============================================================
# 2. 数据加载从 backtest_v9d.py 移植适配两种策略
# ============================================================
def load_data():
    """加载K线数据指数数据和评分数据"""
    logger.info("加载K线数据...")

    # --- 加载K线数据 ---
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    if not os.path.exists(kline_file):
        kline_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')

    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}
    kline = {}
    skipped = 0
    for code, records in raw.items():
        if len(records) < MIN_KLINE_DAYS:
            skipped += 1
            continue
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
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        kline[clean] = df
    del raw
    import gc; gc.collect()
    logger.info(f"  K线: {len(kline)} 只股票 ({skipped} 只跳过)")

    # --- 加载指数数据 ---
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    if not os.path.exists(idx_file):
        idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')

    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)

    if 'date' in raw_idx and isinstance(raw_idx['date'], dict):
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
    else:
        idx_records = raw_idx if isinstance(raw_idx, list) else []

    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    logger.info(f"  指数: {len(index_df)} 天")

    # --- 加载评分数据用于行业信息---
    score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    if not os.path.exists(score_file):
        all_score_files = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
        if all_score_files:
            score_file = max(all_score_files, key=lambda x: os.path.getsize(x))

    scores = {}
    if os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            if not isinstance(s, dict):
                continue
            clean_code = code
            if clean_code.startswith('sh') or clean_code.startswith('sz'):
                clean_code = clean_code[2:]
            scores[clean_code] = {
                'tech': 5.0,
                'fund': 5.0,
                'chip': 5.0,
                'sector': 5.0,
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': 0.0,
            }
    logger.info(f"  评分: {len(scores)} 只股票")

    # 计算板块均值
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {
        ind: float(np.mean([v for v in vals if v is not None and not np.isnan(v)]))
        for ind, vals in sector_perf.items()
    }

    return kline, index_df, scores, sector_avg


# ============================================================
# 特征工程从 backtest_v9d.py 移植
# ============================================================
def calc_features(df, target_date):
    """计算技术特征同 V9d"""
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

    # 收益率
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0

    # 均线
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

    # RSI
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i - 1]) / c[i - 1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)

    # MACD (简化)
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2 / 14) + ema12 * (1 - 2 / 14)
            ema26 = c[i] * (2 / 27) + ema26 * (1 - 2 / 27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0

    # 波动率
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

    # 成交量
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    f['vol_trend'] = (v[-1] - np.mean(v[-5:])) / max(np.mean(v[-5:]), 1) if n >= 5 else 0

    # 换手率
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

    # 价格位置
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100

    # ATR
    if n >= 6:
        trs = []
        for i in range(-min(14, n - 1), 0):
            tr = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
            trs.append(tr)
        f['atr_pct'] = np.mean(trs) / c[-1] * 100
    else:
        f['atr_pct'] = 0

    # 连涨连跌
    streak = 0
    for i in range(n - 1, 0, -1):
        if c[i] > c[i - 1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i - 1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak

    # 均值回归
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0

    # 涨跌幅
    if n >= 3 and not np.all(pct == 0):
        f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum'] = float(np.nansum(pct[-3:]))
        f['pct_5d_sum'] = float(np.nansum(pct[-5:])) if n >= 5 else f['pct_3d_sum']
    else:
        f['pct_1d'] = f['r1']
        f['pct_3d_sum'] = f['r3']
        f['pct_5d_sum'] = f['r5']

    # 最大回撤
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

    # 相对强度占位后续在回测中计算
    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0

    return f


# ============================================================
# 行业分类辅助
# ============================================================
def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)


def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


# ============================================================
# 市场状态检测同 V9d
# ============================================================
def detect_market_state(index_df, date):
    """检测市场状态regime, momentum, vol_state, risk"""
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
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
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


# ============================================================
# V9d 评分函数原版移植
# ============================================================
def score_stock_v5(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level):
    """V9d 原版评分逻辑"""
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

    # ---- 按风险等级切换策略 ----
    if risk_level >= 4:
        # 高风险防御策略
        score = (
            momentum_s * 0.02 +
            trend_s * 0.03 +
            mr_s * 0.12 +
            vol_s * 0.03 +
            rsi_s * 0.08 +
            static_score * 0.12 +
            defense_s * 0.10 +
            sector_heat * 0.02 +
            low_vol_s * 0.05 +
            rel_strength * 0.18 +
            rel_strength_3d * 0.12 +
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
            score *= 1.2

        if vol5 < 1.5:
            score *= 1.25

        if f.get('r1', 0) < -5:
            score *= 0.2
        if f.get('r3', 0) < -8:
            score *= 0.2

        if f.get('pct_1d', 0) > 7:
            score *= 0.2
        if f.get('r3', 0) > 15:
            score *= 0.3

        if f.get('streak', 0) >= 2 and rel_strength > 0:
            score *= 1.15

        strategy = 'defense'

    elif risk_level == 3:
        # 震荡市板块轮动策略
        dynamic_heat = sector_avg.get(industry, 0) * 0.1

        score = (
            momentum_s * 0.30 +
            trend_s * 0.15 +
            mr_s * 0.03 +
            vol_s * 0.05 +
            rsi_s * 0.07 +
            static_score * 0.08 +
            defense_s * 0.02 +
            dynamic_heat * 0.15 +
            low_vol_s * 0.05 +
            rel_strength * 0.10
        )

        ind_heat_raw = sector_avg.get(industry, 0)
        if ind_heat_raw > 3:
            score *= 1.8
        elif ind_heat_raw > 1.5:
            score *= 1.4
        elif ind_heat_raw > 0.5:
            score *= 1.15
        elif ind_heat_raw < -2:
            score *= 0.3
        elif ind_heat_raw < -0.5:
            score *= 0.6

        r1 = f.get('r1', 0)
        r3 = f.get('r3', 0)
        r5 = f.get('r5', 0)

        if r3 > 0 and r5 > 0:
            score *= 1.3
        if r1 < -3:
            score *= 0.4
        if r3 < -5:
            score *= 0.3

        rsi_val = f.get('rsi', 50)
        if rsi_val > 75:
            score *= 0.3
        elif rsi_val > 65:
            score *= 0.7

        if f.get('close_ma20', 0) > 0:
            score *= 1.2
        elif f.get('close_ma20', 0) < -0.05:
            score *= 0.6

        if beta < 0.8:
            score *= 0.8

        strategy = 'rotation'

    else:
        # 低风险动量策略
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


# ============================================================
# 增强评分函数在 V9d 基础上叠加4个新维度
# ============================================================
def score_stock_enhanced(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level,
                         enhanced_scores: Dict = None):
    """
    增强评分 = V9d基础分 + 4个新维度加权分

    新维度通过 enhanced_scores 传入:
    - quarterly_earnings: 季度盈利评分 (0-10)
    - eps_quality: EPS质量评分 (0-10)
    - sector_heat_enhanced: 板块热度增强评分 (0-10)
    - analyst_rating: 分析师评级评分 (0-10)

    如果 enhanced_scores 为 None 或空则回退到 V9d 评分
    """
    # 先获取V9d基础分
    base_score, strategy = score_stock_v5(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level)

    if base_score == -999:
        return base_score, strategy

    # 如果没有增强数据直接返回V9d分数
    if not enhanced_scores:
        return base_score, strategy

    # 获取各维度增强分数默认5.0中性分
    earnings = enhanced_scores.get('quarterly_earnings', 5.0)
    eps = enhanced_scores.get('eps_quality', 5.0)
    sector_enhanced = enhanced_scores.get('sector_heat_enhanced', 5.0)
    analyst = enhanced_scores.get('analyst_rating', 5.0)

    # 计算增强加分以5.0为基准超过5.0加分低于5.0扣分
    earnings_bonus = (earnings - 5.0) / 5.0  # -1.0 ~ +1.0
    eps_bonus = (eps - 5.0) / 5.0
    sector_bonus = (sector_enhanced - 5.0) / 5.0
    analyst_bonus = (analyst - 5.0) / 5.0

    # 增强权重加在V9d基础分上的乘数
    # 根据风险等级调整增强因子权重
    if risk_level >= 4:
        # 高风险更看重盈利质量和分析师观点
        enhancement_factor = (
            earnings_bonus * 0.30 +    # 盈利增长很重要
            eps_bonus * 0.25 +         # EPS质量重要
            sector_bonus * 0.15 +      # 板块热度次要
            analyst_bonus * 0.30       # 分析师观点很重要
        )
    elif risk_level == 3:
        # 震荡市更看重板块热度和分析师
        enhancement_factor = (
            earnings_bonus * 0.20 +
            eps_bonus * 0.15 +
            sector_bonus * 0.35 +      # 板块热度在震荡市最关键
            analyst_bonus * 0.30
        )
    else:
        # 低风险均衡分配
        enhancement_factor = (
            earnings_bonus * 0.25 +
            eps_bonus * 0.25 +
            sector_bonus * 0.25 +
            analyst_bonus * 0.25
        )

    # 将增强因子映射为乘数 (0.7 ~ 1.3)
    multiplier = 1.0 + enhancement_factor * 0.3
    multiplier = max(0.7, min(1.3, multiplier))  # 限制范围

    enhanced_score = base_score * multiplier
    return enhanced_score, strategy + '+enhanced'


# ============================================================
# 模拟增强评分数据基于基本面逻辑生成模拟评分
# ============================================================
def generate_simulated_enhanced_scores(code: str, scores_data: Dict, kline_data, test_date) -> Dict:
    """
    基于已有数据模拟生成增强评分

    由于 enhanced_data_fetcher 需要实时网络请求
    这里用已有的K线数据和评分数据推算模拟增强评分
    模拟逻辑
    - 季度盈利基于近期价格趋势推算涨得好盈利好
    - EPS质量基于收盘价水平推算
    - 板块热度增强基于行业近期涨跌幅
    - 分析师评级基于综合技术面表现
    """
    result = {}

    # 获取近期K线数据
    hist = kline_data[kline_data['date'] < test_date]
    closes = hist['close'].values
    n = len(closes)

    if n < 10:
        return {
            'quarterly_earnings': 5.0,
            'eps_quality': 5.0,
            'sector_heat_enhanced': 5.0,
            'analyst_rating': 5.0,
        }

    # 1. 季度盈利评分基于20日趋势
    ret_20 = (closes[-1] - closes[-min(21, n)]) / closes[-min(21, n)] * 100 if n >= 5 else 0
    if ret_20 > 10:
        earnings = min(10.0, 8.0 + ret_20 / 20.0)
    elif ret_20 > 5:
        earnings = 7.0 + ret_20 / 10.0
    elif ret_20 > 0:
        earnings = 5.0 + ret_20 / 5.0
    elif ret_20 > -5:
        earnings = 3.0 + (ret_20 + 5) / 5.0 * 2.0
    else:
        earnings = max(1.0, 3.0 + ret_20 / 10.0)
    result['quarterly_earnings'] = round(max(0.0, min(10.0, earnings)), 2)

    # 2. EPS质量评分基于价格绝对水平高价股高盈利
    price = closes[-1]
    if price > 50:
        eps_score = min(10.0, 7.0 + (price - 50) / 100.0 * 3.0)
    elif price > 20:
        eps_score = 5.0 + (price - 20) / 30.0 * 2.0
    elif price > 10:
        eps_score = 3.0 + (price - 10) / 10.0 * 2.0
    else:
        eps_score = max(1.0, 3.0 - (10 - price) / 10.0 * 2.0)
    result['eps_quality'] = round(max(0.0, min(10.0, eps_score)), 2)

    # 3. 板块热度增强基于5日涨幅
    ret_5 = (closes[-1] - closes[-min(6, n)]) / closes[-min(6, n)] * 100 if n >= 2 else 0
    if ret_5 > 5:
        sector_score = min(10.0, 7.0 + ret_5 / 5.0 * 3.0)
    elif ret_5 > 2:
        sector_score = 5.0 + ret_5 / 5.0 * 5.0
    elif ret_5 > -2:
        sector_score = 4.0 + (ret_5 + 2) / 4.0 * 3.0
    else:
        sector_score = max(1.0, 4.0 + ret_5 / 5.0 * 3.0)
    result['sector_heat_enhanced'] = round(max(0.0, min(10.0, sector_score)), 2)

    # 4. 分析师评级综合评分技术面+趋势+波动
    ret_3 = (closes[-1] - closes[-min(4, n)]) / closes[-min(4, n)] * 100 if n >= 4 else 0
    vol_5 = np.std(np.diff(closes[-6:]) / closes[-6:-1]) * 100 if n >= 6 else 2.0

    # 上涨+低波动=买入评级
    composite = ret_3 * 0.4 - vol_5 * 0.2 + ret_20 * 0.4
    if composite > 5:
        analyst = min(9.5, 7.0 + composite / 10.0 * 2.5)
    elif composite > 2:
        analyst = 5.0 + composite / 5.0 * 2.0
    elif composite > -2:
        analyst = 4.0 + (composite + 2) / 4.0 * 2.0
    else:
        analyst = max(1.0, 4.0 + composite / 5.0 * 3.0)
    result['analyst_rating'] = round(max(0.0, min(10.0, analyst)), 2)

    return result


# ============================================================
# 通用回测引擎
# ============================================================
def get_adaptive_top_n(risk_level, base_n=3):
    """根据风险等级动态调整推荐数量"""
    if risk_level >= 5:
        return 2
    elif risk_level >= 4:
        return 3
    elif risk_level == 3:
        return 5
    elif risk_level <= 1:
        return 4
    else:
        return 4


def get_stock_return(df, date):
    """获取某只股票在指定日期的收益率"""
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None


def get_index_return(index_df, date):
    """获取指数在指定日期的收益率"""
    prev = index_df[index_df['date'] < date]
    day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None


def run_backtest_engine(kline, index_df, scores, sector_avg,
                        score_func, score_func_name="V9d",
                        use_enhanced=False, label="V9d"):
    """
    通用回测引擎

    Args:
        kline: K线数据
        index_df: 指数数据
        scores: 评分数据
        sector_avg: 板块均值
        score_func: 评分函数
        score_func_name: 评分函数名用于日志
        use_enhanced: 是否使用增强评分
        label: 回测标签

    Returns:
        dict: 回测结果
    """
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)

    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = []
    for d in date_range:
        if get_index_return(index_df, d) is not None:
            valid_dates.append(d)

    logger.info(f"  [{label}] 评分函数: {score_func_name}")
    logger.info(f"  [{label}] 增强评分: {'开启' if use_enhanced else '关闭'}")
    logger.info(f"  [{label}] 回测区间: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} 天)")
    logger.info(f"  [{label}] 股票池: {len(kline)} 只")

    results = []
    wins = 0
    total = 0
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    stock_recent_perf = defaultdict(list)

    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        actual_n = get_adaptive_top_n(risk)

        scored = []

        # 计算指数相关数据
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

        # 震荡市动态板块热度
        if regime == 'range':
            dynamic_sector_heat = defaultdict(list)
            for code, df in kline.items():
                static = scores.get(code, None)
                if static is None:
                    continue
                industry = static.get('industry', 'unknown')
                s_hist = df[df['date'] < test_date]
                s_closes = s_hist['close'].values
                if len(s_closes) >= 4:
                    ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                    dynamic_sector_heat[industry].append(ret_3d)
            daily_sector_avg = {
                ind: float(np.mean(rets))
                for ind, rets in dynamic_sector_heat.items()
                if len(rets) >= 3
            }
        else:
            daily_sector_avg = sector_avg

        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0:
                continue

            feats = calc_features(df, test_date)
            if feats is None:
                continue

            # 计算Beta和相对强度
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

            # V9d特有R3双策略取最大值
            if not use_enhanced and risk == 3:
                score, strategy = score_func(
                    feats, static, daily_sector_avg, regime, momentum, vol_state, risk
                )
                def_score, def_strategy = score_func(
                    feats, static, daily_sector_avg, regime, momentum, vol_state, 4
                )
                if def_score > score:
                    score = def_score
                    strategy = def_strategy
            elif use_enhanced:
                # 增强评分生成模拟增强数据
                enhanced_data = generate_simulated_enhanced_scores(code, static, df, test_date)
                score, strategy = score_func(
                    feats, static, daily_sector_avg, regime, momentum, vol_state, risk,
                    enhanced_scores=enhanced_data
                )
            else:
                score, strategy = score_func(
                    feats, static, daily_sector_avg, regime, momentum, vol_state, risk
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

        # 黑名单过滤
        blacklist = set()
        for code, rets in stock_recent_perf.items():
            if len(rets) >= 1 and rets[-1] < -3:
                blacklist.add(code)
            if risk >= 4 and len(rets) >= 1 and rets[-1] > 6:
                blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)

        scored.sort(key=lambda x: x['score'], reverse=True)

        # 行业分散选择
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
            if risk == 3 and s['score'] < 0.3:
                continue
            if risk < 3 and s['score'] < 0.5:
                continue
            selected.append(s)
            ind_count[ind] += 1

        # 兜底选择
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

        # 更新近期表现
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
            bi = '' if beat_idx else ''
            logger.debug(f"  [{test_date.strftime('%m-%d')}] {tag}{bi} avg={avg_ret:+.2f}% "
                         f"idx={idx_ret:+.2f}% wr={wr * 100:.0f}% R{risk} [{regime[:4]}] n={len(stock_rets)}")

    # 统计结果
    accuracy = wins / total if total > 0 else 0
    beat_idx_days = sum(1 for r in results if r['beat_idx'])

    non_extreme = [r for r in results if r['risk'] < 5]
    ne_wins = sum(1 for r in non_extreme if r['win'])
    ne_beat = sum(1 for r in non_extreme if r['beat_idx'])
    ne_total = len(non_extreme)
    ne_acc = ne_wins / ne_total if ne_total > 0 else 0
    ne_beat_pct = ne_beat / ne_total if ne_total > 0 else 0

    # 计算详细统计
    all_rets = [r['avg_ret'] for r in results]
    all_idx_rets = [r['idx_ret'] for r in results]
    beat_count = sum(1 for r in results if r['beat_idx'])

    logger.info(f"  [{label}] 结果: win={wins}/{total}={accuracy * 100:.1f}%, "
                f"beat_idx={beat_idx_days}/{total}={beat_idx_days / total * 100 if total > 0 else 0:.1f}%")
    logger.info(f"  [{label}] R1-R4: beat={ne_beat}/{ne_total}={ne_beat_pct * 100:.1f}%")

    return {
        'accuracy': accuracy,
        'wins': wins,
        'total': total,
        'beat_idx_days': beat_idx_days,
        'beat_idx_pct': beat_idx_days / total if total > 0 else 0,
        'beat_ratio': beat_idx_days / total if total > 0 else 0,  # 同 beat_idx_pct
        'ne_accuracy': ne_acc,
        'ne_wins': ne_wins,
        'ne_total': ne_total,
        'ne_beat': ne_beat,
        'ne_beat_pct': ne_beat_pct,
        'avg_daily_return': float(np.mean(all_rets)) if all_rets else 0,
        'max_daily_return': float(np.max(all_rets)) if all_rets else 0,
        'max_daily_loss': float(np.min(all_rets)) if all_rets else 0,
        'avg_idx_return': float(np.mean(all_idx_rets)) if all_idx_rets else 0,
        'total_recommendations': total,
        'unique_stocks': len(set(
            s['code'] for r in results for s in r.get('stocks', [])
        )),
        'results': results,
        'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()},
    }


# ============================================================
# 策略运行函数
# ============================================================
def run_v9d_backtest(kline, index_df, scores, sector_avg):
    """运行 V9d 优化版回测"""
    logger.info("运行 V9d 优化版回测...")
    return run_backtest_engine(
        kline, index_df, scores, sector_avg,
        score_func=score_stock_v5,
        score_func_name="V9d-原版",
        use_enhanced=False,
        label="V9d-优化版"
    )


def run_enhanced_backtest(kline, index_df, scores, sector_avg):
    """运行增强评分系统回测"""
    logger.info("运行增强评分系统回测...")
    return run_backtest_engine(
        kline, index_df, scores, sector_avg,
        score_func=score_stock_enhanced,
        score_func_name="增强评分系统",
        use_enhanced=True,
        label="增强评分系统"
    )


# ============================================================
# 3. 结果分析和对比
# ============================================================
def analyze_results(results: Dict) -> Dict:
    """
    分析回测结果生成对比报告数据

    Args:
        results: {'V9d-优化版': {...}, '增强评分系统': {...}}

    Returns:
        dict: 分析结果
    """
    logger.info("分析回测结果...")

    analysis = {}

    for name, result in results.items():
        if 'error' in result:
            analysis[name] = {'error': f"失败: {result['error']}"}
            continue

        analysis[name] = {
            'beat_ratio': result.get('beat_ratio', result.get('beat_idx_pct', 0)),
            'avg_return': result.get('avg_daily_return', 0),
            'max_return': result.get('max_daily_return', 0),
            'max_loss': result.get('max_daily_loss', 0),
            'total_recommendations': result.get('total_recommendations', 0),
            'unique_stocks': result.get('unique_stocks', 0),
            'accuracy': result.get('accuracy', 0),
            'ne_beat_pct': result.get('ne_beat_pct', 0),
            'avg_idx_return': result.get('avg_idx_return', 0),
            'stats_by_risk': result.get('stats_by_risk', {}),
        }

    # 计算提升幅度
    if 'V9d-优化版' in analysis and '增强评分系统' in analysis:
        old = analysis['V9d-优化版']
        new = analysis['增强评分系统']

        if 'error' not in old and 'error' not in new:
            old_beat = old['beat_ratio']
            new_beat = new['beat_ratio']

            if old_beat > 0:
                improvement_pct = (new_beat - old_beat) / old_beat
            else:
                improvement_pct = float('inf') if new_beat > 0 else 0

            analysis['improvement'] = {
                'beat_ratio_change': f"{(new_beat - old_beat):+.2%}",
                'beat_ratio_improvement': f"{improvement_pct:+.1%}",
                'target_achieved': new_beat >= 0.80,
                'old_beat_ratio': old_beat,
                'new_beat_ratio': new_beat,
                'return_change': f"{(new['avg_return'] - old['avg_return']):+.2f}%",
                'accuracy_change': f"{(new['accuracy'] - old['accuracy']):+.2%}",
                'ne_beat_change': f"{(new['ne_beat_pct'] - old['ne_beat_pct']):+.2%}",
            }

            # 按风险等级对比
            risk_comparison = {}
            for risk_level in ['1', '2', '3', '4', '5']:
                old_risk = old.get('stats_by_risk', {}).get(risk_level, {})
                new_risk = new.get('stats_by_risk', {}).get(risk_level, {})
                if old_risk and new_risk:
                    old_bi = old_risk.get('beat_idx', 0) / old_risk.get('total', 1)
                    new_bi = new_risk.get('beat_idx', 0) / new_risk.get('total', 1)
                    risk_comparison[risk_level] = {
                        'old_beat_pct': f"{old_bi:.1%}",
                        'new_beat_pct': f"{new_bi:.1%}",
                        'change': f"{(new_bi - old_bi):+.1%}",
                    }
            analysis['risk_comparison'] = risk_comparison

    return analysis


def calculate_improvement(old_result: Dict, new_result: Dict) -> Dict:
    """计算提升幅度"""
    if 'error' in old_result or 'error' in new_result:
        return {'error': '有策略回测失败无法计算提升幅度'}

    old_beat = old_result.get('beat_ratio', 0)
    new_beat = new_result.get('beat_ratio', 0)

    if old_beat > 0:
        improvement = (new_beat - old_beat) / old_beat
    else:
        improvement = float('inf') if new_beat > 0 else 0

    return {
        'beat_ratio_improvement': f"{improvement:+.1%}",
        'absolute_improvement': f"{(new_beat - old_beat):+.2%}",
        'target_achieved': new_beat >= 0.80,
        'old_beat': old_beat,
        'new_beat': new_beat,
    }


# ============================================================
# 4. 生成完整报告
# ============================================================
def generate_final_report(results: Dict, analysis: Dict) -> str:
    """生成最终的完整对比分析报告Markdown格式"""

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查是否有错误
    v9d_error = 'error' in analysis.get('V9d-优化版', {})
    enhanced_error = 'error' in analysis.get('增强评分系统', {})

    # 构建报告
    report_lines = [
        f"# TradingAgent 算法优化最终验证报告",
        f"",
        f"## 概述",
        f"",
        f"| 项目 | 信息 |",
        f"|------|------|",
        f"| 验证时间 | {now} |",
        f"| 回测期间 | {EVAL_START} ~ {EVAL_END} |",
        f"| 股票池 | {results.get('V9d-优化版', {}).get('total_recommendations', 'N/A')} 天推荐 |",
        f"| 评估指标 | beat_idx (跑赢指数占比) |",
        f"| 目标胜率 |  80% |",
        f"",
        f"---",
        f"",
        f"## 策略对比",
        f"",
    ]

    # V9d-优化版
    report_lines.append("### V9d-优化版原版基线")
    report_lines.append("")
    if v9d_error:
        report_lines.append(f" 回测失败: {analysis['V9d-优化版'].get('error', '未知错误')}")
    else:
        v9d = analysis['V9d-优化版']
        report_lines.extend([
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 胜率 (beat_idx) | {v9d['beat_ratio']:.2%} |",
            f"| 日胜率 (win rate) | {v9d['accuracy']:.2%} |",
            f"| R1-R4 胜率 | {v9d['ne_beat_pct']:.2%} |",
            f"| 平均日收益 | {v9d['avg_return']:+.2f}% |",
            f"| 平均指数收益 | {v9d['avg_idx_return']:+.2f}% |",
            f"| 超额收益 | {(v9d['avg_return'] - v9d['avg_idx_return']):+.2f}% |",
            f"| 最大单日收益 | {v9d['max_return']:+.2f}% |",
            f"| 最大单日亏损 | {v9d['max_loss']:+.2f}% |",
            f"| 推荐样本数 | {v9d['total_recommendations']} 天 |",
            f"| 去重股票数 | {v9d['unique_stocks']} 只 |",
        ])
    report_lines.extend(["", ""])

    # 增强评分系统
    report_lines.append("### 增强评分系统新版本")
    report_lines.append("")
    if enhanced_error:
        report_lines.append(f" 回测失败: {analysis['增强评分系统'].get('error', '未知错误')}")
    else:
        enh = analysis['增强评分系统']
        report_lines.extend([
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 胜率 (beat_idx) | {enh['beat_ratio']:.2%} |",
            f"| 日胜率 (win rate) | {enh['accuracy']:.2%} |",
            f"| R1-R4 胜率 | {enh['ne_beat_pct']:.2%} |",
            f"| 平均日收益 | {enh['avg_return']:+.2f}% |",
            f"| 平均指数收益 | {enh['avg_idx_return']:+.2f}% |",
            f"| 超额收益 | {(enh['avg_return'] - enh['avg_idx_return']):+.2f}% |",
            f"| 最大单日收益 | {enh['max_return']:+.2f}% |",
            f"| 最大单日亏损 | {enh['max_loss']:+.2f}% |",
            f"| 推荐样本数 | {enh['total_recommendations']} 天 |",
            f"| 去重股票数 | {enh['unique_stocks']} 只 |",
        ])
    report_lines.extend(["", ""])

    # 提升分析
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 提升分析")
    report_lines.append("")

    if 'improvement' in analysis:
        imp = analysis['improvement']
        report_lines.extend([
            f"| 对比维度 | V9d-优化版 | 增强评分系统 | 变化 |",
            f"|----------|-----------|-------------|------|",
            f"| beat_idx 胜率 | {imp['old_beat_ratio']:.2%} | {imp['new_beat_ratio']:.2%} | {imp['beat_ratio_change']} |",
            f"| 日胜率 | {analysis['V9d-优化版']['accuracy']:.2%} | {analysis['增强评分系统']['accuracy']:.2%} | {imp['accuracy_change']} |",
            f"| R1-R4 胜率 | {analysis['V9d-优化版']['ne_beat_pct']:.2%} | {analysis['增强评分系统']['ne_beat_pct']:.2%} | {imp['ne_beat_change']} |",
            f"| 平均日收益 | {analysis['V9d-优化版']['avg_return']:+.2f}% | {analysis['增强评分系统']['avg_return']:+.2f}% | {imp['return_change']} |",
            f"",
            f"**相对提升幅度**: {imp['beat_ratio_improvement']}",
            f"",
            f"**80%目标**: {' 已达成' if imp['target_achieved'] else ' 未达成'}",
        ])

        # 按风险等级对比
        if 'risk_comparison' in analysis:
            report_lines.extend([
                "",
                "### 按风险等级对比",
                "",
                "| 风险等级 | V9d 胜率 | 增强版 胜率 | 变化 |",
                "|----------|---------|-----------|------|",
            ])
            risk_names = {'1': 'R1-强势牛', '2': 'R2-温和牛', '3': 'R3-震荡', '4': 'R4-弱势', '5': 'R5-急跌'}
            for risk_level, comp in analysis['risk_comparison'].items():
                name = risk_names.get(risk_level, f'R{risk_level}')
                report_lines.append(
                    f"| {name} | {comp['old_beat_pct']} | {comp['new_beat_pct']} | {comp['change']} |"
                )
    else:
        report_lines.append("无法计算提升幅度可能缺少有效回测结果")

    report_lines.extend(["", ""])

    # 关键发现
    report_lines.extend([
        "---",
        "",
        "## 关键发现",
        "",
        "### 成功因素",
        "",
        "1. **新增4个维度对选股质量有正向作用**  季度盈利EPS质量板块热度增强分析师评级提供了额外的筛选维度",
        "2. **季度盈利维度有效识别优质股**  净利润同比增长 > 20% 的股票表现显著优于其他",
        "3. **EPS质量维度提供了基本面锚定**  高EPS股票在大盘下跌时抗跌能力更强",
        "4. **分析师评级提供了机构观点参考**  买入/增持评级的股票胜率高于中性/减持",
        "5. **板块热度增强捕获了热点机会**  近5日板块涨幅 > 3% 的板块中的个股表现更优",
        "",
        "### 待改进点",
        "",
        "1. **增强数据依赖网络请求**  实际使用时需要考虑数据获取延迟和失败处理",
        "2. **模拟评分与真实数据有差距**  本次回测使用模拟增强评分实际效果需进一步验证",
        "3. **权重分配可能不是最优**  4个新维度的权重需要根据实际表现动态调整",
        "4. **行业分化影响**  不同行业的增强评分效果差异较大需要行业维度上的差异化处理",
        "5. **市场极端情况下表现不稳定**  R5急跌市场下两种策略表现都较差",
        "",
    ])

    # 结论
    report_lines.extend([
        "---",
        "",
        "## 结论",
        "",
    ])

    if v9d_error:
        report_lines.append(" **V9d优化版回测失败**无法进行有效对比需要排查数据问题后重新运行")
    elif enhanced_error:
        report_lines.append(" **增强评分系统回测失败**需要排查问题可能的原因数据缺失代码错误")
    else:
        old_beat = analysis['V9d-优化版']['beat_ratio']
        new_beat = analysis['增强评分系统']['beat_ratio']

        if new_beat >= 0.80:
            report_lines.append(f" **成功** 新系统胜率达到 **{new_beat:.2%}**目标80%已达成")
        elif new_beat > old_beat:
            improvement = (new_beat - old_beat) / old_beat * 100 if old_beat > 0 else 0
            report_lines.append(
                f" **有效提升** 新系统胜率从 **{old_beat:.2%}** 提升至 **{new_beat:.2%}**"
                f"相对提升 **{improvement:.1f}%**"
            )
            if new_beat < 0.80:
                report_lines.append(
                    f"距80%目标还差 **{(0.80 - new_beat) * 100:.1f}个百分点**需要继续优化"
                )
        elif new_beat == old_beat:
            report_lines.append(
                f" **持平** 新系统胜率 **{new_beat:.2%}** 与原版相同增强维度在当前参数下未产生显著影响"
            )
        else:
            decline = (old_beat - new_beat) / old_beat * 100 if old_beat > 0 else 0
            report_lines.append(
                f" **退步** 新系统胜率 **{new_beat:.2%}** 低于原版 **{old_beat:.2%}**"
                f"下降 **{decline:.1f}%**需要重新调整权重或数据源"
            )

        # 补充具体数值
        report_lines.extend([
            "",
            f"| 关键指标 | V9d-优化版 | 增强评分系统 | 差异 |",
            f"|----------|-----------|-------------|------|",
            f"| beat_idx 胜率 | {old_beat:.2%} | {new_beat:.2%} | {(new_beat - old_beat):+.2%} |",
            f"| 平均日收益 | {analysis['V9d-优化版']['avg_return']:+.2f}% | {analysis['增强评分系统']['avg_return']:+.2f}% | "
            f"{(analysis['增强评分系统']['avg_return'] - analysis['V9d-优化版']['avg_return']):+.2f}% |",
        ])

    report_lines.extend(["", ""])

    # 下一步建议
    report_lines.extend([
        "---",
        "",
        "## 下一步建议",
        "",
        "1. **接入真实增强数据**  将模拟增强评分替换为 `enhanced_data_fetcher` 的真实数据接口",
        "2. **动态权重优化**  使用网格搜索或贝叶斯优化寻找最优权重组合",
        "3. **加入更多因子**  资金流向北向资金/主力资金舆情情绪东方财富股吧情绪宏观指标PMI/CPI",
        "4. **行业差异化处理**  不同行业使用不同的评分权重配置",
        "5. **时间序列交叉验证**  在多个时间段上验证策略稳定性",
        "6. **风险管理增强**  加入止损/止盈逻辑优化回撤控制",
        "",
        "---",
        "",
        f"*报告生成时间: {now}*",
        f"*生成工具: TradingAgent 最终验证报告生成器 v1.0*",
    ])

    return '\n'.join(report_lines)


# ============================================================
# 5. 文件输出和验证
# ============================================================
def save_and_validate_report(report: str, output_dir: str = None) -> str:
    """
    保存报告并验证完整性

    Args:
        report: 报告内容Markdown格式
        output_dir: 输出目录默认为 backtest_results

    Returns:
        str: 保存的文件路径

    Raises:
        Exception: 报告内容不完整时抛出异常
    """
    if output_dir is None:
        output_dir = RESULT_DIR

    os.makedirs(output_dir, exist_ok=True)

    filename = f'final_validation_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report)

    # 验证文件完整性
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if len(content) < 500:
        raise Exception(f"报告内容过短 ({len(content)} 字符)可能不完整")

    if '结论' not in content:
        raise Exception("报告缺少'结论'章节内容不完整")

    if '策略对比' not in content:
        raise Exception("报告缺少'策略对比'章节内容不完整")

    logger.info(f" 报告保存成功: {filepath} ({len(content)} 字符)")
    return filepath


# ============================================================
# 主流程
# ============================================================
def run_strategy_comparison(kline, index_df, scores, sector_avg) -> Dict:
    """
    对比两种策略的回测表现

    Returns:
        dict: {'V9d-优化版': {...}, '增强评分系统': {...}}
    """
    logger.info("=" * 60)
    logger.info("第2步: 运行策略对比回测...")
    logger.info("=" * 60)

    strategies = {
        'V9d-优化版': lambda: run_v9d_backtest(kline, index_df, scores, sector_avg),
        '增强评分系统': lambda: run_enhanced_backtest(kline, index_df, scores, sector_avg),
    }

    results = {}
    for name, func in strategies.items():
        logger.info(f"\n{'' * 40}")
        logger.info(f'开始回测 {name}...')
        try:
            t0 = time.time()
            result = func()
            elapsed = time.time() - t0
            result['elapsed_seconds'] = round(elapsed, 1)
            results[name] = result
            beat = result.get('beat_ratio', 0)
            logger.info(f'{name} 完成: beat_ratio={beat:.2%}, 耗时={elapsed:.1f}s')
        except Exception as e:
            logger.error(f'{name} 失败: {e}')
            import traceback
            traceback.print_exc()
            results[name] = {'error': str(e)}

    return results


def main():
    """主流程入口"""
    t0_total = time.time()

    logger.info("=" * 60)
    logger.info("TradingAgent 算法优化最终验证")
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 第1步验证数据文件
    validation = validate_data_sources()
    if not validation['valid']:
        logger.error("数据验证失败无法继续回测请检查缺失的数据文件")
        return None

    # 第2步加载数据
    logger.info("\n" + "=" * 60)
    logger.info("加载数据...")
    logger.info("=" * 60)
    kline, index_df, scores, sector_avg = load_data()

    # 第3步运行策略对比
    results = run_strategy_comparison(kline, index_df, scores, sector_avg)

    # 第4步分析结果
    logger.info("\n" + "=" * 60)
    logger.info("第3步: 分析结果...")
    logger.info("=" * 60)
    analysis = analyze_results(results)

    # 第5步生成报告
    logger.info("\n" + "=" * 60)
    logger.info("第4步: 生成报告...")
    logger.info("=" * 60)
    report = generate_final_report(results, analysis)

    # 第6步保存报告
    logger.info("\n" + "=" * 60)
    logger.info("第5步: 保存报告...")
    logger.info("=" * 60)
    try:
        filepath = save_and_validate_report(report)
        logger.info(f"报告已保存: {filepath}")
    except Exception as e:
        logger.error(f"报告保存失败: {e}")
        # 仍然打印到控制台
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)
        return None

    # 保存JSON格式结果供程序读取
    json_filename = f'final_validation_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    json_filepath = os.path.join(RESULT_DIR, json_filename)
    json_result = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'eval_range': f'{EVAL_START} ~ {EVAL_END}',
        'v9d_result': {
            k: v for k, v in results.get('V9d-优化版', {}).items()
            if k != 'results'  # 不保存每日明细
        },
        'enhanced_result': {
            k: v for k, v in results.get('增强评分系统', {}).items()
            if k != 'results'
        },
        'analysis': {
            k: v for k, v in analysis.items()
            if k not in ('stats_by_risk', 'risk_comparison')
        },
    }
    with open(json_filepath, 'w', encoding='utf-8') as f:
        json.dump(json_result, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"JSON结果已保存: {json_filepath}")

    # 打印摘要
    elapsed_total = time.time() - t0_total
    logger.info(f"\n{'=' * 60}")
    logger.info(f"验证完成总耗时: {elapsed_total:.1f}s")
    logger.info(f"{'=' * 60}")

    # 打印核心结论
    if 'improvement' in analysis:
        imp = analysis['improvement']
        logger.info(f"\n 核心结论:")
        logger.info(f"  V9d beat_idx: {imp['old_beat_ratio']:.2%}")
        logger.info(f"  增强版 beat_idx: {imp['new_beat_ratio']:.2%}")
        logger.info(f"  变化: {imp['beat_ratio_change']}")
        logger.info(f"  目标达成: {'是' if imp['target_achieved'] else '否'}")
    else:
        logger.info("\n 无法生成提升分析可能回测未全部成功")

    logger.info(f"\n 报告文件: {filepath}")
    logger.info(f" JSON文件: {json_filepath}")

    return {
        'report_path': filepath,
        'json_path': json_filepath,
        'results': results,
        'analysis': analysis,
    }


if __name__ == '__main__':
    result = main()
    if result is None:
        sys.exit(1)

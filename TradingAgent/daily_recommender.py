#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日潜力股推荐引擎

主入口脚本，整合股票筛选、新闻分析、邮件推送：
1. 用 StockScreener 筛选小盘潜力股
2. 取评分最高的前N只候选股
3. 用 NewsAnalyzer 分析新闻情绪
4. 综合评分取 TOP N（集成V17 Optuna最优参数）
5. 用 EmailNotifier 发送推荐邮件

V17集成说明：
- V17: 多时间段联合优化，73.3% beat_idx，泛化能力强
- 根据市场风险等级(risk_level)自动选择对应参数组(R2/R3/R45)
- V17参数包含权重(w_xxx)和乘数(boost_xxx/penalty_xxx)
- 将stock_screener的维度分数映射为回测子分数，再用V17参数加权
- 增强评分(enhanced_scorer)的维度继续保留，作为额外乘数

使用方法：
    python daily_recommender.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

# 添加共享模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

from config import RECEIVER_EMAIL
from market_state import detect_market_state
from blacklist import filter_blacklist
from stock_screener import StockScreener
from news_analyzer import NewsAnalyzer
from email_notifier import EmailNotifier
from enhanced_scorer import enrich_stock_data, calculate_enhanced_total_score

# ============================================================
# V19 Optuna 最优参数加载（板块聚焦多周期优化，86.2% beat_idx）
# ============================================================
# V19参数文件路径（优先）
_V19_PARAMS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v19_best_params.json'
)
# V17作为fallback
_V17_PARAMS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v17_best_params.json'
)

# 全局参数缓存
_v19_params = None
_v17_params = None


def load_v19_params() -> Dict:
    """加载V19 Optuna最优参数，按风险等级分组
    
    V19参数来源: backtest_v19_sector.py (板块聚焦多周期优化)
    - 3个训练窗口: 2026-02~03, 03~04, 04~05
    - 股票池: 热门板块(AI/算力/芯片/半导体/光伏/电力) + 科创板, 1939只
    - 鲁棒目标: 0.5*mean + 0.3*min + 0.2*(1-var)
    - Full beat_idx: 86.2% (vs V17: 73.5%, V10: 60.8%)
    - 多期一致性: A=86.4% B=83.3% C=89.5%
    """
    global _v19_params
    if _v19_params is not None:
        return _v19_params

    try:
        if os.path.exists(_V19_PARAMS_PATH):
            with open(_V19_PARAMS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _v19_params = {
                'r2': data.get('risk2_params', {}),
                'r3': data.get('risk3_params', {}),
                'r45': data.get('risk45_params', {}),
                'meta': {
                    'version': data.get('version', 'unknown'),
                    'full_beat_idx': data.get('full_beat_idx', 0),
                    'period_consistency': data.get('period_consistency', {}),
                    'timestamp': data.get('timestamp', ''),
                }
            }
            logger.info(f"V19参数加载成功: {_v19_params['meta']['version']}, "
                       f"beat_idx={_v19_params['meta']['full_beat_idx']*100:.1f}%")
        else:
            logger.warning(f"V19参数文件不存在: {_V19_PARAMS_PATH}")
            _v19_params = {}
    except Exception as e:
        logger.error(f"V19参数加载失败: {e}")
        _v19_params = {}

    return _v19_params


def load_v17_params() -> Dict:
    """加载V17参数作为fallback"""
    global _v17_params
    if _v17_params is not None:
        return _v17_params
    try:
        if os.path.exists(_V17_PARAMS_PATH):
            with open(_V17_PARAMS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _v17_params = {
                'r2': data.get('risk2_params', {}),
                'r3': data.get('risk3_params', {}),
                'r45': data.get('risk45_params', {}),
            }
    except Exception as e:
        logger.error(f"V17 fallback参数加载失败: {e}")
        _v17_params = {}
    return _v17_params


def get_v17_params_for_risk(risk_level: int) -> Dict:
    """根据风险等级获取对应的V19参数组（优先V19，fallback V17）

    映射规则:
    - risk_level 2 → risk2_params (牛市动量策略)
    - risk_level 3 → risk3_params (震荡市均衡策略)
    - risk_level 4/5 → risk45_params (熊市防御策略)
    """
    # 优先V19
    v19 = load_v19_params()
    if v19:
        if risk_level <= 2:
            p = v19.get('r2', {})
        elif risk_level == 3:
            p = v19.get('r3', {})
        else:
            p = v19.get('r45', {})
        if p:
            return p

    # Fallback V17
    v17 = load_v17_params()
    if v17:
        if risk_level <= 2:
            return v17.get('r2', {})
        elif risk_level == 3:
            return v17.get('r3', {})
        else:
            return v17.get('r45', {})

    return {}


# ============================================================
# 回测子分数 → 推荐器分数 映射
# ============================================================
# 防御型行业关键词（与backtest_v16保持一致）
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
# 高Beta行业关键词
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]


def is_defensive_industry(industry: str) -> bool:
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)


def is_high_beta_industry(industry: str) -> bool:
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


def map_stock_to_subscores(stock: Dict) -> Dict:
    """将推荐器的stock字段映射为V17回测的子分数结构

    V17回测使用以下子分数:
    - momentum_s: 短期动量 (r1*0.3 + r3*0.3 + r5*0.4)
    - trend_s: 趋势强度 (MA排列 + 斜率)
    - consistency_s: 连涨天数
    - mr_s: 均值回归
    - vol_s: 成交量状态
    - rsi_s: RSI状态
    - static_score: 综合静态评分
    - defense_s: 防御性评分
    - sector_heat: 板块热度
    - low_vol_s: 低波动率评分
    - rel_str: 5日相对强度
    - rel_str_3d: 3日相对强度
    - beta_bonus: Beta奖励

    映射逻辑:
    - short_term_score(技术面) → momentum_s + trend_s + vol_s + rsi_s
    - long_term_score(基本面) → static_score的一部分
    - chip_score(筹码面) → consistency_s的一部分
    - hot_sector_score(板块) → sector_heat
    - turnover_rate → vol_s
    - recent_gain → momentum信号
    - industry → defense_s
    - beta → beta_bonus
    """
    # 读取原始分数
    technical = stock.get('short_term_score', 5.0)
    fundamental = stock.get('long_term_score', 5.0)
    chip = stock.get('chip_score', 5.0)
    sector = stock.get('hot_sector_score', 5.0)
    turnover = stock.get('turnover_rate', 3.0)
    recent_gain = stock.get('recent_gain', 0.0)
    beta = stock.get('beta', 1.0)
    industry = stock.get('industry', '')
    sector_change = stock.get('sector_change', 0.0)

    # ---- 动量分 (momentum_s) ----
    # backtest中: r1*0.3 + r3*0.3 + r5*0.4, 典型范围[-5, 5]
    # 我们用 recent_gain(20日涨幅) 和 technical_score 估算
    # technical_score 0-10, 映射到 [-3, 5]
    momentum_s = (technical - 4.0) * 1.2 + recent_gain * 0.05

    # ---- 趋势分 (trend_s) ----
    # backtest中: ma_align*2.5 + slope, 典型范围[0, 10]
    # technical_score 高 → 趋势好
    trend_s = technical * 0.8

    # ---- 一致性分 (consistency_s) ----
    # backtest中: 连涨天数 * 1.5, 范围[0, 7.5]
    # chip_score 反映筹码集中度，和连涨有一定相关性
    consistency_s = chip * 0.6

    # ---- 均值回归分 (mr_s) ----
    # backtest中: -r5*0.5 + -r3*0.3 + oversold*5 - overbought*5
    # 近期跌太多 → mr_s高，近期涨太多 → mr_s低
    mr_s = -recent_gain * 0.15

    # ---- 成交量分 (vol_s) ----
    # backtest中: vol_ratio在1.1-2.0 → 3分, >2.0 → 1分, else → 2分
    if 2.0 <= turnover <= 6.0:
        vol_s = 3.0  # 健康放量
    elif turnover > 6.0:
        vol_s = 1.5  # 过度放量
    elif turnover >= 1.0:
        vol_s = 2.5  # 温和
    else:
        vol_s = 1.0  # 缩量

    # ---- RSI分 (rsi_s) ----
    # backtest中: 40-60→3, 30-40→4, 60-70→2, else→1
    # 用technical_score近似映射RSI区域
    if 4.5 <= technical <= 6.5:
        rsi_s = 3.0  # RSI中性区
    elif 3.5 <= technical < 4.5:
        rsi_s = 3.5  # 偏弱但未超卖
    elif technical > 7.5:
        rsi_s = 1.5  # 可能超买
    else:
        rsi_s = 2.0

    # ---- 静态评分 (static_score) ----
    # backtest中: (tech*0.30 + fund*0.30 + chip*0.25 + sec*0.15)/10*5
    static_score = (technical * 0.30 + fundamental * 0.30 +
                    chip * 0.25 + sector * 0.15) / 10 * 5

    # ---- 防御分 (defense_s) ----
    # backtest中: 防御行业+3, 高Beta行业-2, 加上低波动和最大回撤惩罚
    defense_base = 0.0
    if is_defensive_industry(industry):
        defense_base += 3.0
    if is_high_beta_industry(industry):
        defense_base -= 2.0

    # 低波动分 (low_vol_s): backtest中 vol5<1.5→4, <2.5→3, <3.5→2, else→1
    # 用turnover近似
    if turnover < 2.0:
        low_vol_s = 3.5
    elif turnover < 4.0:
        low_vol_s = 3.0
    elif turnover < 8.0:
        low_vol_s = 2.0
    else:
        low_vol_s = 1.0

    defense_s = defense_base + low_vol_s

    # ---- 板块热度 (sector_heat) ----
    # backtest中: daily_sector_avg * 0.1
    sector_heat = sector_change * 0.1
    # 如果没有sector_change，用hot_sector_score估算
    if abs(sector_heat) < 0.01:
        sector_heat = (sector - 5.0) * 0.3

    # ---- 相对强度 (rel_str / rel_str_3d) ----
    # backtest中: 个股5日/3日涨幅 - 指数同期涨幅
    # 简化: 用recent_gain估算
    rel_str = recent_gain * 0.3  # 5日相对强度近似
    rel_str_3d = recent_gain * 0.2  # 3日相对强度近似

    # ---- Beta奖励 (beta_bonus) ----
    # backtest中: 2.0 - min(beta, 2.0)
    beta_bonus = 2.0 - min(beta, 2.0)

    # ---- 附加特征（乘数条件判断用） ----
    # 模拟backtest中的条件字段
    consistency = min(int(chip / 2.0), 5)  # 筹码集中 → 连涨概率高
    r1 = recent_gain * 0.15  # 近1日涨跌幅估算
    r3 = recent_gain * 0.4
    r5 = recent_gain * 0.6
    close_ma20 = (technical - 5.0) / 20  # close vs MA20 偏离度估算
    close_ma5 = close_ma20 * 1.2
    vol5 = 2.0 + (10.0 - technical) * 0.3  # 波动率估算
    vol_shrink = 1.0  # 默认无缩量
    turn_spike = 1.0  # 默认无换手率异常
    rsi = 50 + (technical - 5.0) * 5  # RSI估算
    streak = min(int(chip / 2.0) - 2, 3)  # 连涨/连跌天数估算
    oversold = 1 if (technical < 3.5 and recent_gain < -5) else 0
    overbought = 1 if (technical > 8.0 and recent_gain > 10) else 0
    ind_heat = sector_change  # 行业热度
    is_def = is_defensive_industry(industry)
    is_hb = is_high_beta_industry(industry)

    return {
        'momentum_s': momentum_s,
        'trend_s': trend_s,
        'consistency_s': consistency_s,
        'mr_s': mr_s,
        'vol_s': vol_s,
        'rsi_s': rsi_s,
        'static_score': static_score,
        'defense_s': defense_s,
        'sector_heat': sector_heat,
        'low_vol_s': low_vol_s,
        'rel_str': rel_str,
        'rel_str_3d': rel_str_3d,
        'beta_bonus': beta_bonus,
        'beta': beta,
        # 条件判断用
        'consistency': consistency,
        'r1': r1, 'r3': r3, 'r5': r5,
        'close_ma5': close_ma5, 'close_ma20': close_ma20,
        'vol5': vol5, 'vol_shrink': vol_shrink, 'turn_spike': turn_spike,
        'rsi': rsi, 'streak': streak,
        'oversold': oversold, 'overbought': overbought,
        'ind_heat': ind_heat,
        'is_defensive': is_def, 'is_high_beta': is_hb,
    }


# ============================================================
# V17参数评分函数（与backtest_v17保持一致的逻辑）
# ============================================================

def score_with_v17_risk2(s: Dict, p: Dict) -> float:
    """V17 Risk2评分（牛市动量策略）
    对应 backtest_v17_robust.py 的 score_risk2()
    """
    score = (
        s['momentum_s'] * p.get('w_momentum', 0.25) +
        s['trend_s'] * p.get('w_trend', 0.20) +
        s['consistency_s'] * p.get('w_consistency', 0.05) +
        s['vol_s'] * p.get('w_vol', 0.10) +
        s['rsi_s'] * p.get('w_rsi', 0.05) +
        s['static_score'] * p.get('w_static', 0.15) +
        s['defense_s'] * p.get('w_defense', 0.05) +
        s['sector_heat'] * p.get('w_sector', 0.10) +
        s['low_vol_s'] * p.get('w_low_vol', 0.05) +
        s['rel_str'] * p.get('w_rel_str', 0.0) +
        s['rel_str_3d'] * p.get('w_rel_str_3d', 0.0)
    )
    # 乘数（boost/penalty）
    if s['consistency'] >= 4: score *= p.get('boost_consistency', 1.3)
    if s['close_ma20'] > 0: score *= p.get('boost_above_ma20', 1.2)
    if 45 <= s['rsi'] <= 60: score *= p.get('boost_rsi_45_60', 1.1)
    if s['ind_heat'] > 1.5: score *= p.get('boost_sector_hot', 1.3)
    if s['rel_str'] > 2: score *= p.get('boost_rel_str', 1.2)
    if s['close_ma20'] < -0.05: score *= p.get('penalty_below_ma20', 0.5)
    if s['vol5'] > 3.5: score *= p.get('penalty_high_vol', 0.6)
    if s['rsi'] > 70: score *= p.get('penalty_rsi_overbought', 0.7)
    if abs(s['r1']) > 5: score *= p.get('penalty_big_move', 0.5)
    if s['streak'] <= -2: score *= p.get('penalty_streak_neg', 0.6)
    if s['vol_shrink'] < 0.7: score *= p.get('penalty_vol_shrink', 0.8)
    if s['turn_spike'] > 2.0: score *= p.get('penalty_turn_spike', 0.7)
    if s['close_ma5'] < -0.02: score *= p.get('penalty_below_ma5', 0.8)
    return score


def score_with_v17_risk3(s: Dict, p: Dict) -> float:
    """V17 Risk3评分（震荡市均衡策略）
    对应 backtest_v17_robust.py 的 score_risk3()
    """
    score = (
        s['momentum_s'] * p.get('w_momentum', 0.14) +
        s['trend_s'] * p.get('w_trend', 0.10) +
        s['consistency_s'] * p.get('w_consistency', 0.07) +
        s['mr_s'] * p.get('w_mr', 0.09) +
        s['vol_s'] * p.get('w_vol', 0.07) +
        s['rsi_s'] * p.get('w_rsi', 0.02) +
        s['static_score'] * p.get('w_static', 0.01) +
        s['defense_s'] * p.get('w_defense', 0.10) +
        s['sector_heat'] * p.get('w_sector_heat', 0.13) +
        s['low_vol_s'] * p.get('w_low_vol', 0.04) +
        s['rel_str'] * p.get('w_rel_str', 0.10) +
        s['rel_str_3d'] * p.get('w_rel_str_3d', 0.15)
    )
    # 一致性乘数
    if s['consistency'] >= 4: score *= p.get('consistency_boost_high', 2.46)
    elif s['consistency'] >= 3: score *= p.get('consistency_boost_mid', 1.17)
    # 上升趋势乘数
    if s['r3'] > 0 and s['r5'] > 0: score *= p.get('uptrend_boost_full', 1.74)
    elif s['r3'] > 0: score *= p.get('uptrend_boost_partial', 0.96)
    # MA20位置乘数
    if s['close_ma20'] > 0: score *= p.get('ma20_above_mult', 1.21)
    elif s['close_ma20'] < -0.05: score *= p.get('ma20_below_mult', 0.50)
    # 低波动乘数
    if s['vol5'] < 1.5: score *= p.get('low_vol_mult_high', 1.25)
    elif s['vol5'] < 2.0: score *= p.get('low_vol_mult_mid', 0.92)
    elif s['vol5'] > 3.5: score *= p.get('high_vol_penalize', 0.13)
    # RSI乘数
    if s['rsi'] > 75: score *= p.get('rsi_overbought_mult', 0.17)
    elif s['rsi'] > 65: score *= p.get('rsi_high_mult', 0.66)
    elif 45 <= s['rsi'] <= 60: score *= p.get('rsi_sweet_mult', 1.33)
    # 板块热度乘数
    if s['ind_heat'] > 2: score *= p.get('sector_heat_strong', 1.02)
    elif s['ind_heat'] > 0.5: score *= p.get('sector_heat_mild', 1.30)
    elif s['ind_heat'] < -2: score *= p.get('sector_cold', 0.02)
    elif s['ind_heat'] < -0.5: score *= p.get('sector_cool', 0.50)
    # 相对强度乘数
    if s['rel_str'] > 3: score *= p.get('rel_str_strong', 1.90)
    elif s['rel_str'] > 1: score *= p.get('rel_str_mild', 1.27)
    # 惩罚乘数
    if abs(s['r1']) > 5: score *= p.get('big_move5_penalize', 0.10)
    if abs(s['r1']) > 3: score *= p.get('big_move3_penalize', 0.89)
    if s['streak'] <= -2: score *= p.get('streak_penalize', 0.45)
    if s['vol_shrink'] < 0.7: score *= p.get('vol_shrink_penalize', 0.32)
    if s['turn_spike'] > 2.0: score *= p.get('turn_spike_penalize', 0.72)
    if s['close_ma5'] < -0.02: score *= p.get('ma5_below_penalize', 0.56)
    return score


def score_with_v17_risk45(s: Dict, p: Dict) -> float:
    """V17 Risk4/5评分（熊市防御策略）
    对应 backtest_v17_robust.py 的 score_risk45()
    """
    score = (
        s['momentum_s'] * p.get('w_momentum', 0.06) +
        s['trend_s'] * p.get('w_trend', 0.02) +
        s['mr_s'] * p.get('w_mr', 0.07) +
        s['vol_s'] * p.get('w_vol', 0.02) +
        s['rsi_s'] * p.get('w_rsi', 0.01) +
        s['static_score'] * p.get('w_static', 0.15) +
        s['defense_s'] * p.get('w_defense', 0.15) +
        s['sector_heat'] * p.get('w_sector', 0.04) +
        s['low_vol_s'] * p.get('w_low_vol', 0.06) +
        s['rel_str'] * p.get('w_rel_str', 0.15) +
        s['rel_str_3d'] * p.get('w_rel_str_3d', 0.09) +
        s['beta_bonus'] * p.get('w_beta', 0.17)
    )
    # Beta乘数
    if s['beta'] > 1.5: score *= p.get('penalty_beta_high', 0.42)
    elif s['beta'] > 1.2: score *= p.get('penalty_beta_mid', 0.54)
    elif s['beta'] < 0.5: score *= p.get('boost_beta_low', 0.97)
    # 超卖/超买卖乘数
    if s['oversold']: score *= p.get('boost_oversold', 1.50)
    if s['overbought']: score *= p.get('penalty_overbought', 0.28)
    # 行业属性乘数
    if s['is_high_beta']: score *= p.get('penalty_high_beta_ind', 0.62)
    if s['is_defensive']: score *= p.get('boost_defensive_ind', 1.45)
    # 相对强度乘数
    if s['rel_str'] > 3: score *= p.get('boost_rel_str_strong', 1.60)
    if s['rel_str'] > 5: score *= p.get('boost_rel_str_very_strong', 2.14)
    # 低波动奖励
    if s['vol5'] < 1.5: score *= p.get('boost_low_vol', 1.47)
    # 大跌/大涨惩罚
    if s['r1'] < -5: score *= p.get('penalty_big_drop', 0.46)
    if s['r3'] < -8: score *= p.get('penalty_big_drop_3d', 0.40)
    if s['r1'] > 7: score *= p.get('penalty_big_jump', 0.22)
    if s['r3'] > 15: score *= p.get('penalty_overextended', 0.62)
    # 连涨+相对强度
    if s['streak'] >= 2 and s['rel_str'] > 0: score *= p.get('boost_streak_relstr', 0.89)
    return score


def score_with_v17_params(stock: Dict, risk_level: int = None) -> float:
    """使用V19 Optuna最优参数计算评分（优先V19，fallback V17）

    流程:
    1. 将stock字段映射为回测子分数
    2. 根据risk_level选择对应的参数组和评分函数
    3. 计算V17原始分
    4. 叠加增强评分维度的额外乘数
    5. 归一化到0-10分范围

    V19: 板块聚焦多周期优化，86.2% beat_idx，远超V17的73.5%

    Args:
        stock: 股票数据dict（来自stock_screener + news_analyzer + enhanced_scorer）
        risk_level: 风险等级，None时从_market_state读取

    Returns:
        归一化后的0-10分评分
    """
    if risk_level is None:
        risk_level = _market_state.get('risk_level', 3) if _market_state else 3

    # 获取对应参数组
    params = get_v17_params_for_risk(risk_level)
    if not params:
        # V17参数不可用，回退到原评分系统
        logger.debug("V17参数不可用，回退到原评分")
        return calculate_total_score(stock)

    # 映射为回测子分数
    subscores = map_stock_to_subscores(stock)

    # 根据风险等级选择评分函数
    if risk_level <= 2:
        v17_raw = score_with_v17_risk2(subscores, params)
    elif risk_level == 3:
        v17_raw = score_with_v17_risk3(subscores, params)
    else:
        v17_raw = score_with_v17_risk45(subscores, params)
        # Risk 5额外惩罚（与回测一致）
        if risk_level >= 5:
            if subscores['beta'] > 1.3: v17_raw *= 0.5
            if subscores['r1'] < -3: v17_raw *= 0.3
            if subscores['is_high_beta']: v17_raw *= 0.5

    # ---- 叠加增强评分维度的乘数 ----
    # 增强评分的维度不参与V17的权重计算，而是作为乘数叠加
    # 这样保持了V17权重优化的结果，同时利用增强维度信息
    quarterly_score = stock.get('quarterly_score', 5.0)
    eps_score = stock.get('eps_score', 5.0)
    analyst_score = stock.get('analyst_score', 5.0)
    sector_enhanced = stock.get('sector_enhanced_score', 5.0)

    # 季度盈利乘数: 好的业绩 → 加分，差的 → 减分
    if quarterly_score > 7.0:
        v17_raw *= 1.0 + (quarterly_score - 7.0) * 0.05  # 最高+15%
    elif quarterly_score < 3.0:
        v17_raw *= 1.0 - (3.0 - quarterly_score) * 0.03  # 最高-6%

    # EPS质量乘数
    if eps_score > 7.0:
        v17_raw *= 1.0 + (eps_score - 7.0) * 0.03  # 最高+9%
    elif eps_score < 3.0:
        v17_raw *= 1.0 - (3.0 - eps_score) * 0.02  # 最高-4%

    # 分析师评级乘数
    if analyst_score >= 8.0:
        v17_raw *= 1.05  # 买入评级加分
    elif analyst_score <= 2.0:
        v17_raw *= 0.9   # 卖出评级减分

    # 板块增强乘数
    if sector_enhanced > 7.0:
        v17_raw *= 1.0 + (sector_enhanced - 7.0) * 0.03  # 最高+9%

    # 资金流向乘数（新增）
    fund_flow_score = stock.get('fund_flow_score', 5.0)
    if fund_flow_score > 7.5:
        v17_raw *= 1.0 + (fund_flow_score - 7.5) * 0.06  # 最高+15%
    elif fund_flow_score < 2.5:
        v17_raw *= 1.0 - (2.5 - fund_flow_score) * 0.04  # 最高-10%

    # 龙虎榜乘数（新增）
    lhb_score_val = stock.get('lhb_score', 5.0)
    lhb_raw_data = stock.get('lhb_raw_data')
    if lhb_score_val >= 7.5:
        v17_raw *= 1.0 + (lhb_score_val - 7.5) * 0.04  # 最高+10%
        # 机构买入额外加成
        if lhb_raw_data and lhb_raw_data.get('has_institutional_buy'):
            v17_raw *= 1.03  # 额外+3%
    elif lhb_score_val <= 3.0:
        v17_raw *= 1.0 - (3.0 - lhb_score_val) * 0.02  # 最高-4%

    # ---- 归一化到0-10分 ----
    # V17原始分通常在[-2, 15]范围内
    # 使用sigmoid-like映射归一化
    normalized = max(0.0, min(10.0, 5.0 + v17_raw * 0.4))

    return round(normalized, 2)

# 全局市场状态（启动时检测一次）
_market_state = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), 'daily_recommender.log'),
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger(__name__)

# 候选股数量：筛选后取前N只做新闻分析
TOP_N_CANDIDATES = 15
# 最终推荐数量
RECOMMEND_COUNT = 3
# 同行业最多推荐几只
MAX_SAME_INDUSTRY = 2


def calculate_total_score(stock: Dict, weights: Dict = None) -> float:
    """计算综合评分（支持动态权重，基本面纳入新闻维度，Beta调整）"""
    if weights is None:
        weights = _market_state['weights'] if _market_state else {
            'technical': 0.45, 'chip': 0.20, 'sector': 0.10, 'news': 0.25
        }
    technical = stock.get('short_term_score', 5.0)
    chip = stock.get('chip_score', 5.0)
    sector = stock.get('hot_sector_score', 5.0)
    news = stock.get('sentiment_score', 5.0)
    # 基本面分数纳入：与新闻情绪加权混合（新闻60% + 基本面40%）
    fundamental = stock.get('long_term_score', 5.0)
    news_fundamental = news * 0.6 + fundamental * 0.4

    score = (
        technical * weights['technical'] +
        chip * weights['chip'] +
        sector * weights['sector'] +
        news_fundamental * weights['news']
    )

    # Beta调整：熊市惩罚高Beta，奖励低Beta
    beta = stock.get('beta', 1.0)
    risk_level = _market_state.get('risk_level', 3) if _market_state else 3
    if risk_level >= 4:
        if beta > 1.5:
            score *= 0.8
        elif beta > 1.2:
            score *= 0.9
        elif beta < 0.5:
            score *= 1.2
    elif risk_level <= 2:
        # 牛市：高Beta可以适当加分
        if 1.0 < beta < 1.5:
            score *= 1.05

    return round(score, 2)


def generate_recommendation_reason(stock: Dict) -> str:
    """根据评分数据生成推荐理由"""
    reasons = []

    technical = stock.get('short_term_score', 5.0)
    chip = stock.get('chip_score', 5.0)
    sector = stock.get('hot_sector_score', 5.0)
    news_score = stock.get('sentiment_score', 5.0)
    sentiment = stock.get('sentiment', '中性')
    market_cap = stock.get('market_cap', 0)
    turnover = stock.get('turnover_rate', 0)
    industry = stock.get('industry', '未知')
    matched_sector = stock.get('matched_sector', '')

    # 技术面
    if technical >= 7.0:
        reasons.append(f"技术面强势（{technical:.1f}分），短期趋势向好")
    elif technical >= 5.0:
        reasons.append(f"技术面中性偏好（{technical:.1f}分）")

    # 筹码面
    if chip >= 7.0:
        reasons.append(f"筹码集中度较高（{chip:.1f}分），有主力吸筹迹象")
    elif chip >= 5.0:
        reasons.append(f"筹码分布较为合理（{chip:.1f}分）")

    # 板块热度
    if sector >= 7.0:
        sector_name = matched_sector if matched_sector else industry
        reasons.append(f"所属{sector_name}板块热度较高（{sector:.1f}分）")

    # 新闻情绪
    if news_score >= 7.0 and sentiment == '利好':
        reasons.append(f"近期有利好消息催化（{news_score:.1f}分）")
    elif news_score >= 6.0:
        reasons.append(f"消息面偏正面（{news_score:.1f}分）")

    # 小盘优势
    if market_cap > 0 and market_cap < 50:
        reasons.append(f"市值仅{market_cap:.1f}亿，弹性空间大")
    elif market_cap > 0:
        reasons.append(f"市值{market_cap:.1f}亿，属于小盘股")

    # 换手率
    if 3.0 <= turnover <= 8.0:
        reasons.append(f"换手率{turnover:.1f}%，交投活跃且健康")

    # 增强评分维度
    quarterly_score = stock.get('quarterly_score', 5.0)
    eps_score = stock.get('eps_score', 5.0)
    analyst_score = stock.get('analyst_score', 5.0)

    if quarterly_score > 7:
        profit_change = stock.get('profit_yoy_change', '')
        change_info = f"（净利润同比+{profit_change}%）" if profit_change else ""
        reasons.append(f"近期业绩亮眼{change_info}")
    if eps_score > 7:
        eps_val = stock.get('eps', '')
        eps_info = f"{eps_val}元，" if eps_val else ""
        reasons.append(f"每股收益{eps_info}盈利能力强")
    if analyst_score >= 8:
        reasons.append("多家机构给予'买入'评级")
    if analyst_score <= 2:
        reasons.append("⚠️ 分析师评级偏低，需谨慎")

    # 资金流向维度
    fund_flow_score = stock.get('fund_flow_score', 5.0)
    if fund_flow_score >= 7.5:
        reasons.append(f"主力资金持续流入（{fund_flow_score:.1f}分），资金面看好")
    elif fund_flow_score >= 6.0:
        reasons.append(f"资金面偏好（{fund_flow_score:.1f}分）")
    elif fund_flow_score <= 2.5:
        reasons.append(f"⚠️ 主力资金持续流出（{fund_flow_score:.1f}分），注意风险")

    # 龙虎榜维度
    lhb_score = stock.get('lhb_score', 5.0)
    lhb_raw = stock.get('lhb_raw_data')
    if lhb_score >= 7.5:
        inst_info = "，含机构买入" if lhb_raw and lhb_raw.get('has_institutional_buy') else ""
        reasons.append(f"近期登上龙虎榜{inst_info}（{lhb_score:.1f}分）")
    elif lhb_score >= 6.0:
        reasons.append(f"龙虎榜数据偏正面（{lhb_score:.1f}分）")

    if not reasons:
        reasons.append("综合评分在候选股中排名第一，各维度表现均衡")

    return "；".join(reasons) + "。"


def build_recommendation(stock: Dict) -> Dict:
    """构建推荐结果数据（用于邮件发送）"""
    total_score = calculate_total_score(stock)
    reason = generate_recommendation_reason(stock)
    today = datetime.now().strftime('%Y-%m-%d')

    sentiment_reason = stock.get('sentiment_reason', '暂无新闻分析')
    news_count = stock.get('news_count', 0)
    if news_count > 0:
        sentiment_reason += f"（分析了{news_count}条近期新闻）"

    # V17评分信息
    v17_score = stock.get('v17_score')
    risk_level = _market_state.get('risk_level', 3) if _market_state else 3
    v17_params = get_v17_params_for_risk(risk_level)

    return {
        "date": today,
        "stock_code": stock.get('code', ''),
        "stock_name": stock.get('name', ''),
        "total_score": stock.get('total_score', total_score),
        "technical_score": stock.get('short_term_score', 0),
        "chip_score": stock.get('chip_score', 0),
        "sector_score": stock.get('hot_sector_score', 0),
        "news_score": stock.get('sentiment_score', 5.0),
        "news_sentiment": stock.get('sentiment', '中性'),
        "news_reason": sentiment_reason,
        "market_cap": f"{stock.get('market_cap', 0):.1f}亿",
        "industry": stock.get('industry', '未知'),
        "sector_name": stock.get('matched_sector', stock.get('industry', '未知')),
        "recent_gain_20d": f"{stock.get('recent_gain', 0):+.1f}%",
        "recommendation_reason": reason,
        "quarterly_score": stock.get('quarterly_score'),
        "eps_score": stock.get('eps_score'),
        "sector_enhanced_score": stock.get('sector_enhanced_score'),
        "analyst_score": stock.get('analyst_score'),
        "enhanced_total_score": stock.get('enhanced_total_score'),
        # 新因子维度（资金流向 + 龙虎榜）
        "fund_flow_score": stock.get('fund_flow_score'),
        "lhb_score": stock.get('lhb_score'),
        # V17参数信息
        "v17_score": v17_score,
        "v17_used": v17_score is not None,
        "v17_risk_level": risk_level,
        "v17_param_group": 'r2' if risk_level <= 2 else ('r3' if risk_level == 3 else 'r45'),
    }


def run_daily_recommendation() -> Optional[Dict]:
    """执行完整的每日推荐流程"""
    logger.info("=" * 60)
    logger.info("每日潜力股推荐引擎启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    global _market_state
    logger.info("=" * 60)

    # ---- 第0步：检测市场状态 ----
    logger.info("[步骤0] 检测市场状态...")
    _market_state = detect_market_state()
    logger.info(_market_state['description'])
    w = _market_state['weights']
    logger.info(f"使用权重: 技术{w['technical']} + 筹码{w['chip']} + 板块{w['sector']} + 新闻{w['news']}")

    # ---- 第1步：筛选潜力股 ----
    logger.info("[步骤1] 筛选潜力股...")
    screener = StockScreener(risk_level=_market_state.get('risk_level', 3))
    candidates = screener.screen()

    if not candidates:
        logger.error("筛选结果为空，无法生成推荐")
        return None

    logger.info(f"筛选通过 {len(candidates)} 只潜力股")

    # 黑名单过滤
    pre_count = len(candidates)
    candidates = filter_blacklist(candidates)
    if len(candidates) < pre_count:
        logger.info(f"黑名单过滤: {pre_count} → {len(candidates)} 只")

    if not candidates:
        logger.error("黑名单过滤后无候选股")
        return None

    # 取前N只做深度分析
    top_candidates = candidates[:TOP_N_CANDIDATES]
    logger.info(f"取评分前 {len(top_candidates)} 只候选股:")
    for i, s in enumerate(top_candidates, 1):
        logger.info(f"  {i}. {s['code']} {s['name']} "
                     f"(技术:{s.get('short_term_score', 0):.1f} "
                     f"筹码:{s.get('chip_score', 0):.1f} "
                     f"热度:{s.get('hot_sector_score', 0):.1f} "
                     f"基本面:{s.get('long_term_score', 0):.1f})")

    # ---- 第1.5步：轻量新闻过滤（排除重大利空） ----
    logger.info("[步骤1.5] 轻量新闻过滤...")
    try:
        analyzer = NewsAnalyzer()
        pre_filtered = []
        for stock in top_candidates:
            quick = analyzer.quick_check(stock.get('code', ''), stock.get('name', ''))
            if quick and quick.get('blocked', False):
                logger.info(f"  过滤: {stock['code']} {stock['name']} - {quick.get('reason', '重大利空')}")
            else:
                pre_filtered.append(stock)
        if pre_filtered:
            top_candidates = pre_filtered
            logger.info(f"过滤后剩余 {len(top_candidates)} 只")
        else:
            logger.info("全部被过滤，保留原始候选")
    except Exception as e:
        logger.info(f"轻量过滤跳过: {e}")

    # ---- 第2步：新闻情绪分析 ----
    logger.info(f"[步骤2] 分析 {len(top_candidates)} 只候选股的新闻情绪...")
    analyzer = NewsAnalyzer()
    analyzed_stocks = analyzer.batch_analyze(top_candidates)

    # ---- 第3步：综合评分排序 ----
    risk_level = _market_state.get('risk_level', 3) if _market_state else 3
    v19_available = bool(get_v17_params_for_risk(risk_level))
    if v19_available:
        logger.info(f"[步骤3] 使用V19 Optuna参数评分 (Risk={risk_level})...")
    else:
        logger.info("[步骤3] V19参数不可用，使用原评分系统...")

    for stock in analyzed_stocks:
        # 先用原评分系统作为基础分
        stock['total_score'] = calculate_total_score(stock)
        # 用增强评分系统补充数据（获取季度盈利、EPS、分析师评级等）
        try:
            enriched = enrich_stock_data(stock)
            enhanced_result = enriched.get('enhanced_total_score', {})
            if isinstance(enhanced_result, dict):
                stock['enhanced_total_score'] = enhanced_result.get('total_score', stock['total_score'])
                # 把各维度分数也写回stock
                for key in ['quarterly_score', 'eps_score', 'sector_enhanced_score', 'analyst_score']:
                    if key in enhanced_result:
                        stock[key] = enhanced_result[key]
            else:
                stock['enhanced_total_score'] = enhanced_result
        except Exception as e:
            logger.warning(f"增强评分失败 {stock.get('code','')}: {e}，使用原评分")

        # 如果V19参数可用，用V19评分替代总分
        if v19_available:
            try:
                v19_score = score_with_v17_params(stock, risk_level)
                stock['v17_score'] = v19_score  # 保持字段名兼容
                stock['total_score'] = v19_score  # 使用V19评分作为最终排序依据
            except Exception as e:
                logger.warning(f"V19评分失败 {stock.get('code','')}: {e}，使用增强评分")
                stock['total_score'] = stock.get('enhanced_total_score', stock['total_score'])
        else:
            # V19不可用时，使用增强评分
            stock['total_score'] = stock.get('enhanced_total_score', stock['total_score'])

    analyzed_stocks.sort(key=lambda x: x['total_score'], reverse=True)

    score_mode = "V19" if v19_available else "原评分"
    logger.info(f"综合评分排名 (模式: {score_mode}, Risk={risk_level}):")
    for i, s in enumerate(analyzed_stocks[:5], 1):
        v17_info = f" V17:{s.get('v17_score', 'N/A')}" if 'v17_score' in s else ""
        logger.info(f"  {i}. {s['code']} {s['name']} "
                     f"综合:{s['total_score']:.2f}{v17_info} "
                     f"(技术:{s.get('short_term_score', 0):.1f} "
                     f"筹码:{s.get('chip_score', 0):.1f} "
                     f"热度:{s.get('hot_sector_score', 0):.1f} "
                     f"新闻:{s.get('sentiment_score', 5.0):.1f} "
                     f"盈利:{s.get('quarterly_score', 5.0):.1f} "
                     f"EPS:{s.get('eps_score', 5.0):.1f} "
                     f"评级:{s.get('analyst_score', 5.0):.1f} "
                     f"资金:{s.get('fund_flow_score', 5.0):.1f} "
                     f"龙虎:{s.get('lhb_score', 5.0):.1f})")

    # ---- 第4步：选出TOP N，行业分散 ----
    top_picks = []
    industry_count = {}
    for stock in analyzed_stocks:
        if len(top_picks) >= RECOMMEND_COUNT:
            break
        industry = stock.get('industry', stock.get('matched_sector', '未知'))
        # "未知"行业放宽限制（避免大量股票因无行业标签被过滤）
        max_for_industry = RECOMMEND_COUNT if industry in ('未知', 'unknown', '') else MAX_SAME_INDUSTRY
        if industry_count.get(industry, 0) >= max_for_industry:
            logger.info(f"  跳过 {stock['code']} {stock['name']} ({industry}行业已达上限)")
            continue
        industry_count[industry] = industry_count.get(industry, 0) + 1
        top_picks.append(stock)

    recommendations = [build_recommendation(s) for s in top_picks]

    logger.info("=" * 60)
    logger.info(f"今日推荐 TOP {len(recommendations)} 只:")
    for i, rec in enumerate(recommendations, 1):
        logger.info(f"  {i}. {rec['stock_name']}({rec['stock_code']}) 综合评分:{rec['total_score']}")
        logger.info(f"     理由: {rec['recommendation_reason']}")
    logger.info(f"市场状态: {_market_state['description']}")
    logger.info("=" * 60)

    # ---- 第5步：发送邮件 ----
    logger.info("[步骤5] 发送推荐邮件...")
    notifier = EmailNotifier()
    # 逐只发送邮件
    for i, rec in enumerate(recommendations):
        success = notifier.send_recommendation(rec)
        if success:
            logger.info(f"  推荐{i+1}邮件发送成功: {rec['stock_name']}")
        else:
            logger.error(f"  推荐{i+1}邮件发送失败: {rec['stock_name']}")

    # ---- 保存推荐记录 ----
    save_recommendation_record(recommendations, analyzed_stocks)

    return recommendations


def save_recommendation_record(recommendations: list, all_candidates: List[Dict]):
    """保存推荐记录到本地JSON文件"""
    record_dir = os.path.join(os.path.dirname(__file__), 'recommendation_history')
    os.makedirs(record_dir, exist_ok=True)

    today = datetime.now().strftime('%Y%m%d')
    filepath = os.path.join(record_dir, f'recommendation_{today}.json')

    record = {
        "date": recommendations[0]["date"] if recommendations else "",
        "market_state": _market_state['description'] if _market_state else "",
        "v17_integration": {
            "enabled": any(r.get('v17_used', False) for r in recommendations),
            "param_group": recommendations[0].get('v17_param_group', '') if recommendations else '',
            "risk_level": recommendations[0].get('v17_risk_level', 3) if recommendations else 3,
        },
        "recommended": recommendations,
        "candidates": [
            {
                "code": s.get('code', ''),
                "name": s.get('name', ''),
                "total_score": s.get('total_score', 0),
                "v17_score": s.get('v17_score'),
                "sentiment": s.get('sentiment', '中性'),
                "sentiment_score": s.get('sentiment_score', 5.0),
                "quarterly_score": s.get('quarterly_score'),
                "eps_score": s.get('eps_score'),
                "sector_enhanced_score": s.get('sector_enhanced_score'),
                "analyst_score": s.get('analyst_score'),
                "enhanced_total_score": s.get('enhanced_total_score'),
                "fund_flow_score": s.get('fund_flow_score'),
                "lhb_score": s.get('lhb_score'),
            }
            for s in all_candidates[:10]
        ]
    }

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"推荐记录已保存: {filepath}")
    except Exception as e:
        logger.error(f"保存推荐记录失败: {e}")


if __name__ == '__main__':
    try:
        result = run_daily_recommendation()
        if result:
            print(f"\n今日推荐 TOP {len(result)} 只:")
            for i, r in enumerate(result, 1):
                print(f"  {i}. {r['stock_name']}({r['stock_code']}) 综合评分:{r['total_score']}/10")
            print(f"推荐邮件已发送到 {RECEIVER_EMAIL}")
        else:
            print("\n今日未能生成推荐，请查看日志了解详情")
            sys.exit(1)
    except Exception as e:
        logger.exception(f"推荐引擎运行失败: {e}")
        # 尝试发送错误通知
        try:
            notifier = EmailNotifier()
            notifier.send_error_notification(str(e))
        except Exception:
            pass
        sys.exit(1)

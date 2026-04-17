#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
V4 策略: 市场环境感知 + Beta防御 + 相对强度 + Blacklist

多因子权重模型 + 技术特征 (Beta/RSI/MACD/相对强度)
市场环境分策略: 牛市追涨 / 震荡均衡 / 熊市防御
安全阀机制：过滤 *ST/退市风险、负市盈率、亏损股
"""
import csv
import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict


# ---------------------------------------------------------------------------
# 安全阀：加载财务与状态数据，用于前置过滤
# ---------------------------------------------------------------------------

def load_comprehensive_data(data_dir):
    """
    加载 comprehensive_stock_data（主文件 + part 分片），
    返回 {code: stock_data_dict} 的合并字典。
    """
    all_data = {}

    # 1. 主文件
    comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')
    if os.path.exists(comp_file):
        try:
            with open(comp_file, 'r', encoding='utf-8') as f:
                comp = json.load(f)
            for code, data in comp.get('stocks', {}).items():
                all_data[code] = data
        except Exception as e:
            print(f'[WARN] 加载 comprehensive_stock_data.json 失败: {e}')

    # 2. 分片文件
    part_files = sorted(
        f for f in os.listdir(data_dir)
        if f.startswith('comprehensive_stock_data_part_') and f.endswith('.json')
    )
    for pf in part_files:
        try:
            with open(os.path.join(data_dir, pf), 'r', encoding='utf-8') as f:
                part = json.load(f)
            stocks_dict = part.get('stocks', part)
            if isinstance(stocks_dict, dict):
                for code, data in stocks_dict.items():
                    if isinstance(data, dict) and ('financial_data' in data or 'basic_info' in data):
                        all_data[code] = data
        except Exception:
            continue

    return all_data


def load_st_stocks(data_dir):
    """从 stock_status_cache.json 加载 *ST / 退市风险股票集合。"""
    st_set = set()
    status_file = os.path.join(data_dir, 'stock_status_cache.json')
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            st_set = set(status.get('st_stocks', []))
            st_set |= set(status.get('delisted_stocks', []))
        except Exception as e:
            print(f'[WARN] 加载 stock_status_cache.json 失败: {e}')
    return st_set


def is_stock_name_st(name):
    """通过股票名称判断是否为 ST / *ST / 退市相关。"""
    if not name:
        return False
    name_upper = name.upper()
    return any(tag in name_upper for tag in ['*ST', 'ST', '退市'])


def safety_filter(code, name, comprehensive_data, st_stocks):
    """
    安全阀前置过滤。返回 (通过, 原因) 元组。
    过滤规则：
      1. *ST / 退市风险警告
      2. 市盈率为负（意味着最近年度净利润为负）
      3. 股票名称含 ST / 退市标记
    """
    # 规则 1: ST / 退市状态缓存
    if code in st_stocks:
        return False, '退市风险警告（*ST）'

    # 规则 2: 股票名称包含 ST / 退市标记
    if is_stock_name_st(name):
        return False, '股票名称含退市风险标记'

    # 规则 3: 财务数据校验（市盈率为负 → 净利润为负）
    if code in comprehensive_data:
        fin = comprehensive_data[code].get('financial_data', {})
        pe = fin.get('pe_ratio')
        if pe is not None and pe < 0:
            return False, f'市盈率为负({pe:.2f})，最近年报亏损'

    return True, ''


# ---------------------------------------------------------------------------
# 风险等级与风险提示
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 风险评估阈值常量
# ---------------------------------------------------------------------------
EXTREME_PE_THRESHOLD = 100   # 市盈率极端偏高
HIGH_PE_THRESHOLD = 50       # 市盈率偏高
HIGH_PB_THRESHOLD = 10       # 市净率偏高


def assess_risk_level(stock, comprehensive_data):
    """
    评估单只股票的风险等级与风险提示。

    Returns:
        (risk_level, risk_warnings): 风险等级('高'/'中'/'低')，风险提示列表
    """
    warnings = []
    risk_score = 0  # 累加风险分值，越高风险越大

    code = stock.get('code', '')
    tech = stock.get('tech', 5.0)
    fund = stock.get('fund', 5.0)
    chip = stock.get('chip', 5.0)
    sector = stock.get('hot_sector', 5.0)

    # 1. 技术面风险
    if tech < 4.0:
        warnings.append('技术面评分偏低，短期走势疲弱')
        risk_score += 2
    elif tech < 5.0:
        risk_score += 1

    # 2. 基本面风险
    if fund < 4.0:
        warnings.append('基本面评分较低，基本面支撑不足')
        risk_score += 2
    elif fund < 5.0:
        risk_score += 1

    # 3. 筹码面风险
    if chip < 4.0:
        warnings.append('筹码集中度偏低，资金分散')
        risk_score += 2
    elif chip < 5.0:
        risk_score += 1

    # 4. 财务数据校验（若有）
    if code in comprehensive_data:
        fin = comprehensive_data[code].get('financial_data', {})
        pe = fin.get('pe_ratio')
        pb = fin.get('pb_ratio')

        if pe is not None:
            if pe > EXTREME_PE_THRESHOLD:
                warnings.append(f'市盈率偏高({pe:.1f})，估值泡沫风险')
                risk_score += 2
            elif pe > HIGH_PE_THRESHOLD:
                warnings.append(f'市盈率较高({pe:.1f})，需关注估值回调')
                risk_score += 1

        if pb is not None and pb > HIGH_PB_THRESHOLD:
            warnings.append(f'市净率偏高({pb:.1f})，注意估值风险')
            risk_score += 1

        # 净利润增长为负
        npg = fin.get('net_profit_growth')
        if npg is not None and npg < 0:
            warnings.append(f'净利润同比下滑({npg:.1f}%)，需警惕财报季波动')
            risk_score += 2

    # 5. 板块热度过低
    if sector < 4.0:
        warnings.append('所属板块近期表现低迷')
        risk_score += 1

    # 判定风险等级
    if risk_score >= 5:
        level = '高'
    elif risk_score >= 2:
        level = '中'
    else:
        level = '低'

    if not warnings:
        warnings.append('暂无明显风险')

    return level, warnings


def generate_recommendation_reason(stock):
    """
    根据各维度评分生成推荐理由与选股逻辑理论依据。

    Returns:
        (reason, theory): 推荐理由字符串，理论依据字符串
    """
    tech = stock.get('tech', 5.0)
    fund = stock.get('fund', 5.0)
    chip = stock.get('chip', 5.0)
    sector = stock.get('hot_sector', 5.0)

    reasons = []
    theories = []

    # 技术面
    if tech >= 7.0:
        reasons.append('技术面强势')
        theories.append('均线多头排列')
    elif tech >= 5.5:
        reasons.append('技术面良好')
        theories.append('短期趋势向上')

    # 基本面
    if fund >= 7.0:
        reasons.append('基本面优秀')
        theories.append('低估值修复')
    elif fund >= 5.5:
        reasons.append('基本面稳健')
        theories.append('财务健康')

    # 筹码面
    if chip >= 7.0:
        reasons.append('筹码高度集中')
        theories.append('主力控盘明显')
    elif chip >= 5.5:
        reasons.append('筹码结构良好')
        theories.append('资金流向正面')

    # 板块热度
    if sector >= 7.0:
        reasons.append('板块热度高')
        theories.append('行业景气度上行')
    elif sector >= 5.5:
        reasons.append('板块有一定热度')
        theories.append('行业轮动受益')

    reason_str = '；'.join(reasons) if reasons else '综合评分靠前'
    theory_str = ' + '.join(theories) if theories else '多因子综合评分'

    return reason_str, theory_str


# ---------------------------------------------------------------------------
# 综合评分
# ---------------------------------------------------------------------------

def calculate_weighted_score(tech_score, fund_score, chip_score, sector_trend_score,
                             tech_weight, fund_weight, chip_weight, sector_trend_weight):
    """
    计算加权综合评分
    多因子权重模型：技术形态 + 财务健康度 + 资金流向 + 行业热度
    所有评分维度统一为1-10分范围

    Args:
        tech_score: 技术形态评分 (1-10)
        fund_score: 财务健康度评分 (1-10)
        chip_score: 资金流向评分 (1-10)
        sector_trend_score: 行业热度评分 (1-10)
        tech_weight: 技术形态权重
        fund_weight: 财务健康度权重
        chip_weight: 资金流向权重
        sector_trend_weight: 行业热度权重

    Returns:
        综合评分 (1-10)
    """
    try:
        # 确保分数在合理范围内（所有维度统一为1-10）
        tech_score = max(1.0, min(10.0, float(tech_score)))
        fund_score = max(1.0, min(10.0, float(fund_score)))
        chip_score = max(1.0, min(10.0, float(chip_score)))
        sector_trend_score = max(1.0, min(10.0, float(sector_trend_score)))

        # 归一化权重
        total_weight = tech_weight + fund_weight + chip_weight + sector_trend_weight
        if total_weight > 0:
            tech_weight /= total_weight
            fund_weight /= total_weight
            chip_weight /= total_weight
            sector_trend_weight /= total_weight
        else:
            return 5.0

        # 计算加权评分
        score = (tech_score * tech_weight +
                fund_score * fund_weight +
                chip_score * chip_weight +
                sector_trend_score * sector_trend_weight)

        score = max(1.0, min(10.0, score))

        return round(score, 2)
    except Exception as e:
        print(f"评分计算错误: {e}")
        return 5.0


def analyze_sector_trend_with_ai(industry, stocks_in_sector):
    """
    使用AI大模型分析板块未来趋势

    Args:
        industry: 板块/行业名称
        stocks_in_sector: 该板块内的股票列表

    Returns:
        板块趋势评分 (1-10) 和 简要分析
    """
    try:
        if not stocks_in_sector:
            return 5.0, "该板块股票数据不足"

        avg_tech = sum(s.get('short_term_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)
        avg_fund = sum(s.get('long_term_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)
        avg_chip = sum(s.get('chip_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)

        trend_score = (avg_tech + avg_fund + avg_chip) / 3

        if trend_score >= 7:
            analysis = f"{industry}板块表现强劲，技术面、基本面、筹码面均较优，未来趋势看好"
        elif trend_score >= 6:
            analysis = f"{industry}板块表现良好，各方面评分较为均衡，未来趋势积极"
        elif trend_score >= 5:
            analysis = f"{industry}板块表现一般，部分指标有待改善，需谨慎观察"
        else:
            analysis = f"{industry}板块表现较弱，建议谨慎观望"

        return round(trend_score, 2), analysis
    except Exception as e:
        return 5.0, f"板块分析失败: {str(e)}"


def get_sector_stocks(stocks_data, industry):
    """获取指定板块的股票列表"""
    return [data for code, data in stocks_data.items()
            if data.get('industry', '') == industry]


def select_diversified_top_n(scored_stocks, n=10, max_per_sector=2, min_tech_score=3.0):
    """
    选择分散化的TOP N推荐股票
    避免同一板块/行业过度集中

    Args:
        scored_stocks: 已排序的股票列表（按评分从高到低）
        n: 需要选择的股票数量
        max_per_sector: 每个板块/行业最多选择的股票数
        min_tech_score: 技术面评分最低门槛（过滤技术面太差的股票）

    Returns:
        分散化的TOP N股票列表
    """
    selected = []
    sector_count = {}

    for stock in scored_stocks:
        if len(selected) >= n:
            break

        # 过滤掉技术面评分过低或失败的股票（-10为分析失败标记）
        if stock.get('tech', 0) < min_tech_score or stock.get('fund', 0) <= 0:
            continue

        industry = stock.get('industry', '未知')
        matched_sector = stock.get('matched_sector', '未知')

        group_key = matched_sector if matched_sector and matched_sector != '未知' else industry

        current_count = sector_count.get(group_key, 0)
        if current_count >= max_per_sector:
            continue

        selected.append(stock)
        sector_count[group_key] = current_count + 1

    return selected


# ---------------------------------------------------------------------------
# V4 策略: 市场环境感知 + Beta防御
# ---------------------------------------------------------------------------

DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']


def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)


def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


def load_kline_data(data_dir):
    """Load 6-month K-line data for feature calculation"""
    kline_cache = os.path.join(data_dir, 'kline_cache')
    kline_file = os.path.join(kline_cache, 'kline_6m_2025-10-01_2026-04-07.json')
    
    kline = {}
    if os.path.exists(kline_file):
        with open(kline_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        for code, records in raw.items():
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            df = df.sort_values('date')
            clean = code.replace('sh.', '').replace('sz.', '')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            kline[clean] = df
        print(f'  K-line loaded: {len(kline)} stocks')
    else:
        print(f'  [WARN] K-line file not found: {kline_file}')
    
    return kline


def load_index_data(data_dir):
    """Load index data for market regime detection"""
    kline_cache = os.path.join(data_dir, 'kline_cache')
    idx_file = os.path.join(kline_cache, 'index_6m_2025-10-08_2026-04-07.json')
    
    if not os.path.exists(idx_file):
        print(f'  [WARN] Index file not found')
        return None
    
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    n = len(raw['date'])
    records = []
    for i in range(n):
        key = str(i)
        try:
            ts = raw['date'][key]
            if isinstance(ts, (int, float)):
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d')
            else:
                ds = str(ts)
            records.append({'date': ds, 'close': float(raw['close'][key])})
        except:
            continue
    
    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df = df.dropna(subset=['close']).sort_values('date')
    print(f'  Index loaded: {len(df)} days')
    return df


def detect_market_state(index_df):
    """Detect current market state: regime, risk_level"""
    if index_df is None or len(index_df) < 20:
        return 'range', 3, 'normal'
    
    closes = index_df['close'].values
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]
    
    # Regime
    if current > ma20 * 1.02 and ma5 > ma20:
        regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20:
        regime = 'bear'
    else:
        regime = 'range'
    
    # Volatility
    if n >= 10:
        idx_rets = np.diff(closes[-10:]) / closes[-10:-1] * 100
        idx_vol = np.std(idx_rets)
        vol_state = 'high' if idx_vol > 1.5 else ('normal' if idx_vol > 0.8 else 'low')
    else:
        vol_state = 'normal'
    
    # Risk level
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
    
    return regime, risk, vol_state


def calc_stock_features(df):
    """Calculate technical features for a stock from its K-line DataFrame"""
    if df is None or len(df) < 20:
        return None
    
    c = df['close'].values
    h = df['high'].values if 'high' in df.columns else c
    lo = df['low'].values if 'low' in df.columns else c
    v = df['volume'].values
    turn = df['turn'].values if 'turn' in df.columns else np.ones(len(c))
    pct = df['pctChg'].values if 'pctChg' in df.columns else np.zeros(len(c))
    n = len(c)
    
    f = {}
    
    # Returns
    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0
    
    # MA
    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)
    f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    
    # RSI
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)
    
    # Volatility
    if n >= 6:
        f['vol5'] = np.std(np.diff(c[-6:]) / c[-6:-1]) * 100
    else:
        f['vol5'] = 2
    
    # Volume
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    
    # Turnover
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_ratio'] = turn5 / max(turn10, 0.01)
    else:
        f['turn_ratio'] = 1.0
    
    # Price position
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100
    
    # pctChg
    f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
    f['pct_3d_sum'] = float(np.nansum(pct[-3:])) if n >= 3 else 0
    
    # Mean reversion
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0
    
    # Defaults (filled by caller)
    f['beta'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0
    
    return f


def compute_beta_and_rs(kline, index_df, code):
    """Compute beta and relative strength for a stock vs index"""
    if index_df is None or code not in kline:
        return 1.0, 0.0, 0.0
    
    idx_closes = index_df['close'].values
    idx_n = len(idx_closes)
    
    stock_df = kline[code]
    s_closes = stock_df['close'].values
    
    # Relative strength
    rs5, rs3 = 0.0, 0.0
    if idx_n >= 6 and len(s_closes) >= 6:
        idx_ret5 = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100
        s_ret5 = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100
        rs5 = s_ret5 - idx_ret5
    if idx_n >= 4 and len(s_closes) >= 4:
        idx_ret3 = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100
        s_ret3 = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
        rs3 = s_ret3 - idx_ret3
    
    # Beta
    beta = 1.0
    if idx_n >= 22 and len(s_closes) >= 22:
        idx_rets = np.diff(idx_closes[-21:]) / idx_closes[-21:-1] * 100
        s_rets = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
        sr_len = min(len(s_rets), len(idx_rets))
        if sr_len >= 10:
            s_r = s_rets[-sr_len:]
            i_r = idx_rets[-sr_len:]
            idx_var = np.var(i_r)
            if idx_var > 0.001:
                cov = np.cov(s_r, i_r)[0, 1]
                beta = cov / idx_var
    
    return beta, rs5, rs3


def score_stock_v4(f, static_scores, regime, risk, beta, rel_strength, rel_strength_3d):
    """V4 scoring with regime awareness"""
    if f is None:
        return -999, 'none'
    
    # Hard filters
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return -999, 'limit'
    
    # Static scores
    static_score = 0
    industry = 'unknown'
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sector * 0.15) / 10 * 5
        industry = static_scores.get('industry', 'unknown')
    
    # Components
    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    
    vr = f.get('vol_ratio', 1)
    vol_s = 3 if 1.1 <= vr <= 2.0 else (1 if vr > 2 else 2)
    
    rsi = f.get('rsi', 50)
    rsi_s = 3 if 40 <= rsi <= 60 else (4 if 30 <= rsi < 40 else (2 if 60 < rsi <= 70 else 1))
    
    vol5 = f.get('vol5', 2)
    low_vol_s = 4 if vol5 < 1.5 else (3 if vol5 < 2.5 else (2 if vol5 < 3.5 else 1))
    
    defense_s = low_vol_s
    if is_defensive_industry(industry):
        defense_s += 3
    if is_high_beta_industry(industry):
        defense_s -= 2
    
    if risk >= 4:
        # DEFENSE MODE
        score = (
            momentum_s * 0.02 + trend_s * 0.03 + mr_s * 0.10 +
            vol_s * 0.03 + rsi_s * 0.10 + static_score * 0.15 +
            defense_s * 0.12 + low_vol_s * 0.05 +
            rel_strength * 0.15 + rel_strength_3d * 0.10 +
            (2.0 - min(beta, 2.0)) * 0.12
        )
        if beta > 1.5: score *= 0.4
        elif beta > 1.2: score *= 0.7
        elif beta < 0.5: score *= 1.3
        if f.get('oversold', 0): score *= 1.15
        if f.get('overbought', 0): score *= 0.3
        if is_high_beta_industry(industry): score *= 0.4
        if is_defensive_industry(industry): score *= 1.25
        if rel_strength > 3: score *= 1.3
        if vol5 < 1.5: score *= 1.2
        if f.get('r1', 0) < -5: score *= 0.3
        if f.get('r3', 0) < -8: score *= 0.3
        if f.get('pct_1d', 0) > 7: score *= 0.3
        strategy = 'defense'
    elif risk == 3:
        # BALANCED
        score = (
            momentum_s * 0.12 + trend_s * 0.12 + mr_s * 0.15 +
            vol_s * 0.08 + rsi_s * 0.10 + static_score * 0.18 +
            defense_s * 0.08 + low_vol_s * 0.07 +
            rel_strength * 0.05 + (2.0 - min(beta, 2.0)) * 0.05
        )
        if f.get('oversold', 0): score *= 1.15
        if f.get('overbought', 0): score *= 0.7
        strategy = 'balanced'
    else:
        # MOMENTUM
        score = (
            momentum_s * 0.25 + trend_s * 0.20 + mr_s * 0.05 +
            vol_s * 0.10 + rsi_s * 0.05 + static_score * 0.15 +
            defense_s * 0.05 + low_vol_s * 0.05 +
            rel_strength * 0.05 + (2.0 - min(beta, 2.0)) * 0.05
        )
        if f['r1'] > 5: score *= 0.5
        if f.get('overbought', 0): score *= 0.8
        strategy = 'momentum'
    
    return score, strategy


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    try:
        print('[步骤 3/3] 正在生成短线和长线推荐并导出...\n')

        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

        # ── 加载安全阀所需数据 ──
        print('正在加载财务数据与ST状态（安全阀过滤）...')
        comprehensive_data = load_comprehensive_data(data_dir)
        st_stocks = load_st_stocks(data_dir)
        print(f'  综合数据: {len(comprehensive_data)} 只  |  ST/退市标记: {len(st_stocks)} 只')

        # 查找最新的主板评分文件
        print('正在查找主板基础评分文件...')
        score_files = [f for f in os.listdir(data_dir)
                      if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')]
        if not score_files:
            print('错误：未找到主板评分文件')
            print('请先运行「仅生成主板评分.bat」')
            sys.exit(1)

        latest_file = max(score_files)
        file_path = os.path.join(data_dir, latest_file)
        print(f'使用评分文件: {latest_file}\n')

        # 加载评分数据
        with open(file_path, 'r', encoding='utf-8') as f:
            stocks = json.load(f)

        # ── 安全阀前置过滤 ──
        print('正在执行安全阀过滤（*ST、负PE、亏损股）...')
        filtered_stocks = {}
        filter_reasons = {}
        for code, data in stocks.items():
            name = data.get('name', '')
            passed, reason = safety_filter(code, name, comprehensive_data, st_stocks)
            if passed:
                filtered_stocks[code] = data
            else:
                filter_reasons[code] = reason

        removed = len(stocks) - len(filtered_stocks)
        print(f'  安全阀过滤: {removed} 只被移除，剩余 {len(filtered_stocks)} 只')
        if filter_reasons:
            sample = list(filter_reasons.items())[:5]
            for c, r in sample:
                print(f'    ✖ {c}: {r}')
            if len(filter_reasons) > 5:
                print(f'    ... 还有 {len(filter_reasons) - 5} 只被过滤')
        print()

        # 支持Windows桌面和Linux目录
        desktop_path = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
        os.makedirs(desktop_path, exist_ok=True)

        print('\n正在加载V4策略数据 (K线 + 指数)...')
        kline = load_kline_data(data_dir)
        index_df = load_index_data(data_dir)
        regime, risk_level, vol_state = detect_market_state(index_df)
        print(f'  市场状态: {regime}, 风险等级: R{risk_level}, 波动: {vol_state}')
        strategy_mode = '防御' if risk_level >= 4 else ('均衡' if risk_level == 3 else '追涨')
        print(f'  策略模式: {strategy_mode}\n')

        # ── V4 策略: 选3只股票 ──
        print(f'【V4 {strategy_mode}模式 - 选出TOP3】')

        scored_stocks = []
        for code, data in filtered_stocks.items():
            tech_score = data.get('short_term_score', 5.0)
            fund_score = data.get('long_term_score', 5.0)
            chip_score = data.get('chip_score', 5.0)
            hot_sector_score = data.get('hot_sector_score', 5.0)
            industry = data.get('industry', '未知')
            matched_sector = data.get('matched_sector', '')

            # V4 权重: 技术40% + 财务25% + 资金20% + 热度15%
            base_score = calculate_weighted_score(
                tech_score, fund_score, chip_score, hot_sector_score,
                0.40, 0.25, 0.20, 0.15
            )

            v4_score = base_score
            v4_strategy = 'basic'
            beta, rs5, rs3 = 1.0, 0.0, 0.0
            
            if code in kline and risk_level >= 3:
                feats = calc_stock_features(kline[code])
                beta, rs5, rs3 = compute_beta_and_rs(kline, index_df, code)
                if feats:
                    feats['beta'] = beta
                    feats['rel_strength_5d'] = rs5
                    feats['rel_strength_3d'] = rs3
                    static = {
                        'tech': tech_score, 'fund': fund_score,
                        'chip': chip_score, 'sector': hot_sector_score,
                        'industry': industry
                    }
                    tech_score_v4, v4_strategy = score_stock_v4(
                        feats, static, regime, risk_level, beta, rs5, rs3
                    )
                    if tech_score_v4 != -999:
                        v4_score = tech_score_v4 * 0.6 + base_score * 0.4
            
            scored_stocks.append({
                'code': code,
                'name': data.get('name', 'N/A'),
                'score': round(v4_score, 2),
                'base_score': round(base_score, 2),
                'tech': tech_score,
                'fund': fund_score,
                'chip': chip_score,
                'hot_sector': hot_sector_score,
                'industry': industry,
                'matched_sector': matched_sector or industry,
                'beta': round(beta, 2),
                'rel_strength': round(rs5, 2),
                'v4_strategy': v4_strategy,
            })

        # ── 降权: 无K线数据的股票 (无法做技术验证) ──
        for s in scored_stocks:
            if s['code'] not in kline:
                s['score'] *= 0.60  # 降权40%
                s['v4_strategy'] = 'no_kline'

        # ── 连续推荐去重: 读取上次推荐记录 ──
        last_rec_file = os.path.join(data_dir, 'last_recommendation.json')
        last_rec = set()
        if os.path.exists(last_rec_file):
            try:
                with open(last_rec_file, 'r', encoding='utf-8') as f:
                    lr = json.load(f)
                last_rec = set(lr.get('codes', []))
                last_date = lr.get('date', '')
                today_str = datetime.now().strftime('%Y-%m-%d')
                if last_date == today_str:
                    # 同一天不去重
                    last_rec = set()
                else:
                    print(f'  上次推荐({last_date}): {last_rec} → 今日去重')
            except:
                pass

        scored_stocks.sort(key=lambda x: x['score'], reverse=True)

        # 排除上次推荐的股票
        if last_rec:
            scored_stocks = [s for s in scored_stocks if s['code'] not in last_rec]

        top3 = select_diversified_top_n(scored_stocks, n=3, max_per_sector=1, min_tech_score=3.0)

        # 为每只计算风险等级与推荐理由
        for stock in top3:
            risk_lv, risk_warnings = assess_risk_level(stock, comprehensive_data)
            reason, theory = generate_recommendation_reason(stock)
            stock['risk_level'] = risk_lv
            stock['risk_warnings'] = risk_warnings
            stock['risk_tip'] = '；'.join(risk_warnings)
            stock['reason'] = reason
            stock['theory'] = theory

        # 显示结果
        print(f'  市场: {regime} R{risk_level} | 策略: {strategy_mode}')
        print(f'  TOP3: ', end='')
        for i, stock in enumerate(top3):
            if i > 0:
                print(", ", end='')
            print(f"{stock['code']} {stock['name']}({stock['score']:.2f})", end='')
        print('\n')

        for i, stock in enumerate(top3):
            print(f"  {i+1}. {stock['code']} {stock['name']} "
                  f"评分={stock['score']:.2f} 技术={stock['tech']:.1f} "
                  f"财务={stock['fund']:.1f} 资金={stock['chip']:.1f} "
                  f"行业={stock['industry']}")
            print(f"     推荐: {stock.get('reason', '-')} | 风险: {stock.get('risk_tip', '-')}")
        print()

        # ── 发送邮件 ──
        print('正在发送推荐邮件...')
        try:
            from email_notifier import EmailNotifier
            notifier = EmailNotifier()
            
            today = datetime.now().strftime('%Y-%m-%d')
            strategy_label = f"{strategy_mode}模式(R{risk_level})"
            
            # 构建邮件HTML
            stocks_html = ''
            for i, stock in enumerate(top3):
                stock_data = filtered_stocks.get(stock['code'], {})
                sector_change = stock_data.get('sector_change', 0)
                color = '#e74c3c' if stock.get('v4_strategy') == 'defense' else '#3498db'
                stocks_html += f'''
                <div style="padding:20px; border-bottom:1px solid #eee;">
                    <h2 style="color:{color}; margin:0 0 8px 0;">{i+1}. {stock['name']} ({stock['code']})</h2>
                    <p style="color:#666; margin:4px 0;">行业: {stock['industry']} | 策略: {stock.get('v4_strategy','-')} | Beta: {stock.get('beta','-')} | 相对强度: {stock.get('rel_strength','-')}</p>
                    <table style="width:100%; margin:12px 0;">
                        <tr><td><b>综合评分</b></td><td style="font-size:24px; color:{color};">{stock['score']}</td></tr>
                        <tr><td>技术面</td><td>{stock['tech']:.1f}</td></tr>
                        <tr><td>财务面</td><td>{stock['fund']:.1f}</td></tr>
                        <tr><td>资金面</td><td>{stock['chip']:.1f}</td></tr>
                        <tr><td>板块热度</td><td>{stock['hot_sector']:.2f}</td></tr>
                    </table>
                    <p><b>推荐理由:</b> {stock.get('reason','-')}</p>
                    <p><b>风险提示:</b> <span style="color:#e67e22;">{stock.get('risk_tip','-')}</span></p>
                </div>'''
            
            html = f'''<!DOCTYPE html><html><head><meta charset="utf-8">
            <style>body{{font-family:'Microsoft YaHei',sans-serif;background:#f5f5f5;padding:20px;}}
            .container{{max-width:600px;margin:0 auto;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}}
            .header{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:24px;text-align:center;border-radius:12px 12px 0 0;}}
            .disclaimer{{background:#fff3cd;color:#856404;padding:16px;text-align:center;font-size:12px;}}</style></head>
            <body><div class="container">
            <div class="header"><h1>📊 每日TOP3推荐</h1><p>{today} | {strategy_label}</p></div>
            {stocks_html}
            <div class="disclaimer">⚠️ 以上推荐仅供参考，不构成投资建议。投资有风险，入市需谨慎。<br>V4策略 | 回测跑赢指数73.1%(R1-R4)</div>
            </div></body></html>'''
            
            text = f"每日TOP3推荐 ({today}) [{strategy_label}]\n"
            for i, stock in enumerate(top3):
                text += f"\n{i+1}. {stock['name']}({stock['code']}) 评分{stock['score']}\n"
                text += f"   技术={stock['tech']:.1f} 财务={stock['fund']:.1f} 资金={stock['chip']:.1f}\n"
                text += f"   推荐: {stock.get('reason','-')}\n"
                text += f"   风险: {stock.get('risk_tip','-')}\n"
            
            subject = f"📊 TOP3推荐 | {today} | {strategy_label}"
            result = notifier.send_email(subject, html, text)
            if result:
                print('  [OK] 邮件发送成功!')
            else:
                print('  [FAIL] 邮件发送失败，请检查配置')
        except Exception as e:
            print(f'  [WARN] 邮件发送出错: {e}')

        # 保存本次推荐记录(用于明天去重)
        with open(last_rec_file, 'w', encoding='utf-8') as f:
            json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'codes': [s['code'] for s in top3]}, f)

        # 导出CSV备份
        csv_path = os.path.join(desktop_path, '每日TOP3推荐.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['股票代码', '股票名称', '综合评分', '技术', '财务', '资金', '热度', '行业', '策略', '风险等级', '推荐理由', '风险提示'])
            for stock in top3:
                writer.writerow([
                    stock['code'], stock['name'], stock['score'],
                    stock['tech'], stock['fund'], stock['chip'], stock['hot_sector'],
                    stock['industry'], stock.get('v4_strategy','-'),
                    stock['risk_level'], stock.get('reason','-'), stock.get('risk_tip','-')
                ])
        print(f'  [OK] CSV已备份: {csv_path}')

        print('\n' + '='*60)
        print(f'完成! 市场: {regime} R{risk_level} | 策略: {strategy_mode} | 选出 {len(top3)} 只')
        print('='*60)

    except Exception as e:
        print(f'[FAIL] 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

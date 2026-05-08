#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强评分系统 - 集成4个新数据维度到选股评分

新增维度：
1. 季度盈利评分 — 净利润同比增长、扣非净利润增长
2. EPS质量评分 — 每股盈利水平 + 分析师预测对比
3. 板块热度增强评分 — 在原有基础上叠加板块近5日涨幅
4. 分析师评级评分 — 研报买入/增持/中性/减持评级

综合评分权重（含资金流向+龙虎榜）：
- 技术面: 25%
- 筹码面: 8%
- 板块热度(增强): 12%
- 新闻情绪: 8%
- 季度盈利: 15%
- EPS质量: 8%
- 分析师评级: 4%
- 资金流向: 12%
- 龙虎榜: 8%

作者: TradingAgent 算法工程师
日期: 2026-05-06
"""

import os
import sys
import logging
from typing import Dict, Optional

# 禁用系统代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 导入增强数据获取器
from enhanced_data_fetcher import (
    fetch_quarterly_earnings,
    fetch_analyst_forecast,
    fetch_sector_heat,
    fetch_research_rating,
)
# 导入新因子模块（资金流向 + 龙虎榜）
from new_factors import (
    fetch_fund_flow_data,
    score_fund_flow,
    fetch_lhb_data,
    score_lhb,
)

logger = logging.getLogger(__name__)


# ============================================================
# 辅助函数
# ============================================================
def _safe_float(val, default=None):
    """安全转换为float，失败返回default"""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _clamp_score(score: float, low: float = 0.0, high: float = 10.0) -> float:
    """将分数限制在 [low, high] 范围内"""
    return max(low, min(high, score))


# ============================================================
# 1. 季度盈利评分
# ============================================================
def score_quarterly_earnings(data: dict) -> float:
    """
    季度盈利评分 (0-10)

    输入来自 enhanced_data_fetcher.fetch_quarterly_earnings() 返回的dict

    评分规则:
    - 净利润同比增长 > 30%: 9-10分
    - > 20%: 7-9分
    - > 10%: 5-7分
    - > 0%: 3-5分
    - < 0%: 0-3分（亏损扣分重）
    - 扣非净利润增长额外加分(最高+1)
    - data为None时返回5.0
    """
    if data is None:
        return 5.0

    # 净利润同比增长率
    yoy = _safe_float(data.get('net_profit_yoy'))
    if yoy is None:
        return 5.0  # 数据缺失，中性分数

    # 基础分：根据净利润同比增长率
    if yoy > 30:
        # 30%以上：9-10分，线性映射 30->9, 100->10
        base = min(10.0, 9.0 + (yoy - 30) / 70.0)
    elif yoy > 20:
        # 20%-30%：7-9分，线性映射
        base = 7.0 + (yoy - 20) / 10.0 * 2.0
    elif yoy > 10:
        # 10%-20%：5-7分
        base = 5.0 + (yoy - 10) / 10.0 * 2.0
    elif yoy > 0:
        # 0%-10%：3-5分
        base = 3.0 + yoy / 10.0 * 2.0
    else:
        # 负增长：0-3分，跌幅越大分越低
        # yoy 在 -50% 到 0% 之间线性映射
        base = max(0.0, 3.0 + yoy / 50.0 * 3.0)

    # 扣非净利润增长额外加分（最高+1）
    bonus = 0.0
    deducted_yoy = _safe_float(data.get('deducted_net_profit_yoy'))
    if deducted_yoy is not None:
        if deducted_yoy > 20:
            bonus = 1.0
        elif deducted_yoy > 10:
            bonus = 0.7
        elif deducted_yoy > 0:
            bonus = 0.3

    return _clamp_score(round(base + bonus, 2))


# ============================================================
# 2. EPS质量评分
# ============================================================
def score_eps_quality(earnings_data: dict, forecast: dict) -> float:
    """
    每股盈利评分 (0-10)

    earnings_data 来自 fetch_quarterly_earnings, forecast 来自 fetch_analyst_forecast

    评分规则:
    - EPS > 2.0: 8-10分
    - EPS > 1.0: 6-8分
    - EPS > 0.5: 4-6分
    - EPS > 0: 2-4分
    - EPS <= 0: 0分
    - 有分析师预测且预测EPS > 当前EPS: 额外+1
    - data为None时返回5.0
    """
    if earnings_data is None:
        return 5.0

    eps = _safe_float(earnings_data.get('eps'))
    if eps is None:
        return 5.0  # 数据缺失，中性分数

    # 基础分：根据EPS绝对值
    if eps > 2.0:
        # 2.0以上：8-10分，线性映射 2.0->8, 5.0->10
        base = min(10.0, 8.0 + (eps - 2.0) / 3.0 * 2.0)
    elif eps > 1.0:
        # 1.0-2.0：6-8分
        base = 6.0 + (eps - 1.0) / 1.0 * 2.0
    elif eps > 0.5:
        # 0.5-1.0：4-6分
        base = 4.0 + (eps - 0.5) / 0.5 * 2.0
    elif eps > 0:
        # 0-0.5：2-4分
        base = 2.0 + eps / 0.5 * 2.0
    else:
        # EPS <= 0：0分
        base = 0.0

    # 分析师预测加分
    bonus = 0.0
    if forecast is not None:
        forecast_eps = _safe_float(forecast.get('eps_forecast'))
        if forecast_eps is not None and forecast_eps > eps:
            bonus = 1.0  # 分析师预测未来EPS更高，说明增长预期

    return _clamp_score(round(base + bonus, 2))


# ============================================================
# 3. 板块热度增强评分
# ============================================================
def score_sector_heat_enhanced(basic_sector_score: float, enhanced_data: dict) -> float:
    """
    板块热度增强评分 (0-10)

    basic_sector_score 是现有的 hot_sector_score (已经0-10分制)
    enhanced_data 来自 fetch_sector_heat

    评分规则:
    - 基于现有 basic_sector_score
    - 板块近5日涨幅 > 5%: 额外+2
    - 板块近5日涨幅 > 2%: 额外+1
    - enhanced_data为None时直接返回basic_sector_score
    """
    if enhanced_data is None:
        return _clamp_score(basic_sector_score)

    score = basic_sector_score

    # 板块近5日涨幅加分
    change_pct = _safe_float(enhanced_data.get('sector_change_pct'))
    if change_pct is not None:
        if change_pct > 5:
            score += 2.0
        elif change_pct > 2:
            score += 1.0
        # 板块涨幅为负时不额外扣分（基础分已反映）

    return _clamp_score(round(score, 2))


# ============================================================
# 4. 分析师评级评分
# ============================================================
def score_analyst_rating(rating_data: dict) -> float:
    """
    分析师评级评分 (0-10)

    rating_data 来自 fetch_research_rating

    评分规则:
    - 买入: 8分
    - 增持: 6分
    - 中性: 4分
    - 减持/卖出: 1分
    - 无评级: 5分（中性）
    - 研报数 >= 5: 额外+1
    - rating_data为None时返回5.0
    """
    if rating_data is None:
        return 5.0

    # 评级映射
    rating_str = rating_data.get('latest_rating', '')
    if rating_str is None:
        return 5.0

    rating_str = str(rating_str).strip()

    # 标准化评级关键词匹配
    if '买入' in rating_str or '强烈推荐' in rating_str or '推荐' in rating_str:
        base = 8.0
    elif '增持' in rating_str:
        base = 6.0
    elif '中性' in rating_str or '持有' in rating_str:
        base = 4.0
    elif '减持' in rating_str or '卖出' in rating_str:
        base = 1.0
    else:
        # 无法识别的评级，给中性分
        base = 5.0

    # 研报数量加分
    bonus = 0.0
    rating_count = _safe_float(rating_data.get('rating_count'))
    if rating_count is not None and rating_count >= 5:
        bonus = 1.0

    return _clamp_score(round(base + bonus, 2))


# ============================================================
# 5. 增强综合评分
# ============================================================
def calculate_enhanced_total_score(stock: dict, market_state: dict = None) -> dict:
    """
    增强综合评分

    流程:
    1. 调用 enhanced_data_fetcher 获取4个新维度数据
    2. 调用4个评分函数计算分数
    3. 按新权重计算总分:
       - 技术面: 30%
       - 筹码面: 10%
       - 板块热度(增强): 15%
       - 新闻情绪: 10%
       - 季度盈利: 20%
       - EPS质量: 10%
       - 分析师评级: 5%
    4. 返回 dict 包含总分和各维度分数

    关键: 任何数据获取失败，该维度用5.0(中性)，不影响总分
    """
    stock_code = stock.get('code', '')
    industry = stock.get('industry', '') or stock.get('matched_sector', '')

    # ---- 获取现有维度分数（来自 stock_screener 和 news_analyzer）----
    technical_score = stock.get('short_term_score', 5.0)
    chip_score = stock.get('chip_score', 5.0)
    basic_sector_score = stock.get('hot_sector_score', 5.0)
    news_score = stock.get('sentiment_score', 5.0)
    # 基本面分数纳入新闻情绪（与原系统一致：新闻60% + 基本面40%）
    fundamental_score = stock.get('long_term_score', 5.0)
    news_final = news_score * 0.6 + fundamental_score * 0.4

    # ---- 获取增强维度数据（原有4个维度）----
    earnings_data = None
    try:
        earnings_data = fetch_quarterly_earnings(stock_code)
    except Exception as e:
        logger.warning(f"获取季度盈利数据失败 {stock_code}: {e}")

    forecast_data = None
    try:
        forecast_data = fetch_analyst_forecast(stock_code)
    except Exception as e:
        logger.warning(f"获取分析师预测失败 {stock_code}: {e}")

    sector_enhanced_data = None
    if industry:
        try:
            sector_enhanced_data = fetch_sector_heat(industry)
        except Exception as e:
            logger.warning(f"获取板块热度增强数据失败 {industry}: {e}")

    rating_data = None
    try:
        rating_data = fetch_research_rating(stock_code)
    except Exception as e:
        logger.warning(f"获取研报评级失败 {stock_code}: {e}")

    # ---- 获取新因子数据（资金流向 + 龙虎榜）----
    fund_flow_data = None
    try:
        fund_flow_data = fetch_fund_flow_data(stock_code)
    except Exception as e:
        logger.warning(f"获取资金流向数据失败 {stock_code}: {e}")

    lhb_data = None
    try:
        lhb_data = fetch_lhb_data(stock_code)
    except Exception as e:
        logger.warning(f"获取龙虎榜数据失败 {stock_code}: {e}")

    # ---- 计算各维度分数 ----
    quarterly_score = score_quarterly_earnings(earnings_data)
    eps_score = score_eps_quality(earnings_data, forecast_data)
    sector_enhanced_score = score_sector_heat_enhanced(basic_sector_score, sector_enhanced_data)
    analyst_score = score_analyst_rating(rating_data)
    fund_flow_score = score_fund_flow(fund_flow_data)
    lhb_score = score_lhb(lhb_data)

    # ---- 按新权重计算总分（含资金流向+龙虎榜）----
    weights = {
        'technical': 0.25,
        'chip': 0.08,
        'sector_enhanced': 0.12,
        'news': 0.08,
        'quarterly': 0.15,
        'eps': 0.08,
        'analyst': 0.04,
        'fund_flow': 0.12,
        'lhb': 0.08,
    }

    # 如果有市场状态，可以微调权重（预留接口）
    if market_state and 'enhanced_weights' in market_state:
        custom = market_state['enhanced_weights']
        for k, v in custom.items():
            if k in weights:
                weights[k] = v
        # 归一化权重
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in weights.items()}

    total_score = (
        technical_score * weights['technical']
        + chip_score * weights['chip']
        + sector_enhanced_score * weights['sector_enhanced']
        + news_final * weights['news']
        + quarterly_score * weights['quarterly']
        + eps_score * weights['eps']
        + analyst_score * weights['analyst']
        + fund_flow_score * weights['fund_flow']
        + lhb_score * weights['lhb']
    )

    # Beta调整（与原系统一致）
    beta = stock.get('beta', 1.0)
    risk_level = 3
    if market_state and 'risk_level' in market_state:
        risk_level = market_state['risk_level']
    if risk_level >= 4:
        if beta > 1.5:
            total_score *= 0.8
        elif beta > 1.2:
            total_score *= 0.9
        elif beta < 0.5:
            total_score *= 1.2
    elif risk_level <= 2:
        if 1.0 < beta < 1.5:
            total_score *= 1.05

    return {
        'total_score': round(total_score, 2),
        'technical_score': round(technical_score, 2),
        'chip_score': round(chip_score, 2),
        'sector_enhanced_score': round(sector_enhanced_score, 2),
        'news_score': round(news_final, 2),
        'quarterly_score': round(quarterly_score, 2),
        'eps_score': round(eps_score, 2),
        'analyst_score': round(analyst_score, 2),
        'fund_flow_score': round(fund_flow_score, 2),
        'lhb_score': round(lhb_score, 2),
        'weights': weights,
        # 原始数据也一并返回，方便调试
        'raw_data': {
            'earnings': earnings_data,
            'forecast': forecast_data,
            'sector_heat': sector_enhanced_data,
            'rating': rating_data,
            'fund_flow': fund_flow_data,
            'lhb': lhb_data,
        },
    }


# ============================================================
# 6. 数据补充函数
# ============================================================
def enrich_stock_data(stock: dict) -> dict:
    """
    为单只股票补充新维度数据并计算增强评分

    修改stock dict，添加:
    - quarterly_earnings_data
    - analyst_forecast_data
    - sector_heat_enhanced_data
    - research_rating_data
    - quarterly_score
    - eps_score
    - sector_enhanced_score
    - analyst_score
    - enhanced_total_score (包含总分和各维度明细)
    """
    stock_code = stock.get('code', '')
    industry = stock.get('industry', '') or stock.get('matched_sector', '')

    # ---- 获取新维度数据 ----
    earnings_data = None
    try:
        earnings_data = fetch_quarterly_earnings(stock_code)
    except Exception as e:
        logger.warning(f"enrich: 获取季度盈利数据失败 {stock_code}: {e}")

    forecast_data = None
    try:
        forecast_data = fetch_analyst_forecast(stock_code)
    except Exception as e:
        logger.warning(f"enrich: 获取分析师预测失败 {stock_code}: {e}")

    sector_enhanced_data = None
    if industry:
        try:
            sector_enhanced_data = fetch_sector_heat(industry)
        except Exception as e:
            logger.warning(f"enrich: 获取板块热度增强数据失败 {industry}: {e}")

    rating_data = None
    try:
        rating_data = fetch_research_rating(stock_code)
    except Exception as e:
        logger.warning(f"enrich: 获取研报评级失败 {stock_code}: {e}")

    # ---- 获取新因子数据（资金流向 + 龙虎榜）----
    fund_flow_data = None
    try:
        fund_flow_data = fetch_fund_flow_data(stock_code)
    except Exception as e:
        logger.warning(f"enrich: 获取资金流向数据失败 {stock_code}: {e}")

    lhb_data = None
    try:
        lhb_data = fetch_lhb_data(stock_code)
    except Exception as e:
        logger.warning(f"enrich: 获取龙虎榜数据失败 {stock_code}: {e}")

    # ---- 写入原始数据 ----
    stock['quarterly_earnings_data'] = earnings_data
    stock['analyst_forecast_data'] = forecast_data
    stock['sector_heat_enhanced_data'] = sector_enhanced_data
    stock['research_rating_data'] = rating_data
    stock['fund_flow_raw_data'] = fund_flow_data
    stock['lhb_raw_data'] = lhb_data

    # ---- 计算各维度分数 ----
    quarterly_score = score_quarterly_earnings(earnings_data)
    eps_score_val = score_eps_quality(earnings_data, forecast_data)
    basic_sector = stock.get('hot_sector_score', 5.0)
    sector_enhanced = score_sector_heat_enhanced(basic_sector, sector_enhanced_data)
    analyst_score = score_analyst_rating(rating_data)
    fund_flow_score = score_fund_flow(fund_flow_data)
    lhb_score_val = score_lhb(lhb_data)

    # ---- 写入分数 ----
    stock['quarterly_score'] = quarterly_score
    stock['eps_score'] = eps_score_val
    stock['sector_enhanced_score'] = sector_enhanced
    stock['analyst_score'] = analyst_score
    stock['fund_flow_score'] = fund_flow_score
    stock['lhb_score'] = lhb_score_val

    # ---- 计算增强总分 ----
    enhanced_result = calculate_enhanced_total_score(stock)
    stock['enhanced_total_score'] = enhanced_result

    return stock


# ============================================================
# 测试代码
# ============================================================
if __name__ == '__main__':
    import json

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    # 测试用：模拟一只股票的 dict（模拟 stock_screener 的输出）
    test_stock = {
        'code': '000885',
        'name': '城发环境',
        'industry': '环保',
        'matched_sector': '环保',
        'short_term_score': 6.5,   # 技术面
        'chip_score': 5.8,         # 筹码面
        'hot_sector_score': 4.5,   # 板块热度
        'sentiment_score': 5.0,    # 新闻情绪
        'long_term_score': 5.5,    # 基本面
        'market_cap': 60.0,
        'beta': 1.1,
    }

    print("=" * 60)
    print("增强评分系统 - 单独测试各评分函数")
    print("=" * 60)

    # 1. 测试季度盈利评分
    print("\n--- 1. 季度盈利评分 ---")
    earnings = fetch_quarterly_earnings('000885')
    print(f"  原始数据: {json.dumps(earnings, ensure_ascii=False, default=str) if earnings else 'None'}")
    q_score = score_quarterly_earnings(earnings)
    print(f"  评分: {q_score}")

    # 2. 测试EPS质量评分
    print("\n--- 2. EPS质量评分 ---")
    forecast = fetch_analyst_forecast('000885')
    print(f"  盈利数据: {json.dumps(earnings, ensure_ascii=False, default=str) if earnings else 'None'}")
    print(f"  分析师预测: {json.dumps(forecast, ensure_ascii=False, default=str) if forecast else 'None'}")
    eps_s = score_eps_quality(earnings, forecast)
    print(f"  评分: {eps_s}")

    # 3. 测试板块热度增强评分
    print("\n--- 3. 板块热度增强评分 ---")
    sector_data = fetch_sector_heat('环保')
    print(f"  原始数据: {json.dumps(sector_data, ensure_ascii=False, default=str) if sector_data else 'None'}")
    sector_s = score_sector_heat_enhanced(4.5, sector_data)
    print(f"  基础板块分: 4.5 → 增强后: {sector_s}")

    # 4. 测试分析师评级评分
    print("\n--- 4. 分析师评级评分 ---")
    rating = fetch_research_rating('000885')
    print(f"  原始数据: {json.dumps(rating, ensure_ascii=False, default=str) if rating else 'None'}")
    a_score = score_analyst_rating(rating)
    print(f"  评分: {a_score}")

    # 5. 测试None输入（应全部返回5.0）
    print("\n--- 5. None输入测试 ---")
    print(f"  score_quarterly_earnings(None): {score_quarterly_earnings(None)}")
    print(f"  score_eps_quality(None, None): {score_eps_quality(None, None)}")
    print(f"  score_sector_heat_enhanced(5.0, None): {score_sector_heat_enhanced(5.0, None)}")
    print(f"  score_analyst_rating(None): {score_analyst_rating(None)}")

    # 6. 测试增强综合评分
    print("\n" + "=" * 60)
    print("增强综合评分 - calculate_enhanced_total_score()")
    print("=" * 60)
    result = calculate_enhanced_total_score(test_stock)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    # 7. 测试 enrich_stock_data
    print("\n" + "=" * 60)
    print("数据补充 - enrich_stock_data()")
    print("=" * 60)
    import copy
    test_stock_copy = copy.deepcopy(test_stock)
    enriched = enrich_stock_data(test_stock_copy)
    print(f"  增强总分: {enriched['enhanced_total_score']['total_score']}")
    print(f"  季度盈利分: {enriched['quarterly_score']}")
    print(f"  EPS分: {enriched['eps_score']}")
    print(f"  板块增强分: {enriched['sector_enhanced_score']}")
    print(f"  分析师评级分: {enriched['analyst_score']}")
    print(f"\n  完整增强总分详情:")
    print(json.dumps(enriched['enhanced_total_score'], ensure_ascii=False, indent=2, default=str))

    print("\n" + "=" * 60)
    print("测试完成 [OK]")
    print("=" * 60)

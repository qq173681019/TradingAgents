#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日潜力股推荐引擎

主入口脚本，整合股票筛选、新闻分析、邮件推送：
1. 用 StockScreener 筛选小盘潜力股
2. 取评分最高的前N只候选股
3. 用 NewsAnalyzer 分析新闻情绪
4. 综合评分取 TOP 1
5. 用 EmailNotifier 发送推荐邮件

使用方法：
    python daily_recommender.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# 添加共享模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

from config import RECEIVER_EMAIL
from market_state import detect_market_state
from stock_screener import StockScreener
from news_analyzer import NewsAnalyzer
from email_notifier import EmailNotifier

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
    """计算综合评分（支持动态权重，基本面纳入新闻维度）"""
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

    return round(
        technical * weights['technical'] +
        chip * weights['chip'] +
        sector * weights['sector'] +
        news_fundamental * weights['news'],
        2
    )


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

    return {
        "date": today,
        "stock_code": stock.get('code', ''),
        "stock_name": stock.get('name', ''),
        "total_score": total_score,
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
    screener = StockScreener()
    candidates = screener.screen()

    if not candidates:
        logger.error("筛选结果为空，无法生成推荐")
        return None

    logger.info(f"筛选通过 {len(candidates)} 只潜力股")

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
    logger.info("[步骤3] 计算综合评分并排序...")
    for stock in analyzed_stocks:
        stock['total_score'] = calculate_total_score(stock)

    analyzed_stocks.sort(key=lambda x: x['total_score'], reverse=True)

    logger.info("综合评分排名:")
    for i, s in enumerate(analyzed_stocks[:5], 1):
        logger.info(f"  {i}. {s['code']} {s['name']} "
                     f"综合:{s['total_score']:.2f} "
                     f"(技术:{s.get('short_term_score', 0):.1f} "
                     f"筹码:{s.get('chip_score', 0):.1f} "
                     f"热度:{s.get('hot_sector_score', 0):.1f} "
                     f"新闻:{s.get('sentiment_score', 5.0):.1f})")

    # ---- 第4步：选出TOP N，行业分散 ----
    top_picks = []
    industry_count = {}
    for stock in analyzed_stocks:
        if len(top_picks) >= RECOMMEND_COUNT:
            break
        industry = stock.get('industry', stock.get('matched_sector', '未知'))
        if industry_count.get(industry, 0) >= MAX_SAME_INDUSTRY:
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
        "recommended": recommendations,
        "candidates": [
            {
                "code": s.get('code', ''),
                "name": s.get('name', ''),
                "total_score": s.get('total_score', 0),
                "sentiment": s.get('sentiment', '中性'),
                "sentiment_score": s.get('sentiment_score', 5.0),
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强数据获取器 - 为股票推荐系统新增4个财务/市场数据维度

功能：
1. 季度盈利数据 — 净利润、同比增长率、ROE等
2. 分析师目标价与EPS预测 — 机构预测EPS均值/最小/最大值
3. 板块热度增强 — 板块近5日涨跌幅、资金净流入
4. 研报评级 — 最新评级、近一月研报数、预测EPS

作者: TradingAgent 数据工程师
日期: 2026-05-04
"""

import os
import time
import warnings
from typing import Dict, Optional

import pandas as pd

warnings.filterwarnings('ignore')

# 禁用系统代理，避免请求被拦截
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 尝试导入akshare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[ERROR] akshare库未安装，请运行: pip install akshare")


# ============================================================
# 缓存机制：同一参数5分钟内不重复请求
# ============================================================
_cache: Dict[str, dict] = {}  # key -> {'data': ..., 'ts': timestamp}
_CACHE_TTL = 300  # 5分钟 = 300秒


def _get_cache(key: str):
    """从缓存获取数据，过期返回 None"""
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.time() - entry['ts'] > _CACHE_TTL:
        # 过期，清除
        _cache.pop(key, None)
        return None
    return entry['data']


def _set_cache(key: str, data):
    """写入缓存"""
    _cache[key] = {'data': data, 'ts': time.time()}


def _clean_value(val):
    """清洗 akshare 返回的异常值，如 'False' 字符串转为 None"""
    if val is None:
        return None
    if isinstance(val, str):
        stripped = val.strip()
        if stripped == '' or stripped.lower() == 'false' or stripped.lower() == 'nan' or stripped == '-':
            return None
        return stripped
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return val
    return val


def _to_float(val):
    """将值转为 float，失败返回 None"""
    val = _clean_value(val)
    if val is None:
        return None
    try:
        # 去掉百分号等后缀
        if isinstance(val, str):
            val = val.replace('%', '').replace('亿', '').replace('万', '').strip()
        return float(val)
    except (ValueError, TypeError):
        return None


# ============================================================
# 1. 季度盈利数据
# ============================================================
def fetch_quarterly_earnings(stock_code: str) -> Optional[Dict]:
    """
    获取股票最新一期季度盈利数据

    参数:
        stock_code: 股票代码，如 '000885'
    返回:
        dict 包含:
            - net_profit: 净利润（数值，单位亿）
            - net_profit_yoy: 净利润同比增长率（%）
            - deducted_net_profit_yoy: 扣非净利润同比增长率（%）
            - revenue_yoy: 营收同比增长率（%）
            - eps: 基本每股收益
            - roe: 净资产收益率（%）
        失败返回 None
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'earnings_{stock_code}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        # 同花顺财务摘要
        df = ak.stock_financial_abstract_ths(symbol=stock_code, indicator='按报告期')
        if df is None or df.empty:
            return None

        # 取最新一期（最后一行，akshare 按时间升序排列）
        latest = df.iloc[-1]

        result = {
            'report_date': _clean_value(latest.get('报告期')),
            'net_profit': _clean_value(latest.get('净利润')),
            'net_profit_yoy': _to_float(latest.get('净利润同比增长率')),
            'deducted_net_profit_yoy': _to_float(latest.get('扣非净利润同比增长率')),
            'revenue_yoy': _to_float(latest.get('营业总收入同比增长率')),
            'eps': _to_float(latest.get('基本每股收益')),
            'roe': _to_float(latest.get('净资产收益率')),
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[WARN] fetch_quarterly_earnings({stock_code}) 失败: {e}")
        return None


# ============================================================
# 2. 分析师目标价与EPS预测
# ============================================================
def fetch_analyst_forecast(stock_code: str) -> Optional[Dict]:
    """
    获取分析师对股票的EPS预测数据

    参数:
        stock_code: 股票代码，如 '000885'
    返回:
        dict 包含:
            - forecast_year: 预测年度
            - eps_forecast: 预测EPS均值
            - eps_forecast_min: 预测EPS最小值
            - eps_forecast_max: 预测EPS最大值
            - institution_count: 预测机构数
        失败返回 None
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'analyst_{stock_code}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        df = ak.stock_profit_forecast_ths(symbol=stock_code)
        if df is None or df.empty:
            return None

        # 取第一行（最新的年度预测）
        latest = df.iloc[0]

        result = {
            'forecast_year': _clean_value(latest.get('年度')),
            'eps_forecast': _to_float(latest.get('均值')),
            'eps_forecast_min': _to_float(latest.get('最小值')),
            'eps_forecast_max': _to_float(latest.get('最大值')),
            'institution_count': _to_float(latest.get('预测机构数')),
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[WARN] fetch_analyst_forecast({stock_code}) 失败: {e}")
        return None


# ============================================================
# 3. 板块热度增强
# ============================================================
def fetch_sector_heat(industry_name: str) -> Optional[Dict]:
    """
    获取板块热度增强数据

    参数:
        industry_name: 板块名称，如 '环保'、'光伏'
    返回:
        dict 包含:
            - sector_name: 板块名称
            - sector_change_pct: 板块近5日涨跌幅（%）
            - net_inflow: 板块资金净流入（亿元）
            - stock_count: 板块成分股数量
            - top_gainers: 板块涨幅前3名股票列表
        失败返回 None
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'sector_{industry_name}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        # 第一步：获取所有板块列表，找到目标板块的涨跌幅等信息
        board_df = ak.stock_board_industry_name_em()
        if board_df is None or board_df.empty:
            return None

        # 查找目标板块
        target_row = board_df[board_df['板块名称'] == industry_name]
        if target_row.empty:
            # 尝试模糊匹配
            target_row = board_df[board_df['板块名称'].str.contains(industry_name, na=False)]
        if target_row.empty:
            return None

        row = target_row.iloc[0]
        sector_change = _to_float(row.get('涨跌幅'))
        net_inflow = _to_float(row.get('主力净流入') or row.get('净流入'))

        # 第二步：获取板块成分股
        cons_df = None
        try:
            cons_df = ak.stock_board_industry_cons_em(symbol=industry_name)
        except Exception:
            pass

        stock_count = len(cons_df) if cons_df is not None and not cons_df.empty else 0

        # 板块涨幅前3
        top_gainers = []
        if cons_df is not None and not cons_df.empty and '涨跌幅' in cons_df.columns:
            top3 = cons_df.nlargest(3, '涨跌幅')
            for _, s in top3.iterrows():
                top_gainers.append({
                    'code': str(s.get('代码', '')),
                    'name': str(s.get('名称', '')),
                    'change_pct': _to_float(s.get('涨跌幅')),
                })

        result = {
            'sector_name': industry_name,
            'sector_change_pct': sector_change,
            'net_inflow': net_inflow,
            'stock_count': stock_count,
            'top_gainers': top_gainers,
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[WARN] fetch_sector_heat({industry_name}) 失败: {e}")
        return None


# ============================================================
# 4. 研报评级
# ============================================================
def fetch_research_rating(stock_code: str) -> Optional[Dict]:
    """
    获取股票研报评级数据

    参数:
        stock_code: 股票代码，如 '000885'
    返回:
        dict 包含:
            - latest_rating: 最新评级（买入/增持/中性/减持）
            - rating_count: 近一月研报数
            - target_eps_2026: 2026年预测EPS（如有）
        失败返回 None
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'rating_{stock_code}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        df = ak.stock_research_report_em(symbol=stock_code)
        if df is None or df.empty:
            return None

        # 最新评级：取第一行（东财评级字段）
        latest = df.iloc[0]
        latest_rating = _clean_value(latest.get('东财评级'))

        # 近一月研报数：优先用接口自带的字段，否则按日期计算
        rating_count = 0
        raw_count = latest.get('近一月个股研报数')
        if raw_count is not None:
            rating_count = int(_to_float(raw_count) or 0)
        if rating_count == 0 and '日期' in df.columns:
            from datetime import datetime, timedelta
            one_month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            try:
                df['_date'] = pd.to_datetime(df['日期'], errors='coerce')
                rating_count = int((df['_date'] >= one_month_ago).sum())
            except Exception:
                rating_count = len(df)

        # 查找2026年预测EPS（东财接口有专用列）
        target_eps_2026 = None
        eps_col = '2026-盈利预测-收益'
        if eps_col in df.columns:
            # 取最新一篇有2026预测的研报
            for _, row in df.iterrows():
                val = _to_float(row.get(eps_col))
                if val is not None:
                    target_eps_2026 = val
                    break

        result = {
            'latest_rating': latest_rating,
            'rating_count': rating_count,
            'target_eps_2026': target_eps_2026,
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[WARN] fetch_research_rating({stock_code}) 失败: {e}")
        return None


# ============================================================
# 测试代码
# ============================================================
if __name__ == '__main__':
    import json

    test_code = '000885'  # 城发环境
    print(f"{'='*60}")
    print(f"增强数据获取器 - 测试: {test_code}")
    print(f"{'='*60}")

    # 1. 季度盈利数据
    print(f"\n--- 1. 季度盈利数据 ---")
    earnings = fetch_quarterly_earnings(test_code)
    if earnings:
        for k, v in earnings.items():
            print(f"  {k}: {v}")
    else:
        print("  [无数据]")

    # 2. 分析师EPS预测
    print(f"\n--- 2. 分析师EPS预测 ---")
    forecast = fetch_analyst_forecast(test_code)
    if forecast:
        for k, v in forecast.items():
            print(f"  {k}: {v}")
    else:
        print("  [无数据]")

    # 3. 板块热度增强（城发环境属环保板块）
    print(f"\n--- 3. 板块热度增强 ---")
    sector = fetch_sector_heat('环保')
    if sector:
        for k, v in sector.items():
            if k == 'top_gainers':
                print(f"  top_gainers:")
                for g in v:
                    print(f"    {g['name']}({g['code']}): {g['change_pct']}%")
            else:
                print(f"  {k}: {v}")
    else:
        print("  [无数据]")

    # 4. 研报评级
    print(f"\n--- 4. 研报评级 ---")
    rating = fetch_research_rating(test_code)
    if rating:
        for k, v in rating.items():
            print(f"  {k}: {v}")
    else:
        print("  [无数据]")

    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}")

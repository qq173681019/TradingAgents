#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新因子评分模块 - 资金流向 + 龙虎榜

本模块将 new_data_sources.py 获取的原始数据转化为 0-10 分的评分，
可直接集成到 enhanced_scorer.py 和 daily_recommender.py 中。

因子清单:
  1. 资金流向评分 (fund_flow_score)
     - 主力净流入趋势（5日/3日/1日）
     - 超大单净流入占比
     - 主力持续流入加分，持续流出减分

  2. 龙虎榜评分 (lhb_score)
     - 近期是否上榜
     - 机构买入金额
     - 净买额正负

  3. 北向资金评分 (north_flow_score)
     - 市场整体主力资金方向

  4. 融资融券评分 (margin_score)
     - 融资余额变化趋势

  5. 综合新因子评分 (composite_new_factor_score)
     - 加权组合上述因子

数据获取失败时统一返回 5.0（中性分数）。

作者: TradingAgent 数据工程师
日期: 2026-05-06
"""

import os
import time
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import pandas as pd

# 禁用代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['PYTHONIOENCODING'] = 'utf-8'

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.error("[new_factors] akshare 未安装")

# ============================================================
# 缓存
# ============================================================
_cache: Dict[str, dict] = {}
_CACHE_TTL = 300  # 5分钟


def _get_cache(key: str):
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.time() - entry['ts'] > _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return entry['data']


def _set_cache(key: str, data):
    _cache[key] = {'data': data, 'ts': time.time()}


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _clamp(score: float, low=0.0, high=10.0) -> float:
    return max(low, min(high, score))


# ============================================================
# 1. 资金流向评分
# ============================================================
def fetch_fund_flow_data(stock_code: str) -> Optional[Dict]:
    """
    获取个股资金流向历史数据（最近约20个交易日）

    返回: {
        'code': str,
        'latest_main_net': float,       # 最新一天主力净流入(元)
        'latest_huge_net': float,        # 最新一天超大单净流入(元)
        'main_net_5d': float,            # 近5日主力净流入合计(元)
        'main_net_3d': float,            # 近3日主力净流入合计(元)
        'main_net_1d': float,            # 近1日主力净流入(元)
        'main_pct_latest': float,        # 最新一天主力净流入占比(%)
        'main_pct_5d_avg': float,        # 近5日主力净流入占比均值(%)
        'consecutive_inflow': int,        # 连续净流入天数(负数=连续净流出)
        'days_data': int,                # 有数据的天数
    }
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'fund_flow_{stock_code}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    market = 'sh' if stock_code.startswith(('6', '5')) else 'sz'

    try:
        df = ak.stock_individual_fund_flow(stock=stock_code, market=market)
        if df is None or df.empty:
            return None

        # 取最近20天
        recent = df.tail(20)

        # 列名映射
        col_main_net = None
        col_huge_net = None
        col_main_pct = None
        for c in df.columns:
            c_lower = str(c)
            if '主力净流入' in c_lower and '占比' not in c_lower:
                col_main_net = c
            elif '超大单净流入' in c_lower and '占比' not in c_lower:
                col_huge_net = c
            elif '主力净流入' in c_lower and '占比' in c_lower:
                col_main_pct = c

        if col_main_net is None:
            logger.warning(f"[fund_flow] {stock_code} 找不到主力净流入列")
            return None

        # 计算关键指标
        main_nets = []
        main_pcts = []
        for _, row in recent.iterrows():
            v = _safe_float(row.get(col_main_net))
            if v is not None:
                main_nets.append(v)
            if col_main_pct:
                p = _safe_float(row.get(col_main_pct))
                if p is not None:
                    main_pcts.append(p)

        if not main_nets:
            return None

        # 连续流入/流出天数
        consecutive = 0
        for v in reversed(main_nets):
            if v > 0:
                if consecutive < 0:
                    break
                consecutive += 1
            elif v < 0:
                if consecutive > 0:
                    break
                consecutive -= 1
            else:
                break

        result = {
            'code': stock_code,
            'latest_main_net': main_nets[-1] if main_nets else None,
            'latest_huge_net': _safe_float(recent.iloc[-1].get(col_huge_net)) if col_huge_net else None,
            'main_net_1d': main_nets[-1] if len(main_nets) >= 1 else None,
            'main_net_3d': sum(main_nets[-3:]) if len(main_nets) >= 3 else None,
            'main_net_5d': sum(main_nets[-5:]) if len(main_nets) >= 5 else None,
            'main_pct_latest': main_pcts[-1] if main_pcts else None,
            'main_pct_5d_avg': sum(main_pcts[-5:]) / 5 if len(main_pcts) >= 5 else None,
            'consecutive_inflow': consecutive,
            'days_data': len(main_nets),
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"[fund_flow] {stock_code} 获取失败: {e}")
        return None


def score_fund_flow(data: Optional[Dict]) -> float:
    """
    资金流向评分 (0-10)

    评分规则:
    A) 主力5日净流入趋势 (权重 40%)
       - 5日净流入 > 5亿: 9-10分
       - 5日净流入 > 1亿: 7-9分
       - 5日净流入 > 0: 5-7分
       - 5日净流入 > -1亿: 3-5分
       - 5日净流入 > -5亿: 1-3分
       - 5日净流入 < -5亿: 0-1分

    B) 连续流入/流出天数 (权重 30%)
       - 连续3天+流入: +2
       - 连续2天流入: +1
       - 连续2天流出: -1
       - 连续3天+流出: -2

    C) 超大单方向 (权重 30%)
       - 超大单5日合计 > 2亿: +1.5
       - 超大单5日合计 > 0: +0.5
       - 超大单5日合计 < -2亿: -1.5
       - 超大单5日合计 < 0: -0.5

    data 为 None 时返回 5.0
    """
    if data is None:
        return 5.0

    # A) 5日主力净流入趋势
    net_5d = data.get('main_net_5d')
    if net_5d is None:
        return 5.0

    # 转换为亿元
    net_5d_yi = net_5d / 1e8 if abs(net_5d) > 1e6 else net_5d

    if net_5d_yi > 5:
        base_a = min(10.0, 9.0 + (net_5d_yi - 5) / 10)
    elif net_5d_yi > 1:
        base_a = 7.0 + (net_5d_yi - 1) / 4 * 2
    elif net_5d_yi > 0:
        base_a = 5.0 + net_5d_yi / 1 * 2
    elif net_5d_yi > -1:
        base_a = 3.0 + (net_5d_yi + 1) / 1 * 2
    elif net_5d_yi > -5:
        base_a = 1.0 + (net_5d_yi + 5) / 4 * 2
    else:
        base_a = max(0.0, 1.0 + (net_5d_yi + 5) / 10)

    # B) 连续流入/流出
    consec = data.get('consecutive_inflow', 0) or 0
    bonus_b = 0.0
    if consec >= 5:
        bonus_b = 2.5
    elif consec >= 3:
        bonus_b = 2.0
    elif consec >= 2:
        bonus_b = 1.0
    elif consec <= -5:
        bonus_b = -2.5
    elif consec <= -3:
        bonus_b = -2.0
    elif consec <= -2:
        bonus_b = -1.0

    # C) 超大单方向 (用最新一天代替)
    huge_net = data.get('latest_huge_net')
    bonus_c = 0.0
    if huge_net is not None:
        huge_yi = huge_net / 1e8 if abs(huge_net) > 1e6 else huge_net
        if huge_yi > 2:
            bonus_c = 1.5
        elif huge_yi > 0:
            bonus_c = 0.5
        elif huge_yi > -2:
            bonus_c = -0.5
        else:
            bonus_c = -1.5

    # 加权组合
    score = base_a * 0.4 + (5.0 + bonus_b) * 0.3 + (5.0 + bonus_c) * 0.3

    return _clamp(round(score, 2))


# ============================================================
# 2. 龙虎榜评分
# ============================================================
def fetch_lhb_data(stock_code: str, lookback_days: int = 20) -> Optional[Dict]:
    """
    获取个股近期龙虎榜数据

    返回: {
        'code': str,
        'on_list': bool,               # 近期是否上榜
        'appearances': int,            # 上榜次数
        'total_net_buy': float,        # 合计净买额(元)
        'total_buy_amount': float,     # 合计买入额(元)
        'has_institutional_buy': bool, # 是否有机构买入
        'latest_date': str,            # 最近上榜日期
        'latest_net_buy': float,       # 最近一次净买额
    }
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = f'lhb_{stock_code}'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        sd = start_date.strftime('%Y%m%d')
        ed = end_date.strftime('%Y%m%d')

        df = ak.stock_lhb_detail_em(start_date=sd, end_date=ed)
        if df is None or df.empty:
            _set_cache(cache_key, {'code': stock_code, 'on_list': False, 'appearances': 0})
            return _get_cache(cache_key)

        # 筛选目标股票
        code_col = None
        for c in df.columns:
            if '代码' in str(c):
                code_col = c
                break

        if code_col is None:
            return None

        stock_df = df[df[code_col].astype(str) == stock_code]

        if stock_df.empty:
            result = {
                'code': stock_code,
                'on_list': False,
                'appearances': 0,
                'total_net_buy': 0,
                'total_buy_amount': 0,
                'has_institutional_buy': False,
                'latest_date': None,
                'latest_net_buy': None,
            }
            _set_cache(cache_key, result)
            return result

        # 提取关键数据
        net_buy_col = None
        buy_col = None
        date_col = None
        reason_col = None
        for c in stock_df.columns:
            c_str = str(c)
            if '净买额' in c_str and '龙虎榜' in c_str:
                net_buy_col = c
            elif '买入额' in c_str and '龙虎榜' in c_str:
                buy_col = c
            elif '上榜日' in c_str:
                date_col = c
            elif '上榜原因' in c_str:
                reason_col = c

        net_buys = []
        buy_amounts = []
        for _, row in stock_df.iterrows():
            if net_buy_col:
                v = _safe_float(row.get(net_buy_col))
                if v is not None:
                    net_buys.append(v)
            if buy_col:
                v = _safe_float(row.get(buy_col))
                if v is not None:
                    buy_amounts.append(v)

        # 检查是否有机构买入（通过上榜原因判断）
        has_inst = False
        if reason_col:
            for _, row in stock_df.iterrows():
                reason = str(row.get(reason_col, ''))
                if '机构' in reason:
                    has_inst = True
                    break

        # 也检查机构买卖统计接口
        if not has_inst:
            try:
                jg_df = ak.stock_lhb_jgmmtj_em(start_date=sd, end_date=ed)
                if jg_df is not None and not jg_df.empty:
                    code_col2 = None
                    for c in jg_df.columns:
                        if '代码' in str(c):
                            code_col2 = c
                            break
                    if code_col2:
                        inst_row = jg_df[jg_df[code_col2].astype(str) == stock_code]
                        if not inst_row.empty:
                            has_inst = True
            except Exception:
                pass

        latest_date_val = None
        if date_col:
            latest_date_val = str(stock_df.iloc[0].get(date_col, ''))

        result = {
            'code': stock_code,
            'on_list': True,
            'appearances': len(stock_df),
            'total_net_buy': sum(net_buys) if net_buys else 0,
            'total_buy_amount': sum(buy_amounts) if buy_amounts else 0,
            'has_institutional_buy': has_inst,
            'latest_date': latest_date_val,
            'latest_net_buy': net_buys[0] if net_buys else None,
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"[lhb] {stock_code} 获取失败: {e}")
        return None


def score_lhb(data: Optional[Dict]) -> float:
    """
    龙虎榜评分 (0-10)

    评分规则:
    - 未上榜: 5.0 (中性)
    - 上榜1次 + 净买入 > 0: 6-7分
    - 上榜1次 + 净买入 < 0: 3-4分
    - 上榜2+次 + 净买入 > 0: 7-8分
    - 上榜2+次 + 机构买入: 8-10分
    - 上榜但全是净卖出: 2-3分
    """
    if data is None:
        return 5.0

    if not data.get('on_list', False):
        return 5.0

    appearances = data.get('appearances', 0)
    total_net_buy = data.get('total_net_buy', 0)
    has_inst = data.get('has_institutional_buy', False)

    # 基础分
    base = 5.0

    # 上榜次数加分
    if appearances >= 3:
        base += 1.5
    elif appearances >= 2:
        base += 1.0
    else:
        base += 0.5

    # 净买额加减分
    if total_net_buy is not None:
        net_yi = total_net_buy / 1e8 if abs(total_net_buy) > 1e6 else total_net_buy
        if net_yi > 1:
            base += 2.0
        elif net_yi > 0.3:
            base += 1.5
        elif net_yi > 0:
            base += 1.0
        elif net_yi > -0.3:
            base -= 0.5
        elif net_yi > -1:
            base -= 1.5
        else:
            base -= 2.0

    # 机构买入加分
    if has_inst:
        base += 1.5

    return _clamp(round(base, 2))


# ============================================================
# 3. 市场资金流向评分 (大盘环境)
# ============================================================
def fetch_market_fund_flow() -> Optional[Dict]:
    """
    获取市场整体资金流向（最近5天）

    返回: {
        'main_net_5d': float,       # 近5日主力净流入合计(亿元)
        'super_large_5d': float,    # 近5日超大单净流入合计(亿元)
        'latest_main_net': float,   # 最新一天主力净流入(亿元)
    }
    """
    if not AKSHARE_AVAILABLE:
        return None

    cache_key = 'market_fund_flow'
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        df = ak.stock_market_fund_flow()
        if df is None or df.empty:
            return None

        recent = df.tail(5)

        main_nets = []
        super_nets = []
        for _, row in recent.iterrows():
            # 主力净流入
            mn = None
            sn = None
            for c in row.index:
                c_str = str(c)
                if '主力净流入' in c_str and '占比' not in c_str and '净额' in c_str:
                    mn = _safe_float(row[c])
                elif '超大单净流入' in c_str and '占比' not in c_str and '净额' in c_str:
                    sn = _safe_float(row[c])
            if mn is not None:
                main_nets.append(mn / 1e8)  # 元 → 亿元
            if sn is not None:
                super_nets.append(sn / 1e8)

        if not main_nets:
            return None

        result = {
            'main_net_5d': sum(main_nets),
            'super_large_5d': sum(super_nets) if super_nets else None,
            'latest_main_net': main_nets[-1],
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"[market_fund_flow] 获取失败: {e}")
        return None


def score_market_fund_flow(data: Optional[Dict]) -> float:
    """
    市场资金流向评分 (0-10)

    用于市场环境判断，不针对个股。
    主力5日净流入 > 100亿: 9-10分
    主力5日净流入 > 20亿: 7-9分
    主力5日净流入 > 0: 5-7分
    主力5日净流入 < 0: 3-5分
    主力5日净流入 < -100亿: 1-3分
    """
    if data is None:
        return 5.0

    net_5d = data.get('main_net_5d')
    if net_5d is None:
        return 5.0

    if net_5d > 500:
        score = min(10.0, 9.0 + (net_5d - 500) / 500)
    elif net_5d > 100:
        score = 7.0 + (net_5d - 100) / 400 * 2
    elif net_5d > 0:
        score = 5.0 + net_5d / 100 * 2
    elif net_5d > -500:
        score = 4.0 + (net_5d + 500) / 500 * 1.0
    elif net_5d > -2000:
        score = 2.0 + (net_5d + 2000) / 1500 * 2.0
    else:
        score = max(0.0, 2.0 + (net_5d + 2000) / 2000)

    return _clamp(round(score, 2))


# ============================================================
# 4. 综合新因子评分
# ============================================================
def composite_new_factor_score(stock_code: str, market_fund_data: Dict = None) -> Dict:
    """
    计算综合新因子评分

    权重分配:
    - 资金流向: 50% (个股层面，最重要)
    - 龙虎榜: 30% (事件驱动信号)
    - 市场资金: 20% (大盘环境)

    返回: {
        'fund_flow_score': float,
        'lhb_score': float,
        'market_fund_score': float,
        'composite_score': float,
        'fund_flow_data': dict or None,
        'lhb_data': dict or None,
    }
    """
    # 资金流向
    ff_data = fetch_fund_flow_data(stock_code)
    ff_score = score_fund_flow(ff_data)

    # 龙虎榜
    lhb_data = fetch_lhb_data(stock_code)
    lhb_score = score_lhb(lhb_data)

    # 市场资金
    if market_fund_data is None:
        market_fund_data = fetch_market_fund_flow()
    mf_score = score_market_fund_flow(market_fund_data)

    # 加权
    composite = (
        ff_score * 0.50 +
        lhb_score * 0.30 +
        mf_score * 0.20
    )

    return {
        'fund_flow_score': round(ff_score, 2),
        'lhb_score': round(lhb_score, 2),
        'market_fund_score': round(mf_score, 2),
        'composite_score': round(composite, 2),
        'fund_flow_data': ff_data,
        'lhb_data': lhb_data,
    }


# ============================================================
# 独立运行测试
# ============================================================
if __name__ == '__main__':
    import json

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    test_stocks = ['000001', '002221', '600519', '300750', '002818']

    print("=" * 60)
    print("新因子评分模块 - 测试")
    print("=" * 60)

    # 1. 测试资金流向
    print("\n--- 1. 资金流向评分 ---")
    for code in test_stocks:
        data = fetch_fund_flow_data(code)
        score = score_fund_flow(data)
        if data:
            net_5d = data.get('main_net_5d')
            net_5d_yi = f"{net_5d/1e8:.2f}亿" if net_5d else "N/A"
            consec = data.get('consecutive_inflow', 0)
            print(f"  {code}: 评分={score:.1f} | 5日净流入={net_5d_yi} | 连续={consec}天")
        else:
            print(f"  {code}: 评分={score:.1f} | 数据获取失败")

    # 2. 测试龙虎榜
    print("\n--- 2. 龙虎榜评分 ---")
    for code in test_stocks:
        data = fetch_lhb_data(code)
        score = score_lhb(data)
        on_list = data.get('on_list', False) if data else False
        net_buy = data.get('total_net_buy') if data else None
        has_inst = data.get('has_institutional_buy') if data else False
        print(f"  {code}: 评分={score:.1f} | 上榜={on_list} | 净买额={net_buy} | 机构={has_inst}")

    # 3. 测试市场资金
    print("\n--- 3. 市场资金流向 ---")
    mf_data = fetch_market_fund_flow()
    mf_score = score_market_fund_flow(mf_data)
    if mf_data:
        print(f"  评分={mf_score:.1f} | 5日主力净流入={mf_data.get('main_net_5d', 0):.2f}亿")
    else:
        print(f"  评分={mf_score:.1f} | 数据获取失败")

    # 4. 综合评分
    print("\n--- 4. 综合新因子评分 ---")
    for code in test_stocks:
        result = composite_new_factor_score(code, market_fund_data=mf_data)
        print(f"  {code}: 综合={result['composite_score']:.1f} | "
              f"资金流向={result['fund_flow_score']:.1f} | "
              f"龙虎榜={result['lhb_score']:.1f} | "
              f"大盘={result['market_fund_score']:.1f}")

    # 5. None测试
    print("\n--- 5. None输入测试 ---")
    print(f"  score_fund_flow(None): {score_fund_flow(None)}")
    print(f"  score_lhb(None): {score_lhb(None)}")
    print(f"  score_market_fund_flow(None): {score_market_fund_flow(None)}")

    print("\n" + "=" * 60)
    print("测试完成 [OK]")
    print("=" * 60)

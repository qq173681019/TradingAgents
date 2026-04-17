"""
激进小盘股选股模块
基于缠论1小时线 + 放量突破 + 小盘股特性

策略:
1. 筛选小盘股池 (市值<50亿, 换手>2%, 排除ST)
2. 拉取1小时K线
3. 缠论分析: 寻找买点(一买/二买/三买)
4. 放量确认: 成交量显著放大
5. 综合评分排序，输出Top N
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import json
import os
import sys

# 路径设置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(os.path.dirname(BASE_DIR), 'TradingShared')
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from chanlun.hourly_fetcher import fetch_hourly_kline, fetch_hourly_batch, get_small_cap_stocks
from chanlun.chanlun_core import analyze_chanlun


def score_stock(chanlun_result: dict, df_hourly: pd.DataFrame, stock_info: dict) -> dict:
    """
    对单只股票进行激进评分。
    
    评分维度:
    1. 缠论买点 (0-40分): 一买40, 二买30, 三买20
    2. 放量程度 (0-25分): 最近成交量 vs 20周期均量
    3. 趋势强度 (0-20分): 上涨趋势加分
    4. 小盘优势 (0-15分): 市值越小分越高
    
    Returns:
        {'code': str, 'name': str, 'score': float, 'signal': str, 'details': dict}
    """
    score = 0
    details = {}
    
    # 1. 缠论买点评分
    last_buy = chanlun_result.get('last_buy_signal')
    if last_buy:
        signal_type = last_buy['type']
        if signal_type == 'buy3':
            score += 45  # 三买最实用: 中枢上移确认趋势
            details['buy_point'] = '三买(中枢上移)'
        elif signal_type == 'buy1':
            score += 35  # 一买: 背驰反转
            details['buy_point'] = '一买(趋势背驰)'
        elif signal_type == 'buy2':
            score += 25  # 二买: 回调确认
            details['buy_point'] = '二买(回调不破)'
        details['buy_price'] = last_buy['price']
    else:
        details['buy_point'] = '无明确买点'
        # 没有买点但也有机会: 看趋势+中枢位置
        if chanlun_result.get('trend') == 'up' and chanlun_result.get('zhongshu'):
            last_zs = chanlun_result['zhongshu'][-1]
            last_price = chanlun_result['last_price']
            if last_price > last_zs['high'] * 0.98:  # 接近中枢上沿
                score += 10
                details['buy_point'] = '潜在突破(接近中枢上沿)'
    
    # 2. 放量评分 (权重提高到0-30)
    if 'volume' in df_hourly.columns and len(df_hourly) >= 20:
        vol_series = df_hourly['volume'].dropna()
        if len(vol_series) >= 20:
            avg_vol_20 = vol_series.iloc[-20:].mean()
            recent_vol = vol_series.iloc[-3:].mean()
            
            if avg_vol_20 > 0:
                vol_ratio = recent_vol / avg_vol_20
                details['vol_ratio'] = round(vol_ratio, 2)
                
                if vol_ratio >= 3.0:
                    score += 30
                elif vol_ratio >= 2.0:
                    score += 25
                elif vol_ratio >= 1.5:
                    score += 18
                elif vol_ratio >= 1.2:
                    score += 10
                else:
                    score += 0
    
    # 3. 趋势评分 (权重保持)
    trend = chanlun_result.get('trend', 'consolidation')
    details['trend'] = trend
    if trend == 'up':
        score += 20
        # 笔数多说明活跃
        bi_count = len(chanlun_result.get('bi', []))
        if bi_count >= 6:
            score += 5  # 活跃加分
    elif trend == 'consolidation':
        zhongshu = chanlun_result.get('zhongshu', [])
        if zhongshu:
            last_zs = zhongshu[-1]
            last_price = chanlun_result['last_price']
            if last_price < last_zs['low'] * 1.03:
                score += 10
                details['note'] = '中枢下方蓄势'
    
    # 4. 小盘评分
    market_cap = stock_info.get('market_cap', 0)
    turnover = stock_info.get('turnover_rate', 0)
    details['market_cap'] = market_cap
    details['turnover_rate'] = turnover
    
    if market_cap > 0:
        cap_yi = market_cap / 1e8
        if cap_yi < 20:
            score += 15
        elif cap_yi < 30:
            score += 12
        elif cap_yi < 40:
            score += 8
        else:
            score += 5
    
    details['total_score'] = score
    
    return {
        'code': stock_info['code'],
        'name': stock_info['name'],
        'score': score,
        'signal': details.get('buy_point', '无'),
        'details': details,
    }


def run_aggressive_scan(top_n: int = 10, max_stocks: int = 200) -> List[dict]:
    """
    执行激进小盘股扫描。
    
    Args:
        top_n: 返回前N只
        max_stocks: 最多扫描多少只
    
    Returns:
        排序后的股票列表
    """
    print("=" * 50)
    print("激进小盘股缠论扫描")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    
    # Step 1: 获取小盘股池
    print("\n[1/4] 筛选小盘股池...")
    stock_pool = get_small_cap_stocks(
        max_cap=50e8,
        min_price=3.0,
        max_price=30.0,
        min_turnover=2.0
    )
    
    if stock_pool.empty:
        print("未获取到小盘股数据，可能非交易时间")
        return []
    
    print(f"  筛选出 {len(stock_pool)} 只小盘股")
    
    # 限制数量
    symbols = stock_pool['代码'].tolist()[:max_stocks]
    
    # Step 2: 批量拉取1小时K线
    print(f"\n[2/4] 批量获取1小时K线 ({len(symbols)}只)...")
    kline_data = fetch_hourly_batch(symbols, days=30, delay=0.5)
    
    # Step 3: 缠论分析 + 评分
    print(f"\n[3/4] 缠论分析 + 评分...")
    results = []
    
    for code, df in kline_data.items():
        try:
            # 缠论分析
            cl_result = analyze_chanlun(df)
            
            # 只要有买点才评分
            if cl_result.get('last_buy_signal') is None and cl_result.get('trend') != 'up':
                continue
            
            # 获取股票信息
            row = stock_pool[stock_pool['代码'] == code]
            if row.empty:
                continue
            
            stock_info = {
                'code': code,
                'name': row.iloc[0]['名称'],
                'market_cap': float(row.iloc[0]['总市值']),
                'turnover_rate': float(row.iloc[0]['换手率']),
                'price': float(row.iloc[0]['最新价']),
            }
            
            score_result = score_stock(cl_result, df, stock_info)
            
            # 过滤低分
            if score_result['score'] >= 30:
                results.append(score_result)
                
        except Exception as e:
            continue
    
    # Step 4: 排序输出
    print(f"\n[4/4] 排序输出...")
    results.sort(key=lambda x: x['score'], reverse=True)
    results = results[:top_n]
    
    # 打印结果
    print(f"\n{'='*50}")
    print(f"Top {len(results)} 激进小盘股:")
    print(f"{'='*50}")
    
    for i, r in enumerate(results):
        print(f"\n#{i+1} {r['code']} {r['name']}")
        print(f"  评分: {r['score']} | 买点: {r['signal']}")
        det = r['details']
        if 'vol_ratio' in det:
            print(f"  量比: {det['vol_ratio']}x | 趋势: {det['trend']}")
        if 'market_cap' in det:
            print(f"  市值: {det['market_cap']/1e8:.1f}亿 | 换手: {det.get('turnover_rate', 0):.1f}%")
    
    # 保存结果
    output_file = os.path.join(BASE_DIR, 'data', f'aggressive_scan_{datetime.now().strftime("%Y%m%d_%H%M")}.json')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_file}")
    
    return results


if __name__ == '__main__':
    results = run_aggressive_scan(top_n=10, max_stocks=200)

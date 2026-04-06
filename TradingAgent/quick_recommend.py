#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速推荐脚本 - 直接从缓存数据中计算推荐股票
无需连接API，使用最新的评分数据文件即可计算

用法:
    python quick_recommend.py          # 推荐前3只短线股票
    python quick_recommend.py -n 5     # 推荐前5只
    python quick_recommend.py -t long  # 推荐长线股票
    python quick_recommend.py -v       # 显示详细评分
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime


def _clean_industry_name(industry):
    """清理行业名称后缀"""
    if not industry:
        return industry
    for suffix in ['III', 'II', 'IV', 'Ⅲ', 'Ⅱ', 'Ⅳ', 'Ⅴ', 'Ⅰ', 'I']:
        industry = industry.replace(suffix, '')
    return industry.strip()


def calculate_weighted_score(tech, fund, chip, sector, weights):
    """计算加权综合评分（统一1-10范围）"""
    tech = max(1.0, min(10.0, float(tech)))
    fund = max(1.0, min(10.0, float(fund)))
    chip = max(1.0, min(10.0, float(chip)))
    sector = max(1.0, min(10.0, float(sector)))
    
    score = (tech * weights['tech'] + fund * weights['fund'] +
             chip * weights['chip'] + sector * weights['sector'])
    return round(max(1.0, min(10.0, score)), 2)


def select_diversified(scored_stocks, n=10, max_per_sector=2, min_tech=3.0):
    """分散化选择TOP N（避免同板块垄断）"""
    selected = []
    sector_count = {}
    
    for stock in scored_stocks:
        if len(selected) >= n:
            break
        if stock['tech'] < min_tech or stock['tech'] <= 0 or stock['fund'] <= 0:
            continue
        
        group = stock.get('matched_sector') or stock.get('industry', '未知')
        if sector_count.get(group, 0) >= max_per_sector:
            continue
        
        selected.append(stock)
        sector_count[group] = sector_count.get(group, 0) + 1
    
    return selected


def load_latest_scores(data_dir):
    """加载最新评分文件"""
    score_files = [f for f in os.listdir(data_dir)
                   if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')]
    if not score_files:
        return None, None
    
    latest_file = max(score_files)
    file_path = os.path.join(data_dir, latest_file)
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f), latest_file


def recommend(n=3, strategy='short', verbose=False):
    """
    生成推荐股票列表
    
    Args:
        n: 推荐数量
        strategy: 'short'=短线, 'long'=长线
        verbose: 是否显示详细信息
    
    Returns:
        推荐股票列表
    """
    # 定位数据目录
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
    if not os.path.isdir(data_dir):
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'TradingShared', 'data')
    
    stocks, filename = load_latest_scores(data_dir)
    if not stocks:
        print('❌ 未找到评分数据文件，请先运行评分生成脚本')
        return []
    
    # 提取评分文件日期
    try:
        date_str = filename.split('_')[-2]  # 20260406
        file_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    except (IndexError, ValueError):
        file_date = "未知"
    
    # 权重配置
    weight_configs = {
        'short': {
            'name': '短线',
            'tech': 0.35, 'fund': 0.20, 'chip': 0.20, 'sector': 0.25
        },
        'long': {
            'name': '长线',
            'tech': 0.15, 'fund': 0.35, 'chip': 0.30, 'sector': 0.20
        }
    }
    
    weights = weight_configs.get(strategy, weight_configs['short'])
    
    # 计算所有股票的综合评分
    scored = []
    for code, data in stocks.items():
        tech = data.get('short_term_score', 5.0)
        fund = data.get('long_term_score', 5.0)
        chip = data.get('chip_score', 5.0)
        sector = data.get('hot_sector_score', 5.0)
        
        if tech == -10 or fund == -10:
            continue
        
        score = calculate_weighted_score(tech, fund, chip, sector, weights)
        scored.append({
            'code': code,
            'name': data.get('name', code),
            'score': score,
            'tech': tech,
            'fund': fund,
            'chip': chip,
            'sector': sector,
            'industry': data.get('industry', '未知'),
            'matched_sector': data.get('matched_sector', ''),
            'sector_change': data.get('sector_change', 0)
        })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    
    # 分散化选择
    top_n = select_diversified(scored, n=n, max_per_sector=2, min_tech=3.0)
    
    return top_n, weights, file_date, filename


def main():
    parser = argparse.ArgumentParser(description='快速股票推荐')
    parser.add_argument('-n', type=int, default=3, help='推荐数量 (默认3)')
    parser.add_argument('-t', '--type', choices=['short', 'long'], default='short',
                        help='策略类型: short=短线(默认), long=长线')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细评分')
    args = parser.parse_args()
    
    result = recommend(n=args.n, strategy=args.type, verbose=args.verbose)
    if not result:
        return
    
    top_n, weights, file_date, filename = result
    
    strategy_name = weights['name']
    print(f'\n{"="*60}')
    print(f'📊 {strategy_name}推荐 TOP {args.n} | 数据日期: {file_date}')
    print(f'   权重: 技术面{weights["tech"]*100:.0f}% + 基本面{weights["fund"]*100:.0f}% '
          f'+ 筹码{weights["chip"]*100:.0f}% + 板块{weights["sector"]*100:.0f}%')
    print(f'{"="*60}')
    
    for i, stock in enumerate(top_n, 1):
        sector_info = stock.get('matched_sector') or stock.get('industry', '')
        change = stock.get('sector_change', 0)
        change_str = f'{change:+.1f}%' if change else ''
        
        print(f'\n  🏆 第{i}名: {stock["code"]} {stock["name"]}')
        print(f'     综合评分: {stock["score"]:.2f}/10')
        print(f'     行业: {stock["industry"]} | 匹配板块: {sector_info} {change_str}')
        
        if args.verbose:
            print(f'     ├─ 技术面: {stock["tech"]:.1f}/10')
            print(f'     ├─ 基本面: {stock["fund"]:.1f}/10')
            print(f'     ├─ 筹码面: {stock["chip"]:.1f}/10')
            print(f'     └─ 板块热度: {stock["sector"]:.2f}/10')
    
    print(f'\n{"="*60}')
    print(f'⚠️ 以上推荐仅供参考，不构成投资建议')
    print(f'   数据来源: {filename}')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    main()

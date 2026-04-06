#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
分为短线推荐和长线推荐两部分，并添加AI板块未来趋势分析
"""
import csv
import json
import os
import sys


def calculate_weighted_score(tech_score, fund_score, chip_score, sector_trend_score,
                             tech_weight, fund_weight, chip_weight, sector_trend_weight):
    """
    计算加权综合评分
    所有评分维度统一为1-10分范围

    Args:
        tech_score: 技术面评分 (1-10)
        fund_score: 基本面评分 (1-10)
        chip_score: 筹码面评分 (1-10)
        sector_trend_score: 板块趋势评分 (1-10)
        tech_weight: 技术面权重
        fund_weight: 基本面权重
        chip_weight: 筹码面权重
        sector_trend_weight: 板块趋势权重

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

        # FIX: 评分范围 1-10（所有维度统一）
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
    # 这里可以集成AI大模型进行板块趋势分析
    # 暂时返回一个基于板块内股票表现的简化分析
    try:
        if not stocks_in_sector:
            return 5.0, "该板块股票数据不足"

        # 计算板块内股票的平均技术面、基本面、筹码面评分
        avg_tech = sum(s.get('short_term_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)
        avg_fund = sum(s.get('long_term_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)
        avg_chip = sum(s.get('chip_score', 5) for s in stocks_in_sector) / len(stocks_in_sector)

        # 简单的趋势判断
        trend_score = (avg_tech + avg_fund + avg_chip) / 3

        # 基于评分给出简要分析
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
    """
    获取指定板块的股票列表

    Args:
        stocks_data: 所有股票数据
        industry: 板块/行业名称

    Returns:
        该板块内的股票列表
    """
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
    sector_count = {}  # 板块计数器
    industry_count = {}  # 行业计数器

    for stock in scored_stocks:
        if len(selected) >= n:
            break

        # 过滤掉技术面评分过低或失败的股票（-10为分析失败标记）
        if stock.get('tech', 0) < min_tech_score or stock.get('fund', 0) <= 0:
            continue

        industry = stock.get('industry', '未知')
        matched_sector = stock.get('matched_sector', '未知')

        # 使用更细的粒度：先按matched_sector，再按industry
        group_key = matched_sector if matched_sector and matched_sector != '未知' else industry

        # 检查板块集中度
        current_count = sector_count.get(group_key, 0)
        if current_count >= max_per_sector:
            continue

        selected.append(stock)
        sector_count[group_key] = current_count + 1

    return selected


if __name__ == '__main__':
    try:
        print('[步骤 3/3] 正在生成短线和长线推荐并导出...\n')

        # 获取数据目录
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

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

        # 支持Windows桌面和Linux目录
        desktop_path = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
        os.makedirs(desktop_path, exist_ok=True)

        # 定义2种权重配置（短线和长线）
        # 修复：降低热门板块权重避免板块垄断，提升技术面和基本面的区分作用
        weight_configs = [
            {
                'name': '短线',
                'filename': '推荐_短线.csv',
                'desc': '技术面35% + 筹码20% + 热门板块25% + 基本面20%',
                'tech': 0.35,
                'fund': 0.20,
                'chip': 0.20,
                'sector': 0.25
            },
            {
                'name': '长线',
                'filename': '推荐_长线.csv',
                'desc': '技术面15% + 筹码30% + 基本面35% + 热门板块20%',
                'tech': 0.15,
                'fund': 0.35,
                'chip': 0.30,
                'sector': 0.20
            }
        ]

        print('正在根据权重配置计算综合评分...')

        # 为每种权重配置计算评分并导出前10名
        for config in weight_configs:
            print(f"【{config['name']}推荐】")
            print(f"  权重配置: {config['desc']}")

            # 计算所有股票的综合评分
            scored_stocks = []
            for code, data in stocks.items():
                tech_score = data.get('short_term_score', 5.0)
                fund_score = data.get('long_term_score', 5.0)
                chip_score = data.get('chip_score', 5.0)
                hot_sector_score = data.get('hot_sector_score', 5.0)
                industry = data.get('industry', '未知')
                matched_sector = data.get('matched_sector', '')

                # 计算该配置下的综合评分
                score = calculate_weighted_score(
                    tech_score, fund_score, chip_score, hot_sector_score,
                    config['tech'], config['fund'], config['chip'], config['sector']
                )

                scored_stocks.append({
                    'code': code,
                    'name': data.get('name', 'N/A'),
                    'score': score,
                    'tech': tech_score,
                    'fund': fund_score,
                    'chip': chip_score,
                    'hot_sector': hot_sector_score,
                    'industry': industry,
                    'matched_sector': matched_sector or industry
                })

            # 按评分排序
            scored_stocks.sort(key=lambda x: x['score'], reverse=True)

            # 使用分散化选择，每个板块最多2只
            top_10 = select_diversified_top_n(
                scored_stocks, n=10, max_per_sector=2, min_tech_score=3.0
            )

            # 导出CSV
            csv_path = os.path.join(desktop_path, config['filename'])
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['股票代码', '股票名称', '综合评分', '技术面', '基本面', '筹码面', '热门板块', '所属行业', '匹配板块', '板块涨幅%'])
                for stock in top_10:
                    stock_data = stocks.get(stock['code'], {})
                    matched_sector = stock_data.get('matched_sector', '-')
                    sector_change = stock_data.get('sector_change', 0)

                    writer.writerow([
                        stock['code'],
                        stock['name'],
                        stock['score'],
                        stock['tech'],
                        stock['fund'],
                        stock['chip'],
                        stock['hot_sector'],
                        stock['industry'],
                        matched_sector,
                        f'{sector_change:+.2f}' if sector_change else '-'
                    ])

            print(f"  [OK] 已导出前10名: {config['filename']}")
            print(f"  前3名: ", end='')
            for i, stock in enumerate(top_10[:3]):
                if i > 0:
                    print(", ", end='')
                sector_info = stock.get('matched_sector', stock.get('industry', ''))
                print(f"{stock['code']}({stock['score']:.2f},{sector_info})", end='')
            print('\n')

            # 显示所有10只推荐
            for i, stock in enumerate(top_10):
                print(f"  {i+1:2d}. {stock['code']} {stock['name']:8} "
                      f"综合={stock['score']:.2f} "
                      f"技术={stock['tech']:.1f} 基本={stock['fund']:.1f} "
                      f"筹码={stock['chip']:.1f} 板块={stock['hot_sector']:.2f} "
                      f"行业={stock['industry']} 匹配={stock.get('matched_sector', '-')}")
            print()

        print('='*50)
        print('[OK] 全部导出任务完成！')
        print(f'文件位置: {desktop_path}')
        print('='*50)

    except Exception as e:
        print(f'[FAIL] 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速推荐脚本 - 直接从缓存数据中计算推荐股票
无需连接API，使用最新的评分数据文件即可计算

多因子权重模型：技术形态 (40%) + 财务健康度 (30%) + 资金流向 (20%) + 行业热度 (10%)
安全阀机制：过滤 *ST/退市风险、负市盈率、亏损股

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


def load_comprehensive_data(data_dir):
    """加载 comprehensive_stock_data 合并字典。"""
    all_data = {}
    comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')
    if os.path.exists(comp_file):
        try:
            with open(comp_file, 'r', encoding='utf-8') as f:
                comp = json.load(f)
            for code, data in comp.get('stocks', {}).items():
                all_data[code] = data
        except Exception:
            pass
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
    """加载 ST / 退市风险股票集合。"""
    st_set = set()
    status_file = os.path.join(data_dir, 'stock_status_cache.json')
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            st_set = set(status.get('st_stocks', []))
            st_set |= set(status.get('delisted_stocks', []))
        except Exception:
            pass
    return st_set


def safety_filter(code, name, comprehensive_data, st_stocks):
    """
    安全阀过滤。返回 (通过, 原因)。
    规则：*ST/退市、负市盈率（净利润为负）
    """
    if code in st_stocks:
        return False, '退市风险警告（*ST）'
    if name:
        name_upper = name.upper()
        if any(tag in name_upper for tag in ['*ST', 'ST', '退市']):
            return False, '股票名称含退市风险标记'
    if code in comprehensive_data:
        fin = comprehensive_data[code].get('financial_data', {})
        pe = fin.get('pe_ratio')
        if pe is not None and pe < 0:
            return False, f'市盈率为负({pe:.2f})，最近年报亏损'
    return True, ''


def assess_risk_level(stock, comprehensive_data):
    """评估风险等级与风险提示。"""
    warnings = []
    risk_score = 0

    code = stock.get('code', '')
    tech = stock.get('tech', 5.0)
    fund = stock.get('fund', 5.0)
    chip = stock.get('chip', 5.0)
    sector = stock.get('sector', 5.0)

    if tech < 4.0:
        warnings.append('技术面评分偏低，短期走势疲弱')
        risk_score += 2
    elif tech < 5.0:
        risk_score += 1

    if fund < 4.0:
        warnings.append('基本面评分较低，基本面支撑不足')
        risk_score += 2
    elif fund < 5.0:
        risk_score += 1

    if chip < 4.0:
        warnings.append('筹码集中度偏低，资金分散')
        risk_score += 2
    elif chip < 5.0:
        risk_score += 1

    if code in comprehensive_data:
        fin = comprehensive_data[code].get('financial_data', {})
        pe = fin.get('pe_ratio')
        if pe is not None:
            if pe > 100:
                warnings.append(f'市盈率偏高({pe:.1f})，估值泡沫风险')
                risk_score += 2
            elif pe > 50:
                warnings.append(f'市盈率较高({pe:.1f})，需关注估值回调')
                risk_score += 1
        npg = fin.get('net_profit_growth')
        if npg is not None and npg < 0:
            warnings.append(f'净利润同比下滑({npg:.1f}%)，需警惕财报季波动')
            risk_score += 2

    if sector < 4.0:
        warnings.append('所属板块近期表现低迷')
        risk_score += 1

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
    """生成推荐理由与选股逻辑理论依据。"""
    tech = stock.get('tech', 5.0)
    fund = stock.get('fund', 5.0)
    chip = stock.get('chip', 5.0)
    sector = stock.get('sector', 5.0)

    reasons = []
    theories = []

    if tech >= 7.0:
        reasons.append('技术面强势')
        theories.append('均线多头排列')
    elif tech >= 5.5:
        reasons.append('技术面良好')
        theories.append('短期趋势向上')

    if fund >= 7.0:
        reasons.append('基本面优秀')
        theories.append('低估值修复')
    elif fund >= 5.5:
        reasons.append('基本面稳健')
        theories.append('财务健康')

    if chip >= 7.0:
        reasons.append('筹码高度集中')
        theories.append('主力控盘明显')
    elif chip >= 5.5:
        reasons.append('筹码结构良好')
        theories.append('资金流向正面')

    if sector >= 7.0:
        reasons.append('板块热度高')
        theories.append('行业景气度上行')
    elif sector >= 5.5:
        reasons.append('板块有一定热度')
        theories.append('行业轮动受益')

    reason_str = '；'.join(reasons) if reasons else '综合评分靠前'
    theory_str = ' + '.join(theories) if theories else '多因子综合评分'

    return reason_str, theory_str


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

    # ── 加载安全阀数据 ──
    comprehensive_data = load_comprehensive_data(data_dir)
    st_stocks = load_st_stocks(data_dir)

    # ── 安全阀前置过滤 ──
    filtered_stocks = {}
    filter_count = 0
    for code, data in stocks.items():
        name = data.get('name', '')
        passed, reason = safety_filter(code, name, comprehensive_data, st_stocks)
        if passed:
            filtered_stocks[code] = data
        else:
            filter_count += 1

    # ── 多因子权重配置 ──
    # 技术形态 (40%) + 财务健康度 (30%) + 资金流向 (20%) + 行业热度 (10%)
    weight_configs = {
        'short': {
            'name': '短线',
            'tech': 0.40, 'fund': 0.30, 'chip': 0.20, 'sector': 0.10
        },
        'long': {
            'name': '长线',
            'tech': 0.20, 'fund': 0.35, 'chip': 0.30, 'sector': 0.15
        }
    }

    weights = weight_configs.get(strategy, weight_configs['short'])

    # 计算所有股票的综合评分（使用过滤后的股票池）
    scored = []
    for code, data in filtered_stocks.items():
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

    # ── 为每只推荐附加风险等级与推荐理由 ──
    for stock in top_n:
        risk_level, risk_warnings = assess_risk_level(stock, comprehensive_data)
        reason, theory = generate_recommendation_reason(stock)
        stock['risk_level'] = risk_level
        stock['risk_warnings'] = risk_warnings
        stock['risk_tip'] = '；'.join(risk_warnings)
        stock['reason'] = reason
        stock['theory'] = theory

    return top_n, weights, file_date, filename, filter_count


def main():
    parser = argparse.ArgumentParser(description='快速股票推荐（含安全阀过滤与风险评估）')
    parser.add_argument('-n', type=int, default=3, help='推荐数量 (默认3)')
    parser.add_argument('-t', '--type', choices=['short', 'long'], default='short',
                        help='策略类型: short=短线(默认), long=长线')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细评分')
    args = parser.parse_args()

    result = recommend(n=args.n, strategy=args.type, verbose=args.verbose)
    if not result:
        return

    top_n, weights, file_date, filename, filter_count = result

    strategy_name = weights['name']
    print(f'\n{"="*70}')
    print(f'📊 {strategy_name}推荐 TOP {args.n} | 数据日期: {file_date}')
    print(f'   多因子权重: 技术形态{weights["tech"]*100:.0f}% + 财务健康度{weights["fund"]*100:.0f}% '
          f'+ 资金流向{weights["chip"]*100:.0f}% + 行业热度{weights["sector"]*100:.0f}%')
    if filter_count > 0:
        print(f'   🛡️ 安全阀: 已过滤 {filter_count} 只风险股票（*ST/退市/亏损）')
    print(f'{"="*70}')

    for i, stock in enumerate(top_n, 1):
        sector_info = stock.get('matched_sector') or stock.get('industry', '')
        change = stock.get('sector_change', 0)
        change_str = f'{change:+.1f}%' if change else ''
        risk_level = stock.get('risk_level', '-')
        risk_emoji = {'低': '🟢', '中': '🟡', '高': '🔴'}.get(risk_level, '⚪')

        print(f'\n  🏆 第{i}名: {stock["code"]} {stock["name"]}')
        print(f'     综合评分: {stock["score"]:.2f}/10  |  风险等级: {risk_emoji} {risk_level}')
        print(f'     行业: {stock["industry"]} | 匹配板块: {sector_info} {change_str}')
        print(f'     推荐理由: {stock.get("reason", "-")}')
        print(f'     ⚠️ 风险提示: {stock.get("risk_tip", "-")}')
        print(f'     📐 选股逻辑: {stock.get("theory", "-")}')

        if args.verbose:
            print(f'     ├─ 技术形态: {stock["tech"]:.1f}/10')
            print(f'     ├─ 财务健康度: {stock["fund"]:.1f}/10')
            print(f'     ├─ 资金流向: {stock["chip"]:.1f}/10')
            print(f'     └─ 行业热度: {stock["sector"]:.2f}/10')

    print(f'\n{"="*70}')
    print(f'【选股逻辑理论依据】')
    print(f'  1. 安全阀: 剔除 *ST/退市风险 + 市盈率为负（年报亏损）的股票')
    print(f'  2. 多因子模型: 技术形态(40%) + 财务健康度(30%) + 资金流向(20%) + 行业热度(10%)')
    print(f'  3. 分散化: 每板块最多2只，避免集中度过高')
    print(f'{"="*70}')
    print(f'⚠️ 以上推荐仅供参考，不构成投资建议')
    print(f'   数据来源: {filename}')
    print(f'{"="*70}\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板推荐股票并导出CSV
分为短线推荐和长线推荐两部分

多因子权重模型：技术形态 (40%) + 财务健康度 (30%) + 资金流向 (20%) + 行业热度 (10%)
安全阀机制：过滤 *ST/退市风险、负市盈率、亏损股
"""
import csv
import json
import os
import sys


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
            if pe > 100:
                warnings.append(f'市盈率偏高({pe:.1f})，估值泡沫风险')
                risk_score += 2
            elif pe > 50:
                warnings.append(f'市盈率较高({pe:.1f})，需关注估值回调')
                risk_score += 1

        if pb is not None and pb > 10:
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

        # ── 多因子权重配置 ──
        # 技术形态 (40%) + 财务健康度 (30%) + 资金流向 (20%) + 行业热度 (10%)
        weight_configs = [
            {
                'name': '短线',
                'filename': '推荐_短线.csv',
                'desc': '技术形态40% + 财务健康度30% + 资金流向20% + 行业热度10%',
                'tech': 0.40,
                'fund': 0.30,
                'chip': 0.20,
                'sector': 0.10
            },
            {
                'name': '长线',
                'filename': '推荐_长线.csv',
                'desc': '技术形态20% + 财务健康度35% + 资金流向30% + 行业热度15%',
                'tech': 0.20,
                'fund': 0.35,
                'chip': 0.30,
                'sector': 0.15
            }
        ]

        print('正在根据多因子权重模型计算综合评分...')
        print('  模型说明: 技术形态=short_term_score, 财务健康度=long_term_score, '
              '资金流向=chip_score, 行业热度=hot_sector_score\n')

        # 为每种权重配置计算评分并导出前10名
        for config in weight_configs:
            print(f"【{config['name']}推荐】")
            print(f"  权重配置: {config['desc']}")

            # 计算所有股票的综合评分（使用过滤后的股票池）
            scored_stocks = []
            for code, data in filtered_stocks.items():
                tech_score = data.get('short_term_score', 5.0)
                fund_score = data.get('long_term_score', 5.0)
                chip_score = data.get('chip_score', 5.0)
                hot_sector_score = data.get('hot_sector_score', 5.0)
                industry = data.get('industry', '未知')
                matched_sector = data.get('matched_sector', '')

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

            # ── 为每只推荐股票计算风险等级与推荐理由 ──
            for stock in top_10:
                risk_level, risk_warnings = assess_risk_level(stock, comprehensive_data)
                reason, theory = generate_recommendation_reason(stock)
                stock['risk_level'] = risk_level
                stock['risk_warnings'] = risk_warnings
                stock['risk_tip'] = '；'.join(risk_warnings)
                stock['reason'] = reason
                stock['theory'] = theory

            # 导出CSV（新增：风险等级、风险提示、推荐理由、选股逻辑）
            csv_path = os.path.join(desktop_path, config['filename'])
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    '股票代码', '股票名称', '综合评分',
                    '技术形态', '财务健康度', '资金流向', '行业热度',
                    '所属行业', '匹配板块', '板块涨幅%',
                    '风险等级', '风险提示', '推荐理由', '选股逻辑'
                ])
                for stock in top_10:
                    stock_data = filtered_stocks.get(stock['code'], {})
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
                        f'{sector_change:+.2f}' if sector_change else '-',
                        stock['risk_level'],
                        stock['risk_tip'],
                        stock['reason'],
                        stock['theory']
                    ])

            print(f"  [OK] 已导出前10名: {config['filename']}")
            print(f"  前3名: ", end='')
            for i, stock in enumerate(top_10[:3]):
                if i > 0:
                    print(", ", end='')
                sector_info = stock.get('matched_sector', stock.get('industry', ''))
                print(f"{stock['code']}({stock['score']:.2f},{sector_info})", end='')
            print('\n')

            # 显示所有10只推荐（含风险等级与推荐理由）
            for i, stock in enumerate(top_10):
                rl = stock.get('risk_level', '-')
                print(f"  {i+1:2d}. {stock['code']} {stock['name']:8} "
                      f"综合={stock['score']:.2f} "
                      f"技术={stock['tech']:.1f} 财务={stock['fund']:.1f} "
                      f"资金={stock['chip']:.1f} 热度={stock['hot_sector']:.2f} "
                      f"风险={rl} "
                      f"行业={stock['industry']}")
                print(f"      推荐理由: {stock.get('reason', '-')}")
                print(f"      风险提示: {stock.get('risk_tip', '-')}")
                print(f"      选股逻辑: {stock.get('theory', '-')}")
            print()

        # ── 输出选股逻辑理论依据 ──
        print('='*60)
        print('【选股逻辑理论依据】')
        print('  1. 安全阀过滤: 剔除 *ST/退市风险、市盈率为负（年报亏损）的股票')
        print('  2. 多因子权重: 技术形态(40%) + 财务健康度(30%) + 资金流向(20%) + 行业热度(10%)')
        print('  3. 技术形态: 基于均线排列、MACD、RSI等指标评分')
        print('  4. 财务健康度: 基于市盈率、市净率、营收增长等指标评分')
        print('  5. 资金流向: 基于筹码集中度、股东结构、资金流入/流出评分')
        print('  6. 行业热度: 基于板块近3日涨跌幅与行业景气度评分')
        print('  7. 分散化: 每个板块最多推荐2只，避免集中度过高')
        print('='*60)
        print('[OK] 全部导出任务完成！')
        print(f'文件位置: {desktop_path}')
        print('='*60)

    except Exception as e:
        print(f'[FAIL] 导出失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

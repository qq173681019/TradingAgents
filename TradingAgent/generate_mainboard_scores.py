#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成主板股票基础评分数据  
供 BAT 文件调用 - 基于第1步已更新的数据重新计算评分

修复说明 (2026-03-25):
1. 修复行业字段问题 - 从 comprehensive_stock_data 获取真正的行业名称
2. 修复网络代理问题 - 添加禁用代理和重试机制
3. 修复板块匹配逻辑 - 改进模糊匹配算法
4. 添加多数据源降级处理
"""
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# 导入主程序
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 禁用代理，避免网络连接问题
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# 尝试移除 requests 库的代理设置
try:
    import requests
    requests.sessions.Session.proxies = {}
except:
    pass


def get_sector_changes_3d():
    """
    获取各行业板块近3日涨幅数据
    使用akshare获取板块行情数据
    
    Returns:
        dict: {行业名称: 3日涨幅百分比}
    """
    sector_changes = {}
    
    try:
        import akshare as ak
        
        print('[INFO] 正在获取板块近3日涨幅数据...')
        print('[INFO] 已禁用代理，直接连接...')
        
        # 获取行业板块行情数据
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                # 获取行业板块最新行情
                df_sector = ak.stock_board_industry_name_em()
                if df_sector is not None and not df_sector.empty:
                    print(f'[OK] 获取到 {len(df_sector)} 个行业板块')
                    
                    # 遍历获取每个板块的3日涨幅
                    for idx, row in df_sector.iterrows():
                        try:
                            sector_name = str(row.get('板块名称', '')).strip()
                            if not sector_name:
                                continue
                            
                            # 获取板块K线数据计算3日涨幅
                            df_kline = ak.stock_board_industry_hist_em(
                                symbol=sector_name, 
                                period="日k",
                                start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
                                end_date=datetime.now().strftime("%Y%m%d")
                            )
                            
                            if df_kline is not None and len(df_kline) >= 4:
                                latest_close = float(df_kline.iloc[-1]['收盘'])
                                close_3d_ago = float(df_kline.iloc[-4]['收盘'])
                                change_3d = (latest_close - close_3d_ago) / close_3d_ago * 100
                                sector_changes[sector_name] = round(change_3d, 2)
                            elif df_kline is not None and len(df_kline) >= 2:
                                # 至少有2天数据，计算当前涨幅
                                latest_close = float(df_kline.iloc[-1]['收盘'])
                                prev_close = float(df_kline.iloc[-2]['收盘'])
                                change = (latest_close - prev_close) / prev_close * 100
                                sector_changes[sector_name] = round(change, 2)
                            
                            time.sleep(0.05)  # 避免请求过快
                            
                        except Exception as e:
                            continue
                    
                    print(f'[OK] 成功计算 {len(sector_changes)} 个板块的涨幅')
                    break
                    
            except Exception as e:
                retry_count += 1
                print(f'[WARN] 第{retry_count}次获取失败: {e}')
                if retry_count < max_retries:
                    print(f'[INFO] 等待3秒后重试...')
                    time.sleep(3)
                else:
                    print(f'[ERROR] 已达最大重试次数，使用备用方案')
        
        # 如果获取失败，使用默认的热门板块数据
        if not sector_changes:
            print('[WARN] 无法获取实时板块数据，使用默认热门板块列表')
            # 常见热门板块及其默认评分
            default_hot_sectors = {
                '半导体': 8.0,
                '人工智能': 8.5,
                '机器人': 8.0,
                '算力': 8.0,
                '消费电子': 7.0,
                '新能源汽车': 7.5,
                '光伏': 6.5,
                '储能': 7.0,
                '军工': 6.5,
                '医药': 6.0,
                '白酒': 6.0,
                '银行': 5.0,
                '证券': 5.5,
                '保险': 5.0,
                '房地产': 4.0,
                '煤炭': 5.5,
                '石油': 5.0,
                '有色金属': 6.5,
                '钢铁': 4.5,
                '化工': 5.5,
                '电力': 6.0,
                '通信': 7.0,
                '计算机': 7.5,
                '传媒': 6.5,
                '教育': 5.5,
            }
            sector_changes = default_hot_sectors
            print(f'[INFO] 使用默认热门板块数据，共 {len(sector_changes)} 个')
            
    except ImportError:
        print('[WARN] akshare未安装，使用默认板块数据')
        sector_changes = {
            '半导体': 8.0, '人工智能': 8.5, '机器人': 8.0,
            '新能源汽车': 7.5, '光伏': 6.5, '医药': 6.0
        }
    except Exception as e:
        print(f'[WARN] 获取板块数据异常: {e}，使用默认数据')
        sector_changes = {
            '半导体': 8.0, '人工智能': 8.5, '机器人': 8.0,
            '新能源汽车': 7.5, '光伏': 6.5, '医药': 6.0
        }
    
    return sector_changes


def get_real_industry(stock_code, stock_data, comprehensive_data=None):
    """
    获取股票的真正行业名称

    Args:
        stock_code: 股票代码
        stock_data: 从 batch_stock_scores 获取的股票数据
        comprehensive_data: 从 comprehensive_stock_data 获取的详细数据

    Returns:
        str: 真正的行业名称
    """
    industry = None
    method_used = None

    # 方法1: 从 comprehensive_stock_data 获取
    # FIX: 修复数据结构访问错误
    if comprehensive_data and 'stocks' in comprehensive_data and stock_code in comprehensive_data['stocks']:
        try:
            comp_data = comprehensive_data['stocks'][stock_code]

            # 尝试 industry_concept 字段
            if 'industry_concept' in comp_data and comp_data['industry_concept']:
                ic = comp_data['industry_concept']
                if isinstance(ic, dict):
                    industry = ic.get('industry') or ic.get('industry_name')
                    if industry and isinstance(industry, str):
                        if industry not in ['未知', '', '传统制造业', '新上市企业', '深圳主板']:
                            method_used = 'comprehensive.industry_concept'
                            return industry

            # 尝试 basic_info 字段
            if 'basic_info' in comp_data and comp_data['basic_info']:
                bi = comp_data['basic_info']
                if isinstance(bi, dict):
                    industry = bi.get('industry')
                    if industry and isinstance(industry, str):
                        if industry not in ['未知', '', '传统制造业', '新上市企业', '深圳主板']:
                            method_used = 'comprehensive.basic_info'
                            return industry
        except Exception as e:
            if stock_code in ['000001', '000002', '600519']:
                print(f'[DEBUG] {stock_code} 从comprehensive获取行业信息失败: {e}')

    # 方法2: 从 stock_data 获取
    if stock_data:
        try:
            if 'industry_concept' in stock_data and stock_data['industry_concept']:
                ic = stock_data['industry_concept']
                if isinstance(ic, dict):
                    industry = ic.get('industry') or ic.get('industry_name')
                    if industry and isinstance(industry, str):
                        if industry not in ['未知', '', '传统制造业', '新上市企业', '深圳主板']:
                            method_used = 'stock_data.industry_concept'
                            return industry
        except Exception as e:
            pass

    # 方法3: 根据股票代码推断（保底方案）
    # 加载扩展的行业映射表
    try:
        map_file = os.path.join(os.path.dirname(__file__), 'extended_industry_map.json')
        if os.path.exists(map_file):
            with open(map_file, 'r', encoding='utf-8') as f:
                code_industry_map = json.load(f)
        else:
            # 如果文件不存在，使用基础映射
            code_industry_map = {
                '000001': '银行',  # 平安银行
                '000002': '房地产',  # 万科A
                '000333': '家电',  # 美的集团
                '000651': '家电',  # 格力电器
                '000858': '白酒',  # 五粮液
                '002594': '新能源汽车',  # 比亚迪
                '600000': '银行',  # 浦发银行
                '600036': '银行',  # 招商银行
                '600519': '白酒',  # 贵州茅台
                '600900': '电力',  # 长江电力
                '601318': '保险',  # 中国平安
                '601398': '银行',  # 工商银行
                '601857': '石油',  # 中国石油
                '601888': '免税',  # 中国中免
            }
    except Exception as e:
        code_industry_map = {}

    if stock_code in code_industry_map:
        return code_industry_map[stock_code]

    # 方法4: 使用 akshare 实时查询（最后手段）
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                if '行业' in str(row.get('item', '')):
                    method_used = 'akshare'
                    return row.get('value', '未知')
    except Exception as e:
        pass

    # 记录调试信息
    if stock_code in ['000001', '000002', '600519']:
        print(f'[DEBUG] {stock_code} 行业信息获取失败，method_used={method_used}，返回"未知"')

    return '未知'


def match_sector_score(industry, sector_changes, hot_sectors_list=None):
    """
    根据行业名称匹配板块评分 - 改进版
    使用对数映射提高区分度，让大涨幅板块获得更高分数

    Args:
        industry: 股票的行业名称
        sector_changes: 板块涨幅数据 {板块名: 涨幅}
        hot_sectors_list: 热门板块列表（已废弃，保留参数以兼容）

    Returns:
        tuple: (板块评分, 匹配的板块名, 板块涨幅)
    """
    if not industry or industry == '未知':
        return 5.0, None, 0

    industry_lower = industry.lower()
    best_score = 5.0
    matched_sector = None
    matched_change = 0

    # 行业名称映射表
    industry_alias = {
        '银行': ['银行', '金融', '商业银行'],
        '房地产': ['房地产', '地产', '物业'],
        '白酒': ['白酒', '酒类', '酿酒'],
        '家电': ['家电', '家用电器', '白色家电'],
        '汽车': ['汽车', '整车', '新能源汽车', '新能源车'],
        '半导体': ['半导体', '芯片', '集成电路', '晶圆'],
        '医药': ['医药', '医药生物', '化学制药', '中药', '生物制药'],
        '电力': ['电力', '电力设备', '电网'],
        '煤炭': ['煤炭', '煤化工'],
        '石油': ['石油', '石化', '油气'],
        '钢铁': ['钢铁', '特钢'],
        '有色金属': ['有色金属', '铜', '铝', '锂', '稀土'],
        '化工': ['化工', '化学制品', '化纤'],
        '通信': ['通信', '5G', '光通信'],
        '计算机': ['计算机', 'IT', '软件', '信息技术'],
        '传媒': ['传媒', '影视', '游戏'],
        '军工': ['军工', '国防'],
        '新能源': ['新能源', '光伏', '风电', '储能'],
        '人工智能': ['人工智能', 'AI', '算力'],
        '机器人': ['机器人', '工业机器人', '服务机器人'],
    }

    # FIX: 改进的匹配逻辑 - 使用最长匹配优先
    best_direct_match = None
    best_direct_length = 0

    # 先进行直接匹配（优先级最高）
    for sector_name, change in sector_changes.items():
        sector_lower = sector_name.lower()

        # 检查行业名包含板块名
        if sector_name in industry:
            if len(sector_name) > best_direct_length:
                best_direct_length = len(sector_name)
                best_direct_match = (sector_name, change)

        # 检查板块名包含行业名
        elif industry in sector_name:
            if len(industry) > best_direct_length:
                best_direct_length = len(industry)
                best_direct_match = (sector_name, change)

    if best_direct_match:
        matched_sector, matched_change = best_direct_match
    else:
        # 别名匹配（计算匹配度）
        best_alias_match = None
        best_alias_score = 0

        for sector_name, change in sector_changes.items():
            sector_lower = sector_name.lower()

            for key, aliases in industry_alias.items():
                # 计算行业在别名中的匹配度
                industry_match_score = sum(1 for a in aliases if a in industry)

                # 计算板块在别名中的匹配度
                sector_match_score = sum(1 for a in aliases if a in sector_name)

                # 如果两边都匹配，计算总分
                if industry_match_score > 0 and sector_match_score > 0:
                    total_score = industry_match_score + sector_match_score

                    # 优先选择匹配度最高的
                    if total_score > best_alias_score:
                        best_alias_score = total_score
                        best_alias_match = (sector_name, change)

                    # 如果匹配度相同，选择匹配词更长的
                    elif total_score == best_alias_score:
                        if len(sector_name) > len(best_alias_match[0]):
                            best_alias_match = (sector_name, change)

        if best_alias_match:
            matched_sector, matched_change = best_alias_match

    # FIX: 根据涨幅计算评分 - 使用对数映射提高区分度
    if matched_sector:
        if matched_change > 0:
            # 对数映射：涨幅1%=5分，涨幅10%=9.1分，涨幅20%=11分
            best_score = 5.0 + math.log10(1 + matched_change * 0.5) * 6
        else:
            # 负涨幅线性递减
            best_score = 5.0 + matched_change * 0.6

        best_score = round(max(1.0, min(15.0, best_score)), 2)  # 范围：1-15分

    # 移除热门板块额外加分（避免重复计算，对数映射已经体现了板块热度）

    return best_score, matched_sector, matched_change


if __name__ == '__main__':
    try:
        print('[步骤 2/3] 正在重新计算主板股票基础评分...')
        print('说明：基于第1步更新的数据，重新计算技术面、基本面、筹码面、热门板块评分')
        print('注意：使用已缓存的数据进行计算，不重新获取数据\n')
        
        # 导入主程序类
        print('正在初始化分析器...')
        from a_share_gui_compatible import AShareAnalyzerGUI
        # FIX: 传入None而不是创建Tk实例，避免tkinter依赖问题
        analyzer = AShareAnalyzerGUI(None)
        
        # 加载综合股票数据
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
        
        print('正在加载股票列表...')
        # 加载所有股票代码
        score_file = os.path.join(data_dir, 'batch_stock_scores_none.json')
        if not os.path.exists(score_file):
            score_file = os.path.join(data_dir, 'batch_stock_scores.json')
        
        if not os.path.exists(score_file):
            print('错误：没有找到股票数据文件')
            sys.exit(1)
        
        with open(score_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict) and 'scores' in data:
                all_stocks = data['scores']
            else:
                all_stocks = data
        
        if not all_stocks:
            print('错误：没有找到股票数据')
            sys.exit(1)
        
        # 加载 comprehensive_stock_data 获取真正的行业信息
        print('正在加载详细行业数据...')
        comprehensive_data = {}
        comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')
        if os.path.exists(comp_file):
            try:
                with open(comp_file, 'r', encoding='utf-8') as f:
                    comprehensive_data = json.load(f)
                print(f'[OK] 加载了 {len(comprehensive_data)} 只股票的详细数据')
            except Exception as e:
                print(f'[WARN] 加载 comprehensive_stock_data 失败: {e}')
        
        # 过滤主板股票
        main_board_codes = [
            code for code in all_stocks.keys()
            if code.startswith(('600', '601', '603', '000', '001', '002'))
        ]
        print(f'主板股票总数: {len(main_board_codes)} 只\n')
        
        # 加载热门板块列表
        print('正在加载热门板块数据...')
        hot_sectors_list = set()
        if 'hot_sectors' in data:
            hot_sectors_list = set(data.get('hot_sectors', []))
            print(f'热门板块数量: {len(hot_sectors_list)} 个')
        else:
            print('[WARN] 未找到热门板块数据')
        
        # 获取板块涨幅数据
        print('\n[INFO] 正在计算板块热度...')
        sector_changes_3d = get_sector_changes_3d()
        if sector_changes_3d:
            top_sectors = sorted(sector_changes_3d.items(), key=lambda x: x[1], reverse=True)[:10]
            print('[INFO] 热门板块涨幅排名:')
            for name, change in top_sectors:
                print(f'  {name}: {change:+.2f}%' if isinstance(change, float) else f'  {name}: {change}')
        
        # 重新计算每只股票的基础评分
        print('\n' + '='*60)
        print('开始重新计算评分（基于缓存数据）...')
        print('='*60)
        
        main_board_stocks = {}
        success_count = 0
        failed_count = 0
        start_time = time.time()
        
        # 统计热门板块评分分布
        hot_score_dist = {}
        
        for i, code in enumerate(main_board_codes, 1):
            try:
                if i % 50 == 0 or i == 1:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    print(f'进度: {i}/{len(main_board_codes)} ({i/len(main_board_codes)*100:.1f}%) '
                          f'- 速度: {rate:.1f}只/秒 - 成功: {success_count}, 失败: {failed_count}')
                
                stock_name = all_stocks[code].get('name', analyzer.get_stock_name(code) or 'N/A')
                
                # 1. 技术面和基本面评分
                short_prediction, medium_prediction, long_prediction = analyzer.generate_investment_advice(code, use_cache=True)
                
                if short_prediction.get('failure_reason'):
                    failed_count += 1
                    if i % 100 == 0:
                        print(f'  {code} 失败: {short_prediction.get("failure_reason")}')
                    continue
                
                tech_score = short_prediction.get('score', short_prediction.get('technical_score', 5.0))
                fund_score = long_prediction.get('score', long_prediction.get('fundamental_score', 5.0))
                
                # 2. 筹码面评分
                chip_score = 5.0
                if analyzer.chip_analyzer:
                    try:
                        chip_result = analyzer.chip_analyzer.analyze_stock(code)
                        if not chip_result.get('error') and chip_result.get('health_score', 0) > 0:
                            chip_score = chip_result.get('health_score', 5.0)
                    except Exception:
                        pass
                
                # 3. 热门板块评分 - 使用修复后的逻辑
                # 获取真正的行业名称
                real_industry = get_real_industry(
                    code, 
                    all_stocks.get(code, {}),
                    comprehensive_data
                )
                
                # 匹配板块评分
                hot_sector_score, matched_sector, sector_change = match_sector_score(
                    real_industry,
                    sector_changes_3d,
                    hot_sectors_list
                )
                
                # 统计热门评分分布
                score_key = int(hot_sector_score)
                hot_score_dist[score_key] = hot_score_dist.get(score_key, 0) + 1
                
                # 显示前10个股票的详细信息
                if i <= 10:
                    print(f'  {code} {stock_name:8} 行业: {real_industry:10} '
                          f'匹配: {matched_sector or "无":10} 涨幅: {sector_change:+.1f}% '
                          f'评分: {hot_sector_score}')
                
                # 保存详细评分数据
                stock_data = {
                    'code': code,
                    'name': stock_name,
                    'short_term_score': round(float(tech_score), 2),
                    'long_term_score': round(float(fund_score), 2),
                    'chip_score': round(float(chip_score), 2),
                    'hot_sector_score': round(float(hot_sector_score), 2),
                    'industry': real_industry,  # 使用真正的行业名称
                    'matched_sector': matched_sector,  # 匹配的板块
                    'sector_change': sector_change  # 板块涨幅
                }
                
                main_board_stocks[code] = stock_data
                success_count += 1
                
            except Exception as e:
                if i % 100 == 0:
                    print(f'  {code} 异常: {e}')
                failed_count += 1
                continue
        
        elapsed = time.time() - start_time
        print('\n' + '='*60)
        print(f'计算完成！耗时 {elapsed:.2f}秒')
        print(f'成功: {success_count} 只, 失败: {failed_count} 只')
        print(f'平均速度: {success_count/elapsed:.2f} 只/秒')
        print('='*60)
        
        # 显示评分分布统计
        if main_board_stocks:
            tech_scores = [s.get('short_term_score', 5.0) for s in main_board_stocks.values()]
            fund_scores = [s.get('long_term_score', 5.0) for s in main_board_stocks.values()]
            chip_scores = [s.get('chip_score', 5.0) for s in main_board_stocks.values()]
            hot_scores = [s.get('hot_sector_score', 5.0) for s in main_board_stocks.values()]
            
            print(f'\n评分统计:')
            print(f'  技术面: 平均 {sum(tech_scores)/len(tech_scores):.2f}, '
                  f'范围 [{min(tech_scores):.1f}, {max(tech_scores):.1f}]')
            print(f'  基本面: 平均 {sum(fund_scores)/len(fund_scores):.2f}, '
                  f'范围 [{min(fund_scores):.1f}, {max(fund_scores):.1f}]')
            print(f'  筹码面: 平均 {sum(chip_scores)/len(chip_scores):.2f}, '
                  f'范围 [{min(chip_scores):.1f}, {max(chip_scores):.1f}]')
            print(f'  热门板块: 平均 {sum(hot_scores)/len(hot_scores):.2f}, '
                  f'范围 [{min(hot_scores):.1f}, {max(hot_scores):.1f}]')
            print(f'  热门板块评分分布: {dict(sorted(hot_score_dist.items()))}')
        
        # 保存主板基础评分数据
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(data_dir, f'batch_stock_scores_optimized_主板_{timestamp}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(main_board_stocks, f, ensure_ascii=False, indent=2)
        
        print(f'\n[OK] 主板基础评分数据已保存到: {os.path.basename(output_file)}')
        print(f'[CHART] 共计算 {len(main_board_stocks)} 只主板股票的基础评分数据')
        print(f'[IDEA] 下一步将根据不同权重配置计算综合评分并导出CSV到桌面')
        
        # FIX: 不需要清理root，因为使用的是None而不是Tk实例
        # root.destroy()
        
    except Exception as e:
        print(f'[FAIL] 评分计算失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

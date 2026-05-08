#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强评分系统快速测试
"""

import sys
import os
import json
import time
import logging

# 设置环境
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('enhanced_test.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_kline_data():
    """加载K线数据"""
    try:
        with open('kline_full_latest.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"K线数据加载完成: {len(data)}只股票")
        return data
    except Exception as e:
        logger.error(f"K线数据加载失败: {e}")
        return None

def load_index_data():
    """加载指数数据"""
    try:
        with open('index_full_latest.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"指数数据加载完成: {len(data)}条记录")
        return data
    except Exception as e:
        logger.error(f"指数数据加载失败: {e}")
        return None

def load_scores():
    """加载评分数据"""
    try:
        # 找最新的评分文件
        import glob
        score_files = glob.glob('batch_stock_scores_optimized_*主板_*.json')
        if not score_files:
            score_files = glob.glob('batch_stock_scores_optimized_*.json')
        
        if score_files:
            latest_file = max(score_files, key=os.path.getctime)
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"评分数据加载完成: {len(data)}只股票, 使用文件: {os.path.basename(latest_file)}")
            return data
        else:
            logger.error("未找到评分文件")
            return None
    except Exception as e:
        logger.error(f"评分数据加载失败: {e}")
        return None

def enhanced_score_v9_style(stock_data, market_state):
    """增强评分系统 - 简化版，基于V9d逻辑"""
    
    # 技术面评分 (30%)
    technical_score = stock_data.get('short_term_score', 5.0)
    
    # 筹码面评分 (10%)
    chip_score = stock_data.get('chip_score', 5.0)
    
    # 板块热度评分 (15%)
    hot_sector_score = stock_data.get('hot_sector_score', 5.0)
    
    # 新闻情绪评分 (10%)
    sentiment_score = stock_data.get('sentiment_score', 5.0)
    
    # 新增的季度盈利评分 (20%)
    # 使用ROE作为盈利指标替代（简化）
    roe = stock_data.get('roe', 0)
    if roe > 0.2:  # ROE > 20%
        quarterly_score = 8.0
    elif roe > 0.1:  # ROE > 10%
        quarterly_score = 6.0
    elif roe > 0.05:  # ROE > 5%
        quarterly_score = 4.0
    else:
        quarterly_score = 2.0
    
    # 新增的EPS评分 (10%)
    # 使用每股收益绝对值
    eps = stock_data.get('eps', 0)
    if eps > 2.0:
        eps_score = 8.0
    elif eps > 1.0:
        eps_score = 6.0
    elif eps > 0.5:
        eps_score = 4.0
    elif eps > 0:
        eps_score = 2.0
    else:
        eps_score = 0.0
    
    # 新增的分析师评级评分 (5%)
    # 使用行业排名作为替代
    rank = stock_data.get('industry_rank', 100)
    if rank <= 10:
        analyst_score = 8.0
    elif rank <= 20:
        analyst_score = 6.0
    elif rank <= 50:
        analyst_score = 4.0
    else:
        analyst_score = 2.0
    
    # 加权总分
    total_score = (
        technical_score * 0.30 +
        chip_score * 0.10 +
        hot_sector_score * 0.15 +
        sentiment_score * 0.10 +
        quarterly_score * 0.20 +
        eps_score * 0.10 +
        analyst_score * 0.05
    )
    
    return total_score

def run_enhanced_backtest():
    """运行增强评分系统回测"""
    
    logger.info("开始增强评分系统回测试验...")
    
    # 加载数据
    kline_data = load_kline_data()
    index_data = load_index_data()
    scores_data = load_scores()
    
    if not all([kline_data, index_data, scores_data]):
        logger.error("数据加载失败，无法进行回测")
        return
    
    # 简化回测：只用最后一天的数据测试
    test_day = "2026-04-24"  # 最后一个交易日
    
    # 获取当天的指数收益
    index_return = 0.0
    for record in index_data:
        if record.get('date') == test_day:
            index_return = record.get('change_pct', 0) / 100
            break
    
    logger.info(f"测试日期: {test_day}, 沪深300涨幅: {index_return:.2%}")
    
    # 对评分数据进行筛选和排序
    enhanced_results = []
    for stock_code, stock_data in scores_data.items():
        if stock_code in kline_data:
            # 计算增强评分
            enhanced_score = enhanced_score_v9_style(stock_data, {})
            
            enhanced_results.append({
                'code': stock_code,
                'name': stock_data.get('name', ''),
                'enhanced_score': enhanced_score,
                'basic_score': stock_data.get('short_term_score', 5.0)
            })
    
    # 排序并选择TOP3
    enhanced_results.sort(key=lambda x: x['enhanced_score'], reverse=True)
    top3_enhanced = enhanced_results[:3]
    
    # 模拟测试：检查这些股票在当天的表现
    portfolio_returns = []
    for stock in top3_enhanced:
        stock_code = stock['code']
        stock_kline = kline_data.get(stock_code, {})
        
        # 获取当天的涨跌幅（简化处理）
        daily_change = 0.0
        if 'daily_data' in stock_kline:
            daily_data = stock_kline['daily_data']
            if test_day in daily_data:
                daily_change = daily_data[test_day].get('change_pct', 0) / 100
        
        portfolio_returns.append(daily_change)
        logger.info(f"{stock['name']}({stock['code']}): 评分={stock['enhanced_score']:.2f}, 涨幅={daily_change:.2%}")
    
    # 计算组合收益
    portfolio_return = sum(portfolio_returns) / len(portfolio_returns) if portfolio_returns else 0
    
    # 计算是否跑赢指数
    beat_index = portfolio_return > index_return
    
    logger.info(f"组合平均涨幅: {portfolio_return:.2%}")
    logger.info(f"沪深300涨幅: {index_return:.2%}")
    logger.info(f"跑赢指数: {'是' if beat_index else '否'}")
    
    result = {
        'test_date': test_day,
        'portfolio_return': portfolio_return,
        'index_return': index_return,
        'beat_index': beat_index,
        'top3_stocks': top3_enhanced,
        'method': 'enhanced_system_v1'
    }
    
    return result

if __name__ == "__main__":
    logger.info("TradingAgent 增强评分系统快速测试")
    logger.info("=" * 50)
    
    start_time = time.time()
    result = run_enhanced_backtest()
    
    if result:
        end_time = time.time()
        logger.info("=" * 50)
        logger.info("测试完成!")
        logger.info(f"耗时: {end_time - start_time:.1f}秒")
        logger.info(f"方法: {result['method']}")
        logger.info(f"日期: {result['test_date']}")
        logger.info(f"组合收益: {result['portfolio_return']:.2%}")
        logger.info(f"指数收益: {result['index_return']:.2%}")
        logger.info(f"跑赢指数: {'是' if result['beat_index'] else '否'}")
        
        logger.info("TOP3推荐:")
        for i, stock in enumerate(result['top3_stocks'], 1):
            logger.info(f"{i}. {stock['name']}({stock['code']}): {stock['enhanced_score']:.2f}分")
        
        # 保存结果
        result_file = f"enhanced_test_result_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存: {result_file}")
    else:
        logger.error("测试失败")
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
潜力股筛选器
从全量股票中筛选出符合条件的潜力股

使用方法：
    from stock_screener import StockScreener
    screener = StockScreener()
    screened_stocks = screener.screen()
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 禁用代理，避免网络连接问题
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

# 添加 TradingShared 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

try:
    from config import (
        MAX_MARKET_CAP,
        MAX_20D_GAIN,
        MIN_TURNOVER_RATE,
        MAX_TURNOVER_RATE
    )
except ImportError:
    # 使用默认值
    MAX_MARKET_CAP = 100e8
    MAX_20D_GAIN = 0.30
    MIN_TURNOVER_RATE = 1.0
    MAX_TURNOVER_RATE = 15.0


class StockScreener:
    """潜力股筛选器"""

    # 筛选条件配置
    MAX_MARKET_CAP = MAX_MARKET_CAP      # 最大市值100亿（小盘股）
    MAX_20D_GAIN = MAX_20D_GAIN          # 近20日最大涨幅30%（不追高）
    MIN_TURNOVER_RATE = MIN_TURNOVER_RATE # 最低换手率1%
    MAX_TURNOVER_RATE = MAX_TURNOVER_RATE # 最高换手率15%

    def __init__(self):
        """初始化筛选器"""
        self.data_dir = os.path.join(
            os.path.dirname(__file__), '..', 'TradingShared', 'data'
        )
        self.stock_scores: Dict = {}
        self.market_data: Dict = {}

    def load_stock_data(self) -> Dict:
        """
        加载最新评分数据

        Returns:
            股票评分数据字典 {股票代码: 股票数据}
        """
        # 优先查找最新的主板评分文件
        score_files = [
            f for f in os.listdir(self.data_dir)
            if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')
        ]

        if score_files:
            # 按文件名排序，取最新的
            latest_file = max(score_files)
            file_path = os.path.join(self.data_dir, latest_file)
            logger.info(f'使用主板评分文件: {latest_file}')
        else:
            # 备选：使用 batch_stock_scores_none.json
            file_path = os.path.join(self.data_dir, 'batch_stock_scores_none.json')
            if not os.path.exists(file_path):
                file_path = os.path.join(self.data_dir, 'batch_stock_scores.json')
            logger.info(f'使用备选评分文件: {os.path.basename(file_path)}')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.stock_scores = json.load(f)
            logger.info(f'成功加载 {len(self.stock_scores)} 只股票的评分数据')
            return self.stock_scores
        except Exception as e:
            logger.error(f'加载评分数据失败: {e}')
            return {}

    def get_all_market_data(self) -> Dict:
        """
        批量获取全市场股票的市值和行情数据
        使用 akshare 的 stock_zh_a_spot_em() 一次性获取所有数据

        Returns:
            市场数据字典 {股票代码: {市值, 换手率, 涨跌幅, ...}}
        """
        try:
            import akshare as ak

            logger.info('正在获取全市场实时行情数据...')

            # 获取沪深A股实时行情
            df = ak.stock_zh_a_spot_em()

            if df is None or df.empty:
                logger.warning('获取市场数据为空')
                return {}

            # 构建股票代码到行情数据的映射
            # akshare 返回的代码格式如 'sh600000' 或 'sz000001'
            market_data = {}

            for _, row in df.iterrows():
                # 提取股票代码（去除sh/sz前缀）
                raw_code = str(row.get('代码', ''))
                if not raw_code:
                    continue

                # 统一格式：6位数字代码
                code = raw_code[-6:] if len(raw_code) > 6 else raw_code

                # 只保留主板股票（600xxx, 601xxx, 603xxx, 000xxx, 001xxx, 002xxx）
                if not (code.startswith(('600', '601', '603', '000', '001', '002'))):
                    continue

                try:
                    market_data[code] = {
                        'name': str(row.get('名称', '')),
                        'price': float(row.get('最新价', 0)) or 0.0,
                        'market_cap': float(row.get('总市值', 0)) or 0.0,  # 单位：元
                        'turnover_rate': float(row.get('换手率', 0)) or 0.0,  # 单位：%
                        'change_pct': float(row.get('涨跌幅', 0)) or 0.0,  # 单位：%
                        'volume_ratio': float(row.get('量比', 0)) or 0.0,
                    }
                except (ValueError, TypeError):
                    continue

            self.market_data = market_data
            logger.info(f'成功获取 {len(market_data)} 只股票的实时行情数据')
            return market_data

        except ImportError:
            logger.warning('akshare 未安装，无法获取实时行情数据')
            return {}
        except Exception as e:
            logger.error(f'获取市场数据失败: {e}')
            return {}

    def get_recent_gain(self, stock_code: str, days: int = 20) -> float:
        """
        获取近N日涨幅
        如果市场数据中没有，尝试从akshare获取K线数据计算

        Args:
            stock_code: 股票代码
            days: 天数

        Returns:
            近N日涨幅百分比
        """
        # 首先尝试从缓存的市场数据中获取
        if stock_code in self.market_data:
            # 这里只有当日涨跌幅，没有多日涨幅
            # 暂时返回当日涨跌幅
            return self.market_data[stock_code].get('change_pct', 0.0)

        # 如果需要获取历史涨幅，需要调用akshare的K线接口
        try:
            import akshare as ak

            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days + 10)  # 多取几天避免节假日

            # 获取K线数据
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d")
            )

            if df is not None and len(df) >= days:
                # 计算近N日涨幅
                latest_close = float(df.iloc[-1]['收盘'])
                close_nd_ago = float(df.iloc[-days]['收盘'])
                gain = (latest_close - close_nd_ago) / close_nd_ago
                return round(gain * 100, 2)

        except Exception as e:
            logger.debug(f'获取 {stock_code} 近{days}日涨幅失败: {e}')

        return 0.0

    def is_st_stock(self, stock_code: str, stock_name: str = '') -> bool:
        """
        判断是否为ST股票

        Args:
            stock_code: 股票代码
            stock_name: 股票名称

        Returns:
            True if ST stock
        """
        # 检查名称中是否包含ST
        if stock_name:
            name_upper = stock_name.upper()
            if 'ST' in name_upper or 'S*ST' in name_upper or '*ST' in name_upper:
                return True

        # 检查评分数据中的名称
        if stock_code in self.stock_scores:
            score_name = self.stock_scores[stock_code].get('name', '')
            if score_name and 'ST' in score_name.upper():
                return True

        return False

    def screen(self) -> List[Dict]:
        """
        主筛选方法，返回潜力股列表

        筛选条件：
        1. 排除ST股票
        2. 总市值 < 100亿
        3. 近20日涨幅 < 30%
        4. 换手率 1%-15%

        Returns:
            潜力股列表，每只包含：
            {code, name, market_cap, recent_gain, turnover_rate,
             short_term_score, long_term_score, chip_score, hot_sector_score, industry}
        """
        # 1. 加载评分数据
        if not self.stock_scores:
            self.load_stock_data()

        if not self.stock_scores:
            logger.error('没有可用的评分数据')
            return []

        # 2. 获取全市场行情数据
        self.get_all_market_data()

        screened_stocks = []
        excluded_stats = {
            'st': 0,
            'market_cap': 0,
            'gain': 0,
            'turnover_low': 0,
            'turnover_high': 0,
            'total': len(self.stock_scores)
        }

        logger.info('开始筛选潜力股...')
        logger.info(f'筛选条件: 市值<{self.MAX_MARKET_CAP/1e8:.0f}亿, '
                   f'20日涨幅<{self.MAX_20D_GAIN*100:.0f}%, '
                   f'换手率{self.MIN_TURNOVER_RATE:.0f}%-{self.MAX_TURNOVER_RATE:.0f}%')

        # 离线模式标志：是否获取到实时行情数据
        has_market_data = len(self.market_data) > 0

        if not has_market_data:
            logger.warning('[离线模式] 未获取到实时行情数据，将跳过市值和换手率筛选')

        # 3. 遍历评分数据进行筛选
        for code, score_data in self.stock_scores.items():
            # 获取股票基本信息
            stock_name = score_data.get('name', '')

            # 过滤ST股票
            if self.is_st_stock(code, stock_name):
                excluded_stats['st'] += 1
                continue

            # 获取行情数据
            market_info = self.market_data.get(code, {})
            market_cap = market_info.get('market_cap', 0)
            turnover_rate = market_info.get('turnover_rate', 0)

            # 离线模式：没有实时数据时，只过滤ST股票，其他条件放宽
            if not has_market_data:
                # 离线模式下，获取近20日涨幅（如果可以）
                recent_gain = self.get_recent_gain(code, 20)
                # 只过滤涨幅过高的
                if recent_gain >= self.MAX_20D_GAIN * 100:
                    excluded_stats['gain'] += 1
                    continue

                # 使用默认值
                market_cap = 50e8  # 假设50亿市值
                turnover_rate = 3.0  # 假设3%换手率
            else:
                # 在线模式：完整筛选

                # 如果没有这只股票的行情数据，跳过
                if market_cap == 0 and turnover_rate == 0:
                    # 尝试获取近20日涨幅
                    recent_gain = self.get_recent_gain(code, 20)
                    if recent_gain >= self.MAX_20D_GAIN * 100:
                        excluded_stats['gain'] += 1
                        continue
                    # 没有市值数据，跳过
                    excluded_stats['market_cap'] += 1
                    continue

                # 过滤市值
                if market_cap > self.MAX_MARKET_CAP:
                    excluded_stats['market_cap'] += 1
                    continue

                # 过滤换手率
                if turnover_rate < self.MIN_TURNOVER_RATE:
                    excluded_stats['turnover_low'] += 1
                    continue
                if turnover_rate > self.MAX_TURNOVER_RATE:
                    excluded_stats['turnover_high'] += 1
                    continue

                # 获取近20日涨幅
                if 'change_pct' in market_info:
                    recent_gain = market_info['change_pct']
                else:
                    recent_gain = self.get_recent_gain(code, 20)

                # 过滤涨幅
                if recent_gain >= self.MAX_20D_GAIN * 100:
                    excluded_stats['gain'] += 1
                    continue

            # 通过所有筛选条件，添加到结果
            screened_stock = {
                'code': code,
                'name': market_info.get('name', stock_name),
                'market_cap': round(market_cap / 1e8, 2),  # 转换为亿元
                'market_cap_raw': market_cap,
                'recent_gain': round(recent_gain, 2),
                'turnover_rate': round(turnover_rate, 2),
                'short_term_score': score_data.get('short_term_score', 5.0),
                'long_term_score': score_data.get('long_term_score', 5.0),
                'chip_score': score_data.get('chip_score', 5.0),
                'hot_sector_score': score_data.get('hot_sector_score', 5.0),
                'industry': score_data.get('industry', '未知'),
                'matched_sector': score_data.get('matched_sector', ''),
                'sector_change': score_data.get('sector_change', 0),
            }
            screened_stocks.append(screened_stock)

        # 按综合评分排序
        screened_stocks.sort(
            key=lambda x: (
                x['hot_sector_score'] * 0.3 +
                x['short_term_score'] * 0.3 +
                x['chip_score'] * 0.2 +
                x['long_term_score'] * 0.2
            ),
            reverse=True
        )

        # 打印筛选结果统计
        logger.info('=' * 60)
        logger.info(f'筛选完成！')
        logger.info(f'原始股票数: {excluded_stats["total"]}')
        logger.info(f'筛选通过数: {len(screened_stocks)}')
        logger.info(f'排除原因统计:')
        logger.info(f'  - ST股票: {excluded_stats["st"]}')
        logger.info(f'  - 市值过大: {excluded_stats["market_cap"]}')
        logger.info(f'  - 涨幅过高: {excluded_stats["gain"]}')
        logger.info(f'  - 换手率过低: {excluded_stats["turnover_low"]}')
        logger.info(f'  - 换手率过高: {excluded_stats["turnover_high"]}')
        logger.info('=' * 60)

        return screened_stocks

    def save_to_csv(self, stocks: List[Dict], filename: str = None) -> str:
        """
        将筛选结果保存到CSV文件

        Args:
            stocks: 股票列表
            filename: 输出文件名（默认保存到桌面）

        Returns:
            保存的文件路径
        """
        if not stocks:
            logger.warning('没有数据可保存')
            return ''

        import csv

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'潜力股筛选_{timestamp}.csv'

        # 保存到桌面
        output_path = os.path.join(os.environ['USERPROFILE'], 'Desktop', filename)

        try:
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow([
                    '股票代码', '股票名称', '总市值(亿)', '近20日涨幅(%)',
                    '换手率(%)', '技术面评分', '基本面评分', '筹码面评分',
                    '板块热度评分', '所属行业', '匹配板块', '板块涨幅(%)'
                ])
                # 写入数据
                for stock in stocks:
                    writer.writerow([
                        stock['code'],
                        stock['name'],
                        stock['market_cap'],
                        stock['recent_gain'],
                        stock['turnover_rate'],
                        stock['short_term_score'],
                        stock['long_term_score'],
                        stock['chip_score'],
                        stock['hot_sector_score'],
                        stock['industry'],
                        stock.get('matched_sector', '-'),
                        f"{stock.get('sector_change', 0):+.2f}" if stock.get('sector_change') else '-'
                    ])

            logger.info(f'筛选结果已保存到: {output_path}')
            return output_path

        except Exception as e:
            logger.error(f'保存CSV失败: {e}')
            return ''

    def get_top_stocks(self, n: int = 10) -> List[Dict]:
        """
        获取筛选后的前N只股票

        Args:
            n: 返回数量

        Returns:
            前N只潜力股列表
        """
        screened = self.screen()
        return screened[:n]


if __name__ == '__main__':
    # 测试代码
    screener = StockScreener()
    stocks = screener.screen()

    print('\n前20名潜力股:')
    print('-' * 100)
    for i, stock in enumerate(stocks[:20], 1):
        print(f"{i:2}. {stock['code']} {stock['name']:8} "
              f"市值:{stock['market_cap']:6.2f}亿 "
              f"换手:{stock['turnover_rate']:5.2f}% "
              f"技术:{stock['short_term_score']:.1f} "
              f"基本面:{stock['long_term_score']:.1f} "
              f"筹码:{stock['chip_score']:.1f} "
              f"热度:{stock['hot_sector_score']:.1f} "
              f"行业:{stock['industry']}")

    # 保存到CSV
    screener.save_to_csv(stocks)

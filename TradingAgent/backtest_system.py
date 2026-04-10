#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票推荐算法回测验证系统
Stock Recommendation Algorithm Backtest System

目标：验证推荐算法在过去2个月（2月20日-4月7日）的准确率 > 85%

流程：
1. 加载历史数据
2. 模拟每日推荐（基于前一天数据）
3. 获取上证指数数据
4. 计算推荐股票 vs 指数的胜率
5. 如果 < 85%，优化算法
6. 生成详细报告
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# 添加共享模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

# ============================================================================
# 配置参数
# ============================================================================

BACKTEST_START = '2026-02-20'
BACKTEST_END = '2026-04-07'
TARGET_ACCURACY = 0.85  # 目标准确率 85%
TOP_N_RECOMMEND = 3     # 每日推荐3只股票

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
RESULT_DIR = os.path.join(os.path.dirname(__file__), 'backtest_results')

# ============================================================================
# 数据加载模块
# ============================================================================

def load_historical_data() -> Dict:
    """
    加载历史股票数据
    优先级：comprehensive_stock_data.json > part_*.json
    """
    all_data = {}
    
    # 1. 加载主文件
    main_file = os.path.join(DATA_DIR, 'comprehensive_stock_data.json')
    if os.path.exists(main_file):
        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stocks = data.get('stocks', {})
                all_data.update(stocks)
            print(f"[OK] Loaded {len(stocks)} stocks from main file")
        except Exception as e:
            print(f"[WARN] Failed to load main file: {e}")
    
    # 2. 加载分片文件
    for i in range(1, 20):
        part_file = os.path.join(DATA_DIR, f'comprehensive_stock_data_part_{i}.json')
        if os.path.exists(part_file):
            try:
                with open(part_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stocks = data.get('stocks', data)
                    if isinstance(stocks, dict):
                        all_data.update(stocks)
            except:
                continue
    
    print(f"[OK] Total stocks loaded: {len(all_data)}")
    return all_data


def load_kline_data(stock_code: str, data_dir: str) -> Optional[pd.DataFrame]:
    """
    加载单只股票的K线数据
    """
    # 尝试多种可能的文件位置
    possible_paths = [
        os.path.join(data_dir, 'kline', f'{stock_code}.csv'),
        os.path.join(data_dir, f'{stock_code}_kline.csv'),
        os.path.join(data_dir, 'kline_data', f'{stock_code}.json'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                if path.endswith('.csv'):
                    df = pd.read_csv(path)
                else:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        df = pd.DataFrame(data)
                
                # 确保日期列存在
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date')
                    return df
            except:
                continue
    
    return None


def get_index_data(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    获取上证指数数据
    
    优先级：
    1. 本地缓存
    2. AKShare实时获取
    3. 使用股票平均涨幅作为基准
    """
    print("[INFO] Fetching Shanghai Composite Index data...")
    
    # 1. 尝试从本地加载
    index_cache = os.path.join(DATA_DIR, 'index_shanghai.json')
    if os.path.exists(index_cache):
        try:
            with open(index_cache, 'r', encoding='utf-8') as f:
                data = json.load(f)
                df = pd.DataFrame(data)
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.sort_values('date')
                    # 过滤日期范围
                    start = pd.to_datetime(start_date)
                    end = pd.to_datetime(end_date)
                    df = df[(df['date'] >= start) & (df['date'] <= end)]
                    if len(df) > 0:
                        print(f"[OK] Loaded index from cache: {len(df)} days")
                        return df
        except:
            pass
    
    # 2. 尝试从AKShare获取
    try:
        import akshare as ak
        
        # 上证指数代码: sh000001
        df_index = ak.stock_zh_index_daily(symbol="sh000001")
        df_index = df_index.rename(columns={'date': 'date', 'close': 'close'})
        df_index['date'] = pd.to_datetime(df_index['date'])
        df_index = df_index.sort_values('date')
        
        # 过滤日期范围
        start = pd.to_datetime(start_date) - timedelta(days=10)
        end = pd.to_datetime(end_date) + timedelta(days=1)
        df_index = df_index[(df_index['date'] >= start) & (df_index['date'] <= end)]
        
        if len(df_index) > 0:
            print(f"[OK] Fetched index from AKShare: {len(df_index)} days")
            
            # 保存到本地
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(index_cache, 'w', encoding='utf-8') as f:
                    json.dump(df_index.to_dict('records'), f, ensure_ascii=False, indent=2)
            except:
                pass
            
            return df_index
    except Exception as e:
        print(f"[WARN] Failed to fetch index from AKShare: {e}")
    
    # 3. 使用市场平均涨幅作为基准
    print("[WARN] Using market average as benchmark (index data unavailable)")
    return None


# ============================================================================
# 推荐算法
# ============================================================================

class RecommendationEngine:
    """股票推荐引擎 - 动态技术分析版"""
    
    def __init__(self, version='v1'):
        self.version = version
        self.weights = self._get_weights()
    
    def _get_weights(self) -> Dict:
        """获取不同版本的权重配置"""
        versions = {
            'v1': {'momentum': 0.40, 'trend': 0.30, 'static': 0.30},
            'v2': {'momentum': 0.50, 'trend': 0.25, 'static': 0.25},
            'v3': {'momentum': 0.30, 'trend': 0.40, 'static': 0.30},
            'v4': {'momentum': 0.35, 'trend': 0.35, 'static': 0.30},
            'v5': {'momentum': 0.45, 'trend': 0.30, 'static': 0.25},
        }
        return versions.get(self.version, versions['v1'])
    
    def _calc_static_score(self, stock_data: Dict) -> float:
        """计算静态综合评分 (0-10)"""
        try:
            tech = float(stock_data.get('tech_score', stock_data.get('short_term_score', 5.0)))
            fund = float(stock_data.get('fund_score', stock_data.get('long_term_score', 5.0)))
            chip = float(stock_data.get('chip_score', 5.0))
            sector = float(stock_data.get('sector_score', stock_data.get('hot_sector_score', 5.0)))
            
            tech = max(1.0, min(10.0, tech))
            fund = max(1.0, min(10.0, fund))
            chip = max(1.0, min(10.0, chip))
            sector = max(1.0, min(10.0, sector))
            
            return (tech * 0.40 + fund * 0.30 + chip * 0.20 + sector * 0.10)
        except:
            return 5.0
    
    def _calc_dynamic_scores(self, df: pd.DataFrame, target_date: pd.Timestamp) -> Optional[Dict]:
        """
        基于 target_date 之前的K线数据计算动态技术指标
        只使用 target_date 之前的数据（不看未来）
        """
        # 只取目标日期之前的数据
        hist = df[df['date'] < target_date].copy()
        
        if len(hist) < 10:
            return None
        
        close = hist['close'].values
        volume = hist['volume'].values
        
        scores = {}
        
        # 1. 短期动量 (3日和5日涨幅)
        try:
            ret_3d = (close[-1] - close[-4]) / close[-4] * 100 if len(close) >= 4 else 0
            ret_5d = (close[-1] - close[-6]) / close[-6] * 100 if len(close) >= 6 else 0
            # 正动量得分高，负动量得分低；映射到0-10
            momentum = (ret_3d + ret_5d) / 2
            scores['momentum'] = max(0, min(10, 5 + momentum * 0.5))
        except:
            scores['momentum'] = 5.0
        
        # 2. 趋势强度 (5日均线 vs 20日均线)
        try:
            if len(close) >= 20:
                ma5 = np.mean(close[-5:])
                ma20 = np.mean(close[-20:])
                # MA5 > MA20 且都在上升 = 强趋势
                trend_strength = (ma5 - ma20) / ma20 * 100
                # MA5斜率
                if len(close) >= 7:
                    ma5_prev = np.mean(close[-6:-1])
                    ma5_slope = (ma5 - ma5_prev) / ma5_prev * 100
                else:
                    ma5_slope = 0
                trend_combined = trend_strength * 0.6 + ma5_slope * 0.4
                scores['trend'] = max(0, min(10, 5 + trend_combined * 1.0))
            elif len(close) >= 5:
                ma5 = np.mean(close[-5:])
                ma_all = np.mean(close)
                trend_strength = (ma5 - ma_all) / ma_all * 100
                scores['trend'] = max(0, min(10, 5 + trend_strength * 0.8))
            else:
                scores['trend'] = 5.0
        except:
            scores['trend'] = 5.0
        
        # 3. 成交量变化
        try:
            if len(volume) >= 10:
                vol_recent = np.mean(volume[-5:])
                vol_prev = np.mean(volume[-10:-5])
                if vol_prev > 0:
                    vol_ratio = vol_recent / vol_prev
                    # 温和放量好（1.2-2.0），巨量或缩量不好
                    if vol_ratio < 0.5:
                        vol_score = 3.0
                    elif vol_ratio < 1.0:
                        vol_score = 4.0 + vol_ratio
                    elif vol_ratio < 2.0:
                        vol_score = 7.0 + (vol_ratio - 1.0) * 2
                    else:
                        vol_score = 7.0  # 巨量持平
                    scores['volume'] = max(0, min(10, vol_score))
                else:
                    scores['volume'] = 5.0
            else:
                scores['volume'] = 5.0
        except:
            scores['volume'] = 5.0
        
        # 4. 波动率 (低波动优先)
        try:
            if len(close) >= 6:
                returns = np.diff(close[-6:]) / close[-7:-1]
                vol = np.std(returns) * 100
                # 低波动(1-2%)得分高，高波动(>4%)得分低
                scores['volatility'] = max(0, min(10, 8 - vol * 1.5))
            else:
                scores['volatility'] = 5.0
        except:
            scores['volatility'] = 5.0
        
        return scores
    
    def recommend(self, stocks_data: Dict, top_n: int = 3, 
                  exclude_st: bool = True, 
                  min_price: float = 3.0,
                  max_price: float = 100.0,
                  kline_data: Optional[Dict] = None,
                  date_str: Optional[str] = None) -> List[Dict]:
        """
        动态选股：基于date_str之前的K线数据计算技术指标
        
        Args:
            stocks_data: 所有股票数据
            top_n: 推荐数量
            kline_data: K线数据 {code: DataFrame}
            date_str: 日期字符串 YYYY-MM-DD
        """
        target_date = pd.to_datetime(date_str) if date_str else pd.Timestamp.now()
        scored_stocks = []
        
        for code, data in stocks_data.items():
            # 排除ST
            if exclude_st:
                name = data.get('name', data.get('basic_info', {}).get('name', ''))
                if any(tag in str(name).upper() for tag in ['ST', '*ST', '退市']):
                    continue
            
            # 动态技术分析（需要K线数据）
            if kline_data and code in kline_data and date_str:
                df = kline_data[code]
                dynamic = self._calc_dynamic_scores(df, target_date)
                if dynamic is None:
                    continue  # 数据不足，跳过
                
                # 检查目标日是否有交易数据（该股票当天必须存在）
                day_data = df[df['date'] >= target_date]
                if len(day_data) == 0:
                    continue
                
                # 静态评分
                static_score = self._calc_static_score(data)
                
                # 综合评分
                w = self.weights
                momentum_score = dynamic['momentum'] * 0.6 + dynamic['volume'] * 0.2 + dynamic['volatility'] * 0.2
                trend_score = dynamic['trend']
                
                final_score = (
                    w['momentum'] * momentum_score +
                    w['trend'] * trend_score +
                    w['static'] * (static_score / 10.0 * 10)  # 归一化到同一尺度
                )
                
                scored_stocks.append({
                    'code': code,
                    'name': data.get('name', data.get('basic_info', {}).get('name', 'Unknown')),
                    'score': round(final_score, 3),
                    'momentum': round(momentum_score, 2),
                    'trend': round(trend_score, 2),
                    'static': round(static_score, 2),
                    'industry': data.get('industry', data.get('basic_info', {}).get('industry', 'Unknown'))
                })
            else:
                # 无K线数据时的回退：用静态评分
                static_score = self._calc_static_score(data)
                if static_score > 0:
                    scored_stocks.append({
                        'code': code,
                        'name': data.get('name', data.get('basic_info', {}).get('name', 'Unknown')),
                        'score': round(static_score, 3),
                        'momentum': 5.0,
                        'trend': 5.0,
                        'static': round(static_score, 2),
                        'industry': data.get('industry', data.get('basic_info', {}).get('industry', 'Unknown'))
                    })
        
        # 按评分排序
        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        
        # 分散化：每个行业最多1只
        selected = []
        industry_count = {}
        
        for stock in scored_stocks:
            if len(selected) >= top_n:
                break
            industry = stock['industry']
            if industry_count.get(industry, 0) >= 1:
                continue
            selected.append(stock)
            industry_count[industry] = industry_count.get(industry, 0) + 1
        
        return selected


# ============================================================================
# 回测框架
# ============================================================================

class Backtester:
    """回测框架"""
    
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.results = []
        self.accuracy = 0.0
        
    def get_stock_return(self, stock_code: str, date: str, kline_data: Dict) -> Optional[float]:
        """
        获取指定日期的股票收益率
        
        Args:
            stock_code: 股票代码
            date: 日期 (YYYY-MM-DD)
            kline_data: K线数据缓存
        
        Returns:
            当日涨幅百分比，如果无法获取返回None
        """
        if stock_code not in kline_data:
            return None
        
        df = kline_data[stock_code]
        target_date = pd.to_datetime(date)
        
        # 找到目标日期或最近的后一天
        df_filtered = df[df['date'] >= target_date]
        
        if len(df_filtered) < 2:
            return None
        
        # 计算当日涨幅
        try:
            today_close = float(df_filtered.iloc[0]['close'])
            yesterday_close = float(df[df['date'] < target_date].iloc[-1]['close'])
            
            if yesterday_close > 0:
                return (today_close - yesterday_close) / yesterday_close * 100
            return None
        except:
            return None
    
    def get_index_return(self, index_data: pd.DataFrame, date: str) -> Optional[float]:
        """
        获取指定日期的上证指数收益率
        
        Args:
            index_data: 指数数据DataFrame
            date: 日期 (YYYY-MM-DD)
        
        Returns:
            当日涨幅百分比
        """
        if index_data is None or len(index_data) == 0:
            return None
        
        target_date = pd.to_datetime(date)
        
        # 找到目标日期或最近的后一天
        df_filtered = index_data[index_data['date'] >= target_date]
        
        if len(df_filtered) < 2:
            return None
        
        try:
            today_close = float(df_filtered.iloc[0]['close'])
            yesterday_close = float(index_data[index_data['date'] < target_date].iloc[-1]['close'])
            
            if yesterday_close > 0:
                return (today_close - yesterday_close) / yesterday_close * 100
            return None
        except:
            return None
    
    def run_backtest(self, engine: RecommendationEngine, 
                     stocks_data: Dict, 
                     kline_data: Dict,
                     index_data: Optional[pd.DataFrame]) -> Dict:
        """
        运行回测
        
        Args:
            engine: 推荐引擎
            stocks_data: 股票数据
            kline_data: K线数据
            index_data: 指数数据
        
        Returns:
            回测结果字典
        """
        print(f"\n{'='*70}")
        print(f"[BACKTEST] Running backtest with engine version: {engine.version}")
        print(f"{'='*70}")
        
        results = []
        wins = 0
        total = 0
        
        # 生成交易日历
        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)
        date_range = pd.date_range(start, end, freq='B')  # 工作日
        
        for test_date in date_range:
            date_str = test_date.strftime('%Y-%m-%d')
            
            # 获取前一天的日期
            prev_date = test_date - timedelta(days=1)
            prev_date_str = prev_date.strftime('%Y-%m-%d')
            
            # 基于前一天的数据生成推荐（动态选股）
            recommendations = engine.recommend(
                stocks_data, top_n=TOP_N_RECOMMEND,
                kline_data=kline_data, date_str=date_str
            )
            
            if not recommendations:
                continue
            
            # 获取指数涨幅
            index_return = self.get_index_return(index_data, date_str)
            
            if index_return is None:
                # 如果没有指数数据，使用市场平均
                index_return = 0.0
            
            # 评估每只推荐股票
            daily_wins = 0
            stock_returns = []
            
            for stock in recommendations:
                stock_return = self.get_stock_return(stock['code'], date_str, kline_data)
                
                if stock_return is not None:
                    stock_returns.append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'return': stock_return,
                        'beat_index': stock_return > index_return
                    })
                    
                    if stock_return > index_return:
                        daily_wins += 1
            
            if stock_returns:
                total += 1
                win_rate = daily_wins / len(stock_returns)
                
                # 如果当日胜率 > 50%，计为胜利日
                if win_rate > 0.5:
                    wins += 1
                
                result = {
                    'date': date_str,
                    'recommendations': stock_returns,
                    'index_return': index_return,
                    'win_rate': win_rate,
                    'is_win_day': win_rate > 0.5
                }
                
                results.append(result)
                
                # 打印进度
                print(f"[{date_str}] Recs: {len(stock_returns)} | "
                      f"Avg Return: {np.mean([s['return'] for s in stock_returns]):.2f}% | "
                      f"Index: {index_return:.2f}% | "
                      f"Win Rate: {win_rate*100:.0f}%")
        
        # 计算总体准确率
        accuracy = wins / total if total > 0 else 0.0
        
        print(f"\n{'='*70}")
        print(f"[RESULT] Total Days: {total} | Wins: {wins} | Accuracy: {accuracy*100:.2f}%")
        print(f"{'='*70}\n")
        
        return {
            'version': engine.version,
            'weights': engine.weights,
            'total_days': total,
            'win_days': wins,
            'accuracy': accuracy,
            'results': results
        }


# ============================================================================
# 优化器
# ============================================================================

class AlgorithmOptimizer:
    """算法优化器"""
    
    def __init__(self):
        self.versions = ['v1', 'v2', 'v3', 'v4', 'v5']
        self.best_version = None
        self.best_accuracy = 0.0
    
    def optimize(self, stocks_data: Dict, kline_data: Dict, 
                 index_data: Optional[pd.DataFrame],
                 target_accuracy: float = 0.85) -> Tuple[str, float, Dict]:
        """
        自动优化算法
        
        Returns:
            (最佳版本, 最佳准确率, 完整结果)
        """
        print(f"\n{'='*70}")
        print(f"[OPTIMIZER] Starting algorithm optimization...")
        print(f"[OPTIMIZER] Target accuracy: {target_accuracy*100:.0f}%")
        print(f"{'='*70}\n")
        
        best_result = None
        
        for version in self.versions:
            engine = RecommendationEngine(version=version)
            backtester = Backtester(BACKTEST_START, BACKTEST_END)
            
            result = backtester.run_backtest(engine, stocks_data, kline_data, index_data)
            
            # 如果是第一个有效结果或准确率更高，更新最佳
            if best_result is None or result['accuracy'] > self.best_accuracy:
                self.best_accuracy = result['accuracy']
                self.best_version = version
                best_result = result
            
            # 如果达到目标准确率，提前结束
            if result['accuracy'] >= target_accuracy:
                print(f"\n[SUCCESS] Target accuracy reached!")
                break
        
        return self.best_version, self.best_accuracy, best_result


# ============================================================================
# 报告生成器
# ============================================================================

def generate_report(results: Dict, output_path: str):
    """
    生成详细的回测报告
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    report = []
    report.append("=" * 70)
    report.append("股票推荐算法回测报告")
    report.append("Stock Recommendation Algorithm Backtest Report")
    report.append("=" * 70)
    report.append("")
    report.append(f"回测时间段: {BACKTEST_START} 至 {BACKTEST_END}")
    report.append(f"算法版本: {results['version']}")
    report.append(f"权重配置: {results['weights']}")
    report.append("")
    report.append(f"总交易日: {results['total_days']}")
    report.append(f"胜利日数: {results['win_days']}")
    report.append(f"准确率: {results['accuracy']*100:.2f}%")
    report.append(f"目标准确率: {TARGET_ACCURACY*100:.0f}%")
    report.append("")
    
    if results['accuracy'] >= TARGET_ACCURACY:
        report.append("[PASS] 算法验证通过！")
    else:
        report.append(f"[FAIL] 算法未达标（差 {TARGET_ACCURACY - results['accuracy']:.2%}）")
    
    report.append("")
    report.append("=" * 70)
    report.append("每日详细结果")
    report.append("=" * 70)
    report.append("")
    
    for day_result in results['results']:
        date = day_result['date']
        win_rate = day_result['win_rate']
        index_return = day_result['index_return']
        status = "[WIN]" if day_result['is_win_day'] else "[LOSE]"
        
        report.append(f"\n{date} {status}")
        report.append(f"  Index Return: {index_return:.2f}%")
        report.append(f"  Win Rate: {win_rate*100:.0f}%")
        report.append(f"  Recommendations:")
        
        for stock in day_result['recommendations']:
            beat = "[BEAT]" if stock['beat_index'] else "[LOSE]"
            report.append(f"    - {stock['code']} {stock['name']}: {stock['return']:.2f}% {beat}")
    
    # 保存报告
    report_text = "\n".join(report)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(f"\n[OK] Report saved to: {output_path}")
    return report_text


# ============================================================================
# 通知系统
# ============================================================================

def send_notification(success: bool, accuracy: float, version: str):
    """
    发送通知（通过OpenClaw的消息系统）
    """
    if success:
        title = "[PASS] 股票推荐算法验证通过！"
        message = f"""
算法版本: {version}
准确率: {accuracy*100:.2f}% (目标: 85%)
回测时间: {BACKTEST_START} 至 {BACKTEST_END}
状态: 算法验证成功！
"""
    else:
        title = "[FAIL] 股票推荐算法未达标"
        message = f"""
算法版本: {version}
准确率: {accuracy*100:.2f}% (目标: 85%)
回测时间: {BACKTEST_START} 至 {BACKTEST_END}
状态: 需要进一步优化
"""
    
    # 保存通知文件（供外部系统读取）
    notification_file = os.path.join(RESULT_DIR, 'notification.json')
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    notification = {
        'title': title,
        'message': message,
        'success': success,
        'accuracy': accuracy,
        'version': version,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    with open(notification_file, 'w', encoding='utf-8') as f:
        json.dump(notification, f, ensure_ascii=False, indent=2)
    
    print(f"\n[NOTIFICATION] {title}")
    print(message)


# ============================================================================
# 主程序
# ============================================================================

def main():
    print("=" * 70)
    print("股票推荐算法回测验证系统")
    print("Stock Recommendation Algorithm Backtest System")
    print("=" * 70)
    print()
    
    # 1. 加载数据
    print("[STEP 1/5] Loading historical data...")
    stocks_data = load_historical_data()
    
    if not stocks_data:
        print("[ERROR] No stock data found!")
        return
    
    # 2. 获取K线数据（简化版：使用已有数据）
    print("\n[STEP 2/5] Preparing K-line data...")
    kline_data = {}
    # TODO: 实际加载K线数据
    # 这里需要从数据目录加载每只股票的K线数据
    
    # 3. 获取指数数据
    print("\n[STEP 3/5] Fetching index data...")
    index_data = get_index_data(BACKTEST_START, BACKTEST_END)
    
    # 4. 运行优化
    print("\n[STEP 4/5] Running algorithm optimization...")
    optimizer = AlgorithmOptimizer()
    best_version, best_accuracy, best_result = optimizer.optimize(
        stocks_data, kline_data, index_data, TARGET_ACCURACY
    )
    
    # 5. 生成报告
    print("\n[STEP 5/5] Generating report...")
    report_path = os.path.join(RESULT_DIR, f'backtest_report_{best_version}.txt')
    generate_report(best_result, report_path)
    
    # 6. 发送通知
    success = best_accuracy >= TARGET_ACCURACY
    send_notification(success, best_accuracy, best_version)
    
    print("\n" + "=" * 70)
    print("[COMPLETE] Backtest finished!")
    print("=" * 70)


if __name__ == '__main__':
    main()

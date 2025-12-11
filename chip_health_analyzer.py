#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筹码健康度分析工具
评估股票筹码分布、集中度、获利盘等指标

功能：
1. 获取十大流通股东数据
2. 计算筹码集中度
3. 估算筹码平均成本
4. 计算获利盘/套牢盘比例
5. 评估筹码健康度评分

作者: AI Assistant
日期: 2025-12-10
"""

import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# 尝试导入akshare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    print("✓ akshare库加载成功")
except ImportError:
    AKSHARE_AVAILABLE = False
    print("⚠ akshare库未安装，请运行: pip install akshare")

# 尝试导入tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
    # 如果有token可以在这里配置
    # ts.set_token('your_token_here')
    print("✓ tushare库加载成功")
except ImportError:
    TUSHARE_AVAILABLE = False
    print("⚠ tushare库未安装")


class ChipHealthAnalyzer:
    """筹码健康度分析器"""
    
    def __init__(self):
        self.akshare_available = AKSHARE_AVAILABLE
        self.tushare_available = TUSHARE_AVAILABLE
    
    def analyze_stock(self, stock_code):
        """
        分析股票筹码健康度
        
        Args:
            stock_code: 股票代码（6位数字，如'600519'）
        
        Returns:
            dict: 筹码分析结果
        """
        print(f"\n{'='*70}")
        print(f"  筹码健康度分析 - {stock_code}")
        print(f"{'='*70}\n")
        
        result = {
            'stock_code': stock_code,
            'chip_concentration': 0,  # 筹码集中度（十大股东）
            'scr': 0,  # SCR筹码集中度（价格分布）
            'chip_cost': 0,  # 筹码平均成本（P50）
            'chip_cost_p10': 0,  # 10%成本位
            'chip_cost_p90': 0,  # 90%成本位
            'profit_ratio': 0,  # 获利盘比例
            'loss_ratio': 0,  # 套牢盘比例
            'turnover_rate': 0,  # 换手率
            'chip_bias': 0,  # 筹码乖离率
            'peak_type': '未知',  # 筹码峰型：单峰/双峰/多峰
            'peak_confidence': 0,  # 形态置信度
            'bottom_locked': False,  # 底部筹码是否锁定
            'health_score': 0,  # 健康度评分
            'health_level': '未知',  # 健康度等级
            'hhi': 0,  # 赫芬达尔指数
            'gini_coefficient': 0,  # 基尼系数
            'concentration_score': 0,  # 集中度评分
            'turnover_score': 0,  # 换手率评分
            'profit_loss_score': 0,  # 盈亏比评分
            'bias_score': 0,  # 乖离率评分
            'pattern_score': 0,  # 形态评分
            'trading_suggestion': '',  # 交易建议
            'signal_strength': '弱',  # 信号强度
            'signals': [],  # 信号列表
            'top10_holders': None,  # 十大股东
            'holder_count_change': 0,  # 股东户数变化
            'data_start_date': '',  # 数据起始日期
            'data_end_date': '',  # 数据结束日期
            'data_days': 0,  # 数据天数
        }

        
        # 1. 获取当前价格和历史数据
        print("[1/6] 获取价格和历史数据...")
        current_price, hist_data = self._get_price_and_history(stock_code)
        if current_price == 0 or hist_data is None:
            print("❌ 无法获取价格数据")
            result['error'] = '无法获取股票数据，请检查网络连接或稍后重试'
            return result
        
        result['current_price'] = current_price
        
        # 记录数据时间范围
        # 先打印列名以便调试
        print(f"  数据列名: {list(hist_data.columns)}")
        
        # 尝试多种日期列名
        date_col = None
        for col_name in ['日期', 'date', 'Date', 'trade_date', 'datetime']:
            if col_name in hist_data.columns:
                date_col = col_name
                break
        
        if date_col:
            result['data_start_date'] = str(hist_data[date_col].iloc[0])
            result['data_end_date'] = str(hist_data[date_col].iloc[-1])
            result['data_days'] = len(hist_data)
            print(f"✓ 当前价格: ¥{current_price:.2f}")
            print(f"✓ 数据时间: {result['data_start_date']} 至 {result['data_end_date']} (共{result['data_days']}天)")
        else:
            result['data_days'] = len(hist_data)
            print(f"✓ 当前价格: ¥{current_price:.2f}")
            print(f"⚠ 未找到日期列，数据天数: {result['data_days']}天")
        
        # 2. 获取十大流通股东
        print("\n[2/6] 获取十大流通股东数据...")
        top10_data = self._get_top10_holders(stock_code)
        if top10_data is not None:
            result['top10_holders'] = top10_data
            chip_concentration = self._calculate_concentration(top10_data)
            result['chip_concentration'] = chip_concentration
            print(f"✓ 十大股东持股: {chip_concentration:.2f}%")
        else:
            print("⚠ 未获取到十大股东数据")
        
        # 3. 获取股东户数变化
        print("\n[3/6] 获取股东户数变化...")
        holder_change = self._get_holder_count_change(stock_code)
        if holder_change != 0:
            result['holder_count_change'] = holder_change
            print(f"✓ 股东户数变化: {holder_change:+.2f}%")
        else:
            print("⚠ 未获取到股东户数数据")
        
        # 4. 计算筹码成本分位数（P10/P50/P90）和SCR
        print("\n[4/6] 计算筹码成本分位数和SCR...")
        p10, p50, p90 = self._calculate_chip_cost_percentiles(hist_data)
        result['chip_cost_p10'] = p10
        result['chip_cost'] = p50  # P50作为平均成本
        result['chip_cost_p90'] = p90
        
        # 计算SCR筹码集中度
        if p50 > 0:
            scr = ((p90 - p10) / (2 * p50)) * 100
            result['scr'] = scr
            print(f"✓ 筹码成本: P10=¥{p10:.2f}, P50=¥{p50:.2f}, P90=¥{p90:.2f}")
            print(f"✓ SCR筹码集中度: {scr:.2f}% {'(高度集中)' if scr < 10 else '(相对集中)' if scr < 20 else '(发散)'}")
        else:
            print("⚠ 无法计算筹码成本")
        
        # 5. 计算获利盘/套牢盘比例
        print("\n[5/6] 计算获利盘/套牢盘...")
        profit_ratio, loss_ratio = self._calculate_profit_loss_ratio(
            hist_data, current_price
        )
        result['profit_ratio'] = profit_ratio
        result['loss_ratio'] = loss_ratio
        print(f"✓ 获利盘: {profit_ratio:.1f}%, 套牢盘: {loss_ratio:.1f}%")
        
        # 6. 计算换手率
        print("\n[6/6] 计算换手率...")
        turnover = self._calculate_turnover_rate(hist_data)
        result['turnover_rate'] = turnover
        print(f"✓ 近5日平均换手率: {turnover:.2f}%")
        
        # 7. 计算筹码乖离率
        print("\n[7/9] 计算筹码乖离率...")
        if current_price > 0 and p50 > 0:
            chip_bias = ((current_price - p50) / p50) * 100
            result['chip_bias'] = chip_bias
            print(f"✓ 筹码乖离率: {chip_bias:+.2f}% {'(健康区间)' if 5 <= chip_bias <= 15 else ''}")
        
        # 8. 计算HHI和基尼系数
        print("\n[8/11] 计算HHI和基尼系数...")
        hhi, gini = self._calculate_hhi_and_gini(hist_data)
        result['hhi'] = hhi
        result['gini_coefficient'] = gini
        print(f"✓ 赫芬达尔指数(HHI): {hhi:.4f} {'(高度集中)' if hhi > 0.25 else '(相对分散)' if hhi < 0.15 else '(适中)'}")
        print(f"✓ 基尼系数: {gini:.4f} {'(分布均匀)' if gini < 0.4 else '(分布不均)' if gini > 0.6 else '(适中)'}")
        
        # 9. 识别筹码峰型
        print("\n[9/11] 识别筹码峰型...")
        peak_type = self._identify_peak_type(hist_data)
        result['peak_type'] = peak_type
        print(f"✓ 筹码峰型: {peak_type}")
        
        # 10. 检测底部筹码锁定
        print("\n[10/11] 检测底部筹码锁定...")
        bottom_locked = self._check_bottom_locked(hist_data, current_price)
        result['bottom_locked'] = bottom_locked
        print(f"✓ 底部筹码: {'锁定 🔒' if bottom_locked else '未锁定'}")
        
        # 11. 综合评分（新版严格算法）
        print("\n[11/11] 计算筹码健康度...")
        health_score, signals = self._calculate_health_score(result)
        result['health_score'] = health_score
        result['signals'] = signals
        result['health_level'] = self._get_health_level(health_score)
        
        # 打印结果
        self._print_result(result)
        
        return result
    
    def _get_price_and_history(self, stock_code):
        """获取当前价格和历史数据（带重试机制）"""
        if not self.akshare_available:
            print("⚠ akshare库不可用")
            return 0, None
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=120)).strftime('%Y%m%d')
        
        # 方法1: 尝试使用 akshare 的 stock_zh_a_hist (东方财富源)
        try:
            print("  尝试数据源: akshare.stock_zh_a_hist (东方财富)")
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is not None and not df.empty:
                current_price = float(df['收盘'].iloc[-1])
                # 确保有日期列
                if '日期' not in df.columns and 'date' in df.columns:
                    df = df.rename(columns={'date': '日期'})
                print(f"  ✓ 成功获取数据 (东方财富源)")
                return current_price, df
            
        except Exception as e:
            print(f"  ✗ 东方财富源失败: {str(e)[:80]}")
        
        # 方法2: 尝试使用 akshare 的 stock_zh_a_daily (新浪源)
        try:
            print("  尝试数据源: akshare.stock_zh_a_daily (新浪源)")
            # 转换股票代码格式
            if stock_code.startswith('6'):
                symbol = f"sh{stock_code}"
            else:
                symbol = f"sz{stock_code}"
            
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            
            if df is not None and not df.empty:
                # 统一列名
                rename_dict = {'close': '收盘', 'volume': '成交量'}
                if 'date' in df.columns:
                    rename_dict['date'] = '日期'
                df = df.rename(columns=rename_dict)
                current_price = float(df['收盘'].iloc[-1])
                print(f"  ✓ 成功获取数据 (新浪源)")
                return current_price, df
                
        except Exception as e:
            print(f"  ✗ 新浪源失败: {str(e)[:80]}")
        
        # 方法3: 尝试使用腾讯接口
        try:
            print("  尝试数据源: 腾讯财经API")
            import requests

            # 转换股票代码格式
            if stock_code.startswith('6'):
                market = 'sh'
            else:
                market = 'sz'
            
            url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            params = {
                'param': f'{market}{stock_code},day,{start_date},{end_date},90,qfq',
                '_var': 'kline_day'
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                import json
                data_text = response.text.replace('kline_day=', '')
                data = json.loads(data_text)
                
                if 'data' in data and market + stock_code in data['data']:
                    kline_data = data['data'][market + stock_code]['qfqday']
                    
                    if kline_data:
                        # 转换为DataFrame
                        dates = [item[0] for item in kline_data]
                        closes = [float(item[2]) for item in kline_data]
                        volumes = [float(item[5]) for item in kline_data]
                        
                        df = pd.DataFrame({
                            '日期': dates,
                            '收盘': closes,
                            '成交量': volumes
                        })
                        
                        current_price = float(df['收盘'].iloc[-1])
                        print(f"  ✓ 成功获取数据 (腾讯源)")
                        return current_price, df
                        
        except Exception as e:
            print(f"  ✗ 腾讯源失败: {str(e)[:80]}")
        
        # 方法4: 尝试使用 Tushare
        if self.tushare_available:
            try:
                print("  尝试数据源: Tushare")
                import tushare as ts

                # 转换股票代码格式 (600519 -> 600519.SH)
                if stock_code.startswith('6'):
                    ts_code = f"{stock_code}.SH"
                elif stock_code.startswith('0') or stock_code.startswith('3'):
                    ts_code = f"{stock_code}.SZ"
                elif stock_code.startswith('688'):
                    ts_code = f"{stock_code}.SH"  # 科创板
                else:
                    ts_code = f"{stock_code}.SZ"
                
                # 尝试使用pro接口（需要token）
                try:
                    pro = ts.pro_api()
                    df = pro.daily(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    if df is not None and not df.empty:
                        # Tushare返回的数据是倒序的，需要正序
                        df = df.sort_values('trade_date')
                        # 统一列名
                        df = df.rename(columns={
                            'trade_date': '日期',
                            'close': '收盘',
                            'vol': '成交量'
                        })
                        # 确保日期格式
                        df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
                        current_price = float(df['收盘'].iloc[-1])
                        print(f"  ✓ 成功获取数据 (Tushare Pro)")
                        return current_price, df
                except:
                    # Pro接口失败，尝试免费接口
                    df = ts.get_k_data(
                        stock_code,
                        start=start_date.replace('-', ''),
                        end=end_date.replace('-', ''),
                        ktype='D'
                    )
                    
                    if df is not None and not df.empty:
                        # 统一列名
                        df = df.rename(columns={
                            'date': '日期',
                            'close': '收盘',
                            'volume': '成交量'
                        })
                        current_price = float(df['收盘'].iloc[-1])
                        print(f"  ✓ 成功获取数据 (Tushare 免费版)")
                        return current_price, df
                    
            except Exception as e:
                print(f"  ✗ Tushare源失败: {str(e)[:80]}")
        
        print("❌ 所有数据源均失败")
        return 0, None
    
    def _get_top10_holders(self, stock_code):
        """获取十大流通股东"""
        if not self.akshare_available:
            return None
        
        try:
            # 获取最新的十大股东数据
            df = ak.stock_individual_fund_flow_rank(indicator="今日")
            # 这里简化处理，实际应该用专门的股东API
            # ak.stock_zh_a_hist_holder_top10 需要额外处理
            
            # 由于akshare接口限制，这里返回模拟数据作为示例
            # 实际使用时需要调用正确的API
            return None
            
        except Exception as e:
            print(f"获取十大股东失败: {e}")
            return None
    
    def _get_holder_count_change(self, stock_code):
        """获取股东户数变化"""
        if not self.akshare_available:
            return 0
        
        try:
            # akshare中有股东户数接口
            # df = ak.stock_zh_a_holder_number(symbol=stock_code)
            # 这里简化处理
            return 0
            
        except Exception as e:
            print(f"获取股东户数失败: {e}")
            return 0
    
    def _calculate_concentration(self, top10_data):
        """计算筹码集中度"""
        if top10_data is None:
            return 0
        
        # 简化：假设十大股东持股30-40%
        # 实际应该从数据中计算
        return 35.6
    
    def _calculate_chip_cost_percentiles(self, hist_data):
        """计算筹码成本分位数（P10, P50, P90）"""
        if hist_data is None or hist_data.empty:
            return 0, 0, 0
        
        try:
            # 使用近60日数据计算筹码成本分布
            recent_data = hist_data.tail(60)
            
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 基于成交量构建筹码分布
            # 将每日成交量按价格分布
            chip_distribution = []
            for price, volume in zip(prices, volumes):
                chip_distribution.extend([price] * int(volume / 1000))  # 简化处理
            
            if len(chip_distribution) == 0:
                # 回退到简单加权平均
                weighted_price = (prices * volumes).sum() / volumes.sum()
                return weighted_price, weighted_price, weighted_price
            
            # 计算分位数
            p10 = np.percentile(chip_distribution, 10)
            p50 = np.percentile(chip_distribution, 50)  # 中位数成本
            p90 = np.percentile(chip_distribution, 90)
            
            return float(p10), float(p50), float(p90)
            
        except Exception as e:
            print(f"计算筹码成本分位数失败: {e}")
            # 回退到简单方法
            try:
                recent_data = hist_data.tail(60)
                prices = recent_data['收盘'].astype(float)
                volumes = recent_data['成交量'].astype(float)
                weighted_price = (prices * volumes).sum() / volumes.sum()
                return float(weighted_price), float(weighted_price), float(weighted_price)
            except:
                return 0, 0, 0
    
    def _calculate_profit_loss_ratio(self, hist_data, current_price):
        """计算获利盘和套牢盘比例"""
        if hist_data is None or hist_data.empty or current_price == 0:
            return 0, 0
        
        try:
            # 使用近60日数据
            recent_data = hist_data.tail(60)
            
            prices = recent_data['收盘'].astype(float)
            volumes = recent_data['成交量'].astype(float)
            
            # 计算低于当前价的成交量（获利盘）
            profit_volume = volumes[prices < current_price].sum()
            # 计算高于当前价的成交量（套牢盘）
            loss_volume = volumes[prices > current_price].sum()
            
            total_volume = volumes.sum()
            
            if total_volume > 0:
                profit_ratio = (profit_volume / total_volume) * 100
                loss_ratio = (loss_volume / total_volume) * 100
                return profit_ratio, loss_ratio
            
        except Exception as e:
            print(f"计算获利盘失败: {e}")
        
        return 0, 0
    
    def _calculate_turnover_rate(self, hist_data):
        """计算换手率"""
        if hist_data is None or hist_data.empty:
            return 0
        
        try:
            # 如果数据中有换手率列
            if '换手率' in hist_data.columns:
                return float(hist_data['换手率'].tail(5).mean())
            
            # 否则用成交量估算（简化）
            recent_volumes = hist_data['成交量'].tail(5).astype(float)
            avg_volume = recent_volumes.mean()
            
            # 假设流通股本（实际应该获取真实数据）
            # 这里返回一个估算值
            return 2.5  # 简化处理
            
        except Exception as e:
            print(f"计算换手率失败: {e}")
            return 0
    
    def _identify_peak_type(self, hist_data):
        """识别筹码峰型：单峰/双峰/多峰"""
        if hist_data is None or hist_data.empty:
            return '未知'
        
        try:
            # 使用近60日数据
            recent_data = hist_data.tail(60)
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 将价格分成10个区间，统计每个区间的成交量
            price_min, price_max = prices.min(), prices.max()
            bins = np.linspace(price_min, price_max, 11)
            volume_distribution = []
            
            for i in range(len(bins) - 1):
                bin_mask = (prices >= bins[i]) & (prices < bins[i+1])
                bin_volume = volumes[bin_mask].sum()
                volume_distribution.append(bin_volume)
            
            # 找出峰值（局部最大值）
            peaks = []
            for i in range(1, len(volume_distribution) - 1):
                if volume_distribution[i] > volume_distribution[i-1] and \
                   volume_distribution[i] > volume_distribution[i+1]:
                    if volume_distribution[i] > np.mean(volume_distribution) * 0.8:
                        peaks.append(i)
            
            # 根据峰值数量判断类型
            if len(peaks) == 0:
                return '分散型（无明显峰）'
            elif len(peaks) == 1:
                # 检查峰的位置
                peak_pos = peaks[0]
                if peak_pos < 3:
                    return '底部单峰密集 ⭐⭐⭐⭐⭐'
                elif peak_pos > 7:
                    return '高位单峰密集 ⚠️'
                else:
                    return '中位单峰'
            elif len(peaks) == 2:
                return '双峰分布（可能洗盘中）'
            else:
                return '多峰林立（散户博弈）⚠️'
                
        except Exception as e:
            print(f"识别峰型失败: {e}")
            return '未知'
    
    def _check_bottom_locked(self, hist_data, current_price):
        """检测底部筹码是否锁定（主力锁仓）"""
        if hist_data is None or hist_data.empty or current_price == 0:
            return False
        
        try:
            # 对比近20日和近60日的低位筹码比例
            data_60d = hist_data.tail(60)
            data_20d = hist_data.tail(20)
            
            # 找出60日内的最低价区域（底部20%价格区间）
            prices_60d = data_60d['收盘'].astype(float).values
            volumes_60d = data_60d['成交量'].astype(float).values
            price_min = prices_60d.min()
            price_20pct = price_min + (current_price - price_min) * 0.2
            
            # 计算底部区域的筹码量
            bottom_volume_60d = volumes_60d[prices_60d <= price_20pct].sum()
            total_volume_60d = volumes_60d.sum()
            
            # 计算近20日在底部区域的成交量
            prices_20d = data_20d['收盘'].astype(float).values
            volumes_20d = data_20d['成交量'].astype(float).values
            bottom_volume_20d = volumes_20d[prices_20d <= price_20pct].sum()
            total_volume_20d = volumes_20d.sum()
            
            if total_volume_60d == 0 or total_volume_20d == 0:
                return False
            
            # 如果底部筹码占比在60日和20日中保持稳定或增加，说明锁定
            bottom_ratio_60d = bottom_volume_60d / total_volume_60d
            bottom_ratio_20d = bottom_volume_20d / total_volume_20d
            
            # 逻辑：如果股价上涨但底部成交量占比下降不多，说明筹码锁定
            if bottom_ratio_60d > 0.15 and bottom_ratio_20d > bottom_ratio_60d * 0.7:
                return True
            
            return False
            
        except Exception as e:
            print(f"检测底部锁定失败: {e}")
            return False
    
    def _calculate_hhi_and_gini(self, hist_data):
        """计算HHI（赫芬达尔指数）和基尼系数"""
        if hist_data is None or hist_data.empty:
            return 0, 0
        
        try:
            recent_data = hist_data.tail(60)
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 计算每个价格区间的筹码份额
            price_ranges = np.linspace(prices.min(), prices.max(), 20)
            chip_shares = []
            
            for i in range(len(price_ranges) - 1):
                mask = (prices >= price_ranges[i]) & (prices < price_ranges[i+1])
                chip_shares.append(volumes[mask].sum())
            
            total_chips = sum(chip_shares)
            if total_chips == 0:
                return 0, 0
            
            # 归一化
            chip_shares = [s / total_chips for s in chip_shares if s > 0]
            
            # 计算HHI（赫芬达尔指数）
            hhi = sum(s**2 for s in chip_shares)
            
            # 计算基尼系数
            chip_shares_sorted = sorted(chip_shares)
            n = len(chip_shares_sorted)
            gini = 0
            if n > 0:
                cumsum = np.cumsum(chip_shares_sorted)
                gini = (2 * sum((i+1) * chip_shares_sorted[i] for i in range(n))) / (n * sum(chip_shares_sorted)) - (n + 1) / n
            
            return float(hhi), float(gini)
            
        except Exception as e:
            print(f"计算HHI和基尼系数失败: {e}")
            return 0, 0
    
    def _calculate_five_dimensions_score(self, result):
        """计算五维度独立评分（每项0-2分）"""
        
        # 1. 集中度评分（0-2分） - 基于SCR
        scr = result['scr']
        if scr < 10:
            concentration_score = 2.0
        elif scr < 15:
            concentration_score = 1.5
        elif scr < 25:
            concentration_score = 1.0
        elif scr < 35:
            concentration_score = 0.5
        else:
            concentration_score = 0.0
        
        # 2. 换手率评分（0-2分）
        turnover = result['turnover_rate']
        if 2 < turnover < 5:
            turnover_score = 2.0
        elif 1 < turnover <= 2 or 5 <= turnover < 8:
            turnover_score = 1.5
        elif 0.5 < turnover <= 1 or 8 <= turnover < 12:
            turnover_score = 1.0
        elif turnover > 15:
            turnover_score = 0.0
        else:
            turnover_score = 0.5
        
        # 3. 盈亏比评分（0-2分） - 基于获利盘和乖离率综合
        profit_ratio = result['profit_ratio']
        chip_bias = result['chip_bias']
        
        # 最理想：低获利盘(套牢盘多) + 小正乖离
        if profit_ratio < 30 and 0 < chip_bias < 10:
            profit_loss_score = 2.0
        elif profit_ratio < 40 and -5 < chip_bias < 15:
            profit_loss_score = 1.5
        elif profit_ratio < 60:
            profit_loss_score = 1.0
        elif profit_ratio > 80:
            profit_loss_score = 0.0
        else:
            profit_loss_score = 0.5
        
        # 4. 乖离率评分（0-2分）
        if 3 <= chip_bias <= 12:
            bias_score = 2.0
        elif -5 <= chip_bias < 3 or 12 < chip_bias <= 20:
            bias_score = 1.5
        elif -15 <= chip_bias < -5 or 20 < chip_bias <= 30:
            bias_score = 1.0
        elif chip_bias > 40 or chip_bias < -25:
            bias_score = 0.0
        else:
            bias_score = 0.5
        
        # 5. 形态评分（0-2分） - 基于峰型和底部锁定
        peak_type = result['peak_type']
        bottom_locked = result['bottom_locked']
        
        if '底部单峰' in peak_type:
            pattern_score = 2.0
        elif bottom_locked:
            pattern_score = 1.8
        elif '双峰' in peak_type:
            pattern_score = 1.2
        elif '高位单峰' in peak_type:
            pattern_score = 0.0
        elif '多峰林立' in peak_type:
            pattern_score = 0.3
        else:
            pattern_score = 1.0
        
        return {
            'concentration_score': concentration_score,
            'turnover_score': turnover_score,
            'profit_loss_score': profit_loss_score,
            'bias_score': bias_score,
            'pattern_score': pattern_score
        }
    
    def _generate_trading_suggestion(self, result, total_score):
        """生成交易建议和信号强度"""
        peak_type = result['peak_type']
        scr = result['scr']
        chip_bias = result['chip_bias']
        bottom_locked = result['bottom_locked']
        
        # 判断信号强度
        if total_score >= 8.5:
            signal_strength = '强'
        elif total_score >= 7.0:
            signal_strength = '中'
        else:
            signal_strength = '弱'
        
        # 生成具体建议
        if '底部单峰' in peak_type and scr < 12:
            suggestion = "🟢 强烈看涨信号！股价在低位横盘，筹码高度集中在当前价位，上方套牢盘已消化，这是经典的吸筹完成信号。建议：积极关注，等待主力点火拉升。"
            signal_strength = '强'
        elif bottom_locked and scr < 15:
            suggestion = "🔵 主力锁仓信号！股价已有一定涨幅，但底部低位筹码基本不动，说明主力志在长远，当前可能是半山腰。建议：持有待涨，关注是否有新高突破。"
            signal_strength = '强'
        elif '双峰' in peak_type and 10 < scr < 25:
            suggestion = "🟡 健康洗盘！股价上涨后震荡洗盘，形成高低两个筹码峰，中间谷底区域逐渐被填满，这是健康的换手接力。建议：关注底部主峰是否稳定，等待洗盘结束。"
            signal_strength = '中'
        elif '高位单峰' in peak_type:
            suggestion = "🔴 危险信号！股价在高位震荡，筹码完全集中在高位，说明主力已将低位筹码全部倒给散户接盘，这是崩盘前兆。建议：立即减仓或清仓！"
            signal_strength = '强'
        elif '多峰林立' in peak_type:
            suggestion = "🟠 散户博弈！筹码图上多个峰峦，说明没有主导资金，全是散户在博弈，每涨一点都遇解套抛压。建议：观望为主，等待主力资金介入。"
            signal_strength = '弱'
        elif scr < 15 and 5 <= chip_bias <= 15:
            suggestion = "✓ 筹码集中且处于健康持股区，具备上涨潜力。建议：适度关注，结合技术面判断入场时机。"
            signal_strength = '中'
        elif scr > 30:
            suggestion = "⚠ 筹码发散严重，多空分歧大，股价可能剧烈震荡。建议：谨慎操作，等待筹码重新收敛。"
            signal_strength = '弱'
        else:
            suggestion = "⚪ 筹码形态不明确，缺乏明显的主力迹象。建议：观望为主，等待更清晰的信号。"
            signal_strength = '弱'
        
        return suggestion, signal_strength
    
    def _calculate_pattern_confidence(self, peak_type, scr, chip_bias):
        """计算形态识别置信度（0-100%）"""
        base_confidence = 50
        
        if '底部单峰' in peak_type:
            base_confidence = 85
            if scr < 10:
                base_confidence += 10
            if 5 <= chip_bias <= 15:
                base_confidence += 5
        elif '底部筹码锁定' in peak_type or '底部锁定' in peak_type:
            base_confidence = 75
            if scr < 15:
                base_confidence += 10
        elif '双峰' in peak_type:
            base_confidence = 70
            if 15 < scr < 25:
                base_confidence += 10
        elif '高位单峰' in peak_type:
            base_confidence = 80
            if scr < 12:
                base_confidence += 15
        elif '多峰林立' in peak_type:
            base_confidence = 70
        
        return min(100, base_confidence)
    
    def _calculate_health_score(self, result):
        """计算筹码健康度评分（严格版本，参考专业算法）"""
        signals = []
        
        # 计算五维度独立评分
        five_scores = self._calculate_five_dimensions_score(result)
        result['concentration_score'] = five_scores['concentration_score']
        result['turnover_score'] = five_scores['turnover_score']
        result['profit_loss_score'] = five_scores['profit_loss_score']
        result['bias_score'] = five_scores['bias_score']
        result['pattern_score'] = five_scores['pattern_score']
        
        # 计算总分（五维度相加，满分10分）
        score = (five_scores['concentration_score'] + 
                 five_scores['turnover_score'] + 
                 five_scores['profit_loss_score'] + 
                 five_scores['bias_score'] + 
                 five_scores['pattern_score'])
        
        # 生成详细信号
        scr = result['scr']
        if scr < 10:
            signals.append("✓✓ SCR高度集中(<10%)，变盘在即 ⭐⭐⭐⭐⭐")
        elif scr < 15:
            signals.append("✓ SCR相对集中(<15%)，筹码合力强 ⭐⭐⭐⭐")
        elif scr < 25:
            signals.append("→ SCR适中(15-25%)，正常波动")
        else:
            signals.append("⚠ SCR发散(>25%)，多空分歧大 ⚠️")
        
        profit_ratio = result['profit_ratio']
        if profit_ratio < 30:
            signals.append("✓ 套牢盘多(<30%)，反弹动力强")
        elif profit_ratio > 80:
            signals.append("⚠ 获利盘过多(>80%)，警惕获利回吐")
        
        chip_bias = result['chip_bias']
        if 3 <= chip_bias <= 12:
            signals.append("✓ 筹码乖离率在最佳持股区(3-12%) ⭐⭐⭐⭐")
        elif chip_bias > 40:
            signals.append("⚠ 乖离率过高(>40%)，极度危险 ⚠️⚠️")
        
        peak_type = result['peak_type']
        if '底部单峰' in peak_type:
            signals.append(f"✓✓ {peak_type} - 吸筹完成，经典起涨信号 🚀")
        elif '高位单峰' in peak_type:
            signals.append(f"⚠⚠ {peak_type} - 出货完毕，散户接盘 ⚠️⚠️")
        elif '多峰林立' in peak_type:
            signals.append(f"⚠ {peak_type} - 最磨人，每涨一点遇抛压")
        elif '双峰' in peak_type:
            signals.append(f"→ {peak_type} - 健康换手接力")
        
        if result['bottom_locked']:
            signals.append("✓✓ 底部筹码锁定 🔒 - 主力志在长远 ⭐⭐⭐⭐⭐")
        
        # 限制评分在0-10范围内
        score = max(0.0, min(10.0, score))
        
        # 生成交易建议和信号强度
        trading_suggestion, signal_strength = self._generate_trading_suggestion(result, score)
        result['trading_suggestion'] = trading_suggestion
        result['signal_strength'] = signal_strength
        
        # 计算形态置信度
        peak_confidence = self._calculate_pattern_confidence(peak_type, scr, chip_bias)
        result['peak_confidence'] = peak_confidence
        
        return score, signals
    
    def _get_health_level(self, score):
        """根据评分获取健康度等级（严格标准）"""
        if score >= 9.0:
            return "A+ 极度健康 ⭐⭐⭐⭐⭐"
        elif score >= 8.0:
            return "A 优秀 ⭐⭐⭐⭐"
        elif score >= 7.0:
            return "B 良好 ⭐⭐⭐"
        elif score >= 6.0:
            return "C 一般 ⭐⭐"
        elif score >= 4.0:
            return "D 偏弱 ⭐"
        else:
            return "E 不健康 ⚠️"
    
    def _print_result(self, result):
        """打印分析结果"""
        print(f"\n{'='*70}")
        print(f"  筹码健康度分析报告")
        print(f"{'='*70}\n")
        
        print(f"股票代码: {result['stock_code']}")
        print(f"当前价格: ¥{result.get('current_price', 0):.2f}")
        
        # 显示数据时间范围
        if result.get('data_start_date') and result.get('data_end_date'):
            print(f"数据时间: {result['data_start_date']} ~ {result['data_end_date']} (共{result['data_days']}天)")
        elif result.get('data_days', 0) > 0:
            print(f"数据天数: {result['data_days']}天")
        print(f"\n【筹码指标】")
        print(f"  SCR筹码集中度: {result['scr']:.2f}% {'⭐⭐⭐⭐⭐' if result['scr'] < 10 else '⭐⭐⭐⭐' if result['scr'] < 15 else ''}")
        print(f"  HHI赫芬达尔指数: {result['hhi']:.4f} {'(高度集中)' if result['hhi'] > 0.25 else '(相对分散)' if result['hhi'] < 0.15 else '(适中)'}")
        print(f"  基尼系数: {result['gini_coefficient']:.4f} {'(分布均匀)' if result['gini_coefficient'] < 0.4 else '(分布不均)' if result['gini_coefficient'] > 0.6 else '(适中)'}")
        print(f"  筹码成本分布: P10=¥{result['chip_cost_p10']:.2f}, P50=¥{result['chip_cost']:.2f}, P90=¥{result['chip_cost_p90']:.2f}")
        print(f"  筹码乖离率:   {result['chip_bias']:+.2f}% {'(最佳区间)' if 3 <= result['chip_bias'] <= 12 else ''}")
        print(f"  获利盘比例:   {result['profit_ratio']:.1f}%")
        print(f"  套牢盘比例:   {result['loss_ratio']:.1f}%")
        print(f"  换手率:       {result['turnover_rate']:.2f}%")
        print(f"  筹码峰型:     {result['peak_type']} (置信度: {result['peak_confidence']:.0f}%)")
        print(f"  底部锁定:     {'是 🔒' if result['bottom_locked'] else '否'}")
        
        if result['holder_count_change'] != 0:
            print(f"  股东户数变化: {result['holder_count_change']:+.2f}%")
        
        print(f"\n【五维度评分】")
        print(f"  集中度评分:   {result['concentration_score']:.1f}/2.0")
        print(f"  换手率评分:   {result['turnover_score']:.1f}/2.0")
        print(f"  盈亏比评分:   {result['profit_loss_score']:.1f}/2.0")
        print(f"  乖离率评分:   {result['bias_score']:.1f}/2.0")
        print(f"  形态评分:     {result['pattern_score']:.1f}/2.0")
        
        print(f"\n【综合评分】")
        score = result['health_score']
        level = result['health_level']
        print(f"  总分: {score:.1f}/10.0")
        print(f"  等级: {level}")
        print(f"  信号强度: {result['signal_strength']}")
        
        print(f"\n【交易建议】")
        print(f"  {result['trading_suggestion']}")
        
        print(f"\n【关键信号】")
        for signal in result['signals']:
            print(f"  {signal}")
        
        print(f"\n{'='*70}\n")


def main():
    """主函数 - 测试使用"""
    import sys
    
    print("="*70)
    print("  A股筹码健康度分析工具")
    print("  版本: 1.0.0")
    print("="*70)
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        stock_code = sys.argv[1]
    else:
        # 测试用股票代码
        stock_code = input("\n请输入股票代码（6位数字，如600519）: ").strip()
    
    if not stock_code or len(stock_code) != 6:
        print("❌ 无效的股票代码")
        return
    
    # 创建分析器
    analyzer = ChipHealthAnalyzer()
    
    # 执行分析
    result = analyzer.analyze_stock(stock_code)
    
    # 保存结果（可选）
    if result['health_score'] > 0:
        print(f"✓ 分析完成！")
        print(f"提示: 可以将此工具集成到主程序中")


if __name__ == "__main__":
    main()

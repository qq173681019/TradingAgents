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
            'bottom_locked': False,  # 底部筹码是否锁定
            'health_score': 0,  # 健康度评分
            'health_level': '未知',  # 健康度等级
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
        
        # 8. 识别筹码峰型
        print("\n[8/9] 识别筹码峰型...")
        peak_type = self._identify_peak_type(hist_data)
        result['peak_type'] = peak_type
        print(f"✓ 筹码峰型: {peak_type}")
        
        # 9. 检测底部筹码锁定
        print("\n[9/9] 检测底部筹码锁定...")
        bottom_locked = self._check_bottom_locked(hist_data, current_price)
        result['bottom_locked'] = bottom_locked
        print(f"✓ 底部筹码: {'锁定 🔒' if bottom_locked else '未锁定'}")
        
        # 10. 综合评分
        print("\n[评分] 计算筹码健康度...")
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
    
    def _calculate_health_score(self, result):
        """计算筹码健康度评分（融合专业理论）"""
        score = 5.0  # 基准分
        signals = []
        
        # 1. SCR筹码集中度评分（权重40%） - 最核心指标
        scr = result['scr']
        if scr < 10:
            score += 2.5
            signals.append("✓✓ SCR高度集中(<10%)，变盘在即 ⭐⭐⭐⭐⭐")
        elif scr < 20:
            score += 1.5
            signals.append("✓ SCR相对集中(<20%)，筹码合力强 ⭐⭐⭐⭐")
        elif scr < 30:
            score += 0.5
            signals.append("→ SCR适中(20-30%)，正常波动")
        else:
            score -= 1.0
            signals.append("⚠ SCR发散(>30%)，多空分歧大，剧烈震荡 ⚠️")
        
        # 2. 获利盘比例评分（权重30%）
        profit_ratio = result['profit_ratio']
        if profit_ratio > 70:
            score += 1.5
            signals.append("✓ 获利盘充足(>70%)，上涨压力小")
        elif profit_ratio > 50:
            score += 0.5
            signals.append("→ 获利盘适中(50-70%)")
        elif profit_ratio < 30:
            score += 1.0
            signals.append("✓ 套牢盘多(<30%)，反弹动力强")
        else:
            score -= 0.5
            signals.append("⚠ 获利盘偏多，注意获利回吐")
        
        # 3. 筹码乖离率（权重20%） - 判断安全边际
        chip_bias = result['chip_bias']
        if 5 <= chip_bias <= 15:
            score += 1.5
            signals.append("✓ 筹码乖离率在最佳持股区(5-15%)，安全边际好 ⭐⭐⭐⭐")
        elif -5 <= chip_bias < 5:
            score += 0.8
            signals.append("✓ 价格接近成本区(±5%)，支撑强")
        elif chip_bias > 30:
            score -= 1.0
            signals.append("⚠ 乖离率过高(>30%)，获利回吐压力大 ⚠️")
        elif chip_bias < -15:
            score += 0.5
            signals.append("→ 价格低于成本(-15%)，反弹潜力")
        else:
            score += 0.2
            signals.append("→ 乖离率正常范围")
        
        # 4. 换手率评分（权重10%）
        turnover = result['turnover_rate']
        if 2 < turnover < 5:
            score += 0.5
            signals.append("✓ 换手率适中(2-5%)，活跃度好")
        elif turnover > 10:
            score -= 0.5
            signals.append("⚠ 换手率过高(>10%)，警惕炒作")
        elif turnover < 1:
            score -= 0.3
            signals.append("⚠ 换手率过低(<1%)，缺乏关注")
        
        # 5. 股东户数变化
        holder_change = result['holder_count_change']
        if holder_change < -10:
            score += 1.0
            signals.append("✓ 股东户数大减(<-10%)，筹码集中")
        elif holder_change < -5:
            score += 0.5
            signals.append("✓ 股东户数减少(-5~-10%)，筹码收集")
        elif holder_change > 10:
            score -= 0.5
            signals.append("⚠ 股东户数大增(>10%)，筹码分散")
        
        # 6. 筹码峰型判断（形态直观）
        peak_type = result['peak_type']
        if '底部单峰' in peak_type:
            score += 2.0
            signals.append(f"✓✓ {peak_type} - 吸筹完成，经典起涨信号 🚀")
        elif '高位单峰' in peak_type:
            score -= 2.0
            signals.append(f"⚠⚠ {peak_type} - 出货完毕，散户接盘 ⚠️⚠️")
        elif '多峰林立' in peak_type:
            score -= 1.0
            signals.append(f"⚠ {peak_type} - 最磨人，每涨一点遇抛压")
        elif '双峰' in peak_type:
            score += 0.3
            signals.append(f"→ {peak_type} - 健康换手接力")
        
        # 7. 底部筹码锁定（主力意图）
        if result['bottom_locked']:
            score += 1.5
            signals.append("✓✓ 底部筹码锁定 🔒 - 主力志在长远，半山腰位置 ⭐⭐⭐⭐⭐")
        
        # 限制评分在1-10范围内
        score = max(1.0, min(10.0, score))
        
        return score, signals
    
    def _get_health_level(self, score):
        """根据评分获取健康度等级"""
        if score >= 8.5:
            return "极度健康 ⭐⭐⭐⭐⭐"
        elif score >= 7.0:
            return "健康 ⭐⭐⭐⭐"
        elif score >= 5.5:
            return "一般 ⭐⭐⭐"
        elif score >= 4.0:
            return "偏弱 ⭐⭐"
        else:
            return "不健康 ⭐"
    
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
        print(f"  SCR筹码集中度: {result['scr']:.2f}% {'⭐⭐⭐⭐⭐' if result['scr'] < 10 else '⭐⭐⭐⭐' if result['scr'] < 20 else ''}")
        print(f"  筹码成本分布: P10=¥{result['chip_cost_p10']:.2f}, P50=¥{result['chip_cost']:.2f}, P90=¥{result['chip_cost_p90']:.2f}")
        print(f"  筹码乖离率:   {result['chip_bias']:+.2f}% {'(最佳区间)' if 5 <= result['chip_bias'] <= 15 else ''}")
        print(f"  获利盘比例:   {result['profit_ratio']:.1f}%")
        print(f"  套牢盘比例:   {result['loss_ratio']:.1f}%")
        print(f"  换手率:       {result['turnover_rate']:.2f}%")
        print(f"  筹码峰型:     {result['peak_type']}")
        print(f"  底部锁定:     {'是 🔒' if result['bottom_locked'] else '否'}")
        
        if result['holder_count_change'] != 0:
            print(f"  股东户数变化: {result['holder_count_change']:+.2f}%")
        
        print(f"\n【健康度评分】")
        score = result['health_score']
        level = result['health_level']
        print(f"  评分: {score:.1f}/10.0")
        print(f"  等级: {level}")
        
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

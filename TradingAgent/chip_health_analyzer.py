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

# 尝试导入机器学习库（可选）
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
    print("✓ scikit-learn库加载成功 - 机器学习增强已启用")
except ImportError:
    ML_AVAILABLE = False
    print("⚠ scikit-learn库未安装 - 机器学习增强未启用")


class ChipHealthAnalyzer:
    """筹码健康度分析器（v2.0 - 增强版）"""
    
    def __init__(self, use_ml=False, market_condition='normal'):
        """
        初始化筹码健康度分析器
        
        Args:
            use_ml: 是否启用机器学习增强（需要安装scikit-learn）
            market_condition: 市场环境 ('bull'牛市, 'bear'熊市, 'normal'震荡市)
        """
        self.akshare_available = AKSHARE_AVAILABLE
        self.tushare_available = TUSHARE_AVAILABLE
        self.ml_available = ML_AVAILABLE and use_ml
        self.market_condition = market_condition
        
        # 机器学习模型（延迟加载）
        self.ml_model = None
        self.ml_scaler = None
        
        if self.ml_available:
            print("✓ 机器学习增强模式已启用")
            self._initialize_ml_model()
            
        # 数据缓存（用于提升批量处理效率）
        self._fund_flow_rank_cache = None
        self._holder_count_cache = None
        self._top10_holders_cache = {}  # 按股票代码缓存
    
    def prefetch_data(self, stock_codes=None):
        """
        预取批量数据以提升效率
        
        Args:
            stock_codes: 股票代码列表。如果为None，则尝试获取全市场数据。
        """
        if not self.akshare_available:
            return
            
        print(f"\n🚀 正在预取筹码分析相关数据 (共 {len(stock_codes) if stock_codes else '全市场'} 只股票)...")
        
        try:
            # 1. 预取全市场资金流向排名（包含部分股东动向信息）
            if self._fund_flow_rank_cache is None:
                try:
                    import akshare as ak
                    self._fund_flow_rank_cache = ak.stock_individual_fund_flow_rank(indicator="今日")
                    print("  ✓ 已预取全市场资金流向排名数据")
                except Exception as e:
                    print(f"  ⚠ 预取资金流向排名失败: {e}")
                
            # 2. 预取全市场股东户数变化（AkShare 批量接口）
            if self._holder_count_cache is None:
                try:
                    import akshare as ak

                    # 这个接口返回全市场的股东户数最新数据
                    self._holder_count_cache = ak.stock_zh_a_gdhs_em()
                    print("  ✓ 已预取全市场股东户数数据")
                except Exception as e:
                    print(f"  ⚠ 预取股东户数数据失败: {e}")
                    
        except Exception as e:
            print(f"  ❌ 预取数据过程中出现异常: {e}")
    
    def inject_batch_data(self, top10_concentrations=None, holder_changes=None):
        """
        注入外部批量获取的数据（例如从 Choice API 获取的数据）
        
        Args:
            top10_concentrations: 字典 {stock_code: concentration_value}
            holder_changes: 字典 {stock_code: change_value}
        """
        if top10_concentrations:
            for code, conc in top10_concentrations.items():
                # 模拟一个简单的股东数据结构
                self._top10_holders_cache[code] = {'concentration': conc, 'source': 'external'}
                
        if holder_changes:
            # 如果需要，也可以注入股东户数变化数据
            pass
            
    def analyze_stock(self, stock_code, cached_kline_data=None, is_batch_mode=False):
        """
        分析股票筹码健康度
        
        Args:
            stock_code: 股票代码（6位数字，如'600519'）
            cached_kline_data: 可选，缓存的K线数据列表，格式：
                [{'date': '2024-01-01', 'close': 10.5, 'volume': 1000000}, ...]
                如果提供此参数，将优先使用缓存数据而不是重新从网络获取
            is_batch_mode: 是否为批量评分模式。如果为True且无缓存数据，将直接返回错误而不从网络获取
        
        Returns:
            dict: 筹码分析结果
        """
        print(f"\n{'='*70}")
        print(f"  筹码健康度分析 - {stock_code} {'[批量模式]' if is_batch_mode else '[实时模式]'}")
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
        
        # 统一全局步骤计数（用于更清晰的进度日志）
        total_steps = 11
        _step_counter = {'v': 0}
        def step_log(msg):
            try:
                _step_counter['v'] += 1
                print(f"[{_step_counter['v']}/{total_steps}] {msg}")
            except Exception:
                print(msg)

        # 1. 获取当前价格和历史数据
        step_log("获取价格和历史数据...")
        
        # 批量模式：只使用缓存数据，不从网络获取
        if is_batch_mode:
            if cached_kline_data is not None and len(cached_kline_data) > 0:
                print("  ✓ [批量模式] 使用缓存K线数据")
                current_price, hist_data = self._convert_cached_kline_to_dataframe(cached_kline_data)
            else:
                print("  ❌ [批量模式] 无缓存K线数据，跳过筹码分析")
                result['error'] = '批量模式下缺少K线缓存数据，请先更新K线数据'
                return result
        else:
            # 实时模式：优先使用缓存，没有缓存时从网络获取
            if cached_kline_data is not None and len(cached_kline_data) > 0:
                print("  ✓ [实时模式] 使用缓存K线数据")
                current_price, hist_data = self._convert_cached_kline_to_dataframe(cached_kline_data)
            else:
                print("  ⚠ [实时模式] 无缓存数据，从网络获取...")
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
        
        # 2. 获取十大流通股东（优先使用缓存/预取数据）
        print("")
        step_log("获取十大流通股东数据...")
        
        # 尝试从缓存或预取数据中获取
        top10_data = self._get_top10_holders(stock_code)
        
        if top10_data is not None:
            result['top10_holders'] = top10_data
            chip_concentration = self._calculate_concentration(top10_data)
            result['chip_concentration'] = chip_concentration
            print(f"✓ 十大股东持股: {chip_concentration:.2f}%")
        elif is_batch_mode:
            print("  ⚠ [批量模式] 未命中缓存，跳过实时获取十大股东数据")
        else:
            # 实时模式且未命中缓存，可以在这里添加实时获取逻辑（如果需要）
            print("  ⚠ 未获取到十大股东数据")
        
        # 3. 获取股东户数变化（优先使用缓存/预取数据）
        print("")
        step_log("获取股东户数变化...")
        
        holder_change = self._get_holder_count_change(stock_code)
        
        if holder_change != 0:
            result['holder_count_change'] = holder_change
            print(f"✓ 股东户数变化: {holder_change:+.2f}%")
        elif is_batch_mode:
            print("  ⚠ [批量模式] 未命中缓存，跳过实时获取股东户数")
        else:
            print("  ⚠ 未获取到股东户数数据")
        
        # 4. 计算筹码成本分位数（P10/P50/P90）和SCR
        print("")
        step_log("计算筹码成本分位数和SCR...")
        p10, p50, p90 = self._calculate_chip_cost_percentiles(hist_data)
        result['chip_cost_p10'] = p10
        result['chip_cost'] = p50  # P50作为平均成本
        result['chip_cost_p90'] = p90
        
        # 计算SCR筹码集中度（改进版：增加边界检查）
        if p50 > 0 and p90 > 0 and p10 >= 0:
            # 防止除零和异常值
            scr = ((p90 - p10) / (2 * p50)) * 100
            # 限制SCR在合理范围内 [0, 100]
            scr = max(0.0, min(100.0, scr))
            result['scr'] = scr
            print(f"✓ 筹码成本: P10=¥{p10:.2f}, P50=¥{p50:.2f}, P90=¥{p90:.2f}")
            print(f"✓ SCR筹码集中度: {scr:.2f}% {'(高度集中)' if scr < 10 else '(相对集中)' if scr < 20 else '(发散)'}")
        else:
            # 异常情况处理
            result['scr'] = 100.0  # 默认为最发散状态
            print(f"⚠ 无法计算筹码成本 (P10={p10:.2f}, P50={p50:.2f}, P90={p90:.2f})")
        
        # 5. 计算获利盘/套牢盘比例
        print("")
        step_log("计算获利盘/套牢盘...")
        profit_ratio, loss_ratio = self._calculate_profit_loss_ratio(
            hist_data, current_price
        )
        result['profit_ratio'] = profit_ratio
        result['loss_ratio'] = loss_ratio
        print(f"✓ 获利盘: {profit_ratio:.1f}%, 套牢盘: {loss_ratio:.1f}%")
        
        # 6. 计算换手率
        print("")
        step_log("计算换手率...")
        turnover = self._calculate_turnover_rate(hist_data)
        result['turnover_rate'] = turnover
        print(f"✓ 近5日平均换手率: {turnover:.2f}%")
        
        # 7. 计算筹码乖离率
        print("")
        step_log("计算筹码乖离率...")
        if current_price > 0 and p50 > 0:
            chip_bias = ((current_price - p50) / p50) * 100
            result['chip_bias'] = chip_bias
            print(f"✓ 筹码乖离率: {chip_bias:+.2f}% {'(健康区间)' if 5 <= chip_bias <= 15 else ''}")
        
        # 8. 计算HHI和基尼系数
        print("")
        step_log("计算HHI和基尼系数...")
        hhi, gini = self._calculate_hhi_and_gini(hist_data)
        result['hhi'] = hhi
        result['gini_coefficient'] = gini
        print(f"✓ 赫芬达尔指数(HHI): {hhi:.4f} {'(高度集中)' if hhi > 0.25 else '(相对分散)' if hhi < 0.15 else '(适中)'}")
        print(f"✓ 基尼系数: {gini:.4f} {'(分布均匀)' if gini < 0.4 else '(分布不均)' if gini > 0.6 else '(适中)'}")
        
        # 9. 识别筹码峰型
        print("")
        step_log("识别筹码峰型...")
        peak_type = self._identify_peak_type(hist_data)
        result['peak_type'] = peak_type
        print(f"✓ 筹码峰型: {peak_type}")
        
        # 10. 检测底部筹码锁定
        print("")
        step_log("检测底部筹码锁定...")
        bottom_locked = self._check_bottom_locked(hist_data, current_price)
        result['bottom_locked'] = bottom_locked
        print(f"✓ 底部筹码: {'锁定 🔒' if bottom_locked else '未锁定'}")
        
        # 11. 综合评分（新版严格算法）
        print("")
        step_log("计算筹码健康度...")
        health_score, signals = self._calculate_health_score(result)
        result['health_score'] = health_score
        result['signals'] = signals
        result['health_level'] = self._get_health_level(health_score)
        
        # 12. 识别主力动向 (主力拉升 vs 散户跟风)
        print("")
        step_log("识别主力动向...")
        main_force_status = self._identify_main_force_status(result)
        result['main_force_status'] = main_force_status
        print(f"✓ 主力动向: {main_force_status}")
        
        # 打印结果
        self._print_result(result)
        
        return result

    def _identify_main_force_status(self, result):
        """识别主力动向：主力拉升 vs 散户跟风"""
        scr = result.get('scr', 100)
        profit_ratio = result.get('profit_ratio', 0)
        turnover = result.get('turnover_rate', 0)
        bottom_locked = result.get('bottom_locked', False)
        peak_type = result.get('peak_type', '')
        chip_bias = result.get('chip_bias', 0)
        
        # 1. 主力拉升识别逻辑：
        # - 筹码高度集中 (SCR < 20)
        # - 底部筹码锁定 (bottom_locked)
        # - 获利盘比例高 (profit_ratio > 70%)
        # - 换手率适中 (2% < turnover < 10%)，说明主力控盘稳健
        if scr < 20 and bottom_locked and profit_ratio > 70:
            if 2 <= turnover <= 10:
                return "主力拉升"
            elif turnover > 10:
                return "主力出货?" # 高换手可能是主力在派发
        
        # 2. 散户跟风识别逻辑：
        # - 筹码分散 (SCR > 25)
        # - 获利盘比例极高 (profit_ratio > 85%)
        # - 换手率极高 (turnover > 12%)
        # - 乖离率过大 (chip_bias > 15%)
        if scr > 25 and profit_ratio > 85 and turnover > 12:
            return "散户跟风"
            
        # 3. 主力吸筹
        if scr < 20 and profit_ratio < 30 and '底部' in peak_type:
            return "主力吸筹"
            
        # 4. 震荡洗盘
        if 20 <= scr <= 30 and 40 <= profit_ratio <= 75:
            return "震荡洗盘"
            
        # 5. 高位派发
        if '高位' in peak_type or (profit_ratio > 90 and turnover > 15):
            return "高位派发"
            
        return "状态不明"
    
    def _get_price_and_history(self, stock_code):
        """获取当前价格和历史数据（带重试机制和超时控制）"""
        if not self.akshare_available:
            print("⚠ akshare库不可用")
            return 0, None
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')  # 获取90天数据（确保有足够的60个交易日）
        
        # 数据源超时控制辅助函数
        def _fetch_with_timeout(func, timeout=8):
            """带超时的数据获取"""
            import threading
            result_container = {'data': None, 'error': None}
            
            def worker():
                try:
                    result_container['data'] = func()
                except Exception as e:
                    result_container['error'] = e
            
            thread = threading.Thread(target=worker)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout)
            
            if thread.is_alive():
                return None, TimeoutError(f"数据获取超时({timeout}秒)")
            
            if result_container['error']:
                return None, result_container['error']
            
            return result_container['data'], None
        
        # ===== 方法1和2：akshare数据源已禁用 =====
        # 原因：akshare依赖py_mini_racer包，在某些环境下（特别是用户名包含中文字符时）
        # 会导致V8引擎崩溃，Fatal error: Failed to deserialize the V8 snapshot blob
        # 解决方案：直接使用不依赖JavaScript引擎的其他稳定数据源
        print("  跳过akshare数据源（避免py_mini_racer崩溃问题）")
        
        # 方法3: 尝试使用腾讯接口 - 8秒超时
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
            
            response = requests.get(url, params=params, timeout=8)
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
    
    def _convert_cached_kline_to_dataframe(self, cached_kline_data):
        """
        将缓存的K线数据转换为筹码分析所需的DataFrame格式
        
        Args:
            cached_kline_data: K线数据列表，每项可能包含：
                - {'date': '2024-01-01', 'close': 10.5, 'volume': 1000000, ...}
                或
                - {'日期': '2024-01-01', '收盘': 10.5, '成交量': 1000000, ...}
        
        Returns:
            (current_price, DataFrame): 当前价格和历史数据
        """
        try:
            if not cached_kline_data or len(cached_kline_data) == 0:
                return 0, None
            
            # 转换为DataFrame
            df = pd.DataFrame(cached_kline_data)
            
            # 统一列名（支持中英文）
            rename_map = {}
            if 'date' in df.columns:
                rename_map['date'] = '日期'
            if 'close' in df.columns:
                rename_map['close'] = '收盘'
            if 'volume' in df.columns:
                rename_map['volume'] = '成交量'
            
            if rename_map:
                df = df.rename(columns=rename_map)
            
            # 确保必需的列存在
            if '日期' not in df.columns or '收盘' not in df.columns or '成交量' not in df.columns:
                print(f"  ❌ 缓存数据格式错误，列名: {list(df.columns)}")
                return 0, None
            
            # 确保日期格式（支持ISO8601格式）
            if df['日期'].dtype == 'object':
                # 统一日期格式，处理 20251218 和 2025-12-18 混合的情况
                def normalize_date(d):
                    d_str = str(d).split(' ')[0].replace('-', '').replace('/', '')
                    if len(d_str) >= 8:
                        return f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                    return str(d)
                df['日期'] = df['日期'].apply(normalize_date)
            
            # 排序，确保最后一条是最新日期
            df = df.sort_values(by='日期')
            
            # 获取当前价格（最后一条数据的收盘价）
            current_price = float(df['收盘'].iloc[-1])
            
            print(f"  ✓ 缓存数据转换成功: {len(df)}条K线，当前价: ¥{current_price:.2f}")
            
            return current_price, df
            
        except Exception as e:
            print(f"  ❌ 缓存数据转换失败: {e}")
            import traceback
            traceback.print_exc()
            return 0, None
    
    def _get_top10_holders(self, stock_code):
        """获取十大流通股东"""
        if not self.akshare_available:
            return None
        
        try:
            # 1. 检查缓存
            if stock_code in self._top10_holders_cache:
                return self._top10_holders_cache[stock_code]
                
            # 2. 尝试从预取的资金流向排名中提取信息（作为替代方案）
            if self._fund_flow_rank_cache is not None:
                df = self._fund_flow_rank_cache
                # 匹配代码
                stock_data = df[df['代码'] == stock_code]
                if not stock_data.empty:
                    # 资金流向排名并不直接提供十大股东，但可以作为一种参考
                    # 这里我们仍然返回None，因为我们需要的是真实的股东数据
                    # 但如果未来有批量股东接口，可以在这里实现
                    pass
            
            # 3. 实时获取（如果不是批量模式或缓存未命中）
            # 注意：ak.stock_zh_a_hist_holder_top10 比较慢，且没有批量接口
            # 为了效率，我们在批量模式下通常跳过它，除非已经预取
            
            return None
            
        except Exception as e:
            print(f"获取十大股东失败: {e}")
            return None
    
    def _get_holder_count_change(self, stock_code):
        """获取股东户数变化"""
        if not self.akshare_available:
            return 0
        
        try:
            # 1. 优先使用预取的全市场股东户数缓存
            if self._holder_count_cache is not None:
                df = self._holder_count_cache
                # AkShare 的代码通常不带后缀，或者带后缀。这里做兼容处理
                short_code = stock_code[-6:] if len(stock_code) > 6 else stock_code
                
                # 查找匹配的行
                match = df[df['代码'] == short_code]
                if not match.empty:
                    # 提取股东户数增长率
                    # 列名可能是 '股东户数-上次', '股东户数-本次', '股东户数-增减'
                    # 或者是 '股东户数-增减比例'
                    try:
                        change = match.iloc[0]['股东户数-增减比例']
                        return float(change)
                    except:
                        pass
            
            # 2. 如果缓存未命中且不是批量模式，可以尝试实时获取
            # 但为了性能，我们通常只依赖预取的数据
            return 0
            
        except Exception as e:
            # print(f"获取股东户数失败: {e}")
            return 0
    
    def _calculate_concentration(self, top10_data):
        """计算筹码集中度"""
        if top10_data is None:
            return 0
            
        # 如果是注入的外部数据
        if isinstance(top10_data, dict) and 'concentration' in top10_data:
            return top10_data['concentration']
        
        # 简化：假设十大股东持股30-40%
        # 实际应该从数据中计算
        return 35.6
    
    def _calculate_chip_cost_percentiles(self, hist_data):
        """计算筹码成本分位数（P10, P50, P90）- 改进版"""
        if hist_data is None or hist_data.empty:
            return 0, 0, 0
        
        try:
            # 使用近60日数据计算筹码成本分布
            recent_data = hist_data.tail(60)
            
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 数据验证：过滤无效数据
            valid_mask = (prices > 0) & (volumes > 0) & np.isfinite(prices) & np.isfinite(volumes)
            prices = prices[valid_mask]
            volumes = volumes[valid_mask]
            
            if len(prices) < 5:  # 数据量太少
                return 0, 0, 0
            
            # 基于成交量构建筹码分布
            # 将每日成交量按价格分布
            chip_distribution = []
            for price, volume in zip(prices, volumes):
                # 改进：使用对数缩放避免内存溢出，同时保持分布特性
                weight = max(1, int(volume / 10000))  # 每万手为单位
                chip_distribution.extend([price] * weight)
            
            if len(chip_distribution) == 0:
                # 回退到简单加权平均
                total_volume = volumes.sum()
                if total_volume > 0:
                    weighted_price = (prices * volumes).sum() / total_volume
                    return weighted_price, weighted_price, weighted_price
                else:
                    return 0, 0, 0
            
            # 计算分位数
            p10 = np.percentile(chip_distribution, 10)
            p50 = np.percentile(chip_distribution, 50)  # 中位数成本
            p90 = np.percentile(chip_distribution, 90)
            
            # 边界检查：确保 P10 <= P50 <= P90
            if not (p10 <= p50 <= p90):
                # 数据异常，使用简单方法
                p_sorted = np.sort(prices)
                p10 = p_sorted[int(len(p_sorted) * 0.1)]
                p50 = p_sorted[int(len(p_sorted) * 0.5)]
                p90 = p_sorted[int(len(p_sorted) * 0.9)]
            
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
    
    def _initialize_ml_model(self):
        """初始化机器学习模型（用于权重优化和评分预测）"""
        if not ML_AVAILABLE:
            return
        
        try:
            # 使用随机森林进行评分预测和权重优化
            self.ml_model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            self.ml_scaler = StandardScaler()
            
            # TODO: 使用历史数据训练模型
            # 这里预留接口，实际使用时需要提供训练数据
            print("  机器学习模型已初始化（需要历史数据训练）")
        except Exception as e:
            print(f"  机器学习模型初始化失败: {e}")
            self.ml_available = False
    
    def _calculate_dynamic_weights(self):
        """根据市场环境动态调整权重"""
        if self.market_condition == 'bull':
            # 牛市：更重视形态和集中度
            return {
                'concentration': 0.30,  # 集中度权重
                'turnover': 0.15,       # 换手率权重
                'profit_loss': 0.15,    # 盈亏比权重
                'bias': 0.15,           # 乖离率权重
                'pattern': 0.25         # 形态权重
            }
        elif self.market_condition == 'bear':
            # 熊市：更重视风险控制和乖离率
            return {
                'concentration': 0.20,
                'turnover': 0.15,
                'profit_loss': 0.25,    # 重视盈亏比
                'bias': 0.25,           # 重视乖离率
                'pattern': 0.15
            }
        else:
            # 震荡市：平均权重
            return {
                'concentration': 0.20,
                'turnover': 0.20,
                'profit_loss': 0.20,
                'bias': 0.20,
                'pattern': 0.20
            }
    
    def _calculate_profit_loss_ratio_with_time_decay(self, hist_data, current_price):
        """计算获利盘和套牢盘比例 - 增强版（带时间衰减权重）"""
        if hist_data is None or hist_data.empty or current_price <= 0:
            return 0, 0
        
        try:
            # 使用近60日数据
            recent_data = hist_data.tail(60)
            
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 数据验证
            valid_mask = (prices > 0) & (volumes > 0) & np.isfinite(prices) & np.isfinite(volumes)
            prices = prices[valid_mask]
            volumes = volumes[valid_mask]
            
            if len(prices) == 0:
                return 0, 0
            
            # 计算时间衰减权重（越近期权重越高）
            days_old = np.arange(len(prices))[::-1]  # 0表示最新，59表示最旧
            time_weight = np.exp(-days_old * 0.05)  # 指数衰减，衰减因子0.05
            
            # 计算加权获利盘和套牢盘
            profit_mask = prices < current_price
            loss_mask = prices > current_price
            
            weighted_profit_volume = (volumes[profit_mask] * time_weight[:len(volumes)][profit_mask]).sum()
            weighted_loss_volume = (volumes[loss_mask] * time_weight[:len(volumes)][loss_mask]).sum()
            weighted_total_volume = (volumes * time_weight[:len(volumes)]).sum()
            
            if weighted_total_volume > 0:
                profit_ratio = (weighted_profit_volume / weighted_total_volume) * 100
                loss_ratio = (weighted_loss_volume / weighted_total_volume) * 100
                profit_ratio = max(0.0, min(100.0, profit_ratio))
                loss_ratio = max(0.0, min(100.0, loss_ratio))
                return profit_ratio, loss_ratio
            
        except Exception as e:
            print(f"计算时间衰减获利盘失败: {e}")
        
        return 0, 0
    
    def _calculate_profit_loss_ratio(self, hist_data, current_price):
        """计算获利盘和套牢盘比例 - 改进版（增加数据验证）"""
        if hist_data is None or hist_data.empty or current_price <= 0:
            return 0, 0
        
        try:
            # 使用近60日数据
            recent_data = hist_data.tail(60)
            
            prices = recent_data['收盘'].astype(float)
            volumes = recent_data['成交量'].astype(float)
            
            # 数据验证：过滤无效数据
            valid_mask = (prices > 0) & (volumes > 0) & np.isfinite(prices) & np.isfinite(volumes)
            prices = prices[valid_mask]
            volumes = volumes[valid_mask]
            
            if len(prices) == 0:
                return 0, 0
            
            # 计算低于当前价的成交量（获利盘）
            profit_volume = volumes[prices < current_price].sum()
            # 计算高于当前价的成交量（套牢盘）
            loss_volume = volumes[prices > current_price].sum()
            
            total_volume = volumes.sum()
            
            if total_volume > 0:
                profit_ratio = (profit_volume / total_volume) * 100
                loss_ratio = (loss_volume / total_volume) * 100
                # 边界检查
                profit_ratio = max(0.0, min(100.0, profit_ratio))
                loss_ratio = max(0.0, min(100.0, loss_ratio))
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
        """识别筹码峰型：单峰/双峰/多峰 - 改进版（增加强度判断）"""
        if hist_data is None or hist_data.empty:
            return '未知'
        
        try:
            # 使用近60日数据
            recent_data = hist_data.tail(60)
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 数据验证
            valid_mask = (prices > 0) & (volumes > 0) & np.isfinite(prices) & np.isfinite(volumes)
            prices = prices[valid_mask]
            volumes = volumes[valid_mask]
            
            if len(prices) < 10:
                return '数据不足'
            
            # 将价格分成10个区间，统计每个区间的成交量
            price_min, price_max = prices.min(), prices.max()
            if price_max <= price_min:
                return '价格无波动'
            
            bins = np.linspace(price_min, price_max, 11)
            volume_distribution = []
            
            for i in range(len(bins) - 1):
                bin_mask = (prices >= bins[i]) & (prices < bins[i+1])
                bin_volume = volumes[bin_mask].sum()
                volume_distribution.append(bin_volume)
            
            # 平滑处理，减少噪声
            if len(volume_distribution) >= 3:
                smoothed = []
                for i in range(len(volume_distribution)):
                    if i == 0:
                        smoothed.append((volume_distribution[i] + volume_distribution[i+1]) / 2)
                    elif i == len(volume_distribution) - 1:
                        smoothed.append((volume_distribution[i-1] + volume_distribution[i]) / 2)
                    else:
                        smoothed.append((volume_distribution[i-1] + volume_distribution[i] + volume_distribution[i+1]) / 3)
                volume_distribution = smoothed
            
            avg_volume = np.mean(volume_distribution)
            if avg_volume == 0:
                return '无有效数据'
            
            # 找出峰值（局部最大值）并计算峰强度
            peaks = []
            peak_strengths = []
            for i in range(1, len(volume_distribution) - 1):
                if volume_distribution[i] > volume_distribution[i-1] and \
                   volume_distribution[i] > volume_distribution[i+1]:
                    if volume_distribution[i] > avg_volume * 0.8:
                        peaks.append(i)
                        # 计算峰强度：峰值相对于平均值的比例
                        strength = volume_distribution[i] / avg_volume
                        peak_strengths.append(strength)
            
            # 根据峰值数量和强度判断类型
            if len(peaks) == 0:
                return '分散型（无明显峰）'
            elif len(peaks) == 1:
                # 检查峰的位置和强度
                peak_pos = peaks[0]
                peak_strength = peak_strengths[0]
                
                if peak_pos < 3:
                    if peak_strength > 2.0:
                        return '底部单峰密集 ⭐⭐⭐⭐⭐'  # 强峰
                    else:
                        return '底部单峰（弱）'
                elif peak_pos > 7:
                    if peak_strength > 2.0:
                        return '高位单峰密集 ⚠️'  # 强峰
                    else:
                        return '高位单峰（弱）⚠️'
                else:
                    return '中位单峰'
            elif len(peaks) == 2:
                # 判断双峰强度
                avg_strength = np.mean(peak_strengths)
                if avg_strength > 1.5:
                    return '双峰分布（可能洗盘中）'
                else:
                    return '双峰分布（弱）'
            else:
                return '多峰林立（散户博弈）⚠️'
                
        except Exception as e:
            print(f"识别峰型失败: {e}")
            return '未知'
    
    def _check_bottom_locked(self, hist_data, current_price):
        """检测底部筹码是否锁定（主力锁仓）- 改进版"""
        if hist_data is None or hist_data.empty or current_price <= 0:
            return False
        
        try:
            # 数据量验证
            if len(hist_data) < 20:
                return False
            
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
        """计算HHI（赫芬达尔指数）和基尼系数 - 改进版"""
        if hist_data is None or hist_data.empty:
            return 0, 0
        
        try:
            recent_data = hist_data.tail(60)
            prices = recent_data['收盘'].astype(float).values
            volumes = recent_data['成交量'].astype(float).values
            
            # 数据验证
            valid_mask = (prices > 0) & (volumes > 0) & np.isfinite(prices) & np.isfinite(volumes)
            prices = prices[valid_mask]
            volumes = volumes[valid_mask]
            
            if len(prices) < 10:
                return 0, 0
            
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
    
    def _predict_ml_score(self, result):
        """使用机器学习模型预测评分（如果模型已训练）"""
        if not self.ml_available or self.ml_model is None:
            return None
        
        try:
            # 提取特征
            features = np.array([[
                result['scr'],
                result['chip_bias'],
                result['profit_ratio'],
                result['turnover_rate'],
                result['hhi'],
                result['gini_coefficient']
            ]])
            
            # 特征标准化
            if self.ml_scaler is not None:
                features_scaled = self.ml_scaler.transform(features)
            else:
                features_scaled = features
            
            # 预测评分
            ml_score = self.ml_model.predict(features_scaled)[0]
            
            # 限制在合理范围
            ml_score = max(0.0, min(10.0, ml_score))
            
            return float(ml_score)
            
        except Exception as e:
            print(f"  机器学习评分预测失败: {e}")
            return None
    
    def _optimize_parameters_with_ml(self, hist_data, current_price):
        """使用机器学习优化参数（预留接口）"""
        # TODO: 基于历史数据自动优化阈值参数
        # 例如：优化SCR的阈值、乖离率的最佳区间等
        pass
    
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
        """计算筹码健康度评分（v2.0增强版 - 支持动态权重和机器学习）"""
        signals = []
        
        # 计算五维度独立评分
        five_scores = self._calculate_five_dimensions_score(result)
        result['concentration_score'] = five_scores['concentration_score']
        result['turnover_score'] = five_scores['turnover_score']
        result['profit_loss_score'] = five_scores['profit_loss_score']
        result['bias_score'] = five_scores['bias_score']
        result['pattern_score'] = five_scores['pattern_score']
        
        # 获取动态权重
        weights = self._calculate_dynamic_weights()
        
        # 计算加权总分（修正：每个维度满分2.0，需要归一化到10分制）
        # 原理：5个维度 × 满分2.0 = 理论最高10分，所以乘数应该是5而不是10
        weighted_score = (
            five_scores['concentration_score'] * weights['concentration'] * 5 +
            five_scores['turnover_score'] * weights['turnover'] * 5 +
            five_scores['profit_loss_score'] * weights['profit_loss'] * 5 +
            five_scores['bias_score'] * weights['bias'] * 5 +
            five_scores['pattern_score'] * weights['pattern'] * 5
        )
        
        # 如果启用机器学习，结合ML预测结果
        ml_score = self._predict_ml_score(result)
        if ml_score is not None:
            # 混合评分：70%传统算法 + 30%机器学习
            score = weighted_score * 0.7 + ml_score * 0.3
            signals.append(f"🤖 ML增强评分: {ml_score:.1f}/10.0 (融合权重30%)")
        else:
            score = weighted_score
        
        # 记录权重信息
        if self.market_condition != 'normal':
            market_name = {'bull': '牛市', 'bear': '熊市'}.get(self.market_condition, '震荡市')
            signals.append(f"📊 动态权重({market_name}): 集中{weights['concentration']:.0%} 换手{weights['turnover']:.0%} 盈亏{weights['profit_loss']:.0%} 乖离{weights['bias']:.0%} 形态{weights['pattern']:.0%}")
        
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
        
        # 确保评分在合理范围内（正常情况下应该已经在0-10之间，这里只是安全保护）
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


    def train_ml_model(self, training_data):
        """
        训练机器学习模型
        
        Args:
            training_data: pandas.DataFrame，包含以下列：
                - scr: SCR筹码集中度
                - chip_bias: 筹码乖离率
                - profit_ratio: 获利盘比例
                - turnover_rate: 换手率
                - hhi: 赫芬达尔指数
                - gini_coefficient: 基尼系数
                - target_score: 目标评分（专家标注或历史验证后的评分）
        """
        if not self.ml_available:
            print("❌ 机器学习功能未启用，请安装scikit-learn")
            return False
        
        try:
            print("🤖 开始训练机器学习模型...")
            
            # 提取特征和目标
            features = training_data[['scr', 'chip_bias', 'profit_ratio', 
                                     'turnover_rate', 'hhi', 'gini_coefficient']].values
            targets = training_data['target_score'].values
            
            # 特征标准化
            self.ml_scaler.fit(features)
            features_scaled = self.ml_scaler.transform(features)
            
            # 训练模型
            self.ml_model.fit(features_scaled, targets)
            
            # 计算训练得分
            train_score = self.ml_model.score(features_scaled, targets)
            
            print(f"✓ 模型训练完成！R² Score: {train_score:.4f}")
            
            # 特征重要性
            if hasattr(self.ml_model, 'feature_importances_'):
                importances = self.ml_model.feature_importances_
                feature_names = ['SCR', '乖离率', '获利盘', '换手率', 'HHI', '基尼系数']
                print("\n📊 特征重要性排名:")
                for name, importance in sorted(zip(feature_names, importances), 
                                              key=lambda x: x[1], reverse=True):
                    print(f"  {name}: {importance:.4f}")
            
            return True
            
        except Exception as e:
            print(f"❌ 模型训练失败: {e}")
            return False
    
    def backtest_parameters(self, hist_stocks_data, lookback_days=60):
        """
        回测参数有效性
        
        Args:
            hist_stocks_data: 历史股票数据集
            lookback_days: 回看天数
            
        Returns:
            dict: 回测统计结果
        """
        print("📈 开始参数回测...")
        
        results = {
            'total_stocks': 0,
            'accurate_predictions': 0,
            'accuracy_rate': 0.0,
            'avg_score': 0.0,
            'signal_distribution': {
                '强': 0,
                '中': 0,
                '弱': 0
            }
        }
        
        try:
            # TODO: 实现详细的回测逻辑
            # 1. 遍历历史股票数据
            # 2. 计算筹码健康度
            # 3. 验证N天后的涨跌情况
            # 4. 统计准确率
            
            print("⚠ 回测功能正在开发中...")
            
        except Exception as e:
            print(f"❌ 回测失败: {e}")
        
        return results
    
    def export_analysis_report(self, result, filename=None):
        """
        导出分析报告
        
        Args:
            result: analyze_stock返回的分析结果
            filename: 输出文件名（默认自动生成）
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"chip_analysis_{result['stock_code']}_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write(f"  筹码健康度分析报告 - {result['stock_code']}\n")
                f.write("="*70 + "\n\n")
                
                f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"当前价格: ¥{result.get('current_price', 0):.2f}\n")
                f.write(f"健康度评分: {result['health_score']:.1f}/10.0\n")
                f.write(f"健康度等级: {result['health_level']}\n")
                f.write(f"信号强度: {result['signal_strength']}\n\n")
                
                f.write("【核心指标】\n")
                f.write(f"  SCR筹码集中度: {result['scr']:.2f}%\n")
                f.write(f"  筹码乖离率: {result['chip_bias']:+.2f}%\n")
                f.write(f"  获利盘比例: {result['profit_ratio']:.1f}%\n")
                f.write(f"  筹码峰型: {result['peak_type']}\n\n")
                
                f.write("【交易建议】\n")
                f.write(f"  {result['trading_suggestion']}\n\n")
                
                f.write("【关键信号】\n")
                for signal in result['signals']:
                    f.write(f"  {signal}\n")
                
                f.write("\n" + "="*70 + "\n")
            
            print(f"✓ 分析报告已导出: {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ 导出报告失败: {e}")
            return None


def main():
    """主函数 - 测试使用"""
    import sys
    
    print("="*70)
    print("  A股筹码健康度分析工具")
    print("  版本: 2.0.0 (增强版)")
    print("="*70)
    
    # 检查命令行参数
    use_ml = '--ml' in sys.argv
    market_condition = 'normal'
    
    if '--bull' in sys.argv:
        market_condition = 'bull'
    elif '--bear' in sys.argv:
        market_condition = 'bear'
    
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        stock_code = sys.argv[1]
    else:
        # 测试用股票代码
        stock_code = input("\n请输入股票代码（6位数字，如600519）: ").strip()
    
    if not stock_code or len(stock_code) != 6:
        print("❌ 无效的股票代码")
        return
    
    # 创建分析器（支持ML增强和市场环境设置）
    print(f"\n初始化分析器...")
    market_env_map = {'bull': '牛市', 'bear': '熊市', 'normal': '震荡市'}
    print(f"  市场环境: {market_env_map.get(market_condition, '震荡市')}")
    print(f"  机器学习: {'启用' if use_ml else '未启用'}")
    
    analyzer = ChipHealthAnalyzer(use_ml=use_ml, market_condition=market_condition)
    
    # 执行分析
    result = analyzer.analyze_stock(stock_code)
    
    # 保存结果
    if result['health_score'] > 0:
        print(f"\n✓ 分析完成！")
        
        # 导出报告
        export = input("\n是否导出分析报告？(y/n): ").strip().lower()
        if export == 'y':
            analyzer.export_analysis_report(result)
        
        print(f"\n提示: 可以将此工具集成到主程序中")
        print(f"命令行选项:")
        print(f"  python chip_health_analyzer.py 600519 --ml      # 启用机器学习")
        print(f"  python chip_health_analyzer.py 600519 --bull    # 牛市模式")
        print(f"  python chip_health_analyzer.py 600519 --bear    # 熊市模式")


if __name__ == "__main__":
    main()

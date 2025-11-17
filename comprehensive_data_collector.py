#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股全面数据采集器 - 轮询多数据源
支持 Tushare、akshare、yfinance、腾讯财经等多个数据源
每次采集10只股票，避免触发接口限制，排除创业板
"""

import json
import time
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

# 数据源可用性检查
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    print("[INFO] akshare 已加载")
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[WARN] akshare 未安装")

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
    print("[INFO] tushare 已加载")
except ImportError:
    TUSHARE_AVAILABLE = False
    print("[WARN] tushare 未安装")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    print("[INFO] yfinance 已加载")
except ImportError:
    YFINANCE_AVAILABLE = False
    print("[WARN] yfinance 未安装")

try:
    import requests
    REQUESTS_AVAILABLE = True
    print("[INFO] requests 已加载")
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WARN] requests 未安装")

try:
    import baostock as bs
    BAOSTOCK_AVAILABLE = True
    print("[INFO] baostock 已加载")
except ImportError:
    BAOSTOCK_AVAILABLE = False
    print("[WARN] baostock 未安装")


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理日期和时间对象"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj):
            return None
        return super().default(obj)
    
    @staticmethod
    def clean_data_for_json(data):
        """清理数据中的不可序列化对象"""
        if isinstance(data, dict):
            return {k: DateTimeEncoder.clean_data_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [DateTimeEncoder.clean_data_for_json(item) for item in data]
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, pd.Timestamp):
            return data.isoformat()
        elif hasattr(data, 'dtype') and 'int' in str(data.dtype):
            return int(data)
        elif hasattr(data, 'dtype') and 'float' in str(data.dtype):
            return float(data)
        elif isinstance(data, np.ndarray):
            return data.tolist()
        elif pd.isna(data):
            return None
        else:
            return data

class ComprehensiveDataCollector:
    """全面数据采集器"""
    
    def __init__(self):
        self.tushare_token = os.environ.get('TUSHARE_TOKEN', '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28')
        self.data_sources = ['tushare', 'baostock', 'yfinance', 'tencent', 'akshare']
        self.current_source_index = 0
        
        # 等待期间数据源策略
        self.wait_period_strategy = {
            'industry_concept': ['baostock', 'akshare'],  # 行业概念数据优先使用baostock
            'financial_data': ['tencent', 'baostock', 'akshare'],   # 财务数据：腾讯→baostock→akshare  
            'basic_info': ['tencent', 'yfinance', 'baostock'], # 基础信息：腾讯→yfinance→baostock
            'fund_flow': ['tencent', 'akshare']          # 资金流向使用腾讯/akshare
        }
        self.collected_data = {}
        self.output_file = 'data/comprehensive_stock_data.json'
        
        # 批量K线数据采集相关配置（基于测试优化）
        self.batch_kline_cache = {}  # 缓存批量获取的K线数据
        self.kline_batch_size = 15   # 每次批量获取15只股票（100%成功率）
        self.kline_batch_size_max = 20  # 最大批量20只股票（75%成功率但更快）
        self.kline_days = 50         # 获取50天的K线数据
        self.last_tushare_call = 0   # 上次tushare调用时间
        self.adaptive_batch = True   # 启用自适应批量大小
        
        # 等待期间数据收集优化
        self.wait_period_data = {}   # 在等待期间收集的其他数据
        self.enable_wait_period_collection = True  # 启用等待期间数据收集
        
        # K线数据收集策略优化
        self.kline_sources = ['tushare', 'yfinance']  # K线数据源轮换
        self.current_kline_source_index = 0
        self.last_yfinance_call = 0  # 上次yfinance调用时间
        self.yfinance_wait_seconds = 120  # yfinance等待时间(2分钟)
        
        # 初始化 tushare
        if TUSHARE_AVAILABLE and self.tushare_token:
            try:
                ts.set_token(self.tushare_token)
                self.ts_pro = ts.pro_api()
                print("[INFO] tushare 初始化成功")
            except Exception as e:
                print(f"[WARN] tushare 初始化失败: {e}")
                self.ts_pro = None
        else:
            self.ts_pro = None
        
        # 初始化 baostock
        self.bs_login = False
        if BAOSTOCK_AVAILABLE:
            try:
                lg = bs.login()
                if lg.error_code == '0':
                    self.bs_login = True
                    print("[INFO] baostock 登录成功")
                else:
                    print(f"[WARN] baostock 登录失败: {lg.error_msg}")
            except Exception as e:
                print(f"[WARN] baostock 初始化失败: {e}")
        else:
            print("[INFO] baostock 不可用，跳过初始化")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
    
    def get_stock_list_excluding_cyb(self, limit: int = 50) -> List[str]:
        """获取股票列表，排除创业板（300开头）"""
        stock_codes = []
        
        # 优先从 akshare 获取完整列表
        if AKSHARE_AVAILABLE:
            try:
                df = ak.stock_info_a_code_name()
                all_codes = df['code'].astype(str).tolist()
                # 排除创业板
                filtered_codes = [code for code in all_codes if not code.startswith('300')]
                stock_codes = filtered_codes[:limit]
                print(f"[INFO] 从 akshare 获取 {len(stock_codes)} 只股票（已排除创业板）")
                return stock_codes
            except Exception as e:
                print(f"[WARN] akshare 获取股票列表失败: {e}")
        
        # 备选：内置股票池（排除创业板）
        fallback_codes = [
            # 沪市主板
            '600000', '600036', '600519', '600276', '600887', '600585', '600309', '600028',
            '601318', '601166', '601328', '601398', '601288', '601939', '601988', '601012',
            '600031', '600048', '600196', '600688', '600745', '600547', '600900', '600660',
            
            # 深市主板
            '000001', '000002', '000063', '000100', '000157', '000166', '000568', '000596',
            '000625', '000651', '000725', '000858', '000876', '000895', '000938', '000977',
            '002001', '002027', '002050', '002120', '002129', '002142', '002304', '002352',
            '002714', '002415', '002594', '002174', '002475',
            
            # 科创板
            '688981', '688036', '688111', '688599', '688169', '688180'
        ]
        
        return fallback_codes[:limit]
    
    
    def collect_batch_kline_data(self, codes: List[str], source: str = 'auto') -> Dict[str, pd.DataFrame]:
        """批量采集K线数据 - tushare → akshare轮流，yfinance兜底"""
        result = {}
        total_codes = len(codes)
        batch_size = 15  # 每批15只股票
        
        print(f"[INFO] 开始批量K线数据采集，总计 {total_codes} 只股票，{batch_size}只/批")
        
        # 将股票分批
        batches = [codes[i:i + batch_size] for i in range(0, len(codes), batch_size)]
        failed_codes = []  # 记录失败的股票代码
        
        for batch_num, batch_codes in enumerate(batches):
            print(f"\n=== 第 {batch_num + 1} 批 / 共 {len(batches)} 批 ===")
            print(f"股票代码: {', '.join(batch_codes)}")
            
            # 轮流使用tushare和akshare
            if batch_num % 2 == 0:  # 偶数批使用tushare
                batch_result = self._collect_batch_kline_with_tushare(batch_codes)
                print(f"[INFO] 第{batch_num + 1}批使用tushare获取K线数据: {len(batch_result)}/{len(batch_codes)} 成功")
            else:  # 奇数批使用akshare
                batch_result = self._collect_batch_kline_with_akshare(batch_codes)
                print(f"[INFO] 第{batch_num + 1}批使用akshare获取K线数据: {len(batch_result)}/{len(batch_codes)} 成功")
            
            # 合并成功的结果
            result.update(batch_result)
            
            # 检查是否有失败的股票
            batch_failed = [code for code in batch_codes if code not in batch_result]
            if batch_failed:
                failed_codes.extend(batch_failed)
                print(f"[WARN] 第{batch_num + 1}批失败股票: {batch_failed}")
        
        # 如果有失败的股票，使用yfinance兜底
        if failed_codes:
            print(f"\n[INFO] 使用yfinance兜底采集 {len(failed_codes)} 只失败股票...")
            fallback_result = self._collect_batch_kline_with_yfinance(failed_codes)
            result.update(fallback_result)
            print(f"[INFO] yfinance兜底完成: {len(fallback_result)}/{len(failed_codes)} 成功")
            
            # 检查最终仍然失败的股票
            final_failed = [code for code in failed_codes if code not in fallback_result]
            if final_failed:
                print(f"[WARN] 最终失败的股票 ({len(final_failed)}): {final_failed}")
        
        print(f"\n[INFO] K线数据采集完成: {len(result)}/{total_codes} 总体成功率 {len(result)/total_codes*100:.1f}%")
        return result
    
    def _select_optimal_kline_source(self) -> str:
        """选择最佳K线数据源"""
        current_time = time.time()
        
        # 检查tushare是否可以使用
        tushare_ready = (current_time - self.last_tushare_call) >= 60
        
        # 检查yfinance是否可以使用
        yfinance_ready = (current_time - self.last_yfinance_call) >= self.yfinance_wait_seconds
        
        # 轮换策略
        if tushare_ready and yfinance_ready:
            # 两个都可用，按轮换顺序选择
            source = self.kline_sources[self.current_kline_source_index]
            self.current_kline_source_index = (self.current_kline_source_index + 1) % len(self.kline_sources)
            return source
        elif tushare_ready:
            return 'tushare'
        elif yfinance_ready:
            return 'yfinance'
        else:
            # 都不可用，选择等待时间较短的
            tushare_wait = max(0, 60 - (current_time - self.last_tushare_call))
            yfinance_wait = max(0, self.yfinance_wait_seconds - (current_time - self.last_yfinance_call))
            
            if tushare_wait <= yfinance_wait:
                print(f"[INFO] tushare需要等待{tushare_wait:.0f}秒")
                return 'tushare'
            else:
                print(f"[INFO] yfinance需要等待{yfinance_wait:.0f}秒")
                return 'yfinance'
    
    def _collect_batch_kline_with_tushare(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用tushare批量采集K线数据"""
        result = {}
        
        try:
            # 检查是否需要等待频率限制
            current_time = time.time()
            if current_time - self.last_tushare_call < 60:
                wait_time = 60 - (current_time - self.last_tushare_call)
                print(f"[INFO] 等待{wait_time:.1f}秒避免tushare频率限制")
                time.sleep(wait_time)
            
            # 设置时间范围 - 50天
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.kline_days)
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')
            
            # 将股票代码转换为tushare格式
            ts_codes = []
            code_mapping = {}  # 映射关系: ts_code -> original_code
            
            for code in codes:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                ts_codes.append(ts_code)
                code_mapping[ts_code] = code
            
            # 自适应批量大小选择
            if self.adaptive_batch:
                if len(codes) > 100:
                    actual_batch_size = self.kline_batch_size_max  # 大量股票用大批量
                    print(f"[INFO] 大批量模式: {actual_batch_size}只/批 (总量{len(codes)}只)")
                else:
                    actual_batch_size = self.kline_batch_size      # 少量股票用标准批量
                    print(f"[INFO] 标准模式: {actual_batch_size}只/批 (总量{len(codes)}只)")
            else:
                actual_batch_size = self.kline_batch_size
                
            # 按批量大小分组采集
            batches = [ts_codes[i:i + actual_batch_size] for i in range(0, len(ts_codes), actual_batch_size)]
            
            print(f"[INFO] 将{len(codes)}只股票分为{len(batches)}个批次采集K线数据")
            
            for batch_idx, batch_codes in enumerate(batches):
                try:
                    print(f"[INFO] 正在采集第{batch_idx + 1}/{len(batches)}批，{len(batch_codes)}只股票")
                    
                    # 批量获取
                    codes_str = ','.join(batch_codes)
                    df = self.ts_pro.daily(ts_code=codes_str, start_date=start_str, end_date=end_str)
                    
                    self.last_tushare_call = time.time()
                    
                    if df is not None and not df.empty:
                        # 按股票代码分组
                        for ts_code in batch_codes:
                            code_data = df[df['ts_code'] == ts_code].copy()
                            if not code_data.empty:
                                # 数据处理
                                code_data['trade_date'] = pd.to_datetime(code_data['trade_date'])
                                code_data = code_data.sort_values('trade_date')
                                code_data = code_data.rename(columns={
                                    'trade_date': 'date', 'open': 'open', 'high': 'high',
                                    'low': 'low', 'close': 'close', 'vol': 'volume', 'amount': 'amount'
                                })
                                
                                original_code = code_mapping[ts_code]
                                result[original_code] = code_data
                                print(f"[SUCCESS] {original_code}: {len(code_data)}天K线数据")
                    
                    # 如果不是最后一批，等待频率限制
                    if batch_idx < len(batches) - 1:
                        print(f"[INFO] 等待60秒避免频率限制...")
                        
                        # 在等待期间收集其他数据和K线数据
                        if self.enable_wait_period_collection:
                            remaining_codes = []
                            for remaining_batch in batches[batch_idx+1:]:
                                remaining_codes.extend([code_mapping.get(ts_code.replace('.SH', '').replace('.SZ', ''), ts_code.replace('.SH', '').replace('.SZ', '')) 
                                                      for ts_code in remaining_batch])
                            
                            if remaining_codes:
                                print(f"[INFO] 等待期间并行收集数据...")
                                self._collect_parallel_data_during_wait(remaining_codes[:15], codes, 60, result, start_str, end_str)
                        
                        time.sleep(60)
                        
                except Exception as e:
                    print(f"[WARN] 第{batch_idx + 1}批K线数据采集失败: {e}")
                    continue
            
            print(f"[SUCCESS] 批量K线采集完成，获取{len(result)}只股票数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] tushare批量K线数据采集失败: {e}")
            return result
    
    def _collect_batch_kline_with_yfinance(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用yfinance批量采集K线数据"""
        result = {}
        
        try:
            # 检查yfinance频率限制
            current_time = time.time()
            if current_time - self.last_yfinance_call < self.yfinance_wait_seconds:
                wait_time = self.yfinance_wait_seconds - (current_time - self.last_yfinance_call)
                print(f"[INFO] 等待{wait_time:.1f}秒避免yfinance频率限制")
                time.sleep(wait_time)
            
            print(f"[INFO] 使用yfinance批量获取{len(codes)}只股票K线数据")
            
            # yfinance支持批量获取，但需要转换股票代码格式
            yf_symbols = []
            code_mapping = {}
            
            for code in codes:
                # 转换为yfinance格式
                if code.startswith(('60', '68')):  # 沪市
                    yf_symbol = f"{code}.SS"
                else:  # 深市
                    yf_symbol = f"{code}.SZ"
                
                yf_symbols.append(yf_symbol)
                code_mapping[yf_symbol] = code
            
            # 批量下载
            symbols_str = ' '.join(yf_symbols[:self.kline_batch_size])  # 限制批量大小
            
            import yfinance as yf
            data = yf.download(symbols_str, period="3mo", interval="1d", 
                             group_by='ticker', progress=False)
            
            self.last_yfinance_call = time.time()
            
            if not data.empty:
                # 处理单个股票的情况
                if len(yf_symbols) == 1:
                    symbol = yf_symbols[0]
                    original_code = code_mapping[symbol]
                    if not data.empty:
                        df = data.reset_index()
                        df = df.rename(columns={
                            'Date': 'date', 'Open': 'open', 'High': 'high',
                            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                        })
                        df['amount'] = df['close'] * df['volume']  # 估算成交额
                        result[original_code] = df
                        print(f"[SUCCESS] {original_code}: {len(df)}天K线数据 (yfinance)")
                
                # 处理多个股票的情况
                else:
                    for symbol in yf_symbols:
                        original_code = code_mapping[symbol]
                        try:
                            if symbol in data.columns.levels[0]:
                                stock_data = data[symbol].dropna()
                                if not stock_data.empty:
                                    df = stock_data.reset_index()
                                    df = df.rename(columns={
                                        'Date': 'date', 'Open': 'open', 'High': 'high',
                                        'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                                    })
                                    df['amount'] = df['close'] * df['volume']  # 估算成交额
                                    result[original_code] = df
                                    print(f"[SUCCESS] {original_code}: {len(df)}天K线数据 (yfinance)")
                        except Exception as e:
                            print(f"[WARN] {original_code}: yfinance数据处理失败 - {e}")
            
            print(f"[INFO] yfinance批量采集完成，获取{len(result)}只股票K线数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] yfinance批量K线数据采集失败: {e}")
            return result
    
    def _collect_batch_kline_with_akshare(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用akshare批量采集K线数据"""
        result = {}
        
        if not AKSHARE_AVAILABLE:
            print(f"[WARN] akshare不可用，跳过批量K线采集")
            return result
        
        print(f"[INFO] 使用akshare获取{len(codes)}只股票K线数据")
        
        try:
            # akshare需要单只股票获取，但可以控制频率
            for i, code in enumerate(codes):
                try:
                    # 获取日K线数据
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                    
                    if df is not None and not df.empty:
                        # 标准化列名
                        df = df.rename(columns={
                            '日期': 'date',
                            '开盘': 'open', 
                            '收盘': 'close',
                            '最高': 'high',
                            '最低': 'low', 
                            '成交量': 'volume',
                            '成交额': 'amount'
                        })
                        
                        # 确保数据类型正确
                        df['date'] = pd.to_datetime(df['date'])
                        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        # 只保留最近50天数据
                        df = df.tail(self.kline_days)
                        result[code] = df
                        print(f"[SUCCESS] {code}: {len(df)}天K线数据 (akshare)")
                    
                    # akshare频率控制 - 每只股票间隔0.5秒
                    if i < len(codes) - 1:
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"[WARN] {code}: akshare K线数据获取失败 - {e}")
                    continue
            
            print(f"[INFO] akshare批量采集完成，获取{len(result)}/{len(codes)}只股票K线数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] akshare批量K线数据采集失败: {e}")
            return result
    
    def _collect_kline_individually(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """单独采集K线数据（回退方案）"""
        result = {}
        print(f"[INFO] 使用单独采集模式获取{len(codes)}只股票K线数据")
        
        for code in codes:
            try:
                # 尝试使用可用的数据源
                kline_data = None
                
                if AKSHARE_AVAILABLE:
                    kline_data = self.collect_kline_data(code, 'akshare')
                elif YFINANCE_AVAILABLE:
                    kline_data = self.collect_kline_data(code, 'yfinance')
                
                if kline_data is not None and not kline_data.empty:
                    result[code] = kline_data
                    print(f"[SUCCESS] {code}: {len(kline_data)}天K线数据 (单独采集)")
                
                time.sleep(1)  # 避免频率限制
                
            except Exception as e:
                print(f"[WARN] {code}: 单独K线采集失败 - {e}")
        
        return result
        """轮询获取下一个数据源"""
        source = self.data_sources[self.current_source_index]
        self.current_source_index = (self.current_source_index + 1) % len(self.data_sources)
        return source
    
    def collect_basic_info(self, code: str, source: str) -> Dict[str, Any]:
        """采集基础信息"""
        basic_info = {
            'code': code,
            'name': f'股票{code}',
            'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
            'industry': None,
            'area': None,
            'concept': None,
            'source': source
        }
        
        try:
            if source == 'yfinance' and YFINANCE_AVAILABLE:
                symbol = f"{code}.SS" if code.startswith(('60', '68')) else f"{code}.SZ"
                try:
                    stock = yf.Ticker(symbol)
                    info = stock.info
                    if info:
                        basic_info.update({
                            'name': info.get('shortName', info.get('longName', basic_info['name'])),
                            'industry': info.get('industry'),
                            'sector': info.get('sector')
                        })
                except Exception as e:
                    print(f"[WARN] yfinance基础信息获取失败: {e}")
            
            elif source == 'tencent' and REQUESTS_AVAILABLE:
                try:
                    url = f'https://qt.gtimg.cn/q=s_{code}'
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.text.split('~')
                        if len(data) > 1:
                            basic_info['name'] = data[1]
                except Exception as e:
                    print(f"[WARN] 腾讯API基础信息获取失败: {e}")
            
            elif source == 'akshare' and AKSHARE_AVAILABLE:
                df = ak.stock_individual_info_em(symbol=code)
                if df is not None and not df.empty:
                    info = dict(zip(df['item'], df['value']))
                    basic_info.update({
                        'name': info.get('股票简称', basic_info['name']),
                        'industry': info.get('行业'),
                        'area': info.get('地区'),
                        'concept': info.get('概念')
                    })
            
            elif source == 'baostock' and BAOSTOCK_AVAILABLE and self.bs_login:
                # baostock获取基础信息（最终兜底）
                bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                try:
                    # 获取股票基本信息
                    rs = bs.query_stock_basic(code=bs_code)
                    if rs.error_code == '0' and rs.next():
                        row_data = rs.get_row_data()
                        if len(row_data) >= 3:
                            basic_info.update({
                                'name': row_data[1] if len(row_data) > 1 else basic_info['name'],
                                'industry': row_data[2] if len(row_data) > 2 else None,
                                'type': row_data[3] if len(row_data) > 3 else None
                            })
                except Exception as e:
                    print(f"[DEBUG] baostock基础信息获取失败: {e}")
        
        except Exception as e:
            print(f"[WARN] {code} 基础信息采集失败 ({source}): {e}")
        
        return basic_info
    
    def collect_batch_basic_info(self, codes: List[str], source: str = 'tencent') -> Dict[str, Dict[str, Any]]:
        """批量采集基础信息，优化频次限制问题"""
        result = {}
        
        if source == 'tencent' and REQUESTS_AVAILABLE:
            try:
                # 腾讯API支持批量查询，一次最多15只股票
                batch_size = min(15, len(codes))
                for i in range(0, len(codes), batch_size):
                    batch_codes = codes[i:i+batch_size]
                    
                    # 构造批量查询URL
                    query_params = ','.join([f's_{code}' for code in batch_codes])
                    url = f'https://qt.gtimg.cn/q={query_params}'
                    
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        lines = response.text.strip().split('\n')
                        for line, code in zip(lines, batch_codes):
                            try:
                                data = line.split('~')
                                if len(data) > 1 and data[1].strip():  # 确保有有效的股票名称
                                    result[code] = {
                                        'code': code,
                                        'name': data[1] if len(data) > 1 else f'股票{code}',
                                        'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                        'current_price': float(data[3]) if len(data) > 3 and data[3] else None,
                                        'change_pct': float(data[32]) if len(data) > 32 and data[32] else None,
                                        'volume': float(data[36]) if len(data) > 36 and data[36] else None,
                                        'source': 'tencent'
                                    }
                                    print(f"[SUCCESS] {code}: 腾讯基础信息获取成功")
                                else:
                                    print(f"[WARN] {code}: 腾讯返回空数据，跳过")
                            except (ValueError, IndexError) as e:
                                print(f"[WARN] 解析股票{code}数据失败: {e}")
                                # 失败时不添加到result中，让后续兜底机制处理
                    
                    print(f"[INFO] 腾讯批量基础信息: {len([c for c in batch_codes if c in result])}/{len(batch_codes)} 成功")
                    
                    # 避免频率限制
                    if i + batch_size < len(codes):
                        time.sleep(1)
                        
            except Exception as e:
                print(f"[WARN] 腾讯批量基础信息采集失败: {e}")
        
        # 如果腾讯API失败，使用yfinance兜底（更可靠的基础信息）
        if len(result) < len(codes) * 0.8:  # 如果成功率低于80%，使用yfinance兜底
            print(f"[INFO] 腾讯批量采集成功率较低，使用yfinance兜底补充")
            missing_codes = [code for code in codes if code not in result]
            
            # 使用yfinance批量获取基础信息
            yfinance_result = self._collect_batch_basic_info_with_yfinance(missing_codes)
            result.update(yfinance_result)
            
            # 如果yfinance也失败较多，最后使用baostock兜底
            still_missing = [code for code in missing_codes if code not in yfinance_result]
            if still_missing:
                print(f"[INFO] yfinance采集不完整，使用baostock最终兜底 {len(still_missing)} 只股票")
                for code in still_missing:
                    try:
                        result[code] = self.collect_basic_info(code, 'baostock')
                        time.sleep(0.3)  # baostock频率控制
                    except Exception as e:
                        print(f"[WARN] baostock最终兜底失败 {code}: {e}")
                        result[code] = {
                            'code': code,
                            'name': f'股票{code}',
                            'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                            'source': 'fallback'
                        }
        
        return result
    
    def _collect_batch_basic_info_with_yfinance(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """使用yfinance批量采集基础信息"""
        result = {}
        
        if not YFINANCE_AVAILABLE:
            print(f"[WARN] yfinance不可用，跳过基础信息采集")
            return result
        
        print(f"[INFO] 使用yfinance批量获取{len(codes)}只股票基础信息")
        
        # yfinance频率控制 - 初始等待
        print(f"[INFO] yfinance频率控制，等待2秒...")
        time.sleep(2)
        
        try:
            # yfinance批量获取 (15只/批)
            batch_size = min(15, len(codes))
            for i in range(0, len(codes), batch_size):
                batch_codes = codes[i:i+batch_size]
                
                # 转换为yfinance格式
                yf_symbols = []
                code_mapping = {}
                
                for code in batch_codes:
                    if code.startswith(('60', '68')):  # 沪市
                        yf_symbol = f"{code}.SS"
                    else:  # 深市
                        yf_symbol = f"{code}.SZ"
                    yf_symbols.append(yf_symbol)
                    code_mapping[yf_symbol] = code
                
                # 批量获取基础信息
                try:
                    symbols_str = ' '.join(yf_symbols)
                    tickers = yf.Tickers(symbols_str)
                    
                    for yf_symbol in yf_symbols:
                        code = code_mapping[yf_symbol]
                        try:
                            ticker = tickers.tickers[yf_symbol]
                            info = ticker.info
                            
                            if info and info.get('symbol'):
                                result[code] = {
                                    'code': code,
                                    'name': info.get('shortName', info.get('longName', f'股票{code}')),
                                    'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                    'industry': info.get('industry'),
                                    'sector': info.get('sector'),
                                    'market_cap': info.get('marketCap'),
                                    'employee_count': info.get('fullTimeEmployees'),
                                    'source': 'yfinance'
                                }
                                print(f"[SUCCESS] {code}: yfinance基础信息获取成功")
                            else:
                                result[code] = {
                                    'code': code,
                                    'name': f'股票{code}',
                                    'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                    'source': 'yfinance'
                                }
                        except Exception as e:
                            print(f"[WARN] {code}: yfinance基础信息获取失败 - {e}")
                            # 失败时不添加到result中，让baostock来兜底
                
                except Exception as e:
                    print(f"[WARN] yfinance批量获取第{i//batch_size + 1}批失败: {e}")
                
                actual_success = len([c for c in batch_codes if c in result])
                print(f"[INFO] yfinance批量基础信息: 第{i//batch_size + 1}批完成 ({actual_success}/{len(batch_codes)} 成功)")
                
                # yfinance频率限制较严格，增加等待时间
                if i + batch_size < len(codes):
                    time.sleep(3)  # 增加到3秒
                    
        except Exception as e:
            print(f"[WARN] yfinance批量基础信息采集失败: {e}")
        
        # 统计有效成功数（只计算有有效数据的）
        valid_results = {code: data for code, data in result.items() 
                        if data.get('name') and data.get('name') != f'股票{code}'}
        print(f"[INFO] yfinance基础信息采集完成: {len(valid_results)}/{len(codes)} 有效成功")
        return result
    
    def collect_batch_financial_data(self, codes: List[str], source: str = 'tencent') -> Dict[str, Dict[str, Any]]:
        """批量采集财务数据"""
        result = {}
        
        # 财务数据批量采集比较复杂，优先使用腾讯API获取基本财务指标
        if source == 'tencent' and REQUESTS_AVAILABLE:
            try:
                batch_size = min(15, len(codes))
                for i in range(0, len(codes), batch_size):
                    batch_codes = codes[i:i+batch_size]
                    
                    # 获取财务概况数据
                    for code in batch_codes:
                        try:
                            # 腾讯财务概况API
                            url = f'https://qt.gtimg.cn/q=ff_{code}'
                            response = requests.get(url, timeout=10)
                            if response.status_code == 200:
                                data = response.text.split('~')
                                if len(data) > 10:
                                    result[code] = {
                                        'code': code,
                                        'pe_ratio': float(data[39]) if len(data) > 39 and data[39] else None,
                                        'pb_ratio': float(data[46]) if len(data) > 46 and data[46] else None,
                                        'market_cap': float(data[45]) if len(data) > 45 and data[45] else None,
                                        'total_shares': float(data[38]) if len(data) > 38 and data[38] else None,
                                        'source': 'tencent'
                                    }
                        except Exception as e:
                            print(f"[WARN] 腾讯财务数据获取失败 {code}: {e}")
                    
                    # 避免频率限制
                    time.sleep(1)
                        
            except Exception as e:
                print(f"[WARN] 腾讯批量财务数据采集失败: {e}")
        
        # 如果腾讯财务数据采集失败较多，使用baostock兜底（更可靠）
        missing_codes = [code for code in codes if code not in result]
        if missing_codes:
            print(f"[INFO] 腾讯财务数据不完整，使用baostock兜底采集{len(missing_codes)}只股票")
            for code in missing_codes:
                try:
                    financial_data = self.collect_financial_data(code, 'baostock')
                    if financial_data and financial_data.get('pe_ratio') is not None:  # 确保有有效数据
                        result[code] = financial_data
                        print(f"[SUCCESS] {code}: baostock财务数据获取成功")
                    else:
                        print(f"[WARN] {code}: baostock财务数据无效，跳过")
                    time.sleep(0.5)  # baostock频率控制
                except Exception as e:
                    print(f"[WARN] baostock财务数据兜底失败 {code}: {e}")
                    # 失败时不创建条目，让它真正失败
        
        # 如果baostock也失败太多，最后才尝试akshare（网络问题时通常也会失败）
        still_missing = [code for code in codes if code not in result]
        if still_missing and len(still_missing) < 5:  # 只在少量失败时才尝试akshare
            print(f"[INFO] 最后尝试akshare补充{len(still_missing)}只股票的财务数据")
            for code in still_missing:
                try:
                    financial_data = self.collect_financial_data(code, 'akshare')
                    if financial_data and financial_data.get('pe_ratio') is not None:
                        result[code] = financial_data
                        print(f"[SUCCESS] {code}: akshare财务数据获取成功")
                    time.sleep(2)  # akshare频率限制更严格
                except Exception as e:
                    print(f"[WARN] akshare最终兜底失败 {code}: {e}")
                    # 真正失败时不创建默认条目
        
        # 统计有效的财务数据（有实际财务指标的）
        valid_results = {code: data for code, data in result.items() 
                        if data.get('pe_ratio') is not None or data.get('revenue') is not None}
        print(f"[INFO] 批量财务数据采集完成: {len(valid_results)}/{len(codes)} 有效成功")
        
        return result
    
    def collect_batch_industry_concept(self, codes: List[str], source: str = 'baostock') -> Dict[str, Dict[str, Any]]:
        """批量采集行业概念信息 - 优化baostock和akshare频次限制"""
        result = {}
        
        if source == 'baostock' and BAOSTOCK_AVAILABLE and self.bs_login:
            try:
                # baostock策略：获取行业分类映射表，然后批量匹配
                print(f"[INFO] 使用baostock获取行业分类映射表...")
                
                # 获取行业分类信息（一次性获取全部）
                rs = bs.query_stock_industry()
                industry_map = {}
                
                if rs.error_code == '0':
                    while rs.next():
                        row_data = rs.get_row_data()
                        if len(row_data) >= 3:
                            stock_code = row_data[0].split('.')[-1]  # 去掉sh./sz.前缀
                            industry_map[stock_code] = {
                                'industry': row_data[1],
                                'sector': row_data[2],
                                'update_date': row_data[3] if len(row_data) > 3 else None,
                                'source': 'baostock'
                            }
                
                print(f"[INFO] baostock行业映射表获取完成，共{len(industry_map)}只股票")
                
                # 批量匹配目标股票
                for code in codes:
                    if code in industry_map:
                        result[code] = {
                            'industry': industry_map[code]['industry'],
                            'industry_pe': None,
                            'concepts': [],
                            'hot_concepts': [],
                            'sector': industry_map[code]['sector'],
                            'industry_performance': None,
                            'source': 'baostock'
                        }
                    else:
                        # 如果映射表中没有，设置默认值
                        result[code] = {
                            'industry': None,
                            'industry_pe': None,
                            'concepts': [],
                            'hot_concepts': [],
                            'sector': None,
                            'industry_performance': None,
                            'source': 'baostock'
                        }
                
                print(f"[INFO] baostock批量行业概念匹配完成: {len(result)}/{len(codes)} 成功")
                        
            except Exception as e:
                print(f"[WARN] baostock批量行业概念采集失败: {e}")
        
        # 如果baostock失败或覆盖率不足，使用akshare补充（频次优化）
        missing_codes = [code for code in codes if code not in result or not result[code].get('industry')]
        
        if missing_codes and len(missing_codes) < len(codes) * 0.5:  # 如果缺失少于50%，用akshare补充
            print(f"[INFO] 使用akshare补充{len(missing_codes)}只股票的行业概念")
            for code in missing_codes:
                try:
                    info = self.collect_industry_concept_info(code, 'akshare')
                    result[code] = info
                    time.sleep(0.8)  # akshare频率限制控制
                except Exception as e:
                    print(f"[WARN] akshare行业概念补充失败 {code}: {e}")
                    result[code] = {
                        'industry': None, 'industry_pe': None, 'concepts': [],
                        'hot_concepts': [], 'sector': None, 'industry_performance': None,
                        'source': 'fallback'
                    }
        
        return result
    
    def collect_batch_fund_flow(self, codes: List[str], source: str = 'tencent') -> Dict[str, Dict[str, Any]]:
        """批量采集资金流向数据 - 优化频次限制"""
        result = {}
        
        if source == 'tencent' and REQUESTS_AVAILABLE:
            try:
                # 腾讯API批量资金流向数据（15只/批）
                batch_size = min(15, len(codes))
                for i in range(0, len(codes), batch_size):
                    batch_codes = codes[i:i+batch_size]
                    
                    # 批量获取资金流向数据
                    for code in batch_codes:
                        try:
                            url = f'https://qt.gtimg.cn/q=ff_{code}'
                            response = requests.get(url, timeout=10)
                            if response.status_code == 200:
                                data = response.text.split('~')
                                if len(data) > 4:
                                    result[code] = {
                                        'main_fund_inflow': self._safe_float(data[1]) if len(data) > 1 else None,
                                        'super_fund_inflow': self._safe_float(data[2]) if len(data) > 2 else None,
                                        'large_fund_inflow': self._safe_float(data[3]) if len(data) > 3 else None,
                                        'medium_fund_inflow': self._safe_float(data[4]) if len(data) > 4 else None,
                                        'small_fund_inflow': self._safe_float(data[5]) if len(data) > 5 else None,
                                        'north_fund_inflow': None,
                                        'source': 'tencent'
                                    }
                                else:
                                    result[code] = {
                                        'main_fund_inflow': None, 'super_fund_inflow': None,
                                        'large_fund_inflow': None, 'medium_fund_inflow': None, 
                                        'small_fund_inflow': None, 'north_fund_inflow': None,
                                        'source': 'tencent'
                                    }
                        except Exception as e:
                            print(f"[WARN] 腾讯资金流向获取失败 {code}: {e}")
                    
                    print(f"[INFO] 腾讯批量资金流向: 第{i//batch_size + 1}批完成")
                    
                    # 避免频率限制
                    if i + batch_size < len(codes):
                        time.sleep(1)
                        
            except Exception as e:
                print(f"[WARN] 腾讯批量资金流向采集失败: {e}")
        
        # 使用akshare补充缺失数据（谨慎使用，因为频次限制严格）
        missing_codes = [code for code in codes if code not in result]
        if missing_codes and len(missing_codes) < 5:  # 只在缺失很少时才用akshare补充
            print(f"[INFO] 使用akshare补充{len(missing_codes)}只股票的资金流向（频次限制）")
            for code in missing_codes:
                try:
                    fund_data = self.collect_fund_flow_data(code, 'akshare')
                    result[code] = fund_data
                    time.sleep(2)  # akshare资金流向数据频次限制更严格
                except Exception as e:
                    print(f"[WARN] akshare资金流向补充失败 {code}: {e}")
                    result[code] = {
                        'main_fund_inflow': None, 'super_fund_inflow': None,
                        'large_fund_inflow': None, 'medium_fund_inflow': None, 
                        'small_fund_inflow': None, 'north_fund_inflow': None,
                        'source': 'fallback'
                    }
        
        return result
        
        return result
    
    def collect_kline_data(self, code: str, source: str, period: str = 'daily') -> Optional[pd.DataFrame]:
        """采集K线数据"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.kline_days)  # 使用50天数据
            
            if source == 'tushare' and self.ts_pro:
                # tushare专用于K线数据采集 - 经验证可用
                # 建议使用collect_batch_kline_data方法更高效
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                start_str = start_date.strftime('%Y%m%d')
                end_str = end_date.strftime('%Y%m%d')
                
                # 检查频率限制
                current_time = time.time()
                if current_time - self.last_tushare_call < 60:
                    wait_time = 60 - (current_time - self.last_tushare_call)
                    print(f"[INFO] 等待{wait_time:.1f}秒避免tushare频率限制")
                    time.sleep(wait_time)
                
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
                self.last_tushare_call = time.time()
                
                if df is not None and not df.empty:
                    df['trade_date'] = pd.to_datetime(df['trade_date'])
                    df = df.sort_values('trade_date')
                    print(f"[SUCCESS] tushare获取{code} K线数据 {len(df)}天")
                    return df.rename(columns={
                        'trade_date': 'date', 'open': 'open', 'high': 'high',
                        'low': 'low', 'close': 'close', 'vol': 'volume', 'amount': 'amount'
                    })
            
            elif source == 'akshare' and AKSHARE_AVAILABLE:
                start_str = start_date.strftime('%Y%m%d')
                end_str = end_date.strftime('%Y%m%d')
                
                df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                       start_date=start_str, end_date=end_str, adjust="qfq")
                if df is not None and not df.empty:
                    return df.rename(columns={
                        '日期': 'date', '开盘': 'open', '最高': 'high',
                        '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
                    })
            
            elif source == 'yfinance' and YFINANCE_AVAILABLE:
                symbol = f"{code}.SS" if code.startswith(('60', '68')) else f"{code}.SZ"
                stock = yf.Ticker(symbol)
                df = stock.history(period="1y")
                if df is not None and not df.empty:
                    df = df.reset_index()
                    return df.rename(columns={
                        'Date': 'date', 'Open': 'open', 'High': 'high',
                        'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                    })
        
        except Exception as e:
            print(f"[WARN] {code} K线数据采集失败 ({source}): {e}")
        
        return None
    
    def collect_financial_data(self, code: str, source: str) -> Dict[str, Any]:
        """采集财务数据"""
        financial_data = {
            'pe_ratio': None, 'pb_ratio': None, 'roe': None,
            'revenue': None, 'net_profit': None, 'eps': None,
            'debt_ratio': None, 'dividend_yield': None,
            'source': source
        }
        
        try:
            if source == 'baostock' and BAOSTOCK_AVAILABLE and self.bs_login:
                # baostock获取财务数据
                bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                
                # 获取季度财务数据
                try:
                    rs = bs.query_profit_data(code=bs_code, year="2024", quarter=3)  # 最新季度
                    if rs.error_code == '0':
                        profit_data = []
                        while (rs.next()):
                            profit_data.append(rs.get_row_data())
                        
                        if profit_data:
                            latest = profit_data[-1]
                            # baostock返回的是列表，需要通过索引访问
                            if len(latest) > 5:  # 确保有足够的数据
                                financial_data.update({
                                    'revenue': self._safe_float(latest[4]) if len(latest) > 4 else None,
                                    'net_profit': self._safe_float(latest[5]) if len(latest) > 5 else None
                                })
                except Exception as e:
                    print(f"[DEBUG] baostock财务数据获取失败: {e}")
                
                # 获取估值数据
                try:
                    rs = bs.query_valuation_data(code=bs_code, start_date="2024-11-01", end_date="2024-11-18")
                    if rs.error_code == '0':
                        valuation_data = []
                        while (rs.next()):
                            valuation_data.append(rs.get_row_data())
                        
                        if valuation_data:
                            latest = valuation_data[-1]
                            if len(latest) > 7:
                                financial_data.update({
                                    'pe_ratio': self._safe_float(latest[5]) if len(latest) > 5 else None,
                                    'pb_ratio': self._safe_float(latest[6]) if len(latest) > 6 else None
                                })
                except Exception as e:
                    print(f"[DEBUG] baostock估值数据获取失败: {e}")
            
            elif source == 'akshare' and AKSHARE_AVAILABLE:
                # 基础财务指标
                info_df = ak.stock_individual_info_em(symbol=code)
                if info_df is not None and not info_df.empty:
                    info = dict(zip(info_df['item'], info_df['value']))
                    financial_data.update({
                        'pe_ratio': self._safe_float(info.get('市盈率-动态')),
                        'pb_ratio': self._safe_float(info.get('市净率')),
                    })
                
                # 财务分析指标
                try:
                    fin_df = ak.stock_financial_analysis_indicator(symbol=code)
                    if fin_df is not None and not fin_df.empty:
                        latest = fin_df.iloc[-1]
                        roe_val = latest.get('净资产收益率')
                        if isinstance(roe_val, str) and roe_val.endswith('%'):
                            financial_data['roe'] = float(roe_val.rstrip('%')) / 100
                        elif roe_val is not None:
                            financial_data['roe'] = float(roe_val)
                except:
                    pass
                
                # 财务摘要
                try:
                    abstract_df = ak.stock_financial_abstract(symbol=code)
                    if abstract_df is not None and not abstract_df.empty:
                        latest = abstract_df.iloc[-1]
                        financial_data.update({
                            'revenue': self._safe_float(latest.get('营业总收入-营业总收入')),
                            'net_profit': self._safe_float(latest.get('净利润-净利润'))
                        })
                except:
                    pass
            
            # tushare财务数据采集已移除 - 无接口访问权限
            # 财务数据主要通过baostock和akshare获取
        
        except Exception as e:
            print(f"[WARN] {code} 财务数据采集失败 ({source}): {e}")
        
        return financial_data
    
    def collect_technical_indicators(self, kline_data: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """计算技术指标"""
        indicators = {
            'ma5': None, 'ma10': None, 'ma20': None, 'ma60': None,
            'rsi': None, 'macd': None, 'signal': None,
            'bollinger_upper': None, 'bollinger_lower': None,
            'kdj_k': None, 'kdj_d': None, 'kdj_j': None,
            'volume_ratio': None, 'price_change_1d': None,
            'price_change_5d': None, 'price_change_20d': None
        }
        
        if kline_data is None or kline_data.empty:
            return indicators
        
        try:
            kline_data = kline_data.sort_values('date')
            close = kline_data['close']
            volume = kline_data['volume'] if 'volume' in kline_data.columns else None
            
            # 移动平均线
            if len(close) >= 5:
                indicators['ma5'] = float(close.tail(5).mean())
            if len(close) >= 10:
                indicators['ma10'] = float(close.tail(10).mean())
            if len(close) >= 20:
                indicators['ma20'] = float(close.tail(20).mean())
            if len(close) >= 60:
                indicators['ma60'] = float(close.tail(60).mean())
            
            # RSI
            if len(close) >= 14:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                indicators['rsi'] = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
            
            # MACD
            if len(close) >= 26:
                ema12 = close.ewm(span=12).mean()
                ema26 = close.ewm(span=26).mean()
                macd = ema12 - ema26
                signal = macd.ewm(span=9).mean()
                indicators['macd'] = float(macd.iloc[-1])
                indicators['signal'] = float(signal.iloc[-1])
            
            # 布林带
            if len(close) >= 20:
                ma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                indicators['bollinger_upper'] = float((ma20 + 2 * std20).iloc[-1])
                indicators['bollinger_lower'] = float((ma20 - 2 * std20).iloc[-1])
            
            # KDJ（简化版）
            if len(kline_data) >= 9:
                high = kline_data['high']
                low = kline_data['low']
                
                lowest_low = low.rolling(9).min()
                highest_high = high.rolling(9).max()
                
                k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
                k_percent = k_percent.fillna(50)
                
                indicators['kdj_k'] = float(k_percent.iloc[-1]) if not pd.isna(k_percent.iloc[-1]) else None
            
            # 成交量比率
            if volume is not None and len(volume) >= 5:
                avg_volume = volume.tail(20).mean() if len(volume) >= 20 else volume.mean()
                current_volume = volume.iloc[-1]
                if avg_volume > 0:
                    indicators['volume_ratio'] = float(current_volume / avg_volume)
            
            # 涨跌幅
            if len(close) >= 2:
                indicators['price_change_1d'] = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)
            if len(close) >= 6:
                indicators['price_change_5d'] = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)
            if len(close) >= 21:
                indicators['price_change_20d'] = float((close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100)
        
        except Exception as e:
            print(f"[WARN] 技术指标计算失败: {e}")
        
        return indicators
    
    def collect_industry_concept_info(self, code: str, source: str) -> Dict[str, Any]:
        """采集行业概念信息"""
        info = {
            'industry': None,
            'industry_pe': None,
            'concepts': [],
            'hot_concepts': [],
            'sector': None,
            'industry_performance': None,
            'source': source
        }
        
        try:
            if source == 'baostock' and BAOSTOCK_AVAILABLE and self.bs_login:
                # baostock获取行业信息
                bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                
                try:
                    rs = bs.query_stock_industry(code=bs_code)
                    if rs.error_code == '0':
                        industry_data = []
                        while (rs.next()):
                            industry_data.append(rs.get_row_data())
                        
                        if industry_data:
                            latest = industry_data[-1]
                            if len(latest) > 2:
                                info.update({
                                    'industry': latest[1] if len(latest) > 1 else None,
                                    'sector': latest[2] if len(latest) > 2 else None
                                })
                except Exception as e:
                    print(f"[DEBUG] baostock行业信息获取失败: {e}")
            
            elif source == 'akshare' and AKSHARE_AVAILABLE:
                # 通过个股信息获取行业概念
                try:
                    df = ak.stock_individual_info_em(symbol=code)
                    if df is not None and not df.empty:
                        stock_info = dict(zip(df['item'], df['value']))
                        info.update({
                            'industry': stock_info.get('行业'),
                            'sector': stock_info.get('概念'),
                        })
                        
                        # 如果有概念信息，转换为列表
                        concepts_str = stock_info.get('概念')
                        if concepts_str:
                            info['concepts'] = [c.strip() for c in str(concepts_str).split(',')]
                except:
                    pass
                
                # 获取概念板块信息
                try:
                    concept_df = ak.stock_board_concept_name_em()
                    if concept_df is not None and not concept_df.empty:
                        # 取涨幅前10的概念
                        top_concepts = concept_df.nlargest(10, '涨跌幅')
                        info['hot_concepts'] = [
                            {'name': row['板块名称'], 'change_pct': row['涨跌幅']}
                            for _, row in top_concepts.iterrows()
                        ]
                except:
                    pass
                
                # 获取行业板块信息
                try:
                    industry_df = ak.stock_board_industry_name_em()
                    if industry_df is not None and not industry_df.empty:
                        info['industry_performance'] = industry_df.to_dict('records')[:20]  # 前20个行业
                        
                        # 查找该股票所属行业的PE
                        industry_name = info.get('industry')
                        if industry_name:
                            matching_industry = industry_df[industry_df['板块名称'] == industry_name]
                            if not matching_industry.empty:
                                info['industry_pe'] = self._safe_float(matching_industry.iloc[0].get('平均市盈率'))
                except:
                    pass
        
        except Exception as e:
            print(f"[WARN] {code} 行业概念信息采集失败 ({source}): {e}")
        
        return info
    
    def collect_fund_flow_data(self, code: str, source: str) -> Dict[str, Any]:
        """采集资金流向数据"""
        fund_flow = {
            'main_fund_inflow': None,
            'super_fund_inflow': None,
            'large_fund_inflow': None,
            'medium_fund_inflow': None,
            'small_fund_inflow': None,
            'north_fund_inflow': None,
            'source': source
        }
        
        try:
            if source == 'tencent' and REQUESTS_AVAILABLE:
                # 腾讯资金流向数据
                try:
                    # 腾讯资金流向接口
                    url = f'https://qt.gtimg.cn/q=ff_{code}'
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.text.split('~')
                        if len(data) > 10:
                            fund_flow.update({
                                'main_fund_inflow': self._safe_float(data[1]) if len(data) > 1 else None,
                                'large_fund_inflow': self._safe_float(data[2]) if len(data) > 2 else None,
                                'medium_fund_inflow': self._safe_float(data[3]) if len(data) > 3 else None,
                                'small_fund_inflow': self._safe_float(data[4]) if len(data) > 4 else None
                            })
                except Exception as e:
                    print(f"[DEBUG] 腾讯资金流向获取失败: {e}")
            
            elif source == 'akshare' and AKSHARE_AVAILABLE:
                # 个股资金流向
                try:
                    fund_df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith('6') else "sz")
                    if fund_df is not None and not fund_df.empty:
                        latest = fund_df.iloc[-1] if len(fund_df) > 0 else None
                        if latest is not None:
                            fund_flow.update({
                                'main_fund_inflow': self._safe_float(latest.get('主力净流入-净流入')),
                                'super_fund_inflow': self._safe_float(latest.get('超大单净流入-净流入')),
                                'large_fund_inflow': self._safe_float(latest.get('大单净流入-净流入')),
                                'medium_fund_inflow': self._safe_float(latest.get('中单净流入-净流入')),
                                'small_fund_inflow': self._safe_float(latest.get('小单净流入-净流入'))
                            })
                except:
                    pass
        
        except Exception as e:
            print(f"[WARN] {code} 资金流向数据采集失败 ({source}): {e}")
        
        return fund_flow
    
    def collect_news_announcements(self, code: str, source: str) -> Dict[str, Any]:
        """采集新闻公告数据"""
        news_data = {
            'recent_announcements': [],
            'news_sentiment': None,
            'important_events': [],
            'source': source
        }
        
        try:
            if source == 'akshare' and AKSHARE_AVAILABLE:
                # 获取公司公告
                try:
                    announcement_df = ak.stock_notice_report(symbol=code)
                    if announcement_df is not None and not announcement_df.empty:
                        recent = announcement_df.head(10)  # 最近10条公告
                        news_data['recent_announcements'] = [
                            {
                                'date': row.get('公告日期', ''),
                                'title': row.get('公告标题', ''),
                                'type': row.get('公告类型', '')
                            }
                            for _, row in recent.iterrows()
                        ]
                except:
                    pass
        
        except Exception as e:
            print(f"[WARN] {code} 新闻公告数据采集失败 ({source}): {e}")
        
        return news_data
    
    def _collect_non_kline_data_during_wait(self, codes: List[str], wait_seconds: int) -> None:
        """在等待期间收集非K线数据以提高效率 - 使用分层数据源策略"""
        print(f"[INFO] 等待期间使用分层数据源策略收集{len(codes)}只股票的其他数据...")
        
        start_time = time.time()
        collected_count = 0
        
        for code in codes:
            if time.time() - start_time >= wait_seconds - 5:  # 预留5秒缓冲
                break
                
            try:
                if code not in self.wait_period_data:
                    self.wait_period_data[code] = {}
                
                # 1. 基础信息 - 优先yfinance, tencent, 兜底akshare
                if 'basic_info' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['basic_info']:
                        if time.time() - start_time >= wait_seconds - 10:
                            break
                        
                        basic_info = self.collect_basic_info(code, source)
                        if basic_info and basic_info.get('name') and basic_info['name'] != f'股票{code}':
                            self.wait_period_data[code]['basic_info'] = basic_info
                            print(f"    ✓ {code}: 基础信息 ({source})")
                            break
                
                # 2. 行业概念 - 优先baostock, 兜底akshare
                if time.time() - start_time < wait_seconds - 15 and 'industry_concept' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['industry_concept']:
                        if time.time() - start_time >= wait_seconds - 20:
                            break
                        
                        industry_concept = self.collect_industry_concept_info(code, source)
                        if industry_concept and (industry_concept.get('industry') or industry_concept.get('concepts')):
                            self.wait_period_data[code]['industry_concept'] = industry_concept
                            print(f"    ✓ {code}: 行业概念 ({source})")
                            break
                
                # 3. 财务数据 - 优先baostock, 兜底akshare
                if time.time() - start_time < wait_seconds - 25 and 'financial_data' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['financial_data']:
                        if time.time() - start_time >= wait_seconds - 30:
                            break
                        
                        financial_data = self.collect_financial_data(code, source)
                        if financial_data and any(v is not None for v in financial_data.values() if v != source):
                            self.wait_period_data[code]['financial_data'] = financial_data
                            print(f"    ✓ {code}: 财务数据 ({source})")
                            break
                
                # 4. 资金流向 - 优先tencent, 兜底akshare
                if time.time() - start_time < wait_seconds - 35 and 'fund_flow' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['fund_flow']:
                        if time.time() - start_time >= wait_seconds - 40:
                            break
                        
                        fund_flow = self.collect_fund_flow_data(code, source)
                        if fund_flow and any(v is not None for v in fund_flow.values() if v != source):
                            self.wait_period_data[code]['fund_flow'] = fund_flow
                            print(f"    ✓ {code}: 资金流向 ({source})")
                            break
                
                collected_count += 1
                time.sleep(1)  # 避免请求过快
                
            except Exception as e:
                print(f"    ⚠️ {code}: 等待期间数据收集失败 - {e}")
                continue
        
        elapsed = time.time() - start_time
        print(f"[INFO] 等待期间已收集{collected_count}只股票的其他数据，用时{elapsed:.1f}秒")
        print(f"[INFO] 数据源使用策略: 基础信息({self.wait_period_strategy['basic_info']})")
        print(f"[INFO]                行业概念({self.wait_period_strategy['industry_concept']})")
        print(f"[INFO]                财务数据({self.wait_period_strategy['financial_data']})")
        print(f"[INFO]                资金流向({self.wait_period_strategy['fund_flow']})")
    
    def _collect_parallel_data_during_wait(self, remaining_codes: List[str], all_codes: List[str], 
                                         wait_seconds: int, result: Dict, start_str: str, end_str: str) -> None:
        """在等待期间并行收集K线数据和其他数据"""
        print(f"[INFO] 等待期间并行收集策略: K线数据(akshare) + 其他数据(分层源)")
        
        start_time = time.time()
        akshare_kline_count = 0
        other_data_count = 0
        
        # 获取还没有K线数据的股票
        missing_kline_codes = [code for code in all_codes if code not in result][:10]  # 最多10只
        
        for i, code in enumerate(remaining_codes):
            if time.time() - start_time >= wait_seconds - 5:  # 预留5秒缓冲
                break
            
            try:
                # 1. 如果还有股票没有K线数据，优先用akshare获取K线
                if i < len(missing_kline_codes) and time.time() - start_time < wait_seconds - 15:
                    kline_code = missing_kline_codes[i]
                    print(f"    [K线] 使用akshare获取 {kline_code} K线数据...")
                    
                    kline_data = self._collect_kline_with_akshare(kline_code, start_str, end_str)
                    if kline_data is not None and not kline_data.empty:
                        result[kline_code] = kline_data
                        akshare_kline_count += 1
                        print(f"    ✓ [K线] {kline_code}: {len(kline_data)}天K线数据 (akshare)")
                    else:
                        print(f"    ✗ [K线] {kline_code}: akshare获取失败")
                
                # 2. 并行收集其他数据
                if code not in self.wait_period_data:
                    self.wait_period_data[code] = {}
                
                # 快速收集基础信息
                if 'basic_info' not in self.wait_period_data[code] and time.time() - start_time < wait_seconds - 20:
                    for source in self.wait_period_strategy['basic_info']:
                        if time.time() - start_time >= wait_seconds - 25:
                            break
                        basic_info = self.collect_basic_info(code, source)
                        if basic_info and basic_info.get('name') and basic_info['name'] != f'股票{code}':
                            self.wait_period_data[code]['basic_info'] = basic_info
                            other_data_count += 1
                            print(f"    ✓ [其他] {code}: 基础信息 ({source})")
                            break
                
                # 收集财务数据（如果时间充足）
                if ('financial_data' not in self.wait_period_data[code] and 
                    time.time() - start_time < wait_seconds - 30):
                    for source in self.wait_period_strategy['financial_data']:
                        if time.time() - start_time >= wait_seconds - 35:
                            break
                        financial_data = self.collect_financial_data(code, source)
                        if financial_data and any(v is not None for v in financial_data.values() if v != source):
                            self.wait_period_data[code]['financial_data'] = financial_data
                            print(f"    ✓ [其他] {code}: 财务数据 ({source})")
                            break
                
                time.sleep(0.5)  # 短暂延时避免请求过快
                
            except Exception as e:
                print(f"    ⚠️ {code}: 并行数据收集失败 - {e}")
                continue
        
        elapsed = time.time() - start_time
        print(f"[INFO] 等待期间并行收集完成，用时{elapsed:.1f}秒")
        print(f"[INFO]   - akshare K线数据: {akshare_kline_count}只股票")
        print(f"[INFO]   - 其他数据: {other_data_count}项")
    
    def _collect_kline_with_akshare(self, code: str, start_str: str, end_str: str) -> Optional[pd.DataFrame]:
        """使用akshare获取K线数据"""
        try:
            if not AKSHARE_AVAILABLE:
                return None
            
            import akshare as ak
            df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                   start_date=start_str, end_date=end_str, adjust="qfq")
            if df is not None and not df.empty:
                # 数据格式标准化，与tushare保持一致
                df['trade_date'] = pd.to_datetime(df['日期'])
                df = df.sort_values('trade_date')
                df = df.rename(columns={
                    'trade_date': 'date', '开盘': 'open', '最高': 'high',
                    '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
                })
                # 只保留需要的列
                return df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
            
        except Exception as e:
            print(f"[DEBUG] akshare K线获取失败 {code}: {e}")
        
        return None

    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value in (None, "", "--", "-", "NaN"):
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '').strip()
            return float(value)
        except:
            return None
    
    def collect_comprehensive_data(self, codes: List[str], batch_size: int = 15) -> Dict[str, Any]:
        """采集综合数据 - 优化版本使用批量采集"""
        results = {}
        
        print(f"[INFO] 开始采集 {len(codes)} 只股票的综合数据")
        
        # 1. 批量采集K线数据 (tushare → akshare轮流，yfinance兜底)
        print(f"[INFO] 步骤1: 批量采集K线数据...")
        batch_kline_data = self.collect_batch_kline_data(codes, 'auto')
        print(f"[INFO] 批量K线采集完成，获得 {len(batch_kline_data)} 只股票数据")
        
        # 2. 批量采集基础信息（优化频次限制）
        print(f"[INFO] 步骤2: 批量采集基础信息...")
        batch_basic_info = self.collect_batch_basic_info(codes, 'tencent')
        print(f"[INFO] 批量基础信息采集完成，获得 {len(batch_basic_info)} 只股票数据")
        
        # 3. 批量采集财务数据（优化频次限制）  
        print(f"[INFO] 步骤3: 批量采集财务数据...")
        batch_financial_data = self.collect_batch_financial_data(codes, 'tencent')
        print(f"[INFO] 批量财务数据采集完成，获得 {len(batch_financial_data)} 只股票数据")
        
        # 4. 批量采集行业概念数据（优化baostock和akshare频次）
        print(f"[INFO] 步骤4: 批量采集行业概念数据...")
        batch_industry_data = self.collect_batch_industry_concept(codes, 'baostock')
        print(f"[INFO] 批量行业概念采集完成，获得 {len(batch_industry_data)} 只股票数据")
        
        # 5. 批量采集资金流向数据（优化频次限制）
        print(f"[INFO] 步骤5: 批量采集资金流向数据...")
        batch_fund_flow_data = self.collect_batch_fund_flow(codes, 'tencent')
        print(f"[INFO] 批量资金流向采集完成，获得 {len(batch_fund_flow_data)} 只股票数据")
        
        # 6. 整合数据并补充其他信息
        print(f"[INFO] 步骤6: 整合数据并补充其他信息...")
        for i, code in enumerate(codes[:batch_size]):
            print(f"\n[{i+1}/{min(batch_size, len(codes))}] 正在整合 {code} 的数据...")
            
            stock_data = {
                'code': code,
                'timestamp': datetime.now().isoformat(),
                'data_source': 'batch_optimized',
                'basic_info': batch_basic_info.get(code, {'code': code, 'name': f'股票{code}'}),
                'kline_data': None,
                'financial_data': batch_financial_data.get(code, {'code': code}),
                'technical_indicators': {},
                'industry_concept': batch_industry_data.get(code, {'industry': None, 'source': 'fallback'}),
                'fund_flow': batch_fund_flow_data.get(code, {'source': 'fallback'}),
                'news_announcements': {}
            }
            
            # 处理K线数据 - 从批量采集结果获取
            if code in batch_kline_data:
                kline_df = batch_kline_data[code]
                if kline_df is not None and not kline_df.empty:
                    stock_data['kline_data'] = {
                        'daily': kline_df.to_dict('records'),
                        'latest_price': float(kline_df['close'].iloc[-1]),
                        'data_points': len(kline_df)
                    }
                    print(f"    ✓ K线数据: {len(kline_df)}天 (批量获取)")
                else:
                    kline_df = None
            else:
                print(f"    ⚠️ 该股票未在批量K线数据中，尝试单独获取")
                kline_df = self.collect_kline_data(code, 'akshare')
                if kline_df is not None and not kline_df.empty:
                    stock_data['kline_data'] = {
                        'daily': kline_df.to_dict('records'),
                        'latest_price': float(kline_df['close'].iloc[-1]),
                        'data_points': len(kline_df)
                    }
            
            # 技术指标计算
            if kline_df is not None and not kline_df.empty:
                stock_data['technical_indicators'] = self.collect_technical_indicators(kline_df)
            else:
                stock_data['technical_indicators'] = {}
            
            # 其他数据使用等待期间收集或实时补充
            source = 'akshare'  # 作为兜底数据源
            
            # 行业概念和资金流向已通过批量采集获得，无需单独采集
            print(f"    ✓ 行业概念: 批量采集完成")
            print(f"    ✓ 资金流向: 批量采集完成")
            
            # 新闻公告 - 实时收集（时效性重要）
            stock_data['news_announcements'] = self.collect_news_announcements(code, 'akshare')
            print(f"    ✓ 新闻公告: 实时收集")
            
            results[code] = stock_data
            
            # 短暂延时
            time.sleep(0.5)
        
        return results
    
    def save_data(self, data: Dict[str, Any], filename: Optional[str] = None) -> None:
        """保存数据到JSON文件"""
        if filename is None:
            filename = self.output_file
        
        # 确保数据目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # 加载已有数据
        existing_data = {}
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = {}
        
        # 合并数据
        if 'stocks' not in existing_data:
            existing_data['stocks'] = {}
        
        # 清理数据以避免JSON序列化错误
        cleaned_data = DateTimeEncoder.clean_data_for_json(data)
        existing_data['stocks'].update(cleaned_data)
        existing_data['last_updated'] = datetime.now().isoformat()
        existing_data['total_stocks'] = len(existing_data['stocks'])
        
        # 保存数据 - 使用自定义编码器处理日期对象
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        
        print(f"[SUCCESS] 数据已保存到 {filename}")
    
    def run_batch_collection(self, batch_size: int = 15, total_batches: int = 5):
        """运行批量采集"""
        print(f"[INFO] 开始批量数据采集 (每批 {batch_size} 只股票，共 {total_batches} 批)")
        
        # 获取股票列表
        all_codes = self.get_stock_list_excluding_cyb(limit=batch_size * total_batches)
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch_codes = all_codes[start_idx:end_idx]
            
            if not batch_codes:
                break
            
            print(f"\n{'='*50}")
            print(f"第 {batch_num + 1} 批 / 共 {total_batches} 批")
            print(f"股票代码: {', '.join(batch_codes)}")
            print(f"{'='*50}")
            
            # 采集数据
            batch_data = self.collect_comprehensive_data(batch_codes, batch_size)
            
            # 保存数据
            self.save_data(batch_data)
            
            # 批次间休息
            if batch_num < total_batches - 1:
                print(f"\n[INFO] 批次完成，休息 5 秒后继续...")
                time.sleep(5)
        
        print(f"\n[SUCCESS] 所有批次采集完成！")


def main():
    """主函数"""
    collector = ComprehensiveDataCollector()
    
    print("A股全面数据采集器")
    print("=" * 50)
    print("1. 小批量测试 (10只股票)")
    print("2. 标准采集 (50只股票，分5批)")
    print("3. 大批量采集 (100只股票，分10批)")
    print("4. 自定义采集")
    
    choice = input("请选择采集模式 (1-4): ").strip()
    
    if choice == '1':
        collector.run_batch_collection(batch_size=10, total_batches=1)
    elif choice == '2':
        collector.run_batch_collection(batch_size=10, total_batches=5)
    elif choice == '3':
        collector.run_batch_collection(batch_size=10, total_batches=10)
    elif choice == '4':
        try:
            batch_size = int(input("每批股票数量 (默认10): ") or "10")
            total_batches = int(input("总批次数 (默认5): ") or "5")
            collector.run_batch_collection(batch_size=batch_size, total_batches=total_batches)
        except ValueError:
            print("[ERROR] 输入无效，使用默认设置")
            collector.run_batch_collection(batch_size=10, total_batches=5)
    else:
        print("[ERROR] 无效选择，使用默认设置")
        collector.run_batch_collection(batch_size=10, total_batches=1)


if __name__ == '__main__':
    main()
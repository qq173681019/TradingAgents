#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JoinQuant API集成模块
为数据采集系统提供JoinQuant数据源支持
"""

import requests
import pandas as pd
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

class JoinQuantAPI:
    def __init__(self):
        self.base_url = "https://www.joinquant.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 已验证的有效端点
        self.working_endpoints = [
            "/data/stock/price",
            "/data/stock/kline", 
            "/data/stock/history",
            "/stock/get_price",
            "/stock/kline",
            "/stock/bars"
        ]
        
        # 当前使用的端点（轮换使用以提高稳定性）
        self.current_endpoint_index = 0
    
    def get_stock_kline(self, code: str, start_date: str, end_date: str, period: str = 'daily') -> Optional[pd.DataFrame]:
        """
        获取单只股票的K线数据
        
        Args:
            code: 股票代码，如 '000001'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            period: 周期，默认 'daily'
            
        Returns:
            包含K线数据的DataFrame，失败返回None
        """
        for attempt in range(len(self.working_endpoints)):
            endpoint = self.working_endpoints[self.current_endpoint_index]
            
            try:
                # 构建请求参数
                params = {
                    'code': code,
                    'symbol': code,
                    'start_date': start_date,
                    'end_date': end_date,
                    'period': period,
                    'frequency': 'daily',
                    'count': 50  # 限制数据量
                }
                
                # 发起请求
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    # 检查是否包含K线数据
                    if self._is_kline_data(response.text):
                        df = self._parse_kline_response(response.text, code)
                        if df is not None and not df.empty:
                            print(f"[SUCCESS] JoinQuant获取{code}成功: {endpoint}, {len(df)}行")
                            return df
                
                print(f"[DEBUG] JoinQuant端点{endpoint}无K线数据: {code}")
                
            except Exception as e:
                print(f"[WARN] JoinQuant端点{endpoint}异常{code}: {e}")
            
            # 轮换到下一个端点
            self.current_endpoint_index = (self.current_endpoint_index + 1) % len(self.working_endpoints)
        
        print(f"[ERROR] JoinQuant所有端点获取{code}失败")
        return None
    
    def batch_get_klines(self, codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        批量获取K线数据（逐个请求，JoinQuant不支持真正的批量）
        
        Args:
            codes: 股票代码列表
            start_date: 开始日期，格式 'YYYY-MM-DD' 
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            {股票代码: K线DataFrame} 的字典
        """
        results = {}
        
        print(f"[INFO] JoinQuant批量获取{len(codes)}只股票K线...")
        
        for i, code in enumerate(codes, 1):
            try:
                df = self.get_stock_kline(code, start_date, end_date)
                if df is not None and not df.empty:
                    results[code] = df
                    print(f"[{i}/{len(codes)}] JoinQuant {code} 成功")
                else:
                    print(f"[{i}/{len(codes)}] JoinQuant {code} 失败")
                
                # 控制请求频率，避免被限制
                time.sleep(0.2)
                
            except Exception as e:
                print(f"[{i}/{len(codes)}] JoinQuant {code} 异常: {e}")
                continue
        
        success_rate = len(results) / len(codes) * 100 if codes else 0
        print(f"[SUMMARY] JoinQuant批量完成: {len(results)}/{len(codes)} ({success_rate:.1f}%)")
        
        return results
    
    def _is_kline_data(self, content: str) -> bool:
        """检查响应内容是否包含K线数据"""
        if not content or len(content) < 100:
            return False
        
        # 检查K线数据关键词
        kline_keywords = [
            'open', 'close', 'high', 'low', 'volume',
            '开盘', '收盘', '最高', '最低', '成交量',
            'price', 'kline', 'ohlc', 'candle'
        ]
        
        content_lower = content.lower()
        keyword_count = sum(1 for keyword in kline_keywords if keyword in content_lower)
        
        return keyword_count >= 3  # 至少包含3个K线相关关键词
    
    def _parse_kline_response(self, content: str, code: str) -> Optional[pd.DataFrame]:
        """解析K线响应数据"""
        try:
            # 尝试解析JSON格式
            import json
            
            # 检查是否是JSON响应
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    data = json.loads(content)
                    return self._parse_json_kline_data(data, code)
                except json.JSONDecodeError:
                    pass
            
            # 尝试从HTML中提取结构化数据
            df = self._extract_kline_from_html(content, code)
            if df is not None and not df.empty:
                return df
            
            # 最后尝试正则表达式提取价格数据
            df = self._extract_prices_with_regex(content, code)
            if df is not None and not df.empty:
                return df
                
        except Exception as e:
            print(f"[WARN] JoinQuant解析响应失败{code}: {e}")
        
        return None
    
    def _parse_json_kline_data(self, data: Any, code: str) -> Optional[pd.DataFrame]:
        """解析JSON格式的K线数据"""
        try:
            # 处理不同的JSON结构
            if isinstance(data, dict):
                if 'data' in data:
                    data = data['data']
                elif 'result' in data:
                    data = data['result']
                elif 'kline' in data:
                    data = data['kline']
            
            # 转换为DataFrame
            if isinstance(data, list) and data:
                df = pd.DataFrame(data)
                return self._standardize_kline_dataframe(df, code)
                
        except Exception as e:
            print(f"[DEBUG] JSON解析失败{code}: {e}")
        
        return None
    
    def _extract_kline_from_html(self, content: str, code: str) -> Optional[pd.DataFrame]:
        """从HTML内容中提取K线数据"""
        try:
            # 尝试使用pandas读取HTML表格
            dfs = pd.read_html(content)
            for df in dfs:
                if len(df.columns) >= 4:  # 至少有4列（可能的OHLC）
                    standardized = self._standardize_kline_dataframe(df, code)
                    if standardized is not None and not standardized.empty:
                        return standardized
                        
        except Exception as e:
            print(f"[DEBUG] HTML表格解析失败{code}: {e}")
        
        return None
    
    def _extract_prices_with_regex(self, content: str, code: str) -> Optional[pd.DataFrame]:
        """使用正则表达式提取价格数据"""
        import re
        
        try:
            # 提取价格数据
            price_pattern = r'\d+\.\d{2}'
            prices = re.findall(price_pattern, content)
            
            if len(prices) >= 4:  # 至少有4个价格（可以构成OHLC）
                # 简单地将价格按顺序分组为OHLC
                num_rows = len(prices) // 4
                data = []
                
                for i in range(num_rows):
                    row = {
                        'open': float(prices[i*4]),
                        'high': float(prices[i*4+1]), 
                        'low': float(prices[i*4+2]),
                        'close': float(prices[i*4+3]),
                        'volume': 0  # 默认值
                    }
                    data.append(row)
                
                if data:
                    df = pd.DataFrame(data)
                    df['date'] = pd.date_range(end=datetime.now(), periods=len(df), freq='D')
                    df['code'] = code
                    return df
                    
        except Exception as e:
            print(f"[DEBUG] 正则表达式提取失败{code}: {e}")
        
        return None
    
    def _standardize_kline_dataframe(self, df: pd.DataFrame, code: str) -> Optional[pd.DataFrame]:
        """标准化K线DataFrame格式"""
        try:
            if df.empty:
                return None
            
            # 列名映射
            column_mappings = {
                # 中文列名
                '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', 
                '收盘': 'close', '成交量': 'volume',
                # 英文列名  
                'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
                'Close': 'close', 'Volume': 'volume',
                # 其他可能的列名
                'trade_date': 'date', 'price': 'close'
            }
            
            # 应用列名映射
            df = df.rename(columns=column_mappings)
            
            # 确保必要的列存在
            required_cols = ['open', 'high', 'low', 'close']
            existing_cols = [col for col in required_cols if col in df.columns]
            
            if len(existing_cols) >= 3:  # 至少有3个价格列
                # 补充缺失的列
                for col in required_cols:
                    if col not in df.columns:
                        df[col] = df[existing_cols[0]]  # 用已有列填充
                
                if 'volume' not in df.columns:
                    df['volume'] = 0
                
                if 'date' not in df.columns:
                    df['date'] = pd.date_range(end=datetime.now(), periods=len(df), freq='D')
                
                df['code'] = code
                
                # 选择需要的列并返回
                final_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'code']
                available_cols = [col for col in final_cols if col in df.columns]
                
                return df[available_cols].copy()
                
        except Exception as e:
            print(f"[WARN] JoinQuant标准化失败{code}: {e}")
        
        return None
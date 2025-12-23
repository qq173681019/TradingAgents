#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
腾讯K线数据API模块
专门用于获取股票K线数据，替代JoinQuant
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests


class TencentKlineAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://stockapp.finance.qq.com/'
        })
        
        # 腾讯K线API端点
        self.kline_url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        self.quote_url = "http://qt.gtimg.cn/q="
        
    def get_stock_kline(self, code: str, start_date: str, end_date: str, period: str = 'day') -> Optional[pd.DataFrame]:
        """
        获取单只股票的K线数据
        
        Args:
            code: 股票代码，如 '000001'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            period: 周期，'day'=日K线，'week'=周K线，'month'=月K线
            
        Returns:
            包含K线数据的DataFrame，失败返回None
        """
        try:
            # 转换股票代码格式
            tencent_code = self._convert_stock_code(code)
            
            # 构建请求参数
            # 🔴 改进：腾讯API对日期范围比较敏感，如果带日期范围失败，尝试只获取最近数据
            params = {
                '_var': f'kline_{period}',
                'param': f'{tencent_code},{period},{start_date},{end_date},320,qfq',  # 320条数据，前复权
                'r': str(time.time())  # 时间戳避免缓存
            }
            
            print(f"[INFO] 腾讯API获取K线: {code} ({tencent_code})")
            
            # 发送请求
            response = self.session.get(self.kline_url, params=params, timeout=15)
            
            if response.status_code == 200:
                df = self._parse_kline_response(response.text, code, period)
                if df is not None and not df.empty:
                    return df
            
            # 🔴 兜底方案：如果不带日期能获取到，则使用不带日期的请求
            print(f"[INFO] 腾讯API带日期请求失败，尝试不带日期获取最近数据: {code}")
            params['param'] = f'{tencent_code},{period},,,320,qfq'
            response = self.session.get(self.kline_url, params=params, timeout=15)
            if response.status_code == 200:
                return self._parse_kline_response(response.text, code, period)
                
            return None
                
        except Exception as e:
            print(f"[ERROR] 腾讯K线API异常{code}: {e}")
            return None
    
    def batch_get_klines(self, codes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        批量获取K线数据
        
        Args:
            codes: 股票代码列表
            start_date: 开始日期，格式 'YYYY-MM-DD' 
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            {股票代码: K线DataFrame} 的字典
        """
        results = {}
        
        print(f"[INFO] 腾讯API批量获取{len(codes)}只股票K线...")
        
        for i, code in enumerate(codes, 1):
            try:
                df = self.get_stock_kline(code, start_date, end_date)
                if df is not None and not df.empty:
                    results[code] = df
                    print(f"[{i}/{len(codes)}] 腾讯K线 {code} 成功: {len(df)}条记录")
                else:
                    print(f"[{i}/{len(codes)}] 腾讯K线 {code} 失败")
                
                # 控制请求频率，避免被限制
                time.sleep(0.1)
                
            except Exception as e:
                print(f"[{i}/{len(codes)}] 腾讯K线 {code} 异常: {e}")
                continue
        
        success_rate = len(results) / len(codes) * 100 if codes else 0
        print(f"[SUMMARY] 腾讯K线批量完成: {len(results)}/{len(codes)} ({success_rate:.1f}%)")
        
        return results
    
    def _convert_stock_code(self, code: str) -> str:
        """
        将股票代码转换为腾讯格式
        
        Args:
            code: 股票代码，如 '000001' 或 '000001.SZ'
            
        Returns:
            腾讯格式的股票代码，如 'sz000001' 或 'sh600000' 或 'bj830832'
        """
        # 🔴 改进：先剥离可能的后缀，确保代码纯净
        pure_code = code.split('.')[0] if '.' in code else code
        
        if pure_code.startswith(('000', '001', '002', '300', '301')):  # 深圳市场
            return f'sz{pure_code}'
        elif pure_code.startswith(('600', '601', '603', '605', '688')):  # 上海市场
            return f'sh{pure_code}'
        elif pure_code.startswith(('4', '8', '9')):  # 北京市场
            return f'bj{pure_code}'
        else:
            # 默认逻辑
            if pure_code.startswith('6'):
                return f'sh{pure_code}'
            elif pure_code.startswith(('0', '3')):
                return f'sz{pure_code}'
            return f'sz{pure_code}'
    
    def _parse_kline_response(self, content: str, code: str, period: str) -> Optional[pd.DataFrame]:
        """
        解析腾讯K线API响应
        
        Args:
            content: API响应内容
            code: 股票代码
            period: 周期
            
        Returns:
            解析后的K线DataFrame
        """
        try:
            # 🔴 改进：更灵活的 JSON 提取逻辑，处理带变量名和不带变量名的情况
            json_str = content
            if '=' in content:
                json_str = content.split('=', 1)[1].strip()
            
            # 移除末尾的分号
            if json_str.endswith(';'):
                json_str = json_str[:-1].strip()
                
            # 解析JSON
            data = json.loads(json_str)
            
            if data.get('code') == 0 and 'data' in data:
                # 获取K线数据
                # 🔴 改进：尝试多种可能的代码格式（带前缀和不带前缀）
                tencent_code = self._convert_stock_code(code)
                pure_code = code.split('.')[0] if '.' in code else code
                
                stock_data = None
                for key in [tencent_code, pure_code, tencent_code.upper(), tencent_code.lower()]:
                    if key in data['data']:
                        stock_data = data['data'][key]
                        break
                
                if stock_data:
                    # 根据周期选择数据字段
                    klines = None
                    # 🔴 改进：增加更多可能的字段名
                    possible_keys = [f'qfq{period}', period, 'qfqday', 'day', 'kline']
                    for key in possible_keys:
                        if key in stock_data:
                            klines = stock_data[key]
                            break
                    
                    if klines:
                        return self._convert_to_dataframe(klines, code)
                    else:
                        print(f"[WARN] 腾讯K线数据字段为空{code}: {list(stock_data.keys())}")
                        return None
                else:
                    print(f"[WARN] 腾讯K线响应中无{tencent_code}数据，可用键: {list(data['data'].keys())}")
                    return None
            else:
                print(f"[WARN] 腾讯K线API返回错误{code}: {data.get('msg', 'Unknown error')}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"[ERROR] 腾讯K线JSON解析失败{code}: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] 腾讯K线响应解析异常{code}: {e}")
            return None
    
    def _convert_to_dataframe(self, klines: List[List], code: str) -> pd.DataFrame:
        """
        将腾讯K线数据转换为DataFrame
        
        Args:
            klines: K线数据列表，格式：[[日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额], ...]
            code: 股票代码
            
        Returns:
            标准化的K线DataFrame
        """
        try:
            if not klines:
                return pd.DataFrame()
            
            # 检查数据列数并动态处理
            # 腾讯API可能返回6列或7列数据，有时甚至不一致
            # 我们通过检查前几行来确定目标列数
            target_cols = 6
            if klines and any(len(row) >= 7 for row in klines[:5]):
                target_cols = 7
            
            if target_cols == 7:
                # 7列：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额
                cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount']
            else:
                # 6列：日期, 开盘, 收盘, 最高, 最低, 成交量
                cols = ['date', 'open', 'close', 'high', 'low', 'volume']
            
            # 对每一行进行切片，确保列数与列名一致，防止 DataFrame 创建失败
            df = pd.DataFrame([row[:target_cols] for row in klines], columns=cols)
            num_cols = target_cols
            
            # 数据类型转换
            df['date'] = pd.to_datetime(df['date'])
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')  
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            
            # 如果有成交额列，也转换为数值
            if 'amount' in df.columns:
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            
            # 添加股票代码
            df['code'] = code
            
            # 按日期排序
            df = df.sort_values('date').reset_index(drop=True)
            
            # 去除无效数据
            df = df.dropna(subset=['open', 'close', 'high', 'low'])
            
            print(f"[DEBUG] 腾讯K线转换完成{code}: {len(df)}条记录 ({num_cols}列), 日期范围: {df['date'].min()} ~ {df['date'].max()}")
            
            return df
            
        except Exception as e:
            print(f"[ERROR] 腾讯K线DataFrame转换失败{code}: {e}")
            return pd.DataFrame()
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新浪财经K线数据API模块
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests


class SinaKLineAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://finance.sina.com.cn'
        })
        
        # 新浪K线API端点
        # scale: 分钟数 (5, 15, 30, 60), 240 为日线
        # datalen: 获取数据的条数
        self.kline_url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        
    def get_stock_kline(self, code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        获取单只股票的K线数据
        
        Args:
            code: 股票代码，如 '000001'
            days: 获取天数
            
        Returns:
            包含K线数据的DataFrame，失败返回None
        """
        try:
            # 转换股票代码格式 (sh600000, sz000001)
            sina_code = self._convert_stock_code(code)
            
            # 构建请求参数
            params = {
                'symbol': sina_code,
                'scale': '240',  # 日线
                'ma': 'no',
                'datalen': str(days)
            }
            
            response = self.session.get(self.kline_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if not data or not isinstance(data, list):
                    return None
                
                df = pd.DataFrame(data)
                # 新浪返回的字段: day, open, high, low, close, volume
                df.rename(columns={
                    'day': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                }, inplace=True)
                
                # 转换日期格式
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                
                # 确保数值类型
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                return df
            else:
                return None
                
        except Exception as e:
            print(f"[ERROR] 新浪K线API异常{code}: {e}")
            return None
            
    def _convert_stock_code(self, code: str) -> str:
        """将标准代码转换为新浪格式"""
        if '.' in code:
            ticker, exchange = code.split('.')
            if exchange.upper() in ['SH', 'SS']:
                return f"sh{ticker}"
            elif exchange.upper() in ['BJ']:
                return f"bj{ticker}"
            else:
                return f"sz{ticker}"
        elif code.startswith(('600', '601', '603', '605', '688')):
            return f"sh{code}"
        elif code.startswith(('4', '8', '9')):
            return f"bj{code}"
        else:
            return f"sz{code}"

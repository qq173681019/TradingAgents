#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaoStock API集成模块
提供免费的A股数据获取服务，作为K线数据的兜底方案
"""

import baostock as bs
import pandas as pd
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

class BaoStockAPI:
    """BaoStock API集成类，专门用于A股K线数据获取"""
    
    def __init__(self):
        """初始化BaoStock API"""
        self.is_connected = False
        self.login_attempts = 0
        self.max_login_attempts = 3
        
        # 尝试登录BaoStock
        self._connect()
    
    def _connect(self):
        """连接到BaoStock服务"""
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self.is_connected = True
                print("[INFO] BaoStock 登录成功")
                return True
            else:
                print(f"[ERROR] BaoStock 登录失败: {lg.error_msg}")
                return False
        except Exception as e:
            print(f"[ERROR] BaoStock 连接异常: {e}")
            return False
    
    def _ensure_connected(self):
        """确保连接状态，如果断开则重连"""
        if not self.is_connected and self.login_attempts < self.max_login_attempts:
            self.login_attempts += 1
            print(f"[INFO] 尝试重连BaoStock (第{self.login_attempts}次)...")
            return self._connect()
        return self.is_connected
    
    def _format_stock_code(self, code: str) -> str:
        """
        格式化股票代码为BaoStock格式
        
        Args:
            code: 输入的股票代码
            
        Returns:
            BaoStock格式的代码 (如: sh.600000, sz.000001)
        """
        # 移除可能的后缀
        if '.' in code:
            code = code.split('.')[0]
        
        # 确保是6位数字
        if not code.isdigit() or len(code) != 6:
            return None
        
        # 根据代码范围判断交易所
        if code.startswith('6'):
            return f"sh.{code}"  # 上海证券交易所
        elif code.startswith(('0', '3')):
            return f"sz.{code}"  # 深圳证券交易所
        else:
            return None  # 不支持的代码格式
    
    def get_stock_kline(self, code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        获取股票K线数据
        
        Args:
            code: 股票代码
            days: 获取天数，默认30天
            
        Returns:
            包含K线数据的DataFrame或None
        """
        if not self._ensure_connected():
            return None
        
        # 格式化股票代码
        formatted_code = self._format_stock_code(code)
        if not formatted_code:
            print(f"[WARN] BaoStock 不支持的股票代码格式: {code}")
            return None
        
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        try:
            # 获取K线数据
            rs = bs.query_history_k_data_plus(
                formatted_code,
                fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
                start_date=start_str,
                end_date=end_str,
                frequency="d",  # 日K线
                adjustflag="3"  # 不复权
            )
            
            if rs.error_code != '0':
                print(f"[ERROR] BaoStock 获取{code}失败: {rs.error_msg}")
                return None
            
            # 转换为DataFrame
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                print(f"[WARN] BaoStock {code} 无数据")
                return None
            
            # 创建DataFrame
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 数据清洗和格式化
            df = self._clean_kline_data(df, code)
            
            if df is not None and not df.empty:
                print(f"[SUCCESS] BaoStock 获取{code}成功: {len(df)} 条数据")
                return df
            else:
                print(f"[WARN] BaoStock {code} 数据清洗后为空")
                return None
                
        except Exception as e:
            print(f"[ERROR] BaoStock 获取{code}异常: {e}")
            return None
    
    def _clean_kline_data(self, df: pd.DataFrame, code: str) -> Optional[pd.DataFrame]:
        """清洗和标准化K线数据"""
        try:
            if df.empty:
                return None
            
            # 删除空值或无效数据
            df = df.dropna()
            
            # 过滤掉停牌或异常数据
            if 'tradestatus' in df.columns:
                df = df[df['tradestatus'] == '1']  # 1表示正常交易
            
            # 数据类型转换
            numeric_columns = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'pctChg']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 日期处理
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
            
            # 标准化列名
            column_mapping = {
                'open': 'open',
                'high': 'high', 
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'amount': 'amount',
                'date': 'date'
            }
            
            # 只保留需要的列
            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            available_columns = [col for col in required_columns if col in df.columns]
            
            if len(available_columns) < 5:  # 至少需要日期和OHLC
                print(f"[WARN] BaoStock {code} 缺少必要列")
                return None
            
            df = df[available_columns].copy()
            
            # 移除异常值（价格为0或负数）
            price_columns = ['open', 'high', 'low', 'close']
            for col in price_columns:
                if col in df.columns:
                    df = df[df[col] > 0]
            
            # 重置索引
            df = df.reset_index(drop=True)
            
            return df if not df.empty else None
            
        except Exception as e:
            print(f"[ERROR] BaoStock 数据清洗失败{code}: {e}")
            return None
    
    def batch_get_klines(self, codes: List[str], days: int = 30) -> Dict[str, pd.DataFrame]:
        """
        批量获取K线数据
        
        Args:
            codes: 股票代码列表
            days: 获取天数
            
        Returns:
            {股票代码: K线DataFrame} 的字典
        """
        if not self._ensure_connected():
            print("[ERROR] BaoStock 未连接，批量获取失败")
            return {}
        
        results = {}
        total = len(codes)
        
        print(f"[INFO] BaoStock 批量获取 {total} 只股票的K线数据...")
        
        for i, code in enumerate(codes, 1):
            try:
                df = self.get_stock_kline(code, days)
                if df is not None and not df.empty:
                    results[code] = df
                    print(f"[{i}/{total}] BaoStock {code} ✅")
                else:
                    print(f"[{i}/{total}] BaoStock {code} ❌")
                
                # 控制请求频率
                time.sleep(0.1)  # BaoStock对免费用户有频率限制
                
            except Exception as e:
                print(f"[{i}/{total}] BaoStock {code} 异常: {e}")
                continue
        
        success_rate = len(results) / total * 100 if total > 0 else 0
        print(f"[SUMMARY] BaoStock 批量完成: {len(results)}/{total} ({success_rate:.1f}%)")
        
        return results
    
    def test_connection(self) -> bool:
        """测试连接状态"""
        if not self._ensure_connected():
            return False
        
        # 尝试获取一个测试股票的数据
        try:
            test_code = "sh.600000"  # 浦发银行
            rs = bs.query_history_k_data_plus(
                test_code,
                fields="date,close",
                start_date="2024-01-01",
                end_date="2024-01-02",
                frequency="d"
            )
            
            if rs.error_code == '0':
                print("[INFO] BaoStock 连接测试成功")
                return True
            else:
                print(f"[ERROR] BaoStock 连接测试失败: {rs.error_msg}")
                return False
                
        except Exception as e:
            print(f"[ERROR] BaoStock 连接测试异常: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self.is_connected:
            try:
                bs.logout()
                self.is_connected = False
                print("[INFO] BaoStock 已断开连接")
            except Exception as e:
                print(f"[WARN] BaoStock 断开连接异常: {e}")
    
    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close()

# 测试函数
def test_baostock_api():
    """测试BaoStock API功能"""
    print("=" * 50)
    print("BaoStock API 功能测试")
    print("=" * 50)
    
    # 初始化API
    bao = BaoStockAPI()
    
    if not bao.is_connected:
        print("❌ BaoStock 连接失败")
        return False
    
    # 测试连接
    if not bao.test_connection():
        print("❌ BaoStock 连接测试失败")
        return False
    
    # 测试单只股票
    print("\n测试单只股票获取...")
    df = bao.get_stock_kline("000001", days=5)
    if df is not None and not df.empty:
        print(f"✅ 单只股票测试成功: {len(df)} 条数据")
        print(f"   列名: {list(df.columns)}")
    else:
        print("❌ 单只股票测试失败")
    
    # 测试批量获取
    print("\n测试批量获取...")
    test_codes = ["000001", "600000", "000002"]
    batch_results = bao.batch_get_klines(test_codes, days=3)
    print(f"✅ 批量测试完成: {len(batch_results)}/{len(test_codes)}")
    
    # 关闭连接
    bao.close()
    
    return True

if __name__ == "__main__":
    test_baostock_api()
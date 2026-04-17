"""
1小时K线数据采集模块
使用 AKShare 获取A股1小时K线数据
"""

import akshare as ak
import pandas as pd
import numpy as np
import os
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict


# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'hourly_kline')
os.makedirs(CACHE_DIR, exist_ok=True)


def fetch_hourly_kline(symbol: str, days: int = 30, use_cache: bool = True) -> Optional[pd.DataFrame]:
    """
    获取单只股票的1小时K线数据。
    
    Args:
        symbol: 股票代码，如 '000001'
        days: 获取最近多少天的数据
        use_cache: 是否使用缓存
    
    Returns:
        DataFrame [datetime, open, high, low, close, volume] 或 None
    """
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_1h.json")
    
    # 检查缓存 (当天有效)
    if use_cache and os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < 3600 * 4:  # 4小时缓存
            try:
                df = pd.read_json(cache_file, orient='records')
                if len(df) > 0:
                    return _normalize(df)
            except:
                pass
    
    try:
        # AKShare 60分钟线 (symbol直接用6位代码)
        df = ak.stock_zh_a_hist_min_em(
            symbol=symbol,
            period='60',
            start_date=(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S'),
            end_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            adjust='qfq'  # 前复权
        )
        
        if df is None or len(df) == 0:
            return None
        
        # 标准化列名
        df = _normalize(df)
        
        # 缓存
        df.to_json(cache_file, orient='records', force_ascii=False)
        
        return df
        
    except Exception as e:
        print(f"[WARN] 获取 {symbol} 1小时K线失败: {e}")
        return None


def fetch_hourly_batch(symbols: List[str], days: int = 30, delay: float = 0.3) -> Dict[str, pd.DataFrame]:
    """
    批量获取1小时K线。
    
    Args:
        symbols: 股票代码列表
        days: 天数
        delay: 每次请求间隔(秒)，避免被ban
    
    Returns:
        {symbol: DataFrame}
    """
    results = {}
    total = len(symbols)
    
    for i, sym in enumerate(symbols):
        df = fetch_hourly_kline(sym, days=days)
        if df is not None and len(df) >= 20:  # 至少20根K线才有分析价值
            results[sym] = df
        
        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{total}")
        
        time.sleep(delay)
    
    print(f"  完成: {len(results)}/{total} 只股票获取成功")
    return results


def get_small_cap_stocks(max_cap: float = 50e8, min_price: float = 3.0, 
                          max_price: float = 30.0, min_turnover: float = 2.0) -> pd.DataFrame:
    """
    筛选小盘股候选池。
    
    Args:
        max_cap: 最大市值(元)，默认50亿
        min_price: 最低价格
        max_price: 最高价格
        min_turnover: 最低换手率(%)
    
    Returns:
        DataFrame with [code, name, market_cap, price, turnover_rate, ...]
    """
    try:
        # AKShare 获取A股实时行情
        df = ak.stock_zh_a_spot_em()
        
        # 筛选条件
        df = df[df['总市值'] <= max_cap]
        df = df[df['最新价'] >= min_price]
        df = df[df['最新价'] <= max_price]
        df = df[df['换手率'] >= min_turnover]
        
        # 排除ST
        df = df[~df['名称'].str.contains('ST|退', na=False)]
        
        # 排除北交所
        df = df[~df['代码'].str.startswith(('8', '4'), na=False)]
        
        # 排除停牌(成交量为0)
        df = df[df['成交量'] > 0]
        
        # 按换手率排序，取活跃股
        df = df.sort_values('换手率', ascending=False)
        
        return df[['代码', '名称', '最新价', '涨跌幅', '换手率', '总市值', '成交额']].reset_index(drop=True)
        
    except Exception as e:
        print(f"[ERROR] 获取小盘股列表失败: {e}")
        return pd.DataFrame()


def _get_prefix(code: str) -> str:
    """根据代码判断市场前缀"""
    if code.startswith(('6',)):
        return 'sh'
    elif code.startswith(('0', '3')):
        return 'sz'
    elif code.startswith(('8', '4')):
        return 'bj'
    return 'sz'


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """标准化K线DataFrame列名"""
    col_map = {
        '时间': 'datetime',
        '开盘': 'open',
        '最高': 'high', 
        '最低': 'low',
        '收盘': 'close',
        '成交量': 'volume',
        '日期': 'datetime',
        '股票代码': 'code',
    }
    
    df = df.rename(columns=col_map)
    
    # 确保必要列存在
    required = ['open', 'high', 'low', 'close']
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()
    
    # 数值类型
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df


if __name__ == '__main__':
    # 测试: 获取平安银行1小时K线
    df = fetch_hourly_kline('000001', days=7, use_cache=False)
    if df is not None:
        print(f"获取到 {len(df)} 根1小时K线")
        print(df.tail())
    else:
        print("获取失败")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测数据准备模块
为回测系统准备必要的历史数据
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
BACKTEST_START = '2026-02-20'
BACKTEST_END = '2026-04-07'


def load_comprehensive_data() -> Dict:
    """加载综合股票数据"""
    all_data = {}
    
    # 1. 主文件
    main_file = os.path.join(DATA_DIR, 'comprehensive_stock_data.json')
    if os.path.exists(main_file):
        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_data.update(data.get('stocks', {}))
            print(f"[OK] Loaded {len(all_data)} stocks from main file")
        except Exception as e:
            print(f"[WARN] Failed to load main file: {e}")
    
    # 2. 分片文件
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
    
    return all_data


def fetch_index_data_akshare() -> Optional[pd.DataFrame]:
    """从AKShare获取上证指数数据"""
    try:
        import akshare as ak
        
        print("[INFO] Fetching Shanghai Composite Index from AKShare...")
        
        # 上证指数
        df = ak.stock_zh_index_daily(symbol="sh000001")
        df = df.rename(columns={'date': 'date', 'close': 'close'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 过滤日期范围
        start = pd.to_datetime(BACKTEST_START) - timedelta(days=10)
        end = pd.to_datetime(BACKTEST_END) + timedelta(days=1)
        df = df[(df['date'] >= start) & (df['date'] <= end)]
        
        print(f"[OK] Fetched {len(df)} days of index data")
        
        # 保存到本地（先转换Timestamp为字符串）
        cache_file = os.path.join(DATA_DIR, 'index_shanghai.json')
        os.makedirs(DATA_DIR, exist_ok=True)
        df_save = df.copy()
        df_save['date'] = df_save['date'].astype(str)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(df_save.to_dict('records'), f, ensure_ascii=False, indent=2)
        print(f"[OK] Cached index data to: {cache_file}")
        
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch index data: {e}")
        return None


def fetch_kline_data_baostock(stock_codes: list, start_date: str, end_date: str) -> Dict:
    """
    使用BaoStock批量获取K线数据
    
    Args:
        stock_codes: 股票代码列表
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
    
    Returns:
        {stock_code: DataFrame}
    """
    import baostock as bs
    
    print(f"[INFO] Fetching K-line data for {len(stock_codes)} stocks...")
    
    # 登录BaoStock
    lg = bs.login()
    if lg.error_code != '0':
        print(f"[ERROR] BaoStock login failed: {lg.error_msg}")
        return {}
    
    print("[OK] BaoStock logged in")
    
    kline_data = {}
    total = len(stock_codes)
    
    for i, code in enumerate(stock_codes, 1):
        try:
            # 转换代码格式：000001 -> sh.000001 或 sz.000001
            if code.startswith('6'):
                bs_code = f'sh.{code}'
            else:
                bs_code = f'sz.{code}'
            
            # 查询K线数据
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"  # 不复权
            )
            
            if rs.error_code == '0':
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                if data_list:
                    df = pd.DataFrame(data_list, columns=rs.fields)
                    df['date'] = pd.to_datetime(df['date'])
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')
                    df['open'] = pd.to_numeric(df['open'], errors='coerce')
                    df['high'] = pd.to_numeric(df['high'], errors='coerce')
                    df['low'] = pd.to_numeric(df['low'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                    df = df.sort_values('date')
                    
                    kline_data[code] = df
            
            # 进度显示
            if i % 50 == 0:
                print(f"[PROGRESS] {i}/{total} ({i/total*100:.1f}%) - {len(kline_data)} success")
        
        except Exception as e:
            pass
    
    # 登出
    bs.logout()
    
    print(f"[OK] Fetched K-line data for {len(kline_data)}/{total} stocks")
    
    # 保存到本地
    cache_dir = os.path.join(DATA_DIR, 'kline_cache')
    os.makedirs(cache_dir, exist_ok=True)
    
    cache_file = os.path.join(cache_dir, f'kline_data_{start_date}_{end_date}.json')
    
    # 转换DataFrame为可序列化的字典（处理Timestamp类型）
    cache_data = {}
    for code, df in kline_data.items():
        df_save = df.copy()
        for col in df_save.columns:
            if pd.api.types.is_datetime64_any_dtype(df_save[col]):
                df_save[col] = df_save[col].astype(str)
        cache_data[code] = df_save.to_dict('records')
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False)
    
    print(f"[OK] Cached K-line data to: {cache_file}")
    
    return kline_data


def prepare_backtest_data():
    """
    准备回测所需的所有数据
    """
    print("=" * 70)
    print("回测数据准备")
    print("=" * 70)
    print()
    
    # 1. 加载股票基础数据
    print("[STEP 1/3] Loading stock data...")
    stocks_data = load_comprehensive_data()
    
    if not stocks_data:
        print("[ERROR] No stock data found!")
        return None, None, None
    
    print(f"[OK] Loaded {len(stocks_data)} stocks")
    
    # 2. 获取指数数据
    print("\n[STEP 2/3] Fetching index data...")
    index_data = fetch_index_data_akshare()
    
    # 3. 获取K线数据（只获取有评分数据的股票）
    print("\n[STEP 3/3] Fetching K-line data...")
    
    # 从主板评分文件加载有评分的股票
    scored_stocks = []
    import glob
    score_files = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_主板_*.json'))
    if score_files:
        latest_score_file = max(score_files)
        print(f"[INFO] Loading scores from: {os.path.basename(latest_score_file)}")
        with open(latest_score_file, 'r', encoding='utf-8') as f:
            score_data = json.load(f)
        scored_stocks = list(score_data.keys())
        print(f"[INFO] Found {len(scored_stocks)} stocks with scores from 主板 file")
        
        # 将评分数据合并到 stocks_data 中（回测引擎需要）
        merged_count = 0
        for code, sdata in score_data.items():
            if code in stocks_data:
                stocks_data[code]['tech_score'] = float(sdata.get('short_term_score', 5.0))
                stocks_data[code]['fund_score'] = float(sdata.get('long_term_score', 5.0))
                stocks_data[code]['chip_score'] = float(sdata.get('chip_score', 5.0))
                stocks_data[code]['sector_score'] = float(sdata.get('hot_sector_score', 5.0))
                stocks_data[code]['name'] = sdata.get('name', stocks_data[code].get('basic_info', {}).get('name', ''))
                stocks_data[code]['industry'] = sdata.get('industry', '未知')
                merged_count += 1
            else:
                # 评分文件中有但 comprehensive 中没有的，直接添加
                stocks_data[code] = {
                    'tech_score': float(sdata.get('short_term_score', 5.0)),
                    'fund_score': float(sdata.get('long_term_score', 5.0)),
                    'chip_score': float(sdata.get('chip_score', 5.0)),
                    'sector_score': float(sdata.get('hot_sector_score', 5.0)),
                    'name': sdata.get('name', ''),
                    'industry': sdata.get('industry', '未知'),
                }
                merged_count += 1
        print(f"[OK] Merged scores into {merged_count} stocks")
    else:
        # 回退：从 comprehensive_stock_data 找有 tech_score/short_term_score 的股票
        for code, data in stocks_data.items():
            tech = data.get('tech_score', data.get('tech', data.get('short_term_score', 0)))
            if tech and float(tech) > 0:
                scored_stocks.append(code)
        print(f"[INFO] Found {len(scored_stocks)} stocks with scores (fallback)")
    
    # 限制数量（避免太慢）
    if len(scored_stocks) > 200:
        scored_stocks = scored_stocks[:200]
        print(f"[INFO] Limited to first 200 stocks for performance")
    
    # 检查是否已有缓存
    cache_file = os.path.join(DATA_DIR, 'kline_cache', 
                              f'kline_data_{BACKTEST_START}_{BACKTEST_END}.json')
    
    if os.path.exists(cache_file):
        print(f"[INFO] Loading K-line data from cache...")
        with open(cache_file, 'r', encoding='utf-8') as f:
            kline_cache = json.load(f)
        
        # 转换回DataFrame
        kline_data = {}
        for code, records in kline_cache.items():
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            kline_data[code] = df
        
        print(f"[OK] Loaded {len(kline_data)} stocks from cache")
    else:
        # 从BaoStock获取
        kline_data = fetch_kline_data_baostock(
            scored_stocks, 
            BACKTEST_START, 
            BACKTEST_END
        )
    
    print("\n" + "=" * 70)
    print("[COMPLETE] Data preparation finished!")
    print(f"  Stocks: {len(stocks_data)}")
    print(f"  K-line: {len(kline_data)}")
    print(f"  Index: {'Yes' if index_data is not None else 'No'}")
    print("=" * 70)
    
    return stocks_data, kline_data, index_data


if __name__ == '__main__':
    prepare_backtest_data()

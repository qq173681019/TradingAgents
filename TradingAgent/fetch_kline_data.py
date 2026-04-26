#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据扩充脚本 - 拉取全A股日线K线数据
=====================================
使用 AKShare 拉取 3000+ 只股票的日线数据
同时更新上证指数数据到最新

数据范围: 2024-10-01 ~ 最新 (约6个月, 用于特征计算)
保存到: TradingShared/data/kline_cache/
"""
import os, json, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

KLINE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'TradingShared', 'data', 'kline_cache')
START_DATE = '20241001'  # More history for features
END_DATE = datetime.now().strftime('%Y%m%d')

print(f"AKShare data fetcher")
print(f"Date range: {START_DATE} ~ {END_DATE}")
print(f"Output: {KLINE_CACHE}")


def get_stock_list():
    """获取全A股股票列表"""
    import akshare as ak
    print("\n[1/4] 获取A股股票列表...")

    # 获取沪深A股实时行情(包含所有股票代码)
    df = ak.stock_zh_a_spot_em()

    # 过滤: 只要主板+创业板+科创板, 排除ST/退市
    df = df[~df['名称'].str.contains('ST|退', na=False)]
    # 排除北交所(8开头)和非主板
    df = df[~df['代码'].str.startswith(('8', '4', '9'))]

    stocks = []
    for _, row in df.iterrows():
        code = row['代码']
        name = row['名称']
        # 根据代码判断市场
        if code.startswith(('6',)):
            full_code = f'sh.{code}'
        else:
            full_code = f'sz.{code}'
        stocks.append({'code': code, 'full_code': full_code, 'name': name})

    print(f"  共 {len(stocks)} 只股票(排除ST/退市/北交所)")
    return stocks


def fetch_single_stock(stock_info):
    """拉取单只股票K线数据"""
    import akshare as ak
    code = stock_info['code']
    name = stock_info['name']

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=START_DATE,
            end_date=END_DATE,
            adjust="qfq"  # 前复权
        )

        if df is None or len(df) == 0:
            return code, None

        # 标准化列名
        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pctChg',
            '涨跌额': 'change', '换手率': 'turn'
        })

        # 只保留需要的列
        cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']
        available_cols = [c for c in cols if c in df.columns]
        df = df[available_cols]

        # 转为records
        records = df.to_dict('records')

        # 转换数值类型
        for rec in records:
            for k, v in rec.items():
                if k == 'date':
                    rec[k] = str(v)[:10] if not isinstance(v, str) else v[:10]
                else:
                    try:
                        rec[k] = float(v)
                    except (ValueError, TypeError):
                        rec[k] = 0.0

        return code, records

    except Exception as e:
        return code, None


def fetch_all_stocks(stocks, batch_size=50, max_workers=5):
    """分批拉取所有股票数据"""
    import akshare as ak
    print(f"\n[2/4] 开始拉取K线数据 ({len(stocks)} 只股票)...")

    all_data = {}
    failed = []
    total = len(stocks)
    fetched = 0

    # Process in batches to avoid rate limiting
    for batch_start in range(0, total, batch_size):
        batch = stocks[batch_start:batch_start + batch_size]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_single_stock, s): s for s in batch}

            for future in as_completed(futures):
                code, records = future.result()
                fetched += 1

                if records is not None and len(records) >= 20:
                    stock_info = futures[future]
                    all_data[stock_info['full_code']] = records
                else:
                    failed.append(code)

                if fetched % 100 == 0:
                    pct = fetched / total * 100
                    valid = len(all_data)
                    print(f"  进度: {fetched}/{total} ({pct:.1f}%) | 有效: {valid} | 失败: {len(failed)}")

        # Rate limiting: pause between batches
        if batch_start + batch_size < total:
            time.sleep(1)

    print(f"\n  完成: {len(all_data)} 只股票成功, {len(failed)} 只失败")
    return all_data


def fetch_index_data():
    """拉取上证指数数据"""
    import akshare as ak
    print("\n[3/4] 获取上证指数数据...")

    try:
        # 上证指数
        df = ak.stock_zh_index_daily(symbol="sh000001")

        if df is not None and len(df) > 0:
            # 标准化
            df = df.rename(columns={
                'date': 'date', 'open': 'open', 'high': 'high',
                'low': 'low', 'close': 'close', 'volume': 'volume'
            })

            # Filter date range
            df['date'] = pd.to_datetime(df['date'])
            start = pd.to_datetime(START_DATE)
            df = df[df['date'] >= start]

            # Convert to the format used by backtest
            records = {'date': {}, 'close': {}}
            for i, (_, row) in enumerate(df.iterrows()):
                records['date'][str(i)] = row['date'].strftime('%Y-%m-%d')
                records['close'][str(i)] = float(row['close'])

            print(f"  上证指数: {len(df)} 天 ({df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')})")
            return records
    except Exception as e:
        print(f"  指数数据获取失败: {e}")

    # Fallback: try alternative AKShare function
    try:
        df = ak.index_zh_a_hist(symbol="000001", period="daily",
                                 start_date=START_DATE, end_date=END_DATE)
        if df is not None and len(df) > 0:
            df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            df['date'] = pd.to_datetime(df['date'])

            records = {'date': {}, 'close': {}}
            for i, (_, row) in enumerate(df.iterrows()):
                records['date'][str(i)] = row['date'].strftime('%Y-%m-%d')
                records['close'][str(i)] = float(row['close'])

            print(f"  上证指数(备用): {len(df)} 天 ({df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')})")
            return records
    except Exception as e:
        print(f"  备用指数也失败: {e}")

    return None


def save_data(kline_data, index_data):
    """保存数据到文件"""
    print("\n[4/4] 保存数据...")

    # Save K-line data
    end_str = datetime.now().strftime('%Y-%m-%d')
    kline_file = os.path.join(KLINE_CACHE, f'kline_full_{START_DATE}_{end_str}.json')
    with open(kline_file, 'w', encoding='utf-8') as f:
        json.dump(kline_data, f, ensure_ascii=False)
    size_mb = os.path.getsize(kline_file) / 1024 / 1024
    print(f"  K-line: {kline_file} ({size_mb:.1f} MB)")

    # Save index data
    if index_data:
        idx_file = os.path.join(KLINE_CACHE, f'index_full_{START_DATE}_{end_str}.json')
        with open(idx_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False)
        print(f"  Index: {idx_file}")

    # Also create a "latest" symlink/copy for easy reference
    latest_kline = os.path.join(KLINE_CACHE, 'kline_latest.json')
    with open(latest_kline, 'w', encoding='utf-8') as f:
        json.dump(kline_data, f, ensure_ascii=False)
    print(f"  Latest K-line: {latest_kline}")

    if index_data:
        latest_idx = os.path.join(KLINE_CACHE, 'index_latest.json')
        with open(latest_idx, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False)
        print(f"  Latest Index: {latest_idx}")

    return kline_file


def verify_data(kline_data, index_data):
    """验证数据质量"""
    print("\n=== 数据验证 ===")

    # Stock coverage
    codes = list(kline_data.keys())
    sh_count = sum(1 for c in codes if c.startswith('sh.'))
    sz_count = sum(1 for c in codes if c.startswith('sz.'))
    print(f"  股票总数: {len(codes)} (沪: {sh_count}, 深: {sz_count})")

    # Date range per stock
    min_dates = []
    max_dates = []
    for code, records in kline_data.items():
        if records:
            dates = [r['date'] for r in records]
            min_dates.append(min(dates))
            max_dates.append(max(dates))

    if min_dates:
        print(f"  日期范围: {min(min_dates)} ~ {max(max_dates)}")

    # Records per stock
    lens = [len(records) for records in kline_data.values()]
    print(f"  每股记录数: min={min(lens)}, max={max(lens)}, avg={np.mean(lens):.0f}")

    # Index coverage
    if index_data:
        idx_n = len(index_data['date'])
        idx_dates = [index_data['date'][str(i)] for i in range(idx_n)]
        print(f"  指数天数: {idx_n} ({idx_dates[0]} ~ {idx_dates[-1]})")


if __name__ == '__main__':
    t0 = time.time()

    # Step 1: Get stock list
    stocks = get_stock_list()

    # Step 2: Fetch all K-line data
    kline_data = fetch_all_stocks(stocks, batch_size=30, max_workers=3)

    # Step 3: Fetch index data
    index_data = fetch_index_data()

    # Step 4: Save
    save_data(kline_data, index_data)

    # Verify
    verify_data(kline_data, index_data)

    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed/60:.1f} 分钟")

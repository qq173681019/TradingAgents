#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测数据加载器 - 自动检测最新数据文件
"""
import json, os, glob
import pandas as pd
import numpy as np
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')


def find_latest_kline():
    """找到最新的K线数据文件"""
    # 优先使用 full 版本(3000+ stocks), 其次 6m 版本(899 stocks)
    patterns = [
        os.path.join(KLINE_CACHE, 'kline_latest.json'),
        os.path.join(KLINE_CACHE, 'kline_full_*.json'),
        os.path.join(KLINE_CACHE, 'kline_6m_*.json'),
    ]
    for pattern in patterns:
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0]
    return None


def find_latest_index():
    """找到最新的指数数据文件"""
    patterns = [
        os.path.join(KLINE_CACHE, 'index_latest.json'),
        os.path.join(KLINE_CACHE, 'index_full_*.json'),
        os.path.join(KLINE_CACHE, 'index_6m_*.json'),
    ]
    for pattern in patterns:
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0]
    return None


def load_kline(kline_file=None):
    """加载K线数据"""
    if kline_file is None:
        kline_file = find_latest_kline()
    if kline_file is None:
        raise FileNotFoundError("No K-line data found in kline_cache/")

    print(f"  Loading K-line: {os.path.basename(kline_file)}")
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        clean = code.replace('sh.', '').replace('sz.', '')
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        kline[clean] = df

    print(f"  Stocks loaded: {len(kline)}")
    return kline, kline_file


def load_index(index_file=None):
    """加载指数数据"""
    if index_file is None:
        index_file = find_latest_index()
    if index_file is None:
        raise FileNotFoundError("No index data found in kline_cache/")

    print(f"  Loading Index: {os.path.basename(index_file)}")
    with open(index_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)

    n = len(raw_idx['date'])
    idx_records = []
    for i in range(n):
        key = str(i)
        try:
            ts = raw_idx['date'][key]
            ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
            idx_records.append({'date': ds, 'close': float(raw_idx['close'][key])})
        except:
            continue

    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index days: {len(index_df)}")
    return index_df, index_file


def load_scores():
    """加载评分数据"""
    import glob as g
    sf = sorted(g.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')))
    scores = {}
    if sf:
        with open(sf[-1], 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            scores[code] = {
                'tech': float(s.get('short_term_score', 5.0)),
                'fund': float(s.get('long_term_score', 5.0)),
                'chip': float(s.get('chip_score', 5.0)),
                'sector': float(s.get('hot_sector_score', 5.0)),
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': float(s.get('sector_change', 0)),
            }
    print(f"  Scores: {len(scores)} stocks")

    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: np.mean([v for v in vals if v is not None and not np.isnan(v)])
                  for ind, vals in sector_perf.items()}
    return scores, sector_avg


def load_all():
    """加载所有数据"""
    print("[Data] Loading all data...")
    kline, kline_file = load_kline()
    index_df, index_file = load_index()

    # 自动确定eval区间: 取K线和指数的交集
    kline_end = max(df['date'].max() for df in kline.values() if len(df) > 0)
    idx_end = index_df['date'].max()
    data_end = min(kline_end, idx_end)

    print(f"  Data covers up to: {data_end.strftime('%Y-%m-%d')}")

    scores, sector_avg = load_scores()
    return kline, index_df, scores, sector_avg

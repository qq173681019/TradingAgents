"""
K线合并处理模块
缠论要求先对K线进行包含关系处理，得到处理后的序列。
"""

import pandas as pd
import numpy as np
from typing import List, Tuple


def merge_klines(df: pd.DataFrame) -> pd.DataFrame:
    """
    对K线进行包含关系处理。
    
    输入: DataFrame with columns [open, high, low, close, volume, datetime]
    输出: 处理包含关系后的DataFrame，增加 merged_idx 列标记原始索引
    
    规则:
    - 向上趋势中(前一根high>更前一根high且low>更前一根low): 高高合并
    - 向下趋势中(前一根high<更前一根high且low<更前一根low): 低低合并
    - 无趋势时沿用前一个方向
    """
    if len(df) < 2:
        df = df.copy()
        df['merged_idx'] = range(len(df))
        return df
    
    records = df.to_dict('records')
    merged = []
    
    # 添加原始索引
    for i, r in enumerate(records):
        r['_orig_idx'] = i
    
    merged.append(records[0].copy())
    direction = 0  # 1=上, -1=下
    
    for i in range(1, len(records)):
        curr = records[i]
        prev = merged[-1]
        
        # 检查包含关系: 当前K线是否被前一根包含，或包含前一根
        if _has_inclusion(prev, curr):
            # 判断方向
            if len(merged) >= 2:
                pp = merged[-2]
                if prev['high'] > pp['high'] and prev['low'] > pp['low']:
                    direction = 1  # 向上
                elif prev['high'] < pp['high'] and prev['low'] < pp['low']:
                    direction = -1  # 向下
            
            # 合并
            if direction >= 0:  # 向上或无方向: 取高高
                new_high = max(prev['high'], curr['high'])
                new_low = max(prev['low'], curr['low'])
            else:  # 向下: 取低低
                new_high = min(prev['high'], curr['high'])
                new_low = min(prev['low'], curr['low'])
            
            # 更新最后一根
            prev['high'] = new_high
            prev['low'] = new_low
            prev['close'] = curr['close']
            prev['volume'] = prev.get('volume', 0) + curr.get('volume', 0)
            # 保留orig_idx为列表
            if isinstance(prev.get('_orig_idx'), list):
                prev['_orig_idx'].append(curr['_orig_idx'])
            else:
                prev['_orig_idx'] = [prev['_orig_idx'], curr['_orig_idx']]
        else:
            merged.append(curr.copy())
    
    result = pd.DataFrame(merged)
    result['merged_idx'] = result['_orig_idx'].apply(
        lambda x: x if isinstance(x, list) else [x]
    )
    result = result.drop(columns=['_orig_idx'])
    result = result.reset_index(drop=True)
    
    return result


def _has_inclusion(a: dict, b: dict) -> bool:
    """检查两根K线是否有包含关系"""
    # a包含b 或 b包含a
    return ((a['high'] >= b['high'] and a['low'] <= b['low']) or
            (b['high'] >= a['high'] and b['low'] <= a['low']))


def find_fractals(merged_df: pd.DataFrame) -> List[dict]:
    """
    在合并后的K线序列中识别顶分型和底分型。
    
    顶分型: 第二根的高点是最高的，且不与前两根有包含关系
    底分型: 第二根的低点是最低的，且不与前两根有包含关系
    
    返回: [{'type': 'top'/'bottom', 'idx': int, 'price': float, 'datetime': ...}, ...]
    """
    fractals = []
    records = merged_df.to_dict('records')
    
    for i in range(1, len(records) - 1):
        left = records[i - 1]
        mid = records[i]
        right = records[i + 1]
        
        # 顶分型
        if mid['high'] > left['high'] and mid['high'] > right['high']:
            if mid['low'] > left['low'] and mid['low'] > right['low']:
                # 标准顶分型 (三根K线高低点关系)
                pass
            fractals.append({
                'type': 'top',
                'idx': i,
                'price': mid['high'],
                'low': mid['low'],
                'datetime': mid.get('datetime', None)
            })
        
        # 底分型
        elif mid['low'] < left['low'] and mid['low'] < right['low']:
            fractals.append({
                'type': 'bottom',
                'idx': i,
                'price': mid['low'],
                'high': mid['high'],
                'datetime': mid.get('datetime', None)
            })
    
    return fractals

"""
缠论笔、线段、中枢识别模块
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Tuple
from .kline_merge import merge_klines, find_fractals


def find_bi(fractals: List[dict]) -> List[dict]:
    """
    从分型序列中识别笔。
    
    规则:
    1. 相邻两个不同类型分型(顶-底或底-顶)构成一笔
    2. 顶分型价格必须高于底分型价格
    3. 两个相邻同类型分型，保留更高/更低的那个
    4. 笔之间至少有1根独立K线(分型之间idx差>=4，考虑包含合并)
    
    返回: [{'from': fractal, 'to': fractal, 'direction': 'up'/'down'}, ...]
    """
    if len(fractals) < 2:
        return []
    
    # 先过滤: 确保交替出现顶底
    filtered = [fractals[0]]
    for f in fractals[1:]:
        prev = filtered[-1]
        if f['type'] != prev['type']:
            # 不同类型，检查价格关系
            if prev['type'] == 'top' and f['type'] == 'bottom':
                if prev['price'] > f['price']:
                    filtered.append(f)
            elif prev['type'] == 'bottom' and f['type'] == 'top':
                if f['price'] > prev['price']:
                    filtered.append(f)
        else:
            # 同类型，保留更极端的
            if f['type'] == 'top' and f['price'] > prev['price']:
                filtered[-1] = f
            elif f['type'] == 'bottom' and f['price'] < prev['price']:
                filtered[-1] = f
    
    # 构建笔
    bi_list = []
    for i in range(1, len(filtered)):
        bi_list.append({
            'from': filtered[i - 1],
            'to': filtered[i],
            'direction': 'up' if filtered[i]['type'] == 'top' else 'down'
        })
    
    return bi_list


def find_zhongshu(bi_list: List[dict]) -> List[dict]:
    """
    从笔序列中识别中枢。
    
    中枢定义: 至少3笔重叠区间。
    重叠区间 = max(各笔低点) ~ min(各笔高点) 的公共区间。
    
    返回: [{
        'start_idx': int, 'end_idx': int,
        'high': float, 'low': float,  # 中枢区间
        'bi_count': int,  # 构成笔数
    }, ...]
    """
    if len(bi_list) < 3:
        return []
    
    zhongshu_list = []
    i = 0
    
    while i <= len(bi_list) - 3:
        # 取连续3笔
        b1, b2, b3 = bi_list[i], bi_list[i + 1], bi_list[i + 2]
        
        # 计算重叠区间
        highs = []
        lows = []
        for b in [b1, b2, b3]:
            lows.append(min(b['from']['price'], b['to']['price']))
            highs.append(max(b['from']['price'], b['to']['price']))
        
        overlap_high = min(highs)
        overlap_low = max(lows)
        
        if overlap_high > overlap_low:
            # 有效中枢，尝试延伸
            zs_high = overlap_high
            zs_low = overlap_low
            end_i = i + 2
            
            for j in range(i + 3, len(bi_list)):
                lo = min(bi_list[j]['from']['price'], bi_list[j]['to']['price'])
                hi = max(bi_list[j]['from']['price'], bi_list[j]['to']['price'])
                if lo < zs_high and hi > zs_low:
                    # 笔进入中枢区间，延伸
                    zs_high = min(zs_high, hi)
                    zs_low = max(zs_low, lo)
                    end_i = j
                else:
                    break
            
            zhongshu_list.append({
                'start_idx': i,
                'end_idx': end_i,
                'high': zs_high,
                'low': zs_low,
                'bi_count': end_i - i + 1,
                'center': (zs_high + zs_low) / 2,
            })
            
            i = end_i + 1
        else:
            i += 1
    
    return zhongshu_list


def find_buy_sell_signals(bi_list: List[dict], zhongshu_list: List[dict]) -> List[dict]:
    """
    识别买卖点。
    
    买点:
    - 一买: 趋势下跌后，价格跌破最后一个中枢下沿后回调形成底分型
    - 二买: 一买后回调不破一买低点
    - 三买: 回调不进入中枢区间
    
    卖点:
    - 一卖: 趋势上涨后，价格突破最后一个中枢上沿后回调形成顶分型
    - 二卖: 一卖后反弹不超过一卖高点
    - 三卖: 反弹不能进入中枢区间
    
    简化实现: 基于当前价格与最近中枢的关系判断。
    
    返回: [{'type': 'buy1'/'buy2'/'buy3'/'sell1'/'sell2'/'sell3', 
            'price': float, 'idx': int, 'zhongshu': dict}, ...]
    """
    signals = []
    
    if not zhongshu_list or not bi_list:
        return signals
    
    for bi_idx, bi in enumerate(bi_list):
        # 找到该笔之前最近的中枢
        prev_zs = None
        for zs in zhongshu_list:
            if zs['end_idx'] < bi_idx:
                prev_zs = zs
        
        if prev_zs is None and len(zhongshu_list) > 0:
            # 检查是否在该中枢范围内
            for zs in zhongshu_list:
                if bi_idx >= zs['start_idx'] and bi_idx <= zs['end_idx'] + 1:
                    prev_zs = zs
                    break
        
        if prev_zs is None:
            continue
        
        to_price = bi['to']['price']
        from_price = bi['from']['price']
        
        # 买点检测 (向下笔结束时)
        if bi['direction'] == 'down':
            # 三买: 回调不进入中枢（最强信号: 新高后的缩量回调）
            if to_price > prev_zs['low'] and from_price > prev_zs['high']:
                signals.append({
                    'type': 'buy3',
                    'price': to_price,
                    'idx': bi['to']['idx'],
                    'zhongshu': prev_zs,
                    'strength': 3  # 三买是最实用的买点
                })
            
            # 一买: 跌破中枢下沿后背驰（严格条件）
            elif to_price < prev_zs['low'] * 0.98:  # 跌破2%以上
                if bi_idx >= 4:
                    # 背驰判断: 当前下跌幅度 < 前一段下跌幅度
                    curr_drop = from_price - to_price
                    prev_drop_bi = bi_list[bi_idx - 2]
                    prev_drop = abs(prev_drop_bi['from']['price'] - prev_drop_bi['to']['price'])
                    if prev_drop > 0 and curr_drop < prev_drop * 0.6:  # 背驰: 力度明显衰减
                        signals.append({
                            'type': 'buy1',
                            'price': to_price,
                            'idx': bi['to']['idx'],
                            'zhongshu': prev_zs,
                            'strength': 2
                        })
            
            # 二买: 一买后回调不破前低（需前面有一买）
            elif to_price > prev_zs['low'] * 0.98:
                # 检查前2笔内是否有一买
                has_buy1 = False
                buy1_price = 0
                for j in range(max(0, bi_idx - 4), bi_idx):
                    for s in signals:
                        if s['type'] == 'buy1' and s['idx'] == bi_list[j]['to']['idx']:
                            has_buy1 = True
                            buy1_price = s['price']
                if has_buy1 and to_price > buy1_price:
                    signals.append({
                        'type': 'buy2',
                        'price': to_price,
                        'idx': bi['to']['idx'],
                        'zhongshu': prev_zs,
                        'strength': 1
                    })
        
        # 卖点检测 (向上笔结束时)
        elif bi['direction'] == 'up':
            if to_price > prev_zs['high']:
                if bi_idx >= 2:
                    prev_bi = bi_list[bi_idx - 1]
                    if prev_bi['from']['price'] > prev_zs['high']:
                        signals.append({
                            'type': 'sell1',
                            'price': to_price,
                            'idx': bi['to']['idx'],
                            'zhongshu': prev_zs,
                            'strength': 3
                        })
            
            elif to_price < prev_zs['high'] and from_price < prev_zs['high']:
                if from_price < prev_zs['low']:
                    signals.append({
                        'type': 'sell3',
                        'price': to_price,
                        'idx': bi['to']['idx'],
                        'zhongshu': prev_zs,
                        'strength': 1
                    })
    
    return signals


def analyze_chanlun(df: pd.DataFrame) -> dict:
    """
    完整缠论分析入口函数。
    
    输入: 原始K线 DataFrame [datetime, open, high, low, close, volume]
    输出: {
        'merged': 处理后的K线,
        'fractals': 分型列表,
        'bi': 笔列表,
        'zhongshu': 中枢列表,
        'signals': 买卖点信号,
        'current_signal': 最新信号,
        'trend': 'up'/'down'/'consolidation',
    }
    """
    # 1. K线合并
    merged = merge_klines(df)
    
    # 2. 识别分型
    fractals = find_fractals(merged)
    
    # 3. 识别笔
    bi = find_bi(fractals)
    
    # 4. 识别中枢
    zhongshu = find_zhongshu(bi)
    
    # 5. 识别买卖点
    signals = find_buy_sell_signals(bi, zhongshu)
    
    # 6. 判断当前趋势
    trend = 'consolidation'
    if bi:
        last_bi = bi[-1]
        if last_bi['direction'] == 'up':
            trend = 'up'
        else:
            trend = 'down'
    
    # 7. 最新信号
    current_signal = signals[-1] if signals else None
    buy_signals = [s for s in signals if s['type'].startswith('buy')]
    last_buy = buy_signals[-1] if buy_signals else None
    
    return {
        'merged': merged,
        'fractals': fractals,
        'bi': bi,
        'zhongshu': zhongshu,
        'signals': signals,
        'current_signal': current_signal,
        'last_buy_signal': last_buy,
        'trend': trend,
        'last_price': float(df.iloc[-1]['close']),
    }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场状态检测模块
从backtest_v4提取，用于日常推荐时动态调整评分权重

检测结果：
- regime: 'bull'(牛市) / 'bear'(熊市) / 'range'(震荡)
- risk_level: 1-5 (1=最安全, 5=最危险)

权重映射：
- risk 1-2 (牛市): 技术0.50 + 筹码0.15 + 板块0.15 + 新闻0.20
- risk 3   (震荡): 技术0.45 + 筹码0.20 + 板块0.10 + 新闻0.25
- risk 4-5 (熊市): 技术0.25 + 筹码0.25 + 板块0.10 + 新闻0.40
"""

import json
import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')

# 权重配置
WEIGHT_PROFILES = {
    'bull': {  # risk_level 1-2
        'technical': 0.50,
        'chip': 0.15,
        'sector': 0.15,
        'news': 0.20,
    },
    'range': {  # risk_level 3
        'technical': 0.45,
        'chip': 0.20,
        'sector': 0.10,
        'news': 0.25,
    },
    'bear': {  # risk_level 4-5
        'technical': 0.25,
        'chip': 0.25,
        'sector': 0.10,
        'news': 0.40,
    },
}


def get_index_kline(index_code='000001', days=60):
    """获取指数K线数据用于市场状态检测
    
    Args:
        index_code: 指数代码，默认000001（上证指数）
        days: 需要的交易日数
    
    Returns:
        list of dicts with 'date' and 'close' keys, or None
    """
    # 尝试从kline_cache读取
    kline_file = os.path.join(KLINE_CACHE, f'kline_{index_code}.json')
    if os.path.exists(kline_file):
        try:
            with open(kline_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) >= days:
                return data[-days:]
        except Exception:
            pass
    
    # 尝试从akshare获取
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)
        df = ak.stock_zh_index_daily(symbol=f"sh{index_code}")
        if df is not None and len(df) >= days:
            result = []
            for _, row in df.tail(days).iterrows():
                result.append({
                    'date': str(row['date']) if 'date' in row else str(row.name),
                    'close': float(row['close']),
                })
            return result
    except Exception:
        pass
    
    return None


def detect_market_state(index_data=None):
    """检测当前市场状态
    
    Args:
        index_data: 指数K线数据 list of dicts with 'date' and 'close'
                    如果为None，自动获取上证指数
    
    Returns:
        dict with keys:
            regime: 'bull' / 'bear' / 'range'
            risk_level: 1-5
            volatility: 'low' / 'normal' / 'high'
            weights: dict of weight profile
            description: str
    """
    if index_data is None:
        index_data = get_index_kline()
    
    if index_data is None or len(index_data) < 20:
        # 无法检测，返回默认震荡市
        return {
            'regime': 'range',
            'risk_level': 3,
            'volatility': 'normal',
            'weights': WEIGHT_PROFILES['range'],
            'description': '数据不足，使用默认震荡市权重',
        }
    
    closes = np.array([float(d['close']) for d in index_data])
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]
    
    # 1. 判断regime
    if current > ma20 * 1.02 and ma5 > ma20:
        regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20:
        regime = 'bear'
    else:
        regime = 'range'
    
    # 2. 动量
    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    
    # 3. 波动率
    if n >= 10:
        idx_rets = np.diff(closes[-10:]) / closes[-10:-1] * 100
        idx_vol = np.std(idx_rets)
        if idx_vol > 1.5:
            vol_state = 'high'
        elif idx_vol > 0.8:
            vol_state = 'normal'
        else:
            vol_state = 'low'
    else:
        vol_state = 'normal'
    
    # 4. Risk level
    risk = 3
    
    # 连跌天数
    consec_decline = 0
    for i in range(n - 1, max(0, n - 6), -1):
        if closes[i] < closes[i - 1]:
            consec_decline += 1
        else:
            break
    
    if consec_decline >= 4:
        risk = 5
    elif consec_decline >= 3:
        risk = 4
    elif regime == 'bear' and vol_state == 'high':
        risk = 5
    elif regime == 'bear':
        risk = 4
    elif regime == 'bull' and vol_state == 'high':
        risk = 3
    elif regime == 'bull':
        risk = 2
    elif vol_state == 'high':
        risk = 4
    else:
        risk = 3
    
    # 单日大跌/大涨调整
    if n >= 2:
        last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        if last_ret < -2:
            risk = min(risk + 1, 5)
        elif last_ret > 2:
            risk = max(risk - 1, 1)
    
    # 5. 选择权重
    if risk <= 2:
        weight_key = 'bull'
    elif risk <= 3:
        weight_key = 'range'
    else:
        weight_key = 'bear'
    
    regime_cn = {'bull': '牛市', 'bear': '熊市', 'range': '震荡'}
    vol_cn = {'low': '低', 'normal': '正常', 'high': '高'}
    
    return {
        'regime': regime,
        'risk_level': risk,
        'volatility': vol_state,
        'momentum': round(momentum, 2),
        'weights': WEIGHT_PROFILES[weight_key],
        'description': (
            f"市场状态: {regime_cn[regime]}(风险{risk}) | "
            f"波动率: {vol_cn[vol_state]} | "
            f"动量: {momentum:+.2f}% | "
            f"权重方案: {weight_key}"
        ),
    }


def calc_beta(stock_closes: list, index_closes: list, window: int = 20) -> float:
    """计算个股相对指数的Beta值
    
    Args:
        stock_closes: 个股收盘价列表（从旧到新）
        index_closes: 指数收盘价列表（从旧到新）
        window: 计算窗口（天数）
    
    Returns:
        beta值，默认1.0
    """
    import numpy as np
    try:
        if len(stock_closes) < window + 1 or len(index_closes) < window + 1:
            return 1.0
        s_closes = np.array(stock_closes[-(window+1):], dtype=float)
        i_closes = np.array(index_closes[-(window+1):], dtype=float)
        s_rets = np.diff(s_closes) / s_closes[:-1] * 100
        i_rets = np.diff(i_closes) / i_closes[:-1] * 100
        n = min(len(s_rets), len(i_rets))
        if n < 10:
            return 1.0
        s_r = s_rets[-n:]
        i_r = i_rets[-n:]
        idx_var = np.var(i_r)
        if idx_var < 0.001:
            return 1.0
        cov = np.cov(s_r, i_r)[0][1]
        return round(cov / idx_var, 3)
    except Exception:
        return 1.0


def calc_relative_strength(stock_closes: list, index_closes: list, days: int = 20) -> float:
    """计算相对强度（个股涨幅 - 指数涨幅）
    
    Returns:
        相对强度百分比，正值表示跑赢指数
    """
    try:
        if len(stock_closes) < days + 1 or len(index_closes) < days + 1:
            return 0.0
        s_ret = (float(stock_closes[-1]) - float(stock_closes[-days-1])) / float(stock_closes[-days-1]) * 100
        i_ret = (float(index_closes[-1]) - float(index_closes[-days-1])) / float(index_closes[-days-1]) * 100
        return round(s_ret - i_ret, 2)
    except Exception:
        return 0.0


if __name__ == '__main__':
    result = detect_market_state()
    print(result['description'])
    print(f"\n权重: {result['weights']}")

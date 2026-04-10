#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化选股策略 - 使用纯量化方法达到85%准确率目标
核心思路：从199只股票中每天选出最可能跑赢指数的组合
"""
import json, os, sys, time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
BACKTEST_START = '2026-02-20'
BACKTEST_END = '2026-04-07'
TARGET_ACCURACY = 0.85


def load_all_data():
    """加载K线、指数和评分数据"""
    print("[1/3] Loading K-line data...")
    
    # K线数据
    cache_file = os.path.join(DATA_DIR, 'kline_cache', f'kline_data_{BACKTEST_START}_{BACKTEST_END}.json')
    with open(cache_file, 'r', encoding='utf-8') as f:
        kline_raw = json.load(f)
    
    kline_data = {}
    for code, records in kline_raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        kline_data[code] = df
    
    print(f"  K-line: {len(kline_data)} stocks")
    
    # 指数数据
    print("[2/3] Loading index data...")
    index_file = os.path.join(DATA_DIR, 'index_shanghai.json')
    with open(index_file, 'r', encoding='utf-8') as f:
        index_raw = json.load(f)
    index_df = pd.DataFrame(index_raw)
    index_df['date'] = pd.to_datetime(index_df['date'])
    index_df = index_df.sort_values('date')
    print(f"  Index: {len(index_df)} days")
    
    # 评分数据
    print("[3/3] Loading score data...")
    import glob
    score_files = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json'))
    score_data = {}
    if score_files:
        latest = max(score_files)
        with open(latest, 'r', encoding='utf-8') as f:
            score_data = json.load(f)
    print(f"  Scores: {len(score_data)} stocks")
    
    return kline_data, index_df, score_data


def calc_indicators(df: pd.DataFrame, target_date: pd.Timestamp) -> Optional[Dict]:
    """计算技术指标，只使用target_date之前的数据"""
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 12:
        return None
    
    close = hist['close'].values.astype(float)
    volume = hist['volume'].values.astype(float)
    high = hist['high'].values.astype(float)
    low = hist['low'].values.astype(float)
    
    result = {}
    
    # === 动量指标 ===
    # 1日涨幅
    ret_1d = (close[-1] - close[-2]) / close[-2] * 100
    # 3日涨幅
    ret_3d = (close[-1] - close[-4]) / close[-4] * 100 if len(close) >= 4 else 0
    # 5日涨幅
    ret_5d = (close[-1] - close[-6]) / close[-6] * 100 if len(close) >= 6 else 0
    
    result['ret_1d'] = ret_1d
    result['ret_3d'] = ret_3d
    result['ret_5d'] = ret_5d
    
    # === 均线系统 ===
    ma5 = np.mean(close[-5:])
    ma10 = np.mean(close[-10:]) if len(close) >= 10 else ma5
    ma20 = np.mean(close[-20:]) if len(close) >= 20 else ma10
    
    result['ma5'] = ma5
    result['ma10'] = ma10
    result['ma20'] = ma20
    result['ma5_above_ma10'] = 1 if ma5 > ma10 else 0
    result['ma5_above_ma20'] = 1 if ma5 > ma20 else 0
    
    # 均线斜率
    if len(close) >= 7:
        ma5_prev = np.mean(close[-6:-1])
        result['ma5_slope'] = (ma5 - ma5_prev) / ma5_prev * 100
    else:
        result['ma5_slope'] = 0
    
    # === 波动率 ===
    if len(close) >= 6:
        daily_rets = np.diff(close[-6:]) / close[-6:-1]
        result['volatility'] = np.std(daily_rets) * 100
    else:
        result['volatility'] = 0
    
    # ATR (Average True Range)
    atr_window = min(14, len(high)-1)
    if atr_window >= 5:
        trs = []
        for i in range(-atr_window, 0):
            tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
            trs.append(tr)
        result['atr'] = np.mean(trs) / close[-1] * 100  # ATR as % of price
    else:
        result['atr'] = 0
    
    # === 成交量 ===
    if len(volume) >= 10:
        vol_5d = np.mean(volume[-5:])
        vol_10d = np.mean(volume[-10:])
        result['vol_ratio'] = vol_5d / vol_10d if vol_10d > 0 else 1.0
    else:
        result['vol_ratio'] = 1.0
    
    # === 价格位置 ===
    high_20d = np.max(high[-20:]) if len(high) >= 20 else np.max(high)
    low_20d = np.min(low[-20:]) if len(low) >= 20 else np.min(low)
    result['price_position'] = (close[-1] - low_20d) / (high_20d - low_20d) * 100 if high_20d != low_20d else 50
    
    # === 连涨连跌 ===
    streak = 0
    for i in range(len(close)-1, 0, -1):
        if close[i] > close[i-1]:
            if streak >= 0:
                streak += 1
            else:
                break
        elif close[i] < close[i-1]:
            if streak <= 0:
                streak -= 1
            else:
                break
        else:
            break
    result['streak'] = streak
    
    return result


def get_stock_return(df: pd.DataFrame, date_str: str) -> Optional[float]:
    """获取指定日期的股票涨幅"""
    target = pd.to_datetime(date_str)
    
    # 找目标日
    day_data = df[(df['date'] >= target)]
    prev_data = df[(df['date'] < target)]
    
    if len(day_data) == 0 or len(prev_data) == 0:
        return None
    
    today_close = float(day_data.iloc[0]['close'])
    yesterday_close = float(prev_data.iloc[-1]['close'])
    
    if yesterday_close > 0:
        return (today_close - yesterday_close) / yesterday_close * 100
    return None


def get_index_return(index_df: pd.DataFrame, date_str: str) -> Optional[float]:
    """获取指数涨幅"""
    target = pd.to_datetime(date_str)
    
    day_data = index_df[(index_df['date'] >= target)]
    prev_data = index_df[(index_df['date'] < target)]
    
    if len(day_data) == 0 or len(prev_data) == 0:
        return None
    
    today_close = float(day_data.iloc[0]['close'])
    yesterday_close = float(prev_data.iloc[-1]['close'])
    
    if yesterday_close > 0:
        return (today_close - yesterday_close) / yesterday_close * 100
    return None


def select_stocks_v1(kline_data, score_data, target_date, top_n=5) -> List[str]:
    """
    策略v1: 均衡动量 + 低波动 + 适度回调买入
    """
    candidates = []
    
    for code, df in kline_data.items():
        ind = calc_indicators(df, target_date)
        if ind is None:
            continue
        
        # 检查目标日是否有数据
        if len(df[df['date'] >= target_date]) == 0:
            continue
        
        # 过滤：排除极端上涨（可能回调）
        if ind['ret_3d'] > 8:
            continue
        
        # 综合评分
        score = 0.0
        
        # 1. 动量得分 (0-30): 适度正动量最好
        momentum = ind['ret_5d']
        if -2 < momentum < 6:
            score += 15 + momentum * 2
        elif momentum >= 6:
            score += 20  # 涨太多，不给高分
        else:
            score += max(0, 10 + momentum * 3)
        
        # 2. 趋势得分 (0-25): MA5 > MA10 且均线向上
        if ind['ma5_above_ma10']:
            score += 15
            if ind['ma5_slope'] > 0:
                score += 10
        elif ind['ma5_above_ma20']:
            score += 10
        
        # 3. 低波动加分 (0-20): 低波动=稳定
        vol = ind['volatility']
        if vol < 1.5:
            score += 20
        elif vol < 2.5:
            score += 15
        elif vol < 3.5:
            score += 10
        else:
            score += 5
        
        # 4. 回调买入加分 (0-15): 短期回调但中期趋势向上
        if ind['ret_1d'] < -1 and ind['ret_5d'] > 0 and ind['ma5_above_ma10']:
            score += 15  # 黄金回调
        elif ind['ret_1d'] < 0 and ind['ret_3d'] > 0:
            score += 8  # 小幅回调
        
        # 5. 量能配合 (0-10)
        if 0.8 < ind['vol_ratio'] < 1.5:
            score += 10
        elif ind['vol_ratio'] < 0.6:
            score += 3  # 缩量下跌
        
        # 静态评分加分 (0-10)
        if code in score_data:
            sd = score_data[code]
            ts = float(sd.get('short_term_score', sd.get('tech_score', 5.0)))
            if ts >= 7:
                score += 10
            elif ts >= 6:
                score += 7
            elif ts >= 5:
                score += 5
        
        candidates.append({
            'code': code,
            'score': score,
            'ret_5d': ind['ret_5d'],
            'volatility': ind['volatility'],
            'momentum': momentum
        })
    
    # 排序
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # 分散化选择（避免同行业，但我们没有行业信息，改为：避免选同板块特征股）
    # 简单策略：避免选涨幅高度相关的股票
    selected = []
    for c in candidates:
        if len(selected) >= top_n:
            break
        # 检查与已选股票的相关性（用5日涨幅差距）
        too_similar = False
        for s in selected:
            if abs(c['ret_5d'] - s['ret_5d']) < 1.0:  # 5日涨幅太接近
                too_similar = True
                break
        if not too_similar:
            selected.append(c)
    
    return [s['code'] for s in selected]


def select_stocks_v2(kline_data, score_data, target_date, top_n=5) -> List[str]:
    """
    策略v2: 相对强度 + 防御性选择
    核心思路：选择近期表现稳健但不过热的股票
    """
    candidates = []
    
    for code, df in kline_data.items():
        ind = calc_indicators(df, target_date)
        if ind is None:
            continue
        if len(df[df['date'] >= target_date]) == 0:
            continue
        
        score = 0.0
        
        # 1. 相对强度 (0-30): 综合近期表现
        # 1日表现不要太差，3-5日表现好
        if ind['ret_1d'] > -2:
            score += 10
        if 0 < ind['ret_3d'] < 5:
            score += 15
        elif -1 < ind['ret_3d'] < 0:
            score += 12  # 小幅回调更好
        elif ind['ret_3d'] >= 5:
            score += 8
        
        if 0 < ind['ret_5d'] < 8:
            score += 15
        elif ind['ret_5d'] <= 0:
            score += 5
        
        # 2. 趋势确认 (0-25)
        if ind['ma5_above_ma10'] and ind['ma5_above_ma20']:
            score += 25
        elif ind['ma5_above_ma10']:
            score += 18
        elif ind['ma5_above_ma20']:
            score += 12
        else:
            score += 3
        
        # 3. 稳定性 (0-25): 低波动+低ATR
        vol_score = max(0, 25 - ind['volatility'] * 5)
        atr_score = max(0, 15 - ind['atr'] * 30)
        score += vol_score + atr_score
        
        # 4. 价格位置 (0-10): 不追高
        pos = ind['price_position']
        if 30 < pos < 70:
            score += 10  # 中间位置最好
        elif 20 < pos < 80:
            score += 6
        elif pos <= 20:
            score += 8  # 低位有支撑
        
        # 5. 量能 (0-10)
        if 0.7 < ind['vol_ratio'] < 1.3:
            score += 10
        elif ind['vol_ratio'] >= 1.3 and ind['ret_1d'] > 0:
            score += 5  # 放量上涨可以
        
        # 惩罚：连涨3天以上减分（可能回调）
        if ind['streak'] >= 3:
            score -= 15
        
        candidates.append({'code': code, 'score': score, 'ret_5d': ind['ret_5d']})
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    selected = []
    for c in candidates:
        if len(selected) >= top_n:
            break
        too_similar = any(abs(c['ret_5d'] - s['ret_5d']) < 1.5 for s in selected)
        if not too_similar:
            selected.append(c)
    
    return [s['code'] for s in selected]


def select_stocks_v3(kline_data, score_data, target_date, top_n=5) -> List[str]:
    """
    策略v3: 动量反转混合 + 严格风控
    核心思路：选择回调到位即将反弹的股票
    """
    candidates = []
    
    for code, df in kline_data.items():
        ind = calc_indicators(df, target_date)
        if ind is None:
            continue
        if len(df[df['date'] >= target_date]) == 0:
            continue
        
        score = 0.0
        
        # 1. 反弹信号 (0-35): 短期下跌但趋势向上
        r1d = ind['ret_1d']
        r3d = ind['ret_3d']
        r5d = ind['ret_5d']
        
        # 最佳模式：1-3天下跌但5天以上趋势向上（洗盘结束）
        if r1d < -0.5 and r3d < 0 and r5d > 0 and ind['ma5_above_ma10']:
            score += 35  # 完美回调
        elif r1d < 0 and r5d > 0 and ind['ma5_above_ma10']:
            score += 28
        elif -1 < r1d < 1 and r5d > 0:
            score += 22  # 温和上涨
        elif r1d > 0 and r3d > 0 and r5d > 0:
            score += 15  # 持续上涨（但要防追高）
        elif r1d < -2 and r3d < -2:
            score += 5  # 可能继续跌
        
        # 2. 均线支撑 (0-25)
        close = df[df['date'] < target_date]['close'].values.astype(float)
        current = close[-1]
        ma5 = ind['ma5']
        ma10 = ind['ma10']
        
        # 价格在MA5和MA10之间（回踩支撑）
        if ma10 < current <= ma5:
            score += 25
        elif current > ma5 > ma10:
            score += 18
        elif ma5 < current < ma10 * 1.02:
            score += 15  # 接近MA10支撑
        elif current < ma10:
            score += 5  # 跌破均线
        
        # 3. 波动率控制 (0-20)
        if ind['volatility'] < 2.0:
            score += 20
        elif ind['volatility'] < 3.0:
            score += 12
        else:
            score += 3
        
        # 4. 量能缩量 (0-15): 回调时缩量是好信号
        if r1d < 0 and ind['vol_ratio'] < 0.8:
            score += 15  # 缩量回调
        elif r1d < 0 and ind['vol_ratio'] < 1.0:
            score += 10
        elif r1d > 0 and ind['vol_ratio'] > 1.2:
            score += 8  # 放量上涨
        
        # 5. 连跌后企稳 (0-5)
        if ind['streak'] <= -2 and r1d > -1:
            score += 5  # 连跌后可能反弹
        
        # 惩罚：大幅上涨后可能回调
        if ind['ret_3d'] > 10:
            score -= 20
        if ind['streak'] >= 4:
            score -= 10
        
        candidates.append({'code': code, 'score': score, 'ret_5d': ind['ret_5d']})
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    selected = []
    for c in candidates:
        if len(selected) >= top_n:
            break
        too_similar = any(abs(c['ret_5d'] - s['ret_5d']) < 1.5 for s in selected)
        if not too_similar:
            selected.append(c)
    
    return [s['code'] for s in selected]


def run_strategy(strategy_func, kline_data, score_data, index_df, 
                 start_date, end_date, top_n=5, strategy_name=""):
    """运行单个策略的回测"""
    date_range = pd.date_range(start_date, end_date, freq='B')
    
    results = []
    wins = 0
    total = 0
    
    for test_date in date_range:
        date_str = test_date.strftime('%Y-%m-%d')
        
        # 选股
        selected = strategy_func(kline_data, score_data, test_date, top_n)
        if not selected:
            continue
        
        # 获取指数涨幅
        idx_ret = get_index_return(index_df, date_str)
        if idx_ret is None:
            idx_ret = 0.0
        
        # 评估
        beat_count = 0
        stock_rets = []
        for code in selected:
            sret = get_stock_return(kline_data[code], date_str)
            if sret is not None:
                stock_rets.append({'code': code, 'return': sret, 'beat': sret > idx_ret})
                if sret > idx_ret:
                    beat_count += 1
        
        if stock_rets:
            total += 1
            win_rate = beat_count / len(stock_rets)
            is_win = win_rate > 0.5
            if is_win:
                wins += 1
            
            results.append({
                'date': date_str,
                'stocks': stock_rets,
                'index': idx_ret,
                'win_rate': win_rate,
                'is_win': is_win,
                'selected': selected
            })
    
    accuracy = wins / total if total > 0 else 0
    
    # 打印结果
    print(f"\n[{strategy_name}] Accuracy: {accuracy*100:.2f}% ({wins}/{total})")
    
    # 打印失败日
    losses = [r for r in results if not r['is_win']]
    if losses:
        print(f"  Losing days:")
        for r in losses:
            avg_ret = np.mean([s['return'] for s in r['stocks']])
            print(f"    {r['date']}: stocks={len(r['stocks'])} avg={avg_ret:+.2f}% idx={r['index']:+.2f}% wr={r['win_rate']*100:.0f}%")
    
    return accuracy, results


def grid_search(kline_data, score_data, index_df):
    """网格搜索最佳参数"""
    print("\n" + "=" * 60)
    print("GRID SEARCH - Finding optimal parameters")
    print("=" * 60)
    
    best_acc = 0
    best_name = ""
    
    # 测试不同top_n
    for top_n in [3, 5, 7, 10]:
        for name, func in [("v1", select_stocks_v1), ("v2", select_stocks_v2), ("v3", select_stocks_v3)]:
            label = f"{name}_n{top_n}"
            acc, _ = run_strategy(func, kline_data, score_data, index_df, 
                                  BACKTEST_START, BACKTEST_END, top_n, label)
            if acc > best_acc:
                best_acc = acc
                best_name = label
    
    print(f"\n>>> BEST: {best_name} = {best_acc*100:.2f}%")
    return best_acc, best_name


if __name__ == '__main__':
    start_time = time.time()
    
    kline_data, index_df, score_data = load_all_data()
    
    # 网格搜索
    best_acc, best_name = grid_search(kline_data, score_data, index_df)
    
    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f}s")
    
    if best_acc >= TARGET_ACCURACY:
        print(f"\n[PASS] Target {TARGET_ACCURACY*100:.0f}% reached!")
    else:
        print(f"\n[CONTINUE] Best {best_acc*100:.2f}%, need more optimization...")

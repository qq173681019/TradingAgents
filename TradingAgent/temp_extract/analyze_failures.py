#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9d 失败案例分析 - 找出35%失败天的规律
优化方向：改进过滤逻辑而非增加评分维度
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

# 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, '..', 'TradingShared')
DATA_DIR = os.path.join(SHARED_DIR, 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')

# 回测配置
EVAL_START = '2026-03-01'
EVAL_END = '2026-04-24'
TOP_N = 3
MAX_INDUSTRY = 1

# 防御性行业
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]

def load_data():
    """加载K线和指数数据"""
    print("加载数据...")
    
    # K线
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    with open(kline_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    kline = {}
    skipped = 0
    for code, data in raw.items():
        # K线数据可能是列表或字典格式
        if isinstance(data, list):
            # 列表格式: [{date, open, high, low, close, volume}, ...]
            rows = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    date_val = item.get('date', '')
                    close_val = float(item.get('close', 0))
                    if close_val <= 0:
                        continue
                    rows.append({
                        'date': pd.Timestamp(date_val),
                        'open': float(item.get('open', 0)),
                        'high': float(item.get('high', 0)),
                        'low': float(item.get('low', 0)),
                        'close': close_val,
                        'volume': float(item.get('volume', 0)),
                    })
                except:
                    continue
            if len(rows) >= 40:
                df = pd.DataFrame(rows).sort_values('date')
                kline[code] = df
            else:
                skipped += 1
        elif isinstance(data, dict) and 'daily_data' in data:
            records = data['daily_data']
            if len(records) < 2:
                skipped += 1
                continue
            rows = []
            for d, v in records.items():
                if not isinstance(v, dict):
                    continue
                rows.append({
                    'date': pd.Timestamp(d),
                    'open': float(v.get('open', 0)),
                    'high': float(v.get('high', 0)),
                    'low': float(v.get('low', 0)),
                    'close': float(v.get('close', 0)),
                    'volume': float(v.get('volume', 0)),
                })
            if rows:
                df = pd.DataFrame(rows).sort_values('date')
                df = df[df['close'] > 0].copy()
                if len(df) >= 40:
                    kline[code] = df
                else:
                    skipped += 1
        else:
            skipped += 1
    
    # 指数
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    with open(idx_file, 'r', encoding='utf-8') as f:
        idx_raw = json.load(f)
    
    # 指数数据是列式存储，需要转置
    if isinstance(idx_raw, dict) and 'date' in idx_raw:
        n_rows = len(idx_raw['date'])
        idx_rows = []
        for i in range(n_rows):
            row = {}
            for col in idx_raw:
                row[col] = idx_raw[col].get(str(i), idx_raw[col].get(i, ''))
            idx_rows.append(row)
        index_df = pd.DataFrame(idx_rows)
        index_df['date'] = pd.to_datetime(index_df['date'])
        index_df = index_df.sort_values('date').reset_index(drop=True)
    else:
        index_df = pd.DataFrame(idx_raw)
        index_df['date'] = pd.to_datetime(index_df['date'])
    
    # 评分
    score_files = [
        os.path.join(DATA_DIR, 'batch_stock_scores_2805.json'),
        os.path.join(DATA_DIR, 'batch_stock_scores_none.json'),
    ]
    scores = {}
    for sf in score_files:
        if os.path.exists(sf):
            with open(sf, 'r', encoding='utf-8') as f:
                scores.update(json.load(f))
    
    print(f"  K线: {len(kline)} 只 (跳过 {skipped})")
    print(f"  指数: {len(index_df)} 天")
    print(f"  评分: {len(scores)} 只")
    
    return kline, index_df, scores

def calc_features(df, test_date):
    """计算技术特征"""
    hist = df[df['date'] < test_date]
    if len(hist) < 30:
        return None
    
    closes = hist['close'].values
    volumes = hist['volume'].values
    n = len(closes)
    
    # 基本收益率
    ret_5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret_10 = (closes[-1] - closes[-11]) / closes[-11] * 100 if n >= 11 else 0
    ret_20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    
    # 波动率
    daily_rets = np.diff(closes[-21:]) / closes[-21:-1] if n >= 21 else np.array([0])
    vol_20 = np.std(daily_rets) * 100 if len(daily_rets) > 1 else 2.0
    
    # RSI
    diffs = np.diff(closes[-21:]) if n >= 21 else np.array([0])
    gains = np.where(diffs > 0, diffs, 0)
    losses = np.where(diffs < 0, -diffs, 0)
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
    rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 50
    
    # 均线
    ma5 = np.mean(closes[-5:]) if n >= 5 else closes[-1]
    ma10 = np.mean(closes[-10:]) if n >= 10 else closes[-1]
    ma20 = np.mean(closes[-20:]) if n >= 20 else closes[-1]
    
    # 量比
    vol_ma5 = np.mean(volumes[-5:]) if n >= 5 else volumes[-1]
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 > 0 else 1.0
    
    return {
        'ret_5d': ret_5,
        'ret_10d': ret_10,
        'ret_20d': ret_20,
        'vol_20d': vol_20,
        'rsi_14': rsi,
        'ma5_above_ma10': 1 if ma5 > ma10 else 0,
        'ma5_above_ma20': 1 if ma5 > ma20 else 0,
        'ma10_above_ma20': 1 if ma10 > ma20 else 0,
        'price_above_ma5': 1 if closes[-1] > ma5 else 0,
        'price_above_ma20': 1 if closes[-1] > ma20 else 0,
        'vol_ratio': vol_ratio,
        'close': closes[-1],
    }

def detect_market_state(index_df, test_date):
    """检测市场状态"""
    hist = index_df[index_df['date'] < test_date]
    if len(hist) < 30:
        return 'unknown', 0, 'normal', 3
    
    closes = hist['close'].values
    n = len(closes)
    
    # 动量
    momentum = (closes[-1] - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    
    # 波动率
    daily_rets = np.diff(closes[-21:]) / closes[-21:-1] if n >= 21 else np.array([0])
    vol = np.std(daily_rets) * 100 if len(daily_rets) > 1 else 1.0
    
    # 市场状态
    if momentum > 3:
        regime = 'bull'
    elif momentum < -3:
        regime = 'bear'
    else:
        regime = 'range'
    
    # 风险等级
    if vol > 2.0:
        vol_state = 'high'
    elif vol > 1.0:
        vol_state = 'normal'
    else:
        vol_state = 'low'
    
    if regime == 'bear' and vol > 1.5:
        risk = 5
    elif regime == 'bear':
        risk = 4
    elif regime == 'range' and vol > 1.5:
        risk = 4
    elif regime == 'range':
        risk = 3
    elif vol > 1.5:
        risk = 3
    else:
        risk = 2
    
    return regime, momentum, vol_state, risk

def score_stock_v9d(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level):
    """V9d评分函数 - 简化版"""
    if features is None:
        return -999, 'none'
    
    f = features
    score = 5.0
    strategy = 'balanced'
    
    # 动量评分
    if f['ret_5d'] > 3:
        score += 1.5
    elif f['ret_5d'] > 1:
        score += 0.8
    elif f['ret_5d'] < -3:
        score -= 1.5
    elif f['ret_5d'] < -1:
        score -= 0.8
    
    # RSI评分
    if 40 < f['rsi_14'] < 70:
        score += 0.5
    elif f['rsi_14'] > 80:
        score -= 1.0
    elif f['rsi_14'] < 20:
        score += 0.3  # 超卖反弹
    
    # 均线排列
    if f['ma5_above_ma10'] and f['ma10_above_ma20']:
        score += 1.0
    elif not f['ma5_above_ma10'] and not f['ma10_above_ma20']:
        score -= 0.5
    
    # 波动率
    if f['vol_20d'] > 4.0:
        score -= 0.5
    elif f['vol_20d'] < 1.5:
        score += 0.3
    
    # 追高过滤
    if f['ret_5d'] > 8:
        score -= 2.0
    if f['ret_10d'] > 15:
        score -= 1.5
    
    # 市场状态调整
    if risk_level >= 4:
        score = score * 0.8
        if f['vol_20d'] > 3.0:
            score -= 1.0
    elif risk_level <= 2:
        if f['ret_5d'] > 2:
            score += 0.5
    
    return round(score, 2), strategy

def analyze_failures():
    """分析失败案例"""
    kline, index_df, scores = load_data()
    
    # 获取有效交易日
    date_range = pd.date_range(EVAL_START, EVAL_END, freq='B')
    valid_dates = []
    for d in date_range:
        if d in index_df['date'].values:
            valid_dates.append(d)
    
    print(f"\n回测区间: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} 天)")
    print("=" * 80)
    
    stock_recent_perf = defaultdict(list)
    results = []
    
    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        
        # 板块平均
        sector_heat = defaultdict(list)
        for code, df in kline.items():
            static = scores.get(code)
            if static:
                industry = static.get('industry', 'unknown')
                hist = df[df['date'] < test_date]
                if len(hist) >= 4:
                    c = hist['close'].values
                    sector_heat[industry].append((c[-1] - c[-4]) / c[-4] * 100)
        sector_avg = {k: np.mean(v) for k, v in sector_heat.items() if len(v) >= 3}
        
        # 评分
        scored = []
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0:
                continue
            feats = calc_features(df, test_date)
            if feats is None:
                continue
            
            score, strategy = score_stock_v9d(
                feats, scores.get(code), sector_avg, regime, momentum, vol_state, risk
            )
            if score == -999:
                continue
            
            static = scores.get(code, {})
            industry = static.get('industry', 'unknown')
            scored.append({
                'code': code,
                'name': static.get('name', ''),
                'score': score,
                'industry': industry,
                'strategy': strategy,
                'features': feats,
            })
        
        # Blacklist
        blacklist = set()
        for code, rets in stock_recent_perf.items():
            if len(rets) >= 1 and rets[-1] < -3:
                blacklist.add(code)
            if risk >= 4 and len(rets) >= 1 and rets[-1] > 6:
                blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        # 行业分散选择
        selected = []
        ind_count = defaultdict(int)
        actual_n = 2 if risk >= 5 else 3 if risk >= 4 else 5 if risk == 3 else 4 if risk <= 1 else 3
        
        for s in scored:
            if len(selected) >= actual_n:
                break
            if s['code'] in blacklist:
                continue
            ind = s['industry']
            if ind_count[ind] >= MAX_INDUSTRY:
                continue
            if risk >= 4 and s['score'] < 0.3:
                continue
            if risk == 3 and s['score'] < 0.3:
                continue
            if risk < 3 and s['score'] < 0.5:
                continue
            selected.append(s)
            ind_count[ind] += 1
        
        if not selected:
            non_bl = [s for s in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk >= 4 or risk == 3 else 2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected:
            continue
        
        # 指数收益
        idx_hist = index_df[index_df['date'] < test_date]
        idx_day = index_df[index_df['date'] >= test_date]
        if len(idx_hist) == 0 or len(idx_day) == 0:
            continue
        idx_ret = (float(idx_day.iloc[0]['close']) - float(idx_hist.iloc[-1]['close'])) / float(idx_hist.iloc[-1]['close']) * 100
        
        # 股票收益
        stock_rets = []
        for s in selected:
            code = s['code']
            s_hist = kline[code][kline[code]['date'] < test_date]
            s_day = kline[code][kline[code]['date'] >= test_date]
            if len(s_hist) > 0 and len(s_day) > 0:
                sr = (float(s_day.iloc[0]['close']) - float(s_hist.iloc[-1]['close'])) / float(s_hist.iloc[-1]['close']) * 100
                stock_rets.append({
                    'code': code,
                    'name': s['name'],
                    'ret': sr,
                    'score': s['score'],
                    'industry': s['industry'],
                    'features': s['features'],
                })
                stock_recent_perf[code].append(sr)
                if len(stock_recent_perf[code]) > 3:
                    stock_recent_perf[code] = stock_recent_perf[code][-3:]
        
        if stock_rets:
            avg_ret = np.mean([r['ret'] for r in stock_rets])
            beat = avg_ret > idx_ret
            
            results.append({
                'date': str(test_date.date()),
                'idx_ret': round(idx_ret, 2),
                'avg_ret': round(avg_ret, 2),
                'excess': round(avg_ret - idx_ret, 2),
                'beat': beat,
                'risk': risk,
                'regime': regime,
                'momentum': round(momentum, 2),
                'vol_state': vol_state,
                'n_selected': len(stock_rets),
                'stocks': stock_rets,
            })
    
    # 分析失败案例
    failures = [r for r in results if not r['beat']]
    wins = [r for r in results if r['beat']]
    
    print(f"\n总天数: {len(results)}")
    print(f"胜天数: {len(wins)} ({len(wins)/len(results)*100:.1f}%)")
    print(f"败天数: {len(failures)} ({len(failures)/len(results)*100:.1f}%)")
    
    print("\n" + "=" * 80)
    print("失败案例分析 (按风险等级)")
    print("=" * 80)
    
    # 按风险等级统计
    risk_stats = defaultdict(lambda: {'total': 0, 'fail': 0})
    for r in results:
        risk_stats[r['risk']]['total'] += 1
        if not r['beat']:
            risk_stats[r['risk']]['fail'] += 1
    
    for risk in sorted(risk_stats.keys()):
        s = risk_stats[risk]
        print(f"  风险{risk}: {s['total']}天, 失败{s['fail']}天 ({s['fail']/s['total']*100:.0f}%)")
    
    print("\n" + "=" * 80)
    print("失败日详情")
    print("=" * 80)
    
    for f in failures:
        print(f"\n日期: {f['date']} | 风险:{f['risk']} | 市场:{f['regime']} | 动量:{f['momentum']}% | 波动:{f['vol_state']}")
        print(f"  指数: {f['idx_ret']:.2f}% | 组合: {f['avg_ret']:.2f}% | 超额: {f['excess']:.2f}%")
        for s in f['stocks']:
            feat = s['features']
            print(f"  {s['name']}({s['code']}): {s['ret']:.2f}% | 评分:{s['score']} | 5日涨:{feat['ret_5d']:.1f}% | RSI:{feat['rsi_14']:.0f} | 量比:{feat['vol_ratio']:.1f} | 行业:{s['industry']}")
    
    # 失败模式分析
    print("\n" + "=" * 80)
    print("失败模式统计")
    print("=" * 80)
    
    # 失败天的市场特征
    fail_momentum = [f['momentum'] for f in failures]
    fail_vol = [f['vol_state'] for f in failures]
    fail_regime = [f['regime'] for f in failures]
    fail_idx_ret = [f['idx_ret'] for f in failures]
    
    print(f"失败天动量均值: {np.mean(fail_momentum):.2f}%")
    print(f"失败天动量范围: {min(fail_momentum):.2f}% ~ {max(fail_momentum):.2f}%")
    print(f"失败天指数收益均值: {np.mean(fail_idx_ret):.2f}%")
    print(f"失败天市场状态分布: {dict(pd.Series(fail_regime).value_counts())}")
    print(f"失败天波动率分布: {dict(pd.Series(fail_vol).value_counts())}")
    
    # 失败天选股特征
    fail_stock_features = defaultdict(list)
    for f in failures:
        for s in f['stocks']:
            fail_stock_features['ret_5d'].append(s['features']['ret_5d'])
            fail_stock_features['rsi'].append(s['features']['rsi_14'])
            fail_stock_features['vol'].append(s['features']['vol_20d'])
            fail_stock_features['vol_ratio'].append(s['features']['vol_ratio'])
            fail_stock_features['score'].append(s['score'])
    
    print(f"\n失败天选股特征均值:")
    for k, v in fail_stock_features.items():
        print(f"  {k}: {np.mean(v):.2f} (std: {np.std(v):.2f})")
    
    # 成功天选股特征对比
    win_stock_features = defaultdict(list)
    for w in wins:
        for s in w['stocks']:
            win_stock_features['ret_5d'].append(s['features']['ret_5d'])
            win_stock_features['rsi'].append(s['features']['rsi_14'])
            win_stock_features['vol'].append(s['features']['vol_20d'])
            win_stock_features['vol_ratio'].append(s['features']['vol_ratio'])
            win_stock_features['score'].append(s['score'])
    
    print(f"\n成功天选股特征均值:")
    for k, v in win_stock_features.items():
        print(f"  {k}: {np.mean(v):.2f} (std: {np.std(v):.2f})")
    
    # 差异分析
    print(f"\n成功 vs 失败 差异:")
    for k in fail_stock_features.keys():
        diff = np.mean(win_stock_features[k]) - np.mean(fail_stock_features[k])
        print(f"  {k}: {diff:+.2f} (成功 - 失败)")
    
    # 保存结果
    result_file = os.path.join(BASE_DIR, 'backtest_results', f'failure_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(result_file, 'w', encoding='utf-8') as f_out:
        json.dump({
            'summary': {
                'total_days': len(results),
                'win_days': len(wins),
                'fail_days': len(failures),
                'win_rate': len(wins)/len(results)*100,
            },
            'risk_stats': {str(k): v for k, v in risk_stats.items()},
            'failures': failures,
            'fail_stock_features': {k: [round(x, 2) for x in v] for k, v in fail_stock_features.items()},
            'win_stock_features': {k: [round(x, 2) for x in v] for k, v in win_stock_features.items()},
        }, f_out, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n结果已保存: {result_file}")

if __name__ == '__main__':
    analyze_failures()

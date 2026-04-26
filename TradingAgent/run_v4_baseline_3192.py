#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run V4 baseline with expanded 3192-stock dataset
Compares with original 899-stock results
"""

import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
import glob

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

# Data starts 2026-01-05, so we have ~34 trading days before 2026-02-20 for features
EVAL_START = '2026-02-20'
EVAL_END = '2026-04-24'   # extended from 2026-04-07 (old data limit)
TOP_N = 3
MAX_INDUSTRY = 2


def load_data():
    print("[1/3] Loading data...")

    # New full dataset
    kline_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
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
    print(f"  K-line: {len(kline)} stocks")

    # Index
    idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)

    n = len(raw_idx['date'])
    idx_records = []
    for i in range(n):
        key = str(i)
        try:
            ts = raw_idx['date'][key]
            if isinstance(ts, (int, float)):
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d')
            else:
                ds = str(ts)
            idx_records.append({'date': ds, 'close': float(raw_idx['close'][key])})
        except:
            continue
    index_df = pd.DataFrame(idx_records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    print(f"  Index: {len(index_df)} days, {index_df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {index_df['date'].iloc[-1].strftime('%Y-%m-%d')}")

    # Scores (same as V4)
    sf = sorted(glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')))
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
    print(f"  Scores: {len(scores)} stocks (with static scores)")
    print(f"  Stocks WITHOUT scores: {len(kline) - len(scores)}")

    # Sector avg
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change', 0))
    sector_avg = {ind: np.mean([v for v in vals if v is not None and not np.isnan(v)])
                  for ind, vals in sector_perf.items()}

    return kline, index_df, scores, sector_avg


# ============================================================
# V4 feature calc (identical to backtest_v4.py)
# ============================================================
def calc_features(df, target_date):
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 20:
        return None

    c = hist['close'].values
    v = hist['volume'].values
    h = hist['high'].values if 'high' in hist.columns else c
    lo = hist['low'].values if 'low' in hist.columns else c
    turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
    pct = hist['pctChg'].values if 'pctChg' in hist.columns else np.zeros(len(c))

    n = len(c)
    f = {}

    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0

    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10

    f['close_ma5'] = c[-1] / ma5 - 1
    f['close_ma10'] = c[-1] / ma10 - 1
    f['close_ma20'] = c[-1] / ma20 - 1
    f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    f['ma10_slope'] = (ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1]) if n >= 11 else 0
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)

    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    f['rsi'] = 100 - 100 / (1 + np.mean(gains) / max(np.mean(losses), 0.01))

    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0

    if n >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        f['vol5'] = np.std(rets) * 100
    else:
        f['vol5'] = 0
    if n >= 11:
        rets10 = np.diff(c[-11:]) / c[-11:-1]
        f['vol10'] = np.std(rets10) * 100
    else:
        f['vol10'] = f.get('vol5', 0)

    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0
    f['vol_trend'] = (v[-1] - np.mean(v[-5:])) / max(np.mean(v[-5:]), 1) if n >= 5 else 0

    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_ratio'] = turn5 / max(turn10, 0.01)
        f['turn_avg'] = turn5
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_ratio'] = 1.0
        f['turn_avg'] = 0
        f['turn_spike'] = 1.0

    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100

    if n >= 6:
        trs = []
        for i in range(-min(14, n-1), 0):
            tr = max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1]))
            trs.append(tr)
        f['atr_pct'] = np.mean(trs) / c[-1] * 100
    else:
        f['atr_pct'] = 0

    streak = 0
    for i in range(n-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak

    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0

    if n >= 3 and not np.all(pct == 0):
        f['pct_1d'] = float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum'] = float(np.nansum(pct[-3:]))
        f['pct_5d_sum'] = float(np.nansum(pct[-5:])) if n >= 5 else f['pct_3d_sum']
    else:
        f['pct_1d'] = f['r1']
        f['pct_3d_sum'] = f['r3']
        f['pct_5d_sum'] = f['r5']

    if n >= 10:
        peak = c[-10]; max_dd = 0
        for i in range(-9, 1):
            if c[i] > peak: peak = c[i]
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd: max_dd = dd
        f['max_dd_10d'] = max_dd
    else:
        f['max_dd_10d'] = 0

    f['dist_support'] = (c[-1] - np.min(c[-w20:])) / c[-1] * 100

    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0

    return f


# ============================================================
# V4 market state detection (identical)
# ============================================================
DEFENSIVE_KEYWORDS = ['电力','水务','燃气','公用','银行','医药','食品','饮料','高速公路','港口','机场','交通','通信','电信']
HIGH_BETA_KEYWORDS = ['半导体','芯片','新能源','光伏','锂电','军工','证券','保险','房地产','钢铁','煤炭','有色']

def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)

def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)

def detect_market_state(index_df, date):
    hist = index_df[index_df['date'] < date].copy()
    if len(hist) < 20:
        return 'range', 0, 'normal', 3
    closes = hist['close'].values
    n = len(closes)
    ma20 = np.mean(closes[-20:])
    ma5 = np.mean(closes[-5:])
    current = closes[-1]
    if current > ma20 * 1.02 and ma5 > ma20: regime = 'bull'
    elif current < ma20 * 0.98 and ma5 < ma20: regime = 'bear'
    else: regime = 'range'
    ret5 = (current - closes[-6]) / closes[-6] * 100 if n >= 6 else 0
    ret20 = (current - closes[-21]) / closes[-21] * 100 if n >= 21 else 0
    momentum = ret5 * 0.6 + ret20 * 0.4
    if n >= 10:
        idx_vol = np.std(np.diff(closes[-10:]) / closes[-10:-1] * 100)
        vol_state = 'high' if idx_vol > 1.5 else ('normal' if idx_vol > 0.8 else 'low')
    else:
        vol_state = 'normal'
    risk = 3
    consec = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] < closes[i-1]: consec += 1
        else: break
    if consec >= 4: risk = 5
    elif consec >= 3: risk = 4
    elif regime == 'bear' and vol_state == 'high': risk = 5
    elif regime == 'bear': risk = 4
    elif regime == 'bull' and vol_state == 'high': risk = 3
    elif regime == 'bull': risk = 2
    elif vol_state == 'high': risk = 4
    if n >= 2:
        lr = (closes[-1] - closes[-2]) / closes[-2] * 100
        if lr < -2: risk = min(risk + 1, 5)
        elif lr > 2: risk = max(risk - 1, 1)
    return regime, momentum, vol_state, risk


# ============================================================
# V4 scoring (identical)
# ============================================================
def score_stock_v4(features, static_scores, sector_avg, regime, momentum, vol_state, risk_level):
    if features is None:
        return -999, 'filtered'
    f = features
    if f.get('pct_1d', 0) > 9.5 or f.get('pct_1d', 0) < -9.5:
        return -999, 'limit'

    static_score = 0
    if static_scores:
        tech = max(static_scores.get('tech', 5), 0)
        fund = max(static_scores.get('fund', 5), 0)
        chip = max(static_scores.get('chip', 5), 0)
        sector = max(static_scores.get('sector', 5), 0)
        static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sector * 0.15) / 10 * 5

    momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
    trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
    mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5
    vr = f.get('vol_ratio', 1)
    vol_s = 3 if 1.1 <= vr <= 2.0 else (1 if vr > 2.0 else 2)
    rsi = f.get('rsi', 50)
    rsi_s = 3 if 40 <= rsi <= 60 else (4 if 30 <= rsi < 40 else (2 if 60 < rsi <= 70 else 1))
    vol5 = f.get('vol5', 2)
    low_vol_s = 4 if vol5 < 1.5 else (3 if vol5 < 2.5 else (2 if vol5 < 3.5 else 1))
    defense_s = 0
    industry = static_scores.get('industry', 'unknown') if static_scores else 'unknown'
    if is_defensive_industry(industry): defense_s += 3
    if is_high_beta_industry(industry): defense_s -= 2
    defense_s += low_vol_s
    rel_strength = f.get('rel_strength_5d', 0)
    rel_strength_3d = f.get('rel_strength_3d', 0)
    beta = f.get('beta_20d', 1.0)
    max_dd = f.get('max_dd_10d', 0)
    if max_dd < -15: defense_s -= 3
    elif max_dd < -10: defense_s -= 1
    sector_heat = sector_avg.get(industry, 0) * 0.1

    if risk_level >= 4:
        score = (
            momentum_s * 0.02 + trend_s * 0.03 + mr_s * 0.10 + vol_s * 0.03 +
            rsi_s * 0.10 + static_score * 0.15 + defense_s * 0.12 + sector_heat * 0.03 +
            low_vol_s * 0.05 + rel_strength * 0.15 + rel_strength_3d * 0.10 +
            (2.0 - min(beta, 2.0)) * 0.12
        )
        if beta > 1.5: score *= 0.4
        elif beta > 1.2: score *= 0.7
        elif beta < 0.5: score *= 1.3
        if f.get('oversold', 0): score *= 1.15
        if f.get('overbought', 0): score *= 0.3
        if is_high_beta_industry(industry): score *= 0.4
        if is_defensive_industry(industry): score *= 1.25
        if rel_strength > 3: score *= 1.3
        if vol5 < 1.5: score *= 1.2
        if f.get('r1', 0) < -5: score *= 0.3
        if f.get('r3', 0) < -8: score *= 0.3
        if f.get('pct_1d', 0) > 7: score *= 0.3
        strategy = 'defense'
    elif risk_level == 3:
        score = (
            momentum_s * 0.12 + trend_s * 0.12 + mr_s * 0.15 + vol_s * 0.08 +
            rsi_s * 0.10 + static_score * 0.18 + defense_s * 0.08 + sector_heat * 0.10 +
            low_vol_s * 0.07
        )
        if f.get('oversold', 0): score *= 1.15
        if f.get('overbought', 0): score *= 0.7
        strategy = 'balanced'
    else:
        score = (
            momentum_s * 0.25 + trend_s * 0.20 + mr_s * 0.05 + vol_s * 0.10 +
            rsi_s * 0.05 + static_score * 0.15 + defense_s * 0.05 + sector_heat * 0.10 +
            low_vol_s * 0.05
        )
        if f['r1'] > 5: score *= 0.5
        if f.get('overbought', 0): score *= 0.8
        strategy = 'momentum'
    return score, strategy


def get_adaptive_top_n(risk_level, base_n=3):
    if risk_level >= 5: return max(1, base_n - 2)
    elif risk_level >= 4: return max(2, base_n - 1)
    elif risk_level <= 1: return base_n + 1
    else: return base_n


def get_stock_return(df, date):
    prev = df[df['date'] < date]; day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0: return None
    try: return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except: return None

def get_index_return(index_df, date):
    prev = index_df[index_df['date'] < date]; day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0: return None
    try: return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except: return None


def run_backtest(kline, index_df, scores, sector_avg, top_n=TOP_N, adaptive_n=True, label=''):
    eval_start = pd.to_datetime(EVAL_START)
    eval_end = pd.to_datetime(EVAL_END)
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = [d for d in date_range if get_index_return(index_df, d) is not None]

    print(f"\n  [{label}] Eval: {EVAL_START} ~ {EVAL_END} ({len(valid_dates)} days)")
    print(f"  [{label}] Pool: {len(kline)} stocks, Top-N: {top_n} (adaptive: {adaptive_n})")

    results = []
    wins = 0; total = 0
    stats_by_risk = defaultdict(lambda: {'wins': 0, 'total': 0, 'beat_idx': 0})
    stock_recent_perf = defaultdict(list)

    for test_date in valid_dates:
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        actual_n = get_adaptive_top_n(risk, top_n) if adaptive_n else top_n

        idx_hist = index_df[index_df['date'] < test_date]
        idx_closes = idx_hist['close'].values
        idx_n = len(idx_closes)
        idx_rets_20 = np.diff(idx_closes[-21:]) / idx_closes[-22:-21] * 100 if idx_n >= 22 else None
        idx_ret_5d = (idx_closes[-1] - idx_closes[-6]) / idx_closes[-6] * 100 if idx_n >= 6 else 0
        idx_ret_3d = (idx_closes[-1] - idx_closes[-4]) / idx_closes[-4] * 100 if idx_n >= 4 else 0

        scored = []
        for code, df in kline.items():
            if len(df[df['date'] >= test_date]) == 0: continue
            feats = calc_features(df, test_date)
            if feats is None: continue
            s_closes = df[df['date'] < test_date]['close'].values
            s_n = len(s_closes)
            if idx_rets_20 is not None and s_n >= 22:
                s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
                sr_len = min(len(s_rets_20), len(idx_rets_20))
                if sr_len >= 10:
                    s_r = s_rets_20[-sr_len:]; i_r = idx_rets_20[-sr_len:]
                    idx_var = np.var(i_r)
                    if idx_var > 0.001:
                        feats['beta_20d'] = np.cov(s_r, i_r)[0, 1] / idx_var
            if s_n >= 6:
                feats['rel_strength_5d'] = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100 - idx_ret_5d
            if s_n >= 4:
                feats['rel_strength_3d'] = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100 - idx_ret_3d

            static = scores.get(code, None)
            score, strategy = score_stock_v4(feats, static, sector_avg, regime, momentum, vol_state, risk)
            if score == -999: continue
            industry = static.get('industry', 'unknown') if static else 'unknown'
            scored.append({'code': code, 'name': static.get('name', '') if static else '',
                          'score': score, 'industry': industry, 'strategy': strategy})

        # Blacklist
        blacklist = set()
        for code, rets in stock_recent_perf.items():
            if len(rets) >= 1:
                if rets[-1] < -3: blacklist.add(code)
                if risk >= 4 and rets[-1] > 6: blacklist.add(code)
            if len(rets) >= 2 and rets[-1] < 0 and rets[-2] < 0:
                blacklist.add(code)

        scored.sort(key=lambda x: x['score'], reverse=True)
        selected = []
        ind_count = defaultdict(int)
        for s in scored:
            if len(selected) >= actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']] >= MAX_INDUSTRY: continue
            if risk >= 4 and s['score'] < 0.3: continue
            if risk < 3 and s['score'] < 0.5: continue
            selected.append(s)
            ind_count[s['industry']] += 1

        if not selected:
            non_bl = [s for s in scored if s['code'] not in blacklist]
            selected = non_bl[:min(2, len(non_bl))]
        if not selected:
            selected = scored[:min(2, len(scored))]
        if not selected: continue

        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None: idx_ret = 0
        daily_wins = 0
        stock_rets = []
        for s in selected:
            sr = get_stock_return(kline[s['code']], test_date)
            if sr is not None:
                beat = sr > idx_ret
                stock_rets.append({'code': s['code'], 'name': s['name'], 'ret': round(sr, 2),
                                  'beat': beat, 'score': round(s['score'], 2), 'strategy': s['strategy']})
                if beat: daily_wins += 1

        for s in stock_rets:
            stock_recent_perf[s['code']].append(s['ret'])
            if len(stock_recent_perf[s['code']]) > 3:
                stock_recent_perf[s['code']] = stock_recent_perf[s['code']][-3:]

        if stock_rets:
            total += 1
            wr = daily_wins / len(stock_rets)
            is_win = wr > 0.5
            if is_win: wins += 1
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            results.append({'date': test_date.strftime('%Y-%m-%d'), 'regime': regime, 'risk': risk,
                          'vol_state': vol_state, 'n_stocks': len(stock_rets), 'stocks': stock_rets,
                          'idx_ret': round(idx_ret, 2), 'avg_ret': round(avg_ret, 2),
                          'wr': round(wr, 2), 'win': is_win, 'beat_idx': beat_idx})
            stats_by_risk[risk]['total'] += 1
            if is_win: stats_by_risk[risk]['wins'] += 1
            if beat_idx: stats_by_risk[risk]['beat_idx'] += 1
            tag = 'W' if is_win else 'L'
            bi = chr(8593) if beat_idx else chr(8595)
            print(f"  [{test_date.strftime('%m-%d')}] {tag}[{bi}IDX] avg={avg_ret:+.2f}% idx={idx_ret:+.2f}% "
                  f"wr={wr*100:.0f}% R{risk} [{regime[:4]}] n={len(stock_rets)}")

    accuracy = wins / total if total > 0 else 0
    beat_days = sum(1 for r in results if r['beat_idx'])
    print(f"\n  [{label}] RESULT: {wins}/{total} = {accuracy*100:.1f}% win, {beat_days}/{total} = {beat_days/total*100:.1f}% beat_idx")
    for r in sorted(stats_by_risk.keys()):
        s = stats_by_risk[r]
        print(f"    R{r}: {s['wins']}/{s['total']} win={s['wins']/s['total']*100:.0f}% bi={s['beat_idx']/s['total']*100:.0f}%")
    return {'accuracy': accuracy, 'beat_days': beat_days, 'total': total,
            'beat_pct': beat_days/total if total > 0 else 0, 'results': results,
            'stats_by_risk': {str(k): v for k, v in stats_by_risk.items()}}


def save_report(results_all, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [f"{'='*60}", "V4 Baseline with 3192 Stocks (Expanded Pool)", f"{'='*60}",
             f"Data: kline_full_latest.json (3192 stocks) + index_full_latest.json",
             f"Eval: {EVAL_START} ~ {EVAL_END}", ""]

    for label, result in results_all:
        bi = result['beat_days']
        t = result['total']
        lines.append(f"\n--- {label} ---")
        lines.append(f"Beat Index: {bi}/{t} = {bi/t*100:.1f}%" if t > 0 else "No data")
        lines.append(f"Win Rate:   {result['accuracy']*100:.1f}%")
        for r in sorted(result['stats_by_risk'].keys()):
            s = result['stats_by_risk'][r]
            if s['total'] > 0:
                lines.append(f"  R{r}: win={s['wins']/s['total']*100:.0f}% bi={s['beat_idx']/s['total']*100:.0f}% ({s['total']} days)")

        lines.append(f"\n  Daily Details ({label}):")
        for d in result['results']:
            tag = 'W' if d['win'] else 'L'
            bia = chr(8593) + 'IDX' if d['beat_idx'] else chr(8595) + 'IDX'
            lines.append(f"  {d['date']} [{tag}][{bia}] avg={d['avg_ret']:+.2f}% idx={d['idx_ret']:+.2f}% "
                         f"wr={d['wr']*100:.0f}% R{d['risk']} [{d['regime'][:4]}] n={d['n_stocks']}")
            for s in d['stocks']:
                b = 'V' if s['beat'] else 'X'
                lines.append(f"    {s['code']} {s['name']}: {s['ret']:+.2f}% [{b}] ({s['strategy']})")

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\nReport saved: {path}")


if __name__ == '__main__':
    t0 = time.time()
    print(f"{'='*60}\nV4 Baseline - 3192 Stock Pool Test\n{'='*60}")
    kline, index_df, scores, sector_avg = load_data()

    # Run V4 with 3 configs (same as original)
    results_all = []

    print("\n[2/4] V4 Adaptive (R5=1, R4=2, R3=3)...")
    r1 = run_backtest(kline, index_df, scores, sector_avg, top_n=3, adaptive_n=True, label='adaptive')
    results_all.append(('adaptive', r1))

    print("\n[3/4] V4 Fixed top3...")
    r2 = run_backtest(kline, index_df, scores, sector_avg, top_n=3, adaptive_n=False, label='fixed3')
    results_all.append(('fixed3', r2))

    print("\n[4/4] V4 Fixed top5...")
    r3 = run_backtest(kline, index_df, scores, sector_avg, top_n=5, adaptive_n=False, label='fixed5')
    results_all.append(('fixed5', r3))

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: V4 Baseline with 3192 stocks")
    print(f"Eval: {EVAL_START} ~ {EVAL_END}")
    print(f"{'='*60}")
    best_label, best = max(results_all, key=lambda x: x[1]['beat_pct'])
    for label, r in results_all:
        tag = ' <-- BEST' if label == best_label else ''
        print(f"  {label:10s}: beat_idx={r['beat_pct']*100:.1f}% ({r['beat_days']}/{r['total']}), "
              f"win={r['accuracy']*100:.1f}%{tag}")
    print(f"\n  Previous result (899 stocks): 66.7% beat_idx (22/33)")
    print(f"  Improvement: {'YES' if best['beat_pct'] > 0.667 else 'NO'} "
          f"({best['beat_pct']*100:.1f}% vs 66.7%)")

    # Save report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(RESULT_DIR, f'backtest_v4_3192_{ts}.txt')
    save_report(results_all, report_path)

    # Save JSON summary
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v4_baseline_3192',
        'stock_pool': 3192,
        'eval_start': EVAL_START,
        'eval_end': EVAL_END,
        'results': {label: {'accuracy': r['accuracy'], 'beat_pct': r['beat_pct'],
                            'beat_days': r['beat_days'], 'total': r['total']}
                   for label, r in results_all},
        'best': best_label,
        'comparison': {'old_pool': 899, 'old_beat_idx': 0.667}
    }
    fp = os.path.join(RESULT_DIR, f'final_result_v4_3192.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\nTime: {time.time()-t0:.0f}s")

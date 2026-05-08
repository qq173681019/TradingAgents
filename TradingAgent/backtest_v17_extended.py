#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V17 Extended Backtest - Multi-Period Validation vs V10/V14

Uses V17 Optuna-optimized params (r2/r3/r45) across extended time periods.
V17 was trained on 3 windows (A/B/C) with robust multi-period optimization.

Scoring: V17 params for ALL risk levels (r2, r3, r45).
Comparison: V10 original + V14 params for same periods.

Memory efficient: compute sub-scores on-the-fly (no precompute).
"""

import json, os, sys, time, gc, warnings, functools
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
SHARED_DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# Config
# ============================================================================
MIN_KLINE_DAYS = 40
MAX_INDUSTRY = 1
MEMORY_LIMIT_MB = 8000

# ============================================================================
# Load V17 Best Params
# ============================================================================
V17_PARAMS_FILE = os.path.join(SHARED_DATA_DIR, 'optuna_v17_best_params.json')
with open(V17_PARAMS_FILE, 'r', encoding='utf-8') as f:
    _v17 = json.load(f)
V17_R2_PARAMS = _v17['risk2_params']
V17_R3_PARAMS = _v17['risk3_params']
V17_R45_PARAMS = _v17['risk45_params']

# V14 params for comparison
V14_PARAMS = {
    'w_momentum': 0.1367368225983983,
    'w_trend': 0.09637994830301756,
    'w_consistency': 0.07239465845883288,
    'w_mr': 0.08574774661868874,
    'w_vol': 0.06881629015116482,
    'w_rsi': 0.020767455891327818,
    'w_static': 0.006128774990345904,
    'w_defense': 0.1047185559418257,
    'w_sector_heat': 0.1265592668216359,
    'w_low_vol': 0.035520741096385325,
    'w_rel_str': 0.10048010450673954,
    'w_rel_str_3d': 0.14574963462163745,
    'consistency_boost_high': 2.462901723200523,
    'consistency_boost_mid': 1.1698048442226556,
    'uptrend_boost_full': 1.7353555723902283,
    'uptrend_boost_partial': 0.9607630572681164,
    'ma20_above_mult': 1.2066113765603486,
    'ma20_below_mult': 0.5036854829973982,
    'low_vol_mult_high': 1.253243786482494,
    'low_vol_mult_mid': 0.918021431097559,
    'high_vol_penalize': 0.12550706946792134,
    'rsi_overbought_mult': 0.16802490273066453,
    'rsi_high_mult': 0.6567544068873018,
    'rsi_sweet_mult': 1.3327284601521754,
    'sector_heat_strong': 1.0231488329038572,
    'sector_heat_mild': 1.3018677990995955,
    'sector_cold': 0.021878077981025618,
    'sector_cool': 0.5007357312346158,
    'rel_str_strong': 1.897554342386533,
    'rel_str_mild': 1.268640002021058,
    'big_move5_penalize': 0.10155970323875607,
    'big_move3_penalize': 0.8884580226191793,
    'streak_penalize': 0.4538002132233489,
    'vol_shrink_penalize': 0.3220782190128671,
    'turn_spike_penalize': 0.7179315118846368,
    'ma5_below_penalize': 0.5632256989490149,
}

# ============================================================================
# Memory Monitor
# ============================================================================
def check_memory(limit_mb=MEMORY_LIMIT_MB):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if mb > limit_mb:
            gc.collect()
            print(f"  [MEM] {mb:.0f}MB over limit, GC triggered")
            return True
        return False
    except ImportError:
        return False

def print_mem(label=""):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label:
            print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError:
        pass

# ============================================================================
# Code normalization
# ============================================================================
def normalize_code(code):
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code

# ============================================================================
# Data Loading
# ============================================================================
def load_merged_kline():
    print("[1/3] Loading and merging kline data...")
    old_file = os.path.join(KLINE_CACHE, 'kline_full_20250901_20260424.json')
    new_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}

    print(f"  Loading old: {os.path.basename(old_file)} ({os.path.getsize(old_file)/1024/1024:.1f}MB)")
    with open(old_file, 'r', encoding='utf-8') as f:
        old_raw = json.load(f)
    old_data = {}
    for code, records in old_raw.items():
        old_data[normalize_code(code)] = records

    print(f"  Loading new: {os.path.basename(new_file)} ({os.path.getsize(new_file)/1024/1024:.1f}MB)")
    with open(new_file, 'r', encoding='utf-8') as f:
        new_raw = json.load(f)
    new_data = {}
    for code, records in new_raw.items():
        new_data[normalize_code(code)] = records

    del old_raw, new_raw
    gc.collect()

    print("  Merging datasets...")
    merged = {}
    all_codes = set(old_data.keys()) | set(new_data.keys())
    for code in all_codes:
        combined = []
        seen = set()
        for r in old_data.get(code, []) + new_data.get(code, []):
            d = r.get('date', '')
            if d and d not in seen:
                seen.add(d)
                combined.append({k: v for k, v in r.items() if k in NEED_COLS})
        if len(combined) < MIN_KLINE_DAYS:
            continue
        df = pd.DataFrame(combined)
        df['date'] = pd.to_datetime(df['date'], format='mixed').dt.tz_localize(None)
        df = df.sort_values('date').drop_duplicates(subset='date', keep='last')
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        merged[code] = df

    del old_data, new_data
    gc.collect()

    mins = [df['date'].min() for df in merged.values()]
    maxs = [df['date'].max() for df in merged.values()]
    print(f"  Merged: {len(merged)} stocks, {min(mins).date()} ~ {max(maxs).date()}")
    return merged

def load_index_extended():
    print("[2/3] Loading index data...")
    idx_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    if not os.path.exists(idx_file):
        idx_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    with open(idx_file, 'r', encoding='utf-8') as f:
        raw_idx = json.load(f)
    records = []
    if 'date' in raw_idx and isinstance(raw_idx['date'], dict):
        n = len(raw_idx['date'])
        for i in range(n):
            try:
                key = str(i)
                ts = raw_idx['date'].get(key)
                cl = float(raw_idx['close'].get(key, 0))
                if ts is None or cl <= 0: continue
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
                records.append({'date': ds, 'close': cl})
            except: continue
    del raw_idx; gc.collect()
    if not records:
        idx_file2 = os.path.join(KLINE_CACHE, 'index_full_latest.json')
        with open(idx_file2, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        for i in range(len(raw.get('date', {}))):
            key = str(i)
            try:
                ds = str(raw['date'][key]); cl = float(raw['close'][key])
                if ds and cl > 0: records.append({'date': ds, 'close': cl})
            except: continue
        del raw; gc.collect()
    index_df = pd.DataFrame(records)
    index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
    index_df = index_df.dropna(subset=['close']).sort_values('date')
    index_df['close'] = index_df['close'].astype('float32')
    print(f"  Index: {len(index_df)} days, {index_df['date'].min().date()} ~ {index_df['date'].max().date()}")
    return index_df

def _load_scores():
    import glob
    sf = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    if not os.path.exists(sf):
        all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
        if all_sf: sf = max(all_sf, key=lambda x: os.path.getsize(x))
    scores = {}
    if os.path.exists(sf):
        with open(sf, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            if not isinstance(s, dict): continue
            scores[normalize_code(code)] = {
                'tech': 5.0, 'fund': 5.0, 'chip': 5.0, 'sector': 5.0,
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': 0.0,
            }
    print(f"  Scores: {len(scores)} stocks")
    return scores

# ============================================================================
# Feature Engineering (identical to V17)
# ============================================================================
def calc_features(df, target_date):
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 20: return None
    c = hist['close'].values; v = hist['volume'].values
    h = hist['high'].values if 'high' in hist.columns else c
    lo = hist['low'].values if 'low' in hist.columns else c
    turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
    pct = hist['pctChg'].values if 'pctChg' in hist.columns else np.zeros(len(c))
    n = len(c); f = {}
    f['r1'] = (c[-1]-c[-2])/c[-2]*100 if n>=2 else 0
    f['r3'] = (c[-1]-c[-4])/c[-4]*100 if n>=4 else 0
    f['r5'] = (c[-1]-c[-6])/c[-6]*100 if n>=6 else 0
    f['r10'] = (c[-1]-c[-11])/c[-11]*100 if n>=11 else 0
    f['r20'] = (c[-1]-c[-21])/c[-21]*100 if n>=21 else 0
    ma5=np.mean(c[-5:]); ma10=np.mean(c[-10:]) if n>=10 else ma5; ma20=np.mean(c[-20:]) if n>=20 else ma10
    f['close_ma5']=c[-1]/ma5-1; f['close_ma10']=c[-1]/ma10-1; f['close_ma20']=c[-1]/ma20-1
    f['ma5_slope']=(ma5-np.mean(c[-6:-1]))/np.mean(c[-6:-1]) if n>=6 else 0
    f['ma10_slope']=(ma10-np.mean(c[-11:-1]))/np.mean(c[-11:-1]) if n>=11 else 0
    f['ma_bull']=int(c[-1]>ma5>ma10>ma20)
    f['ma_align']=int(ma5>ma10)+int(ma5>ma20)+int(ma10>ma20)
    w=min(14,n-1); gains=[]; losses=[]
    for i in range(-w,0):
        chg=(c[i]-c[i-1])/c[i-1]*100; gains.append(max(chg,0)); losses.append(max(-chg,0))
    ag=np.mean(gains); al=max(np.mean(losses),0.01); f['rsi']=100-100/(1+ag/al)
    if n>=26:
        ema12=ema26=c[-1]
        for i in range(-26,0):
            ema12=c[i]*(2/14)+ema12*(1-2/14); ema26=c[i]*(2/27)+ema26*(1-2/27)
        f['macd']=ema12-ema26
    else: f['macd']=0
    f['vol5']=np.std(np.diff(c[-6:])/c[-6:-1])*100 if n>=6 else 0
    f['vol10']=np.std(np.diff(c[-11:])/c[-11:-1])*100 if n>=11 else f.get('vol5',0)
    f['vol_ratio']=np.mean(v[-5:])/np.mean(v[-10:]) if n>=10 and np.mean(v[-10:])>0 else 1.0
    f['vol_trend']=(v[-1]-np.mean(v[-5:]))/max(np.mean(v[-5:]),1) if n>=5 else 0
    f['vol_shrink']=np.mean(v[-5:])/max(np.mean(v[-10:-5]),1) if n>=10 else 1.0
    if n>=10 and not np.all(turn==1):
        t5=np.nanmean(turn[-5:]); t10=np.nanmean(turn[-10:])
        f['turn_ratio']=t5/max(t10,0.01); f['turn_avg']=t5; f['turn_spike']=turn[-1]/max(t5,0.01)
    else: f['turn_ratio']=1.0; f['turn_avg']=0; f['turn_spike']=1.0
    w20=min(20,n); f['price_pos']=(c[-1]-np.min(c[-w20:]))/max(np.max(c[-w20:])-np.min(c[-w20:]),0.01)*100
    if n>=6:
        trs=[max(h[i]-lo[i],abs(h[i]-c[i-1]),abs(lo[i]-c[i-1])) for i in range(-min(14,n-1),0)]
        f['atr_pct']=np.mean(trs)/c[-1]*100
    else: f['atr_pct']=0
    streak=0
    for i in range(n-1,0,-1):
        if c[i]>c[i-1]: streak=streak+1 if streak>=0 else 1
        elif c[i]<c[i-1]: streak=streak-1 if streak<=0 else -1
        else: break
    f['streak']=streak
    f['mr_5d']=-f['r5']; f['mr_3d']=-f['r3']
    f['oversold']=1 if (f['rsi']<35 and f['r5']<-3) else 0
    f['overbought']=1 if (f['rsi']>70 and f['r5']>5) else 0
    if n>=3 and not np.all(pct==0):
        f['pct_1d']=float(pct[-1]) if not np.isnan(pct[-1]) else 0
        f['pct_3d_sum']=float(np.nansum(pct[-3:])); f['pct_5d_sum']=float(np.nansum(pct[-5:])) if n>=5 else f['pct_3d_sum']
    else: f['pct_1d']=f['r1']; f['pct_3d_sum']=f['r3']; f['pct_5d_sum']=f['r5']
    if n>=10:
        peak=c[-10]; max_dd=0
        for i in range(-9,1):
            if c[i]>peak: peak=c[i]
            dd=(c[i]-peak)/peak*100
            if dd<max_dd: max_dd=dd
        f['max_dd_10d']=max_dd
    else: f['max_dd_10d']=0
    f['dist_support']=(c[-1]-np.min(c[-w20:]))/c[-1]*100
    f['beta_20d']=1.0; f['rel_strength_5d']=0.0; f['rel_strength_3d']=0.0
    f['consistency']=0
    if n>=5:
        for i in range(-4,0):
            if c[i+1]>c[i]: f['consistency']+=1
    return f

# ============================================================================
# Market State Detection (identical to V17)
# ============================================================================
DEFENSIVE_KEYWORDS = ['电力','水务','燃气','公用','银行','医药','食品','饮料','高速公路','港口','机场','交通','通信','电信']
HIGH_BETA_KEYWORDS = ['半导体','芯片','新能源','光伏','锂电','军工','证券','保险','房地产','钢铁','煤炭','有色']

def is_defensive_industry(industry):
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)

def is_high_beta_industry(industry):
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)

def detect_market_state(index_df, date):
    hist = index_df[index_df['date'] < date].copy()
    if len(hist) < 20: return 'range', 0, 'normal', 3
    closes = hist['close'].values; n = len(closes)
    ma20=np.mean(closes[-20:]); ma5=np.mean(closes[-5:]); current=closes[-1]
    if current > ma20*1.02 and ma5 > ma20: regime='bull'
    elif current < ma20*0.98 and ma5 < ma20: regime='bear'
    else: regime='range'
    ret5=(current-closes[-6])/closes[-6]*100 if n>=6 else 0
    ret20=(current-closes[-21])/closes[-21]*100 if n>=21 else 0
    momentum=ret5*0.6+ret20*0.4
    if n>=10:
        idx_rets=np.diff(closes[-10:])/closes[-10:-1]*100; idx_vol=np.std(idx_rets)
        if idx_vol>1.5: vol_state='high'
        elif idx_vol>0.8: vol_state='normal'
        else: vol_state='low'
    else: vol_state='normal'
    risk=3
    consec=0
    for i in range(n-1,max(0,n-6),-1):
        if closes[i]<closes[i-1]: consec+=1
        else: break
    if consec>=4: risk=5
    elif consec>=3: risk=4
    elif regime=='bear' and vol_state=='high': risk=5
    elif regime=='bear': risk=4
    elif regime=='bull' and vol_state=='high': risk=3
    elif regime=='bull': risk=2
    elif vol_state=='high': risk=4
    else: risk=3
    if n>=2:
        last_ret=(closes[-1]-closes[-2])/closes[-2]*100
        if last_ret<-2: risk=min(risk+1,5)
        elif last_ret>2: risk=max(risk-1,1)
    return regime, momentum, vol_state, risk

# ============================================================================
# V17 Scoring Functions (from backtest_v17_robust.py)
# ============================================================================
def compute_stock_subscores(code, df, test_date, index_df, idx_rets_20, idx_ret_5d, idx_ret_3d, static, daily_sector_avg):
    """Compute sub-scores for a stock on a given date (identical to V17)."""
    feats = calc_features(df, test_date)
    if feats is None: return None
    
    stock_hist = df[df['date'] < test_date]
    s_closes = stock_hist['close'].values
    s_n = len(s_closes)
    
    beta = 1.0
    if idx_rets_20 is not None and s_n >= 23:
        s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
        sr_len = min(len(s_rets_20), len(idx_rets_20))
        if sr_len >= 10:
            s_r = s_rets_20[-sr_len:]; i_r = idx_rets_20[-sr_len:]
            idx_var = np.var(i_r)
            if idx_var > 0.001: beta = np.cov(s_r, i_r)[0, 1] / idx_var
    
    rel_str = (s_closes[-1]-s_closes[-6])/s_closes[-6]*100 - idx_ret_5d if s_n>=6 else 0.0
    rel_str_3d = (s_closes[-1]-s_closes[-4])/s_closes[-4]*100 - idx_ret_3d if s_n>=4 else 0.0
    
    f = feats
    if f.get('pct_1d',0) > 9.5 or f.get('pct_1d',0) < -9.5: return None
    
    momentum_s = f['r1']*0.3 + f['r3']*0.3 + f['r5']*0.4
    trend_s = f['ma_align']*2.5 + f.get('ma5_slope',0)*50 + f.get('ma10_slope',0)*30
    mr_s = f['mr_5d']*0.5 + f['mr_3d']*0.3 + f.get('oversold',0)*5 - f.get('overbought',0)*5
    
    vr = f.get('vol_ratio',1)
    if 1.1<=vr<=2.0: vol_s=3.0
    elif vr>2.0: vol_s=1.0
    else: vol_s=2.0
    
    rsi = f.get('rsi',50)
    if 40<=rsi<=60: rsi_s=3.0
    elif 30<=rsi<40: rsi_s=4.0
    elif 60<rsi<=70: rsi_s=2.0
    else: rsi_s=1.0
    
    vol5 = f.get('vol5',2)
    if vol5<1.5: low_vol_s=4.0
    elif vol5<2.5: low_vol_s=3.0
    elif vol5<3.5: low_vol_s=2.0
    else: low_vol_s=1.0
    
    industry = static.get('industry','unknown') if static else 'unknown'
    is_def = is_defensive_industry(industry)
    is_hb = is_high_beta_industry(industry)
    defense_base = 0.0
    if is_def: defense_base += 3.0
    if is_hb: defense_base -= 2.0
    max_dd = f.get('max_dd_10d',0)
    dd_pen = -3.0 if max_dd<-15 else (-1.0 if max_dd<-10 else 0.0)
    defense_s = defense_base + low_vol_s + dd_pen
    
    sector_heat = daily_sector_avg.get(industry,0) * 0.1
    ind_heat = daily_sector_avg.get(industry,0)
    consistency = f.get('consistency',0)
    consistency_s = consistency * 1.5
    
    static_score = 0.0
    if static:
        tech=max(static.get('tech',5),0); fund=max(static.get('fund',5),0)
        chip=max(static.get('chip',5),0); sec=max(static.get('sector',5),0)
        static_score = (tech*0.30+fund*0.30+chip*0.25+sec*0.15)/10*5
    
    beta_bonus = 2.0 - min(beta, 2.0)
    
    return {
        'code': code, 'industry': industry,
        'momentum_s': momentum_s, 'trend_s': trend_s, 'consistency_s': consistency_s,
        'mr_s': mr_s, 'vol_s': vol_s, 'rsi_s': rsi_s, 'static_score': static_score,
        'defense_s': defense_s, 'sector_heat': sector_heat, 'low_vol_s': low_vol_s,
        'rel_str': rel_str, 'rel_str_3d': rel_str_3d, 'beta_bonus': beta_bonus,
        'beta': beta, 'consistency': consistency,
        'r1': f.get('r1',0), 'r3': f.get('r3',0), 'r5': f.get('r5',0),
        'close_ma5': f.get('close_ma5',0), 'close_ma20': f.get('close_ma20',0),
        'vol5': vol5, 'vol_shrink': f.get('vol_shrink',1), 'turn_spike': f.get('turn_spike',1),
        'rsi': rsi, 'streak': f.get('streak',0),
        'oversold': f.get('oversold',0), 'overbought': f.get('overbought',0),
        'ind_heat': ind_heat, 'is_defensive': is_def, 'is_high_beta': is_hb,
    }

def score_v17_risk2(s, p):
    score = (s['momentum_s']*p['w_momentum'] + s['trend_s']*p['w_trend'] + s['consistency_s']*p['w_consistency']
             + s['vol_s']*p['w_vol'] + s['rsi_s']*p['w_rsi'] + s['static_score']*p['w_static']
             + s['defense_s']*p['w_defense'] + s['sector_heat']*p['w_sector'] + s['low_vol_s']*p['w_low_vol']
             + s['rel_str']*p['w_rel_str'] + s['rel_str_3d']*p['w_rel_str_3d'])
    if s['consistency']>=4: score*=p['boost_consistency']
    if s['close_ma20']>0: score*=p['boost_above_ma20']
    if 45<=s['rsi']<=60: score*=p['boost_rsi_45_60']
    if s['ind_heat']>1.5: score*=p['boost_sector_hot']
    if s['rel_str']>2: score*=p['boost_rel_str']
    if s['close_ma20']<-0.05: score*=p['penalty_below_ma20']
    if s['vol5']>3.5: score*=p['penalty_high_vol']
    if s['rsi']>70: score*=p['penalty_rsi_overbought']
    if abs(s['r1'])>5: score*=p['penalty_big_move']
    if s['streak']<=-2: score*=p['penalty_streak_neg']
    if s['vol_shrink']<0.7: score*=p['penalty_vol_shrink']
    if s['turn_spike']>2.0: score*=p['penalty_turn_spike']
    if s['close_ma5']<-0.02: score*=p['penalty_below_ma5']
    return score

def score_v17_risk3(s, p):
    score = (s['momentum_s']*p['w_momentum'] + s['trend_s']*p['w_trend'] + s['consistency_s']*p['w_consistency']
             + s['mr_s']*p['w_mr'] + s['vol_s']*p['w_vol'] + s['rsi_s']*p['w_rsi']
             + s['static_score']*p['w_static'] + s['defense_s']*p['w_defense']
             + s['sector_heat']*p['w_sector_heat'] + s['low_vol_s']*p['w_low_vol']
             + s['rel_str']*p['w_rel_str'] + s['rel_str_3d']*p['w_rel_str_3d'])
    if s['consistency']>=4: score*=p['consistency_boost_high']
    elif s['consistency']>=3: score*=p['consistency_boost_mid']
    if s['r3']>0 and s['r5']>0: score*=p['uptrend_boost_full']
    elif s['r3']>0: score*=p['uptrend_boost_partial']
    if s['close_ma20']>0: score*=p['ma20_above_mult']
    elif s['close_ma20']<-0.05: score*=p['ma20_below_mult']
    if s['vol5']<1.5: score*=p['low_vol_mult_high']
    elif s['vol5']<2.0: score*=p['low_vol_mult_mid']
    elif s['vol5']>3.5: score*=p['high_vol_penalize']
    if s['rsi']>75: score*=p['rsi_overbought_mult']
    elif s['rsi']>65: score*=p['rsi_high_mult']
    elif 45<=s['rsi']<=60: score*=p['rsi_sweet_mult']
    if s['ind_heat']>2: score*=p['sector_heat_strong']
    elif s['ind_heat']>0.5: score*=p['sector_heat_mild']
    elif s['ind_heat']<-2: score*=p['sector_cold']
    elif s['ind_heat']<-0.5: score*=p['sector_cool']
    if s['rel_str']>3: score*=p['rel_str_strong']
    elif s['rel_str']>1: score*=p['rel_str_mild']
    if abs(s['r1'])>5: score*=p['big_move5_penalize']
    if abs(s['r1'])>3: score*=p['big_move3_penalize']
    if s['streak']<=-2: score*=p['streak_penalize']
    if s['vol_shrink']<0.7: score*=p['vol_shrink_penalize']
    if s['turn_spike']>2.0: score*=p['turn_spike_penalize']
    if s['close_ma5']<-0.02: score*=p['ma5_below_penalize']
    return score

def score_v17_risk45(s, p):
    score = (s['momentum_s']*p['w_momentum'] + s['trend_s']*p['w_trend'] + s['mr_s']*p['w_mr']
             + s['vol_s']*p['w_vol'] + s['rsi_s']*p['w_rsi'] + s['static_score']*p['w_static']
             + s['defense_s']*p['w_defense'] + s['sector_heat']*p['w_sector'] + s['low_vol_s']*p['w_low_vol']
             + s['rel_str']*p['w_rel_str'] + s['rel_str_3d']*p['w_rel_str_3d'] + s['beta_bonus']*p['w_beta'])
    if s['beta']>1.5: score*=p['penalty_beta_high']
    elif s['beta']>1.2: score*=p['penalty_beta_mid']
    elif s['beta']<0.5: score*=p['boost_beta_low']
    if s['oversold']: score*=p['boost_oversold']
    if s['overbought']: score*=p['penalty_overbought']
    if s['is_high_beta']: score*=p['penalty_high_beta_ind']
    if s['is_defensive']: score*=p['boost_defensive_ind']
    if s['rel_str']>3: score*=p['boost_rel_str_strong']
    if s['rel_str']>5: score*=p['boost_rel_str_very_strong']
    if s['vol5']<1.5: score*=p['boost_low_vol']
    if s['r1']<-5: score*=p['penalty_big_drop']
    if s['r3']<-8: score*=p['penalty_big_drop_3d']
    if s['r1']>7: score*=p['penalty_big_jump']
    if s['r3']>15: score*=p['penalty_overextended']
    if s['streak']>=2 and s['rel_str']>0: score*=p['boost_streak_relstr']
    return score

# ============================================================================
# V14 Risk 3 Scoring (for comparison - uses raw features)
# ============================================================================
def score_v14_risk3(feats, static, daily_sector_avg, params):
    f = feats
    if f.get('pct_1d',0)>9.5 or f.get('pct_1d',0)<-9.5: return -999
    static_score = 0
    if static:
        tech=max(static.get('tech',5),0); fund=max(static.get('fund',5),0)
        chip=max(static.get('chip',5),0); sec=max(static.get('sector',5),0)
        static_score = (tech*0.30+fund*0.30+chip*0.25+sec*0.15)/10*5
    momentum_s=f['r1']*0.3+f['r3']*0.3+f['r5']*0.4
    trend_s=f['ma_align']*2.5+f.get('ma5_slope',0)*50+f.get('ma10_slope',0)*30
    mr_s=f['mr_5d']*0.5+f['mr_3d']*0.3+f.get('oversold',0)*5-f.get('overbought',0)*5
    vr=f.get('vol_ratio',1)
    vol_s=3 if 1.1<=vr<=2.0 else (1 if vr>2.0 else 2)
    rsi=f.get('rsi',50)
    rsi_s=3 if 40<=rsi<=60 else (4 if 30<=rsi<40 else (2 if 60<rsi<=70 else 1))
    vol5=f.get('vol5',2)
    low_vol_s=4 if vol5<1.5 else (3 if vol5<2.5 else (2 if vol5<3.5 else 1))
    industry=static.get('industry','unknown') if static else 'unknown'
    defense_s=0
    if is_defensive_industry(industry): defense_s+=3
    if is_high_beta_industry(industry): defense_s-=2
    defense_s+=low_vol_s
    rel_strength=f.get('rel_strength_5d',0); rel_strength_3d=f.get('rel_strength_3d',0)
    max_dd=f.get('max_dd_10d',0)
    if max_dd<-15: defense_s-=3
    elif max_dd<-10: defense_s-=1
    sector_heat=daily_sector_avg.get(industry,0)*0.1
    consistency=f.get('consistency',0); consistency_s=consistency*1.5
    score=(momentum_s*params['w_momentum']+trend_s*params['w_trend']+consistency_s*params['w_consistency']
           +mr_s*params['w_mr']+vol_s*params['w_vol']+rsi_s*params['w_rsi']+static_score*params['w_static']
           +defense_s*params['w_defense']+sector_heat*params['w_sector_heat']+low_vol_s*params['w_low_vol']
           +rel_strength*params['w_rel_str']+rel_strength_3d*params['w_rel_str_3d'])
    if consistency>=4: score*=params['consistency_boost_high']
    elif consistency>=3: score*=params['consistency_boost_mid']
    if f.get('r3',0)>0 and f.get('r5',0)>0: score*=params['uptrend_boost_full']
    elif f.get('r3',0)>0: score*=params['uptrend_boost_partial']
    if f.get('close_ma20',0)>0: score*=params['ma20_above_mult']
    elif f.get('close_ma20',0)<-0.05: score*=params['ma20_below_mult']
    if vol5<1.5: score*=params['low_vol_mult_high']
    elif vol5<2.0: score*=params['low_vol_mult_mid']
    elif vol5>3.5: score*=params['high_vol_penalize']
    if rsi>75: score*=params['rsi_overbought_mult']
    elif rsi>65: score*=params['rsi_high_mult']
    elif 45<=rsi<=60: score*=params['rsi_sweet_mult']
    ind_heat=daily_sector_avg.get(industry,0)
    if ind_heat>2: score*=params['sector_heat_strong']
    elif ind_heat>0.5: score*=params['sector_heat_mild']
    elif ind_heat<-2: score*=params['sector_cold']
    elif ind_heat<-0.5: score*=params['sector_cool']
    if rel_strength>3: score*=params['rel_str_strong']
    elif rel_strength>1: score*=params['rel_str_mild']
    if abs(f.get('r1',0))>5: score*=params['big_move5_penalize']
    if abs(f.get('r1',0))>3: score*=params['big_move3_penalize']
    if f.get('streak',0)<=-2: score*=params['streak_penalize']
    if f.get('vol_shrink',1)<0.7: score*=params['vol_shrink_penalize']
    if f.get('turn_spike',1)>2.0: score*=params['turn_spike_penalize']
    if f.get('close_ma5',0)<-0.02: score*=params['ma5_below_penalize']
    return score

# ============================================================================
# V10 Scoring for Risk 1/2/4/5 (baseline)
# ============================================================================
def score_v10_others(features, static, sector_avg, regime, momentum, vol_state, risk_level):
    if features is None: return -999
    f = features
    if f.get('pct_1d',0)>9.5 or f.get('pct_1d',0)<-9.5: return -999
    static_score = 0
    if static:
        tech=max(static.get('tech',5),0); fund=max(static.get('fund',5),0)
        chip=max(static.get('chip',5),0); sec=max(static.get('sector',5),0)
        static_score = (tech*0.30+fund*0.30+chip*0.25+sec*0.15)/10*5
    momentum_s=f['r1']*0.3+f['r3']*0.3+f['r5']*0.4
    trend_s=f['ma_align']*2.5+f.get('ma5_slope',0)*50+f.get('ma10_slope',0)*30
    mr_s=f['mr_5d']*0.5+f['mr_3d']*0.3+f.get('oversold',0)*5-f.get('overbought',0)*5
    vr=f.get('vol_ratio',1); vol_s=3 if 1.1<=vr<=2.0 else (1 if vr>2.0 else 2)
    rsi=f.get('rsi',50); rsi_s=3 if 40<=rsi<=60 else (4 if 30<=rsi<40 else (2 if 60<rsi<=70 else 1))
    vol5=f.get('vol5',2); low_vol_s=4 if vol5<1.5 else (3 if vol5<2.5 else (2 if vol5<3.5 else 1))
    industry=static.get('industry','unknown') if static else 'unknown'
    defense_s=0
    if is_defensive_industry(industry): defense_s+=3
    if is_high_beta_industry(industry): defense_s-=2
    defense_s+=low_vol_s
    rel_strength=f.get('rel_strength_5d',0); rel_strength_3d=f.get('rel_strength_3d',0)
    beta=f.get('beta_20d',1.0)
    max_dd=f.get('max_dd_10d',0)
    if max_dd<-15: defense_s-=3
    elif max_dd<-10: defense_s-=1
    sector_heat=sector_avg.get(industry,0)*0.1
    if risk_level>=4:
        score=(momentum_s*0.02+trend_s*0.03+mr_s*0.12+vol_s*0.03+rsi_s*0.08+static_score*0.12
               +defense_s*0.10+sector_heat*0.02+low_vol_s*0.05+rel_strength*0.18+rel_strength_3d*0.12
               +(2.0-min(beta,2.0))*0.10)
        if beta>1.5: score*=0.3
        elif beta>1.2: score*=0.6
        elif beta<0.5: score*=1.4
        if f.get('oversold',0): score*=1.2
        if f.get('overbought',0): score*=0.2
        if is_high_beta_industry(industry): score*=0.3
        if is_defensive_industry(industry): score*=1.3
        if rel_strength>3: score*=1.4
        if rel_strength>5: score*=1.2
        if vol5<1.5: score*=1.25
        if f.get('r1',0)<-5: score*=0.2
        if f.get('r3',0)<-8: score*=0.2
        if f.get('pct_1d',0)>7: score*=0.2
        if f.get('r3',0)>15: score*=0.3
        if f.get('streak',0)>=2 and rel_strength>0: score*=1.15
    else:
        score=(momentum_s*0.25+trend_s*0.20+mr_s*0.05+vol_s*0.10+rsi_s*0.05
               +static_score*0.15+defense_s*0.05+sector_heat*0.10+low_vol_s*0.05)
        if f['r1']>5: score*=0.5
        if f.get('overbought',0): score*=0.8
    return score

# ============================================================================
# Helpers
# ============================================================================
def get_adaptive_top_n(risk):
    if risk>=5: return 2
    elif risk>=4: return 3
    elif risk==3: return 3
    else: return 4

def get_stock_return(df, date):
    prev=df[df['date']<date]; day=df[df['date']>=date]
    if len(prev)==0 or len(day)==0: return None
    try: return (float(day.iloc[0]['close'])-float(prev.iloc[-1]['close']))/float(prev.iloc[-1]['close'])*100
    except: return None

def get_index_return(index_df, date):
    prev=index_df[index_df['date']<date]; day=index_df[index_df['date']>=date]
    if len(prev)==0 or len(day)==0: return None
    try: return (float(day.iloc[0]['close'])-float(prev.iloc[-1]['close']))/float(prev.iloc[-1]['close'])*100
    except: return None

def build_blacklist(stock_recent_perf, risk):
    bl = set()
    for code, rets in stock_recent_perf.items():
        if len(rets)>=1 and rets[-1]<-3: bl.add(code)
        if risk>=4 and len(rets)>=1 and rets[-1]>6: bl.add(code)
        if len(rets)>=2 and rets[-1]<0 and rets[-2]<0: bl.add(code)
        if len(rets)>=3 and rets[-1]<0 and rets[-2]<0 and rets[-3]<0: bl.add(code)
    return bl

# ============================================================================
# Single Period Backtest Engine
# ============================================================================
def run_period_backtest(kline, index_df, scores, sector_avg, start_str, end_str, period_label, version='v17'):
    eval_start = pd.to_datetime(start_str); eval_end = pd.to_datetime(end_str)
    date_range = pd.date_range(eval_start, eval_end, freq='B')
    valid_dates = [d for d in date_range if get_index_return(index_df, d) is not None]
    active_stocks = {code: df for code, df in kline.items() if len(df) >= MIN_KLINE_DAYS}
    
    print(f"\n  [{period_label}] ({version}) {start_str} ~ {end_str} ({len(valid_dates)} trading days)")
    if len(valid_dates) < 5:
        print(f"  SKIP: Too few trading days ({len(valid_dates)})"); return None
    
    results = []; stock_recent_perf = defaultdict(list)
    stats_by_risk = defaultdict(lambda: {'wins':0,'total':0,'beat_idx':0})
    daily_rets = []; daily_idx_rets = []
    
    for day_idx, test_date in enumerate(valid_dates):
        regime, momentum, vol_state, risk = detect_market_state(index_df, test_date)
        actual_n = get_adaptive_top_n(risk)
        
        idx_hist = index_df[index_df['date'] < test_date]; idx_closes = idx_hist['close'].values; idx_n = len(idx_closes)
        if idx_n >= 22:
            idx_diff = np.diff(idx_closes[-21:]); idx_base = idx_closes[-21:-1]
            idx_rets_20 = idx_diff[:len(idx_base)] / idx_base[:len(idx_diff)] * 100
        else: idx_rets_20 = None
        idx_ret_5d = (idx_closes[-1]-idx_closes[-6])/idx_closes[-6]*100 if idx_n>=6 else 0
        idx_ret_3d = (idx_closes[-1]-idx_closes[-4])/idx_closes[-4]*100 if idx_n>=4 else 0
        
        # Dynamic sector heat
        if regime == 'range':
            dsh = defaultdict(list)
            for code, df in active_stocks.items():
                st = scores.get(code); 
                if st is None: continue
                ind = st.get('industry','unknown')
                sh = df[df['date']<test_date]['close'].values
                if len(sh)>=4: dsh[ind].append((sh[-1]-sh[-4])/sh[-4]*100)
            daily_sector_avg = {ind: float(np.mean(r)) for ind, r in dsh.items() if len(r)>=3}
        else:
            daily_sector_avg = sector_avg
        
        scored = []
        for code, df in active_stocks.items():
            if len(df[df['date']>=test_date])==0: continue
            static = scores.get(code)
            
            if version == 'v17':
                ss = compute_stock_subscores(code, df, test_date, index_df, idx_rets_20, idx_ret_5d, idx_ret_3d, static, daily_sector_avg)
                if ss is None: continue
                if risk == 2: sc = score_v17_risk2(ss, V17_R2_PARAMS)
                elif risk == 3: sc = score_v17_risk3(ss, V17_R3_PARAMS)
                else:
                    sc = score_v17_risk45(ss, V17_R45_PARAMS)
                    if risk == 5:
                        if ss['beta']>1.3: sc*=0.5
                        if ss['r1']<-3: sc*=0.3
                        if ss['is_high_beta']: sc*=0.5
                strategy = f'v17_r{risk}'
            elif version == 'v14':
                feats = calc_features(df, test_date)
                if feats is None: continue
                stock_hist = df[df['date']<test_date]; s_closes = stock_hist['close'].values; s_n = len(s_closes)
                if idx_rets_20 is not None and s_n>=23:
                    s_rets_20 = np.diff(s_closes[-21:])/s_closes[-21:-1]*100
                    sr_len = min(len(s_rets_20),len(idx_rets_20))
                    if sr_len>=10:
                        idx_var = np.var(idx_rets_20[-sr_len:])
                        if idx_var>0.001: feats['beta_20d'] = np.cov(s_rets_20[-sr_len:],idx_rets_20[-sr_len:])[0,1]/idx_var
                if s_n>=6: feats['rel_strength_5d'] = (s_closes[-1]-s_closes[-6])/s_closes[-6]*100 - idx_ret_5d
                if s_n>=4: feats['rel_strength_3d'] = (s_closes[-1]-s_closes[-4])/s_closes[-4]*100 - idx_ret_3d
                
                if risk == 3:
                    sc = score_v14_risk3(feats, static, daily_sector_avg, V14_PARAMS)
                    if sc == -999: continue
                else:
                    sc = score_v10_others(feats, static, daily_sector_avg, regime, momentum, vol_state, risk)
                    if sc == -999: continue
                strategy = f'v14_r{risk}'
            else:  # v10
                feats = calc_features(df, test_date)
                if feats is None: continue
                stock_hist = df[df['date']<test_date]; s_closes = stock_hist['close'].values; s_n = len(s_closes)
                if idx_rets_20 is not None and s_n>=23:
                    s_rets_20 = np.diff(s_closes[-21:])/s_closes[-21:-1]*100
                    sr_len = min(len(s_rets_20),len(idx_rets_20))
                    if sr_len>=10:
                        idx_var = np.var(idx_rets_20[-sr_len:])
                        if idx_var>0.001: feats['beta_20d'] = np.cov(s_rets_20[-sr_len:],idx_rets_20[-sr_len:])[0,1]/idx_var
                if s_n>=6: feats['rel_strength_5d'] = (s_closes[-1]-s_closes[-6])/s_closes[-6]*100 - idx_ret_5d
                if s_n>=4: feats['rel_strength_3d'] = (s_closes[-1]-s_closes[-4])/s_closes[-4]*100 - idx_ret_3d
                sc = score_v10_others(feats, static, daily_sector_avg, regime, momentum, vol_state, risk)
                if sc == -999: continue
                strategy = f'v10_r{risk}'
            
            industry = static.get('industry','unknown') if static else 'unknown'
            scored.append({'code':code, 'score':sc, 'industry':industry, 'strategy':strategy})
        
        blacklist = build_blacklist(stock_recent_perf, risk)
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        selected = []; ind_count = defaultdict(int)
        for s in scored:
            if len(selected)>=actual_n: break
            if s['code'] in blacklist: continue
            if ind_count[s['industry']]>=MAX_INDUSTRY: continue
            if risk>=4 and s['score']<0.3: continue
            if risk==3 and s['score']<0.3: continue
            if risk<3 and s['score']<0.5: continue
            selected.append(s); ind_count[s['industry']]+=1
        
        if not selected:
            non_bl = [s for s in scored if s['code'] not in blacklist]
            selected = non_bl[:min(1 if risk>=4 or risk==3 else 2, len(non_bl))]
        if not selected: selected = scored[:min(2,len(scored))]
        if not selected: continue
        
        idx_ret = get_index_return(index_df, test_date)
        if idx_ret is None: idx_ret = 0
        
        stock_rets = []
        for s in selected:
            sr = get_stock_return(kline[s['code']], test_date)
            if sr is not None:
                stock_rets.append({'code':s['code'],'ret':round(sr,2),'beat':sr>idx_ret,'score':round(s['score'],2),'strategy':s['strategy']})
        
        for s in stock_rets:
            stock_recent_perf[s['code']].append(s['ret'])
            if len(stock_recent_perf[s['code']])>5: stock_recent_perf[s['code']]=stock_recent_perf[s['code']][-5:]
        
        if stock_rets:
            wr = sum(1 for x in stock_rets if x['beat'])/len(stock_rets)
            avg_ret = np.mean([x['ret'] for x in stock_rets])
            beat_idx = avg_ret > idx_ret
            daily_rets.append(avg_ret); daily_idx_rets.append(idx_ret)
            results.append({
                'date':test_date.strftime('%Y-%m-%d'),'regime':regime,'risk':risk,
                'n_stocks':len(stock_rets),'idx_ret':round(idx_ret,2),'avg_ret':round(avg_ret,2),
                'wr':round(wr,2),'win':wr>0.5,'beat_idx':beat_idx,
            })
            stats_by_risk[risk]['total']+=1
            if wr>0.5: stats_by_risk[risk]['wins']+=1
            if beat_idx: stats_by_risk[risk]['beat_idx']+=1
        
        if (day_idx+1)%10==0: check_memory()
    
    if not results:
        print(f"  No valid results!"); return None
    
    wins=sum(1 for r in results if r['win']); total=len(results)
    beat_idx_days=sum(1 for r in results if r['beat_idx'])
    
    cum_ret = float(np.sum(daily_rets)) if daily_rets else 0
    cum_idx_ret = float(np.sum(daily_idx_rets)) if daily_idx_rets else 0
    avg_daily_ret = float(np.mean(daily_rets)) if daily_rets else 0
    max_daily_loss = float(np.min(daily_rets)) if daily_rets else 0
    
    cum_series = np.cumsum(daily_rets)
    running_max = np.maximum.accumulate(cum_series)
    max_drawdown = float(np.min(cum_series - running_max)) if len(cum_series)>0 else 0
    
    regime_stats = defaultdict(lambda: {'wins':0,'total':0,'beat_idx':0})
    for r in results:
        regime_stats[r['regime']]['total']+=1
        if r['win']: regime_stats[r['regime']]['wins']+=1
        if r['beat_idx']: regime_stats[r['regime']]['beat_idx']+=1
    
    print(f"\n  [{period_label}] {version}: {beat_idx_days}/{total} = {beat_idx_days/total*100:.1f}% beat_idx"
          f" | cum_ret={cum_ret:+.1f}% | maxDD={max_drawdown:+.1f}%")
    for r in sorted(stats_by_risk.keys()):
        s=stats_by_risk[r]; bi=s['beat_idx']/s['total']*100 if s['total']>0 else 0
        print(f"    R{r}: {s['beat_idx']}/{s['total']} = {bi:.0f}%")
    
    return {
        'period':period_label,'version':version,'start':start_str,'end':end_str,
        'total':total,'wins':wins,'beat_idx_days':beat_idx_days,'beat_idx_pct':beat_idx_days/total,
        'avg_daily_ret':avg_daily_ret,'max_daily_loss':max_daily_loss,
        'cum_ret':cum_ret,'cum_idx_ret':cum_idx_ret,'max_drawdown':max_drawdown,
        'stats_by_risk':{str(k):v for k,v in stats_by_risk.items()},
        'stats_by_regime':{k:v for k,v in regime_stats.items()},
    }

# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()
    print("="*70)
    print("V17 Extended Backtest - Multi-Period Validation")
    print("  V17: Multi-period Optuna params (trained A/B/C windows)")
    print("  V14: Single-period Optuna params (trained 03/01~04/24)")
    print("  V10: Original hand-tuned (baseline)")
    print("="*70)
    
    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = _load_scores()
    
    sector_perf = defaultdict(list)
    for code, s in scores.items():
        sector_perf[s['industry']].append(s.get('sector_change',0))
    sector_avg = {ind: float(np.mean([v for v in vals if v is not None])) for ind, vals in sector_perf.items()}
    
    print_mem("All data loaded")
    
    PERIODS = [
        ("2025-11-15","2025-12-31","Nov-Dec 2025"),
        ("2026-01-05","2026-02-06","Jan 2026"),
        ("2026-02-09","2026-03-06","Feb 2026"),
        ("2026-03-09","2026-04-07","Mar-Apr 2026"),
        ("2026-01-05","2026-04-07","Jan-Apr 2026 (3mo)"),
        ("2025-11-15","2026-04-07","Full range (4.5mo)"),
    ]
    
    summary = {}
    
    # Run V17 for all periods
    for start, end, label in PERIODS:
        r = run_period_backtest(kline, index_df, scores, sector_avg, start, end, label, version='v17')
        if r: summary[f'v17_{label}'] = r
        gc.collect(); print_mem(f"After V17 {label}")
    
    # Run V14 for all periods
    for start, end, label in PERIODS:
        r = run_period_backtest(kline, index_df, scores, sector_avg, start, end, label, version='v14')
        if r: summary[f'v14_{label}'] = r
        gc.collect(); print_mem(f"After V14 {label}")
    
    # Run V10 for key periods only
    v10_periods = [("2026-01-05","2026-04-07","Jan-Apr 2026 (3mo)"), ("2025-11-15","2026-04-07","Full range (4.5mo)")]
    for start, end, label in v10_periods:
        r = run_period_backtest(kline, index_df, scores, sector_avg, start, end, label, version='v10')
        if r: summary[f'v10_{label}'] = r
        gc.collect(); print_mem(f"After V10 {label}")
    
    # ========================================================================
    # Comparison Report
    # ========================================================================
    print(f"\n\n{'='*90}")
    print("V10 vs V14 vs V17 COMPARISON")
    print("="*90)
    print(f"{'Period':<24} {'V17':>10} {'V14':>10} {'V10':>10} {'V17-R3':>10} {'V14-R3':>10}")
    print("-"*90)
    
    for start, end, label in PERIODS:
        v17k = f'v17_{label}'; v14k = f'v14_{label}'; v10k = f'v10_{label}'
        v17bi = f"{summary[v17k]['beat_idx_pct']*100:.1f}%" if v17k in summary else "N/A"
        v14bi = f"{summary[v14k]['beat_idx_pct']*100:.1f}%" if v14k in summary else "N/A"
        v10bi = f"{summary[v10k]['beat_idx_pct']*100:.1f}%" if v10k in summary else "N/A"
        v17r3 = summary[v17k]['stats_by_risk'].get('3',{}) if v17k in summary else {}
        v14r3 = summary[v14k]['stats_by_risk'].get('3',{}) if v14k in summary else {}
        v17r3s = f"{v17r3.get('beat_idx',0)/max(v17r3.get('total',1),1)*100:.1f}%" if v17r3 else "N/A"
        v14r3s = f"{v14r3.get('beat_idx',0)/max(v14r3.get('total',1),1)*100:.1f}%" if v14r3 else "N/A"
        print(f"  {label:<22} {v17bi:>10} {v14bi:>10} {v10bi:>10} {v17r3s:>10} {v14r3s:>10}")
    
    # ========================================================================
    # Save
    # ========================================================================
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    # Build clean summary dict
    output_summary = {}
    for start, end, label in PERIODS:
        entry = {}
        for ver in ['v17','v14','v10']:
            k = f'{ver}_{label}'
            if k in summary:
                r = summary[k]
                r3 = r['stats_by_risk'].get('3',{})
                entry[ver] = {
                    'beat_idx_pct': round(r['beat_idx_pct']*100,1),
                    'r3_beat_idx_pct': round(r3.get('beat_idx',0)/max(r3.get('total',1),1)*100,1),
                    'avg_daily_ret': round(r['avg_daily_ret'],4),
                    'cum_ret': round(r['cum_ret'],2),
                    'cum_idx_ret': round(r['cum_idx_ret'],2),
                    'max_drawdown': round(r['max_drawdown'],2),
                    'max_daily_loss': round(r['max_daily_loss'],2),
                    'total_days': r['total'],
                    'stats_by_risk': r['stats_by_risk'],
                    'stats_by_regime': r['stats_by_regime'],
                }
        if entry:
            output_summary[label] = entry
    
    output = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v17-extended-validation',
        'description': 'V10/V14/V17 multi-period comparison',
        'v17_params_source': V17_PARAMS_FILE,
        'data_stocks': len(kline),
        'periods_tested': len(PERIODS),
        'summary': output_summary,
        'elapsed_seconds': round(time.time()-t0,1),
    }
    
    fp = os.path.join(RESULT_DIR, 'backtest_v17_extended.json')
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResults saved: {fp}")
    
    elapsed = time.time()-t0
    print(f"Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("="*70)
    return output

if __name__ == '__main__':
    main()

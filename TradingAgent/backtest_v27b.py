#!/usr/bin/env python3
# NOTE: Run with python3 (not python) to avoid JSON parsing issues
# -*- coding: utf-8 -*-
"""
V27b - Precision Optimization: Focus on stock quality over market timing

Key insight from V27 attempt: no-trade rules are fragile and block WINs.
Better approach: improve stock selection quality so fewer FAILs happen.

Changes from V26:
  1. V25 FROZEN weights (not re-optimized)
  2. Real trading calendar from V26
  3. Cooldown from V26  
  4. Extended test window from V26
  5. Limit-up/IPO filters from V26
  6. NEW: Select fewer stocks (2-3) for better concentration
  7. NEW: Stock volatility penalty (avoid unstable stocks)
  8. NEW: Max 1 per industry (better diversification)
  9. NEW: Light no-trade only on consec_rally >= 4 AND strong_bull (very conservative)
  10. NEW: Trend strength bonus - prefer stocks with strong uptrends

Only tune: n_rec, min_score, vol_penalty, cooldown_weight, trend_bonus, industry_limit
"""
import json, os, sys, time, gc, warnings, functools
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
SHARED_DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

MIN_KLINE_DAYS = 30
MEMORY_LIMIT_MB = 8000
V19_POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
V19_USE_POOL = True

PERIOD_A = ('2026-02-07', '2026-03-03')
PERIOD_B = ('2026-03-03', '2026-03-28')
PERIOD_C = ('2026-03-28', '2026-04-22')
PERIOD_D = ('2026-04-22', '2026-05-13')

N_TRIALS = 400

COOLDOWN_DAYS = 3
USE_COOLDOWN = True
LIMIT_UP_THRESHOLD = 15.0
IPO_MIN_DAYS = 30

PT_ST_KEYWORDS = ['PT', 'ST', '*ST', '退']
BLOCKED_CODE_PREFIXES = ['2', '9', '4']

DEFENSIVE_KEYWORDS = ['电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
                      '高速公路', '港口', '机场', '交通', '通信', '电信']
HIGH_BETA_KEYWORDS = ['半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
                      '保险', '房地产', '钢铁', '煤炭', '有色']

V25_FROZEN_WEIGHTS = {
    'weights_bull': [0.1074, 0.1969, 0.2725, 0.0693, 0.2106, 0.1433],
    'weights_range': [0.1074, 0.1969, 0.2725, 0.0693, 0.2106, 0.1433],
    'weights_bear': [0.1198, 0.1427, 0.3039, 0.0773, 0.2349, 0.1214],
    'min_score_threshold': 62.25,
}

def is_defensive_industry(industry): return any(kw in industry for kw in DEFENSIVE_KEYWORDS)
def is_high_beta_industry(industry): return any(kw in industry for kw in HIGH_BETA_KEYWORDS)

def check_memory(limit_mb=MEMORY_LIMIT_MB):
    try:
        import psutil; mb = psutil.Process().memory_info().rss / 1024 / 1024
        if mb > limit_mb: gc.collect(); return True
        return False
    except ImportError: return False

def print_mem(label=""):
    try:
        import psutil; mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label: print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError: pass

def normalize_code(code):
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'): return code[2:]
    return code

def is_tradeable(code, name='', static=None):
    if len(code) >= 1 and code[0] in BLOCKED_CODE_PREFIXES: return False
    for kw in PT_ST_KEYWORDS:
        if kw in name: return False
    return True


# ===== Data Loading (same as V26) =====
def load_merged_kline():
    print("[1/3] Loading kline data...")
    v19_pool = None
    if V19_USE_POOL and os.path.exists(V19_POOL_FILE):
        with open(V19_POOL_FILE, 'r', encoding='utf-8') as f:
            v19_pool = set(json.load(f))
    new_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
    NEED_COLS = {'date', 'open', 'high', 'low', 'close', 'volume', 'pctChg', 'turn'}
    with open(new_file, 'r', encoding='utf-8') as f: raw_data = json.load(f)
    merged = {}
    for code, records in raw_data.items():
        clean = normalize_code(code)
        if v19_pool is not None and clean not in v19_pool: continue
        if not records: continue
        combined = []
        seen = set()
        for r in records:
            d = r.get('date', '')
            if d and d not in seen: seen.add(d); combined.append({k: v for k, v in r.items() if k in NEED_COLS})
        if len(combined) < MIN_KLINE_DAYS: continue
        df = pd.DataFrame(combined)
        df['date'] = pd.to_datetime(df['date'], format='mixed').dt.tz_localize(None)
        df = df.sort_values('date').drop_duplicates(subset='date', keep='last')
        for col in ['open', 'high', 'low', 'close', 'volume', 'turn', 'pctChg']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
        merged[clean] = df
    del raw_data; gc.collect()
    print(f"  Loaded: {len(merged)} stocks")
    return merged

def _parse_index_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f: raw = json.load(f)
    records = []
    if 'date' in raw and isinstance(raw['date'], dict):
        n = len(raw['date'])
        for i in range(n):
            try:
                ts = raw['date'].get(str(i)); cl = float(raw['close'].get(str(i), 0))
                if ts is None or cl <= 0: continue
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
                records.append({'date': ds, 'close': cl})
            except: continue
    del raw; return records

def load_index_extended():
    print("[2/3] Loading index data...")
    old_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    new_file = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    old_r = _parse_index_file(old_file) if os.path.exists(old_file) else []
    new_r = _parse_index_file(new_file) if os.path.exists(new_file) else []
    seen = set(); all_r = []
    for r in old_r + new_r:
        if r['date'] not in seen: seen.add(r['date']); all_r.append(r)
    gc.collect()
    df = pd.DataFrame(all_r)
    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
    df = df.dropna(subset=['close']).sort_values('date').drop_duplicates(subset='date', keep='last')
    df['close'] = df['close'].astype('float32')
    print(f"  Index: {len(df)} days")
    return df

def _load_scores():
    import glob
    opt_pat = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
    opt_files = sorted(glob.glob(opt_pat), key=lambda x: (os.path.getsize(x) > 100000, os.path.getmtime(x)), reverse=True)
    scores = {}
    for sf in opt_files:
        if os.path.getsize(sf) < 100000: continue
        try:
            with open(sf, 'r', encoding='utf-8') as f: sd = json.load(f)
            for code, s in sd.items():
                if not isinstance(s, dict): continue
                c = normalize_code(code)
                scores[c] = {'tech': float(s.get('short_term_score', 5.0)), 'fund': float(s.get('long_term_score', 5.0)),
                             'chip': float(s.get('chip_score', 5.0)), 'sector': float(s.get('hot_sector_score', 5.0)),
                             'name': s.get('name', ''), 'industry': s.get('industry', s.get('matched_sector', 'unknown')),
                             'sector_change': float(s.get('sector_change', 0.0))}
            break
        except: continue
    print(f"  Scores: {len(scores)} stocks")
    return scores


def get_trading_dates(index_df, start_str, end_str):
    start, end = pd.to_datetime(start_str), pd.to_datetime(end_str)
    return sorted(index_df.loc[(index_df['date'] >= start) & (index_df['date'] <= end), 'date'].tolist())

def get_stock_return(df, date):
    rows = df[df['date'] >= date]
    if len(rows) < 2: return None
    try: return (float(rows.iloc[1]['close']) - float(rows.iloc[0]['close'])) / float(rows.iloc[0]['close']) * 100
    except: return None

def get_index_return(index_df, date):
    rows = index_df[index_df['date'] >= date]
    if len(rows) < 2: return None
    try: return (float(rows.iloc[1]['close']) - float(rows.iloc[0]['close'])) / float(rows.iloc[0]['close']) * 100
    except: return None

def count_recent_limit_ups(c, lookback=5, threshold=LIMIT_UP_THRESHOLD):
    n = len(c); count = 0
    for i in range(max(1, n - lookback), n):
        if (c[i] - c[i-1]) / c[i-1] * 100 > threshold: count += 1
    return count


# ===== Market Regime (V25 logic + extra info) =====
def detect_market_regime(index_df, date):
    hist = index_df[index_df['date'] < date]
    if len(hist) < 20: return 'range', 0.5, 3, {}
    closes = hist['close'].values; n = len(closes)
    ma5, ma10, ma20 = np.mean(closes[-5:]), np.mean(closes[-10:]), np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if n >= 60 else ma20
    trend_score = sum([closes[-1]>ma5, ma5>ma10, ma10>ma20, ma20>ma60])
    ret5 = (closes[-1]-closes[-6])/closes[-6]*100 if n>=6 else 0
    ret20 = (closes[-1]-closes[-21])/closes[-21]*100 if n>=21 else 0
    ret60 = (closes[-1]-closes[-61])/closes[-61]*100 if n>=61 else 0
    momentum = ret5*0.5 + ret20*0.3 + ret60*0.2
    volatility = np.std((closes[-20:]-closes[-21:-1])/closes[-21:-1]*100) if n>=21 else 0.8
    if trend_score>=3 and momentum>2: regime, risk = 'strong_bull', 1
    elif trend_score>=2 and momentum>0: regime, risk = 'bull', 2
    elif trend_score<=1 and momentum<-2: regime, risk = 'bear', 4
    elif trend_score==0 and momentum<-3: regime, risk = 'crisis', 5
    else: regime, risk = 'range', 3
    if volatility > 1.5: risk = min(risk+1, 5)
    consec_up = 0
    for i in range(n-1, max(0, n-6), -1):
        if closes[i] > closes[i-1]: consec_up += 1
        else: break
    confidence = min(abs(trend_score-2)/2.0 + abs(momentum)/5.0, 1.0)
    extra = {'momentum': momentum, 'consec_up': consec_up, 'volatility': volatility,
             'prev_day_ret': (closes[-1]-closes[-2])/closes[-2]*100 if n>=2 else 0}
    return regime, confidence, risk, extra

def should_trade(regime, confidence, risk, extra):
    if risk >= 5: return False, 0
    if risk == 4 and confidence > 0.6: return True, 1
    if risk == 3 and confidence < 0.3: return False, 0
    # V27b: Targeted no-trade rules
    consec_up = extra.get('consec_up', 0)
    prev_ret = extra.get('prev_day_ret', 0)
    momentum = extra.get('momentum', 0)
    # Rule 1: Strong bull after 3+ consecutive up days + moderate prev gain = exhaustion
    if risk <= 1 and consec_up >= 3 and 0.3 < prev_ret < 1.2:
        return False, 0
    # Rule 2: Strong bull with extreme momentum and flat/weak prev day = overextension
    if risk <= 1 and momentum > 3.5 and prev_ret < 0.1:
        return False, 0
    # Rule 3: Very long consecutive rally (5+)
    if risk <= 1 and consec_up >= 5:
        return False, 0
    if risk <= 2: return True, 3 if risk == 1 else 2
    return True, 2


# ===== Sector Rotation =====
def identify_hot_sectors(kline, scores, date, lookback=5):
    sector_returns = defaultdict(list)
    for code, df in kline.items():
        static = scores.get(code)
        if not static: continue
        ind = static.get('industry', 'unknown')
        if ind in ('unknown', '未知', ''): continue
        hist = df[df['date'] < date]
        if len(hist) < lookback+1: continue
        c = hist['close'].values
        sector_returns[ind].append((c[-1]-c[-lookback-1])/c[-lookback-1]*100)
    heat = {}
    for ind, rets in sector_returns.items():
        if len(rets) >= 3: heat[ind] = np.mean(rets)*0.4 + sum(1 for r in rets if r>0)/len(rets)*5*0.6
    return heat


# ===== Sub-score modules (same as V25/V26) =====
def multi_timeframe_trend_score(c):
    n = len(c)
    if n < 20: return 50, 'neutral'
    ma5, ma10, ma20 = np.mean(c[-5:]), np.mean(c[-10:]), np.mean(c[-20:])
    ds = 0
    if c[-1]>ma5>ma10>ma20: ds += 40
    elif c[-1]>ma5>ma10: ds += 30
    elif c[-1]>ma5: ds += 15
    elif c[-1]<ma5<ma10<ma20: ds -= 40
    elif c[-1]<ma5<ma10: ds -= 30
    elif c[-1]<ma5: ds -= 15
    if n>=6:
        s = (ma5-np.mean(c[-6:-1]))/max(np.mean(c[-6:-1]),0.01)*100
        ds += max(-15, min(15, s*8 if abs(s)>1 else s*5))
    score = ds * 0.4
    if n>=60:
        wc = c[::5]
        if len(wc)>=12:
            wm5, wm10 = np.mean(wc[-5:]), np.mean(wc[-10:])
            if wc[-1]>wm5>wm10: score += 40*0.4
            elif wc[-1]>wm5: score += 20*0.4
            elif wc[-1]<wm5<wm10: score -= 40*0.4
    score = max(0, min(100, (score+100)/2))
    d = 'strong_up' if score>=75 else 'up' if score>=55 else 'neutral' if score>=45 else 'down' if score>=25 else 'strong_down'
    return score, d

def money_flow_score(c, v, hi, lo, turn):
    n = len(c)
    if n < 10: return 50.0
    uv = [v[i] for i in range(-10,0) if c[i]>c[i-1]]
    dv = [v[i] for i in range(-10,0) if c[i]<=c[i-1]]
    vr = (np.mean(uv) if uv else 1) / max(np.mean(dv) if dv else 1, 1)
    s = 50
    if vr > 2.0: s += 15
    elif vr > 1.5: s += 8
    elif vr < 0.7: s -= 10
    for i in range(-3,0):
        body = abs(c[i]-c[i-1]); tw = max(hi[i]-lo[i], 0.01)
        if c[i]>c[i-1] and (body+min(c[i],c[i-1])-lo[i])/tw > 0.7: s += 3
    if n>=10 and not np.all(turn==1):
        tr = turn[-1]/max(np.mean(turn[-6:-1]),0.1)
        if tr>2 and c[-1]>c[-2]: s += 10
        elif tr>2 and c[-1]<c[-2]: s -= 15
    return max(0, min(100, s))

def relative_strength_rank(code, c, industry, peer_data):
    if len(c) < 6: return 50
    my = (c[-1]-c[-6])/c[-6]*100
    pr = [r for pc, r in peer_data if pc != code]
    if len(pr) < 2: return 50
    return sum(1 for r in pr if r < my) / len(pr) * 100

def calc_volume_health(c, v):
    n = len(c)
    if n < 10: return 50
    s = 50
    for i in range(-5,0):
        if c[i]>c[i-1] and v[i]>v[i-1]: s += 3
        elif c[i]<c[i-1] and v[i]<v[i-1]: s += 2
        elif c[i]<c[i-1] and v[i]>v[i-1]: s -= 3
    return max(0, min(100, s))

def detect_divergence(c, v, lookback=20):
    n = len(c)
    if n < lookback: return {'bullish': False, 'bearish': False, 'strength': 0}
    obv = [0]
    for i in range(1, n):
        if c[i]>c[i-1]: obv.append(obv[-1]+v[i])
        elif c[i]<c[i-1]: obv.append(obv[-1]-v[i])
        else: obv.append(obv[-1])
    obv = np.array(obv); recent = min(lookback, n)
    result = {'bullish': False, 'bearish': False, 'strength': 0}
    pmin = np.argmin(c[-recent:])
    if pmin >= recent-5:
        obv_at = obv[-(recent-pmin)] if pmin < recent else obv[-1]
        obv_min = np.min(obv[-recent:])
        if obv_at > obv_min*1.1: result['bullish'] = True; result['strength'] = min(1.0, (obv_at-obv_min)/max(abs(obv_min),1))
    pmax = np.argmax(c[-recent:])
    if pmax >= recent-5:
        obv_at = obv[-(recent-pmax)] if pmax < recent else obv[-1]
        obv_max = np.max(obv[-recent:])
        if obv_at < obv_max*0.9: result['bearish'] = True; result['strength'] = min(1.0, (obv_max-obv_at)/max(abs(obv_max),1))
    return result

def compute_stock_volatility(c, lookback=10):
    n = len(c)
    if n < lookback+1: return 0.8
    return float(np.std((c[-lookback:]-c[-lookback-1:-1])/c[-lookback-1:-1]*100))


# ===== Precompute =====
def precompute(kline, index_df, scores, start_str, end_str):
    valid_dates = get_trading_dates(index_df, start_str, end_str)
    valid_dates = [d for d in valid_dates if get_index_return(index_df, d) is not None]
    print(f"  {start_str}~{end_str}: {len(valid_dates)} trading days")

    daily_data = []
    for day_idx, test_date in enumerate(valid_dates):
        regime, confidence, risk, extra = detect_market_regime(index_df, test_date)
        should, n_rec = should_trade(regime, confidence, risk, extra)
        idx_ret = get_index_return(index_df, test_date) or 0
        sector_heat = identify_hot_sectors(kline, scores, test_date)

        ind_peers = defaultdict(list)
        cache = {}
        for code, df in kline.items():
            static = scores.get(code)
            name = static.get('name', '') if static else ''
            if not is_tradeable(code, name): continue
            if len(df[df['date'] >= test_date]) == 0: continue
            hist = df[df['date'] < test_date]
            c = hist['close'].values
            if len(c) < 20: continue
            if len(df) < IPO_MIN_DAYS: continue
            last_pct = (c[-1]-c[-2])/c[-2]*100
            if last_pct > LIMIT_UP_THRESHOLD: continue
            if count_recent_limit_ups(c) >= 2: continue
            ind = static.get('industry', 'unknown') if static else 'unknown'
            ret5 = (c[-1]-c[-6])/c[-6]*100 if len(c)>=6 else 0
            ind_peers[ind].append((code, ret5))
            v = hist['volume'].values
            hi = hist['high'].values if 'high' in hist.columns else c
            lo = hist['low'].values if 'low' in hist.columns else c
            turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
            es = 50
            if static:
                es = (static.get('tech',5)*5+static.get('fund',5)*3+static.get('chip',5)*2+static.get('sector',5)*3)/13*10
            cache[code] = {'c':c,'v':v,'hi':hi,'lo':lo,'turn':turn,'industry':ind,'name':name,
                           'stock_return':get_stock_return(df, test_date),'extra_score':es,
                           'stock_vol':compute_stock_volatility(c)}

        stock_scores = []
        for code, cc in cache.items():
            ts, td = multi_timeframe_trend_score(cc['c'])
            ms = money_flow_score(cc['c'], cc['v'], cc['hi'], cc['lo'], cc['turn'])
            sh = max(0, min(100, (sector_heat.get(cc['industry'], 0)+5)*10))
            rs = relative_strength_rank(code, cc['c'], cc['industry'], ind_peers.get(cc['industry'],[]))
            vs = calc_volume_health(cc['c'], cc['v'])
            isd, ish = is_defensive_industry(cc['industry']), is_high_beta_industry(cc['industry'])
            if risk>=4: ra = 80 if isd else (20 if ish else 40)
            elif risk<=2: ra = 70 if ish else (40 if isd else 55)
            else: ra = 55
            div = detect_divergence(cc['c'], cc['v'])
            stock_scores.append({
                'code':code,'name':cc['name'],'industry':cc['industry'],
                'trend_s':ts,'money_s':ms,'sector_s':sh,'rs_s':rs,'vol_s':vs,'risk_adj':ra,
                'extra_s':cc['extra_score'],'trend_dir':td,
                'div_bull':div['bullish'],'div_bear':div['bearish'],'div_str':div['strength'],
                'stock_return':cc['stock_return'],'stock_vol':cc['stock_vol'],
            })

        daily_data.append({
            'test_date':test_date,'regime':regime,'confidence':confidence,'risk':risk,
            'should_trade':should,'n_recommend':n_rec,'idx_ret':idx_ret,
            'extra':extra,'stocks':stock_scores,
        })
        if (day_idx+1)%10==0: check_memory()
    return daily_data


class CooldownTracker:
    def __init__(self, days=COOLDOWN_DAYS):
        self.days = days; self.last = {}
    def is_ok(self, code, date):
        if code not in self.last: return True
        return (date - self.last[code]).days >= self.days
    def mark(self, code, date):
        self.last[code] = date
    def penalty(self, code, date):
        if code not in self.last: return 0
        d = (date - self.last[code]).days
        return 0 if d >= self.days else (self.days-d)/self.days*10


def evaluate(daily_data, cfg, detailed=False):
    beat_count = total = skipped = no_trade = 0
    day_details = []
    cd = CooldownTracker(COOLDOWN_DAYS)
    
    n_rec_default = cfg.get('n_rec', 3)
    max_ind = cfg.get('max_industry', 1)
    min_score = cfg.get('min_score', 62)
    cd_weight = cfg.get('cooldown_weight', 5.0)
    vol_pen_w = cfg.get('vol_penalty_weight', 3.0)
    vol_pen_t = cfg.get('vol_penalty_threshold', 2.0)
    w_extra = cfg.get('w_extra', 0.0)
    trend_bonus = cfg.get('trend_bonus', 0.0)

    for dd in daily_data:
        risk, regime, idx_ret = dd['risk'], dd['regime'], dd['idx_ret']
        test_date = dd['test_date']

        if not dd['should_trade']:
            no_trade += 1
            if detailed: day_details.append({'date':str(test_date.date()),'regime':regime,'risk':risk,
                                              'n_stocks':0,'avg_ret':0,'idx_ret':round(idx_ret,2),
                                              'beat':False,'no_trade':True,'top':[]})
            continue

        n_rec = n_rec_default
        w = cfg['weights_bull'] if risk<=2 else (cfg['weights_bear'] if risk>=4 else cfg['weights_range'])

        scored = []
        for s in dd['stocks']:
            final = (s['trend_s']*w[0]+s['money_s']*w[1]+s['sector_s']*w[2]+
                     s['rs_s']*w[3]+s['vol_s']*w[4]+s['risk_adj']*w[5]+s['extra_s']*w_extra)
            tw = sum(w)+w_extra
            if tw > 0: final /= tw
            if s['div_bull']: final += 5*s['div_str']
            if s['div_bear']: final -= 8*s['div_str']
            # Cooldown
            final -= cd.penalty(s['code'], test_date) * cd_weight
            # Vol penalty
            if s['stock_vol'] > vol_pen_t:
                final -= (s['stock_vol']-vol_pen_t)/vol_pen_t * vol_pen_w
            # Trend bonus for strong up stocks
            if trend_bonus != 0 and s['trend_dir'] == 'strong_up':
                final += trend_bonus
            scored.append((s, final))

        scored.sort(key=lambda x: x[1], reverse=True)
        selected = []; ind_c = defaultdict(int)
        for s, sc in scored:
            if len(selected) >= n_rec: break
            if sc < min_score: continue
            if s['trend_dir'] == 'strong_down': continue
            if s['div_bear'] and s['div_str'] > 0.5: continue
            if not cd.is_ok(s['code'], test_date): continue
            if ind_c[s['industry']] >= max_ind: continue
            selected.append((s, sc)); ind_c[s['industry']] += 1

        # Fallback (relax min_score)
        if len(selected) < n_rec:
            for s, sc in scored:
                if len(selected) >= n_rec: break
                if any(x[0]['code']==s['code'] for x in selected): continue
                if sc < min_score-10: break
                if s['trend_dir']=='strong_down': continue
                if not cd.is_ok(s['code'], test_date): continue
                if ind_c[s['industry']] >= max_ind: continue
                selected.append((s, sc)); ind_c[s['industry']] += 1

        if not selected:
            skipped += 1; continue

        for s, sc in selected: cd.mark(s['code'], test_date)
        rets = [s['stock_return'] for s, sc in selected if s['stock_return'] is not None]
        if rets:
            avg = np.mean(rets); beat = avg > idx_ret
            total += 1
            if beat: beat_count += 1
            if detailed:
                day_details.append({'date':str(test_date.date()),'regime':regime,'risk':risk,
                                    'n_stocks':len(rets),'avg_ret':round(avg,2),'idx_ret':round(idx_ret,2),
                                    'beat':beat,'no_trade':False,
                                    'top':[{'code':s['code'],'name':s['name'],'score':round(sc,1),
                                            'ret':round(s['stock_return'],2) if s['stock_return'] else None}
                                           for s, sc in selected[:3]]})

    return beat_count/total if total>0 else 0, beat_count, total, skipped, no_trade, day_details


def optimize(train_data, valid_data, n_trials=N_TRIALS):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    print(f"\n[Optimization] V27b — {n_trials} trials, frozen V25 weights")
    best = {'obj': -999, 'cfg': None}
    all_train = train_data['A'] + train_data['B'] + valid_data

    def objective(trial):
        cfg = {
            'weights_bull': V25_FROZEN_WEIGHTS['weights_bull'],
            'weights_range': V25_FROZEN_WEIGHTS['weights_range'],
            'weights_bear': V25_FROZEN_WEIGHTS['weights_bear'],
            'n_rec': trial.suggest_int('n_rec', 2, 4),
            'max_industry': trial.suggest_int('max_industry', 1, 2),
            'min_score': trial.suggest_float('min_score', 50, 68),
            'cooldown_weight': trial.suggest_float('cd_w', 0, 15),
            'vol_penalty_weight': trial.suggest_float('vol_pen_w', 0, 10),
            'vol_penalty_threshold': trial.suggest_float('vol_pen_t', 1.0, 3.5),
            'w_extra': trial.suggest_float('w_extra', 0, 0.3),
            'trend_bonus': trial.suggest_float('trend_bonus', -5, 10),
        }
        tr_bi, tr_bc, tr_bt, _, _, _ = evaluate(all_train, cfg)
        ab_bi, _, _, _, _, _ = evaluate(train_data['A']+train_data['B'], cfg)
        c_bi, _, _, _, _, _ = evaluate(valid_data, cfg)
        stability = min(ab_bi, c_bi)
        obj = 0.5*tr_bi + 0.4*stability - abs(ab_bi-c_bi)*0.3*0.1
        if obj > best['obj']:
            best['obj'] = obj; best['cfg'] = cfg
            print(f"    [Trial {trial.number}] obj={obj:.4f} all={tr_bc}/{tr_bt}={tr_bi*100:.0f}% "
                  f"AB={ab_bi*100:.0f}% C={c_bi*100:.0f}% n_rec={cfg['n_rec']} min={cfg['min_score']:.0f} "
                  f"max_ind={cfg['max_industry']} trend_b={cfg['trend_bonus']:.1f}")
        return obj

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, timeout=900, show_progress_bar=False)
    print(f"\n  Best obj: {best['obj']:.4f}")
    return best['cfg'], best['obj']


def main():
    t0 = time.time()
    print("="*70)
    print("V27b - Precision Optimization: Stock quality > Market timing")
    print("  V25 frozen weights | Cooldown | Vol penalty | Industry limit=1")
    print("="*70)

    kline = load_merged_kline()
    index_df = load_index_extended()
    scores = _load_scores()
    print_mem("Loaded")

    test_dates = get_trading_dates(index_df, '2026-04-22', '2026-05-13')
    print(f"\n  Test dates ({len(test_dates)}): {[str(d.date()) for d in test_dates]}")

    periods = {}
    for lbl, (ps, pe) in [('A',PERIOD_A),('B',PERIOD_B),('C',PERIOD_C),('D',PERIOD_D)]:
        print(f"\n  Period {lbl}: {ps}~{pe}")
        periods[lbl] = precompute(kline, index_df, scores, ps, pe)
        gc.collect()

    del kline; gc.collect()

    best_cfg, best_obj = optimize({'A':periods['A'],'B':periods['B']}, periods['C'])

    print(f"\n{'='*70}")
    print(f"  V27b WALK-FORWARD EVALUATION")
    print(f"{'='*70}")

    results = {}
    for lbl in ['A','B','C','D']:
        bi, bc, bt, sk, nt, det = evaluate(periods[lbl], best_cfg, detailed=True)
        results[lbl] = {'bi':bi,'bc':bc,'bt':bt,'sk':sk,'nt':nt,'det':det}
        print(f"  Period {lbl}: {bc}/{bt} = {bi*100:.1f}% (no_trade={nt}, skipped={sk})")

    D = results['D']
    print(f"\n  [TEST] Period D: {D['bc']}/{D['bt']} = {D['bi']*100:.1f}% (no_trade={D['nt']})")
    print(f"\n  Day-by-day:")
    for d in D['det']:
        if d.get('no_trade'):
            print(f"    {d['date']} risk={d['risk']} NO-TRADE idx={d['idx_ret']:+.2f}%")
        else:
            m = "WIN" if d['beat'] else "FAIL"
            t = ', '.join(f"{x['name'][:4]}({x['ret']:+.1f}%)" for x in d['top'] if x.get('ret') is not None)
            print(f"    {d['date']} {d['regime']} risk={d['risk']} avg={d['avg_ret']:+.2f}% idx={d['idx_ret']:+.2f}% "
                  f"{m} [{d['n_stocks']}stks] | {t}")

    tr_bi, tr_bc, tr_bt, _, _, _ = evaluate(periods['A']+periods['B'], best_cfg)
    gap = (tr_bi - D['bi'])*100
    print(f"\n  Train: {tr_bc}/{tr_bt}={tr_bi*100:.1f}%  Valid: {results['C']['bc']}/{results['C']['bt']}={results['C']['bi']*100:.1f}%  Test: {D['bc']}/{D['bt']}={D['bi']*100:.1f}%")
    print(f"  Gap: {gap:.1f}pp")

    print(f"\n  Best params: n_rec={best_cfg['n_rec']}, max_ind={best_cfg['max_industry']}, "
          f"min_score={best_cfg['min_score']:.1f}, cd_w={best_cfg['cooldown_weight']:.1f}, "
          f"vol_pen={best_cfg['vol_penalty_weight']:.1f}@{best_cfg['vol_penalty_threshold']:.1f}, "
          f"trend_bonus={best_cfg['trend_bonus']:.1f}")

    # Save
    os.makedirs(RESULT_DIR, exist_ok=True)
    final = {
        'version': 'v27b', 'timestamp': datetime.now().isoformat(),
        'train': {'beat_idx': tr_bi, 'days': tr_bt},
        'valid': {'beat_idx': results['C']['bi'], 'days': results['C']['bt']},
        'test': {'beat_idx': D['bi'], 'days': D['bt'], 'no_trade': D['nt']},
        'params': {k: v for k, v in best_cfg.items() if k not in ('weights_bull','weights_range','weights_bear')},
        'test_details': D['det'],
        'comparison': {'v25': 76.9, 'v26': 50.0, 'v27b': round(D['bi']*100, 1)},
        'elapsed_s': time.time()-t0,
    }
    def conv(o):
        if isinstance(o, (np.bool_,)): return bool(o)
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, dict): return {k:conv(v) for k,v in o.items()}
        if isinstance(o, list): return [conv(v) for v in o]
        return o
    final = conv(final)
    with open(os.path.join(RESULT_DIR, 'backtest_v27b.json'), 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    # Save params
    params_out = {'version': 'v27b', 'timestamp': datetime.now().isoformat(),
                  'test_beat_idx': D['bi'], 'params': final['params']}
    with open(os.path.join(SHARED_DATA_DIR, 'optuna_v27b_best_params.json'), 'w', encoding='utf-8') as f:
        json.dump(params_out, f, ensure_ascii=False, indent=2)

    print(f"\n  Total: {time.time()-t0:.0f}s")
    print("="*70)

if __name__ == '__main__':
    main()

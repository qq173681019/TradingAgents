"""V20 Backtest Patch Script - Apply all 4 fixes to V19 to create V20"""
import re

SRC = r'D:\GitHub\TradingAgents\TradingAgent\backtest_v20_fixed.py'

with open(SRC, 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# Fix 1: T+1 returns (get_stock_return + get_index_return)
# ============================================================
old_get_stock = '''def get_stock_return(df, date):
    prev = df[df['date'] < date]
    day = df[df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None

def get_index_return(index_df, date):
    prev = index_df[index_df['date'] < date]
    day = index_df[index_df['date'] >= date]
    if len(prev) == 0 or len(day) == 0:
        return None
    try:
        return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
    except:
        return None'''

new_get_stock = '''def get_stock_return(df, date):
    """T+1 return: buy at test_date close, sell at next trading day close"""
    day_rows = df[df['date'] >= date]
    if len(day_rows) < 2:
        return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None

def get_index_return(index_df, date):
    """T+1 return: aligned with stock_return"""
    day_rows = index_df[index_df['date'] >= date]
    if len(day_rows) < 2:
        return None
    try:
        buy_price = float(day_rows.iloc[0]['close'])
        sell_price = float(day_rows.iloc[1]['close'])
        return (sell_price - buy_price) / buy_price * 100
    except:
        return None'''

assert old_get_stock in content, "Fix1: get_stock_return not found"
content = content.replace(old_get_stock, new_get_stock)
print("Fix 1 applied: T+1 returns")

# ============================================================
# Fix 2: Multiplicative -> Additive scoring (score_risk2/3/45)
# ============================================================

# --- score_risk2 ---
old_r2 = '''def score_risk2(s, p):
    score = (
        s['momentum_s'] * p['w_momentum'] +
        s['trend_s'] * p['w_trend'] +
        s['consistency_s'] * p['w_consistency'] +
        s['vol_s'] * p['w_vol'] +
        s['rsi_s'] * p['w_rsi'] +
        s['static_score'] * p['w_static'] +
        s['defense_s'] * p['w_defense'] +
        s['sector_heat'] * p['w_sector'] +
        s['low_vol_s'] * p['w_low_vol'] +
        s['rel_str'] * p['w_rel_str'] +
        s['rel_str_3d'] * p['w_rel_str_3d']
    )
    if s['consistency'] >= 4: score *= p['boost_consistency']
    if s['close_ma20'] > 0: score *= p['boost_above_ma20']
    if 45 <= s['rsi'] <= 60: score *= p['boost_rsi_45_60']
    if s['ind_heat'] > 1.5: score *= p['boost_sector_hot']
    if s['rel_str'] > 2: score *= p['boost_rel_str']
    if s['close_ma20'] < -0.05: score *= p['penalty_below_ma20']
    if s['vol5'] > 3.5: score *= p['penalty_high_vol']
    if s['rsi'] > 70: score *= p['penalty_rsi_overbought']
    if abs(s['r1']) > 5: score *= p['penalty_big_move']
    if s['streak'] <= -2: score *= p['penalty_streak_neg']
    if s['vol_shrink'] < 0.7: score *= p['penalty_vol_shrink']
    if s['turn_spike'] > 2.0: score *= p['penalty_turn_spike']
    if s['close_ma5'] < -0.02: score *= p['penalty_below_ma5']
    return score'''

new_r2 = '''def score_risk2(s, p):
    """V20 Risk2: additive bonus/penalty (not multiplicative)"""
    score = (
        s['momentum_s'] * p['w_momentum'] +
        s['trend_s'] * p['w_trend'] +
        s['consistency_s'] * p['w_consistency'] +
        s['vol_s'] * p['w_vol'] +
        s['rsi_s'] * p['w_rsi'] +
        s['static_score'] * p['w_static'] +
        s['defense_s'] * p['w_defense'] +
        s['sector_heat'] * p['w_sector'] +
        s['low_vol_s'] * p['w_low_vol'] +
        s['rel_str'] * p['w_rel_str'] +
        s['rel_str_3d'] * p['w_rel_str_3d']
    )
    if s['consistency'] >= 4: score += p['b_consistency']
    if s['close_ma20'] > 0: score += p['b_above_ma20']
    if 45 <= s['rsi'] <= 60: score += p['b_rsi_45_60']
    if s['ind_heat'] > 1.5: score += p['b_sector_hot']
    if s['rel_str'] > 2: score += p['b_rel_str']
    if s['close_ma20'] < -0.05: score -= p['p_below_ma20']
    if s['vol5'] > 3.5: score -= p['p_high_vol']
    if s['rsi'] > 70: score -= p['p_rsi_overbought']
    if abs(s['r1']) > 5: score -= p['p_big_move']
    if s['streak'] <= -2: score -= p['p_streak_neg']
    if s['vol_shrink'] < 0.7: score -= p['p_vol_shrink']
    if s['turn_spike'] > 2.0: score -= p['p_turn_spike']
    if s['close_ma5'] < -0.02: score -= p['p_below_ma5']
    return score'''

assert old_r2 in content, "Fix2: score_risk2 not found"
content = content.replace(old_r2, new_r2)

# --- score_risk3 ---
old_r3_mults = [
    ("if s['consistency'] >= 4: score *= p['consistency_boost_high']\n    elif s['consistency'] >= 3: score *= p['consistency_boost_mid']",
     "if s['consistency'] >= 4: score += p['b_consistency_high']\n    elif s['consistency'] >= 3: score += p['b_consistency_mid']"),
    ("if s['r3'] > 0 and s['r5'] > 0: score *= p['uptrend_boost_full']\n    elif s['r3'] > 0: score *= p['uptrend_boost_partial']",
     "if s['r3'] > 0 and s['r5'] > 0: score += p['b_uptrend_full']\n    elif s['r3'] > 0: score += p['b_uptrend_partial']"),
    ("if s['close_ma20'] > 0: score *= p['ma20_above_mult']\n    elif s['close_ma20'] < -0.05: score *= p['ma20_below_mult']",
     "if s['close_ma20'] > 0: score += p['b_ma20_above']\n    elif s['close_ma20'] < -0.05: score -= p['p_ma20_below']"),
    ("if s['vol5'] < 1.5: score *= p['low_vol_mult_high']\n    elif s['vol5'] < 2.0: score *= p['low_vol_mult_mid']\n    elif s['vol5'] > 3.5: score *= p['high_vol_penalize']",
     "if s['vol5'] < 1.5: score += p['b_low_vol_high']\n    elif s['vol5'] < 2.0: score += p['b_low_vol_mid']\n    elif s['vol5'] > 3.5: score -= p['p_high_vol']"),
    ("if s['rsi'] > 75: score *= p['rsi_overbought_mult']\n    elif s['rsi'] > 65: score *= p['rsi_high_mult']\n    elif 45 <= s['rsi'] <= 60: score *= p['rsi_sweet_mult']",
     "if s['rsi'] > 75: score -= p['p_rsi_overbought']\n    elif s['rsi'] > 65: score -= p['p_rsi_high']\n    elif 45 <= s['rsi'] <= 60: score += p['b_rsi_sweet']"),
    ("if s['ind_heat'] > 2: score *= p['sector_heat_strong']\n    elif s['ind_heat'] > 0.5: score *= p['sector_heat_mild']\n    elif s['ind_heat'] < -2: score *= p['sector_cold']\n    elif s['ind_heat'] < -0.5: score *= p['sector_cool']",
     "if s['ind_heat'] > 2: score += p['b_sector_strong']\n    elif s['ind_heat'] > 0.5: score += p['b_sector_mild']\n    elif s['ind_heat'] < -2: score -= p['p_sector_cold']\n    elif s['ind_heat'] < -0.5: score -= p['p_sector_cool']"),
    ("if s['rel_str'] > 3: score *= p['rel_str_strong']\n    elif s['rel_str'] > 1: score *= p['rel_str_mild']",
     "if s['rel_str'] > 3: score += p['b_rel_str_strong']\n    elif s['rel_str'] > 1: score += p['b_rel_str_mild']"),
    ("if abs(s['r1']) > 5: score *= p['big_move5_penalize']\n    if abs(s['r1']) > 3: score *= p['big_move3_penalize']",
     "if abs(s['r1']) > 5: score -= p['p_big_move5']\n    if abs(s['r1']) > 3: score -= p['p_big_move3']"),
    ("if s['streak'] <= -2: score *= p['streak_penalize']",
     "if s['streak'] <= -2: score -= p['p_streak']"),
    ("if s['vol_shrink'] < 0.7: score *= p['vol_shrink_penalize']",
     "if s['vol_shrink'] < 0.7: score -= p['p_vol_shrink']"),
    ("if s['turn_spike'] > 2.0: score *= p['turn_spike_penalize']",
     "if s['turn_spike'] > 2.0: score -= p['p_turn_spike']"),
    ("if s['close_ma5'] < -0.02: score *= p['ma5_below_penalize']",
     "if s['close_ma5'] < -0.02: score -= p['p_ma5_below']"),
]

for old, new in old_r3_mults:
    assert old in content, f"Fix2: score_risk3 fragment not found: {old[:40]}"
    content = content.replace(old, new)

# --- score_risk45 ---
old_r45_mults = [
    ("if s['beta'] > 1.5: score *= p['penalty_beta_high']\n    elif s['beta'] > 1.2: score *= p['penalty_beta_mid']\n    elif s['beta'] < 0.5: score *= p['boost_beta_low']",
     "if s['beta'] > 1.5: score -= p['p_beta_high']\n    elif s['beta'] > 1.2: score -= p['p_beta_mid']\n    elif s['beta'] < 0.5: score += p['b_beta_low']"),
    ("if s['oversold']: score *= p['boost_oversold']",
     "if s['oversold']: score += p['b_oversold']"),
    ("if s['overbought']: score *= p['penalty_overbought']",
     "if s['overbought']: score -= p['p_overbought']"),
    ("if s['is_high_beta']: score *= p['penalty_high_beta_ind']",
     "if s['is_high_beta']: score -= p['p_high_beta_ind']"),
    ("if s['is_defensive']: score *= p['boost_defensive_ind']",
     "if s['is_defensive']: score += p['b_defensive_ind']"),
    ("if s['rel_str'] > 3: score *= p['boost_rel_str_strong']\n    if s['rel_str'] > 5: score *= p['boost_rel_str_very_strong']",
     "if s['rel_str'] > 3: score += p['b_rel_str_strong']\n    if s['rel_str'] > 5: score += p['b_rel_str_very_strong']"),
    ("if s['vol5'] < 1.5: score *= p['boost_low_vol']",
     "if s['vol5'] < 1.5: score += p['b_low_vol']"),
    ("if s['r1'] < -5: score *= p['penalty_big_drop']",
     "if s['r1'] < -5: score -= p['p_big_drop']"),
    ("if s['r3'] < -8: score *= p['penalty_big_drop_3d']",
     "if s['r3'] < -8: score -= p['p_big_drop_3d']"),
    ("if s['r1'] > 7: score *= p['penalty_big_jump']",
     "if s['r1'] > 7: score -= p['p_big_jump']"),
    ("if s['r3'] > 15: score *= p['penalty_overextended']",
     "if s['r3'] > 15: score -= p['p_overextended']"),
    ("if s['streak'] >= 2 and s['rel_str'] > 0: score *= p['boost_streak_relstr']",
     "if s['streak'] >= 2 and s['rel_str'] > 0: score += p['b_streak_relstr']"),
]

for old, new in old_r45_mults:
    assert old in content, f"Fix2: score_risk45 fragment not found: {old[:40]}"
    content = content.replace(old, new)

print("Fix 2 applied: Additive scoring")

# ============================================================
# Fix 3: Real static scores (not all 5.0)
# ============================================================
old_load_scores = '''def _load_scores():
    import glob
    score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
    if not os.path.exists(score_file):
        all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
        if all_sf:
            score_file = max(all_sf, key=lambda x: os.path.getsize(x))
    
    scores = {}
    if score_file and os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            sd = json.load(f)
        for code, s in sd.items():
            if not isinstance(s, dict):
                continue
            clean = normalize_code(code)
            scores[clean] = {
                'tech': 5.0, 'fund': 5.0, 'chip': 5.0, 'sector': 5.0,
                'name': s.get('name', ''),
                'industry': s.get('industry', 'unknown'),
                'sector_change': 0.0,
            }
    print(f"  Scores: {len(scores)} stocks")
    return scores'''

new_load_scores = '''def _load_scores():
    """V20: Load real static scores (not hardcoded 5.0)"""
    import glob
    
    # Priority: latest optimized file with real scores
    opt_pattern = os.path.join(DATA_DIR, 'batch_stock_scores_optimized_*.json')
    opt_files = sorted(glob.glob(opt_pattern), key=lambda x: (os.path.getsize(x) > 100000, os.path.getmtime(x)), reverse=True)
    
    scores = {}
    loaded_from = None
    
    for score_file in opt_files:
        if os.path.getsize(score_file) < 100000:
            continue
        try:
            with open(score_file, 'r', encoding='utf-8') as f:
                sd = json.load(f)
            for code, s in sd.items():
                if not isinstance(s, dict):
                    continue
                clean = normalize_code(code)
                scores[clean] = {
                    'tech': float(s.get('short_term_score', 5.0)),
                    'fund': float(s.get('long_term_score', 5.0)),
                    'chip': float(s.get('chip_score', 5.0)),
                    'sector': float(s.get('hot_sector_score', 5.0)),
                    'name': s.get('name', ''),
                    'industry': s.get('industry', s.get('matched_sector', 'unknown')),
                    'sector_change': float(s.get('sector_change', 0.0)),
                }
            loaded_from = os.path.basename(score_file)
            break
        except:
            continue
    
    if not scores:
        score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
        if not os.path.exists(score_file):
            all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
            if all_sf:
                score_file = max(all_sf, key=lambda x: os.path.getsize(x))
        if os.path.exists(score_file):
            loaded_from = os.path.basename(score_file)
            with open(score_file, 'r', encoding='utf-8') as f:
                sd = json.load(f)
            for code, s in sd.items():
                if not isinstance(s, dict):
                    continue
                clean = normalize_code(code)
                scores[clean] = {
                    'tech': float(s.get('short_term_score', 5.0)),
                    'fund': float(s.get('long_term_score', 5.0)),
                    'chip': float(s.get('chip_score', 5.0)),
                    'sector': float(s.get('hot_sector_score', 5.0)),
                    'name': s.get('name', ''),
                    'industry': s.get('industry', 'unknown'),
                    'sector_change': 0.0,
                }
    
    if scores:
        tech_v = [v['tech'] for v in scores.values()]
        fund_v = [v['fund'] for v in scores.values()]
        chip_v = [v['chip'] for v in scores.values()]
        sec_v = [v['sector'] for v in scores.values()]
        print(f"  Scores: {len(scores)} stocks (from {loaded_from})")
        print(f"    tech: mean={np.mean(tech_v):.2f} std={np.std(tech_v):.2f}")
        print(f"    fund: mean={np.mean(fund_v):.2f} std={np.std(fund_v):.2f}")
        print(f"    chip: mean={np.mean(chip_v):.2f} std={np.std(chip_v):.2f}")
        print(f"    sector: mean={np.mean(sec_v):.2f} std={np.std(sec_v):.2f}")
    else:
        print(f"  Scores: 0 stocks (WARNING)")
    
    return scores'''

assert old_load_scores in content, "Fix3: _load_scores not found"
content = content.replace(old_load_scores, new_load_scores)
print("Fix 3 applied: Real static scores")

# ============================================================
# Fix 4: Always dynamic sector heat
# ============================================================
old_sector = '''        # Dynamic sector heat
        if regime == 'range':
            dynamic_sector_heat = defaultdict(list)
            for code, df in kline.items():
                static = scores.get(code, None)
                if static is None: continue
                industry = static.get('industry', 'unknown')
                s_hist = df[df['date'] < test_date]
                s_closes = s_hist['close'].values
                if len(s_closes) >= 4:
                    ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                    dynamic_sector_heat[industry].append(ret_3d)
            daily_sector_avg = {ind: float(np.mean(rets)) for ind, rets in dynamic_sector_heat.items() if len(rets) >= 3}
        else:
            daily_sector_avg = sector_avg'''

new_sector = '''        # Dynamic sector heat (V20: always dynamic, fallback to static)
        dynamic_sector_heat = defaultdict(list)
        for code, df in kline.items():
            static = scores.get(code, None)
            if static is None: continue
            industry = static.get('industry', 'unknown')
            s_hist = df[df['date'] < test_date]
            s_closes = s_hist['close'].values
            if len(s_closes) >= 4:
                ret_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100
                dynamic_sector_heat[industry].append(ret_3d)
        daily_sector_avg = {ind: float(np.mean(rets)) for ind, rets in dynamic_sector_heat.items() if len(rets) >= 3}
        if not daily_sector_avg:
            daily_sector_avg = sector_avg'''

assert old_sector in content, "Fix4: sector heat block not found"
content = content.replace(old_sector, new_sector)
print("Fix 4 applied: Always dynamic sector heat")

# ============================================================
# Fix 5: Update Optuna param keys (multiplicative -> additive names)
# ============================================================

# R2 params
old_r2_mult_keys = """    MULT_KEYS = [
        'boost_consistency', 'boost_above_ma20', 'boost_rsi_45_60',
        'boost_sector_hot', 'boost_rel_str',
        'penalty_below_ma20', 'penalty_high_vol', 'penalty_rsi_overbought',
        'penalty_big_move', 'penalty_streak_neg', 'penalty_vol_shrink',
        'penalty_turn_spike', 'penalty_below_ma5',
    ]
    MULT_RANGES = {
        'boost_consistency': (1.0, 2.0), 'boost_above_ma20': (0.8, 1.8),
        'boost_rsi_45_60': (0.8, 1.5), 'boost_sector_hot': (0.8, 1.8),
        'boost_rel_str': (0.8, 1.8),
        'penalty_below_ma20': (0.1, 0.8), 'penalty_high_vol': (0.1, 0.8),
        'penalty_rsi_overbought': (0.1, 0.8), 'penalty_big_move': (0.1, 0.8),
        'penalty_streak_neg': (0.1, 0.8), 'penalty_vol_shrink': (0.2, 1.0),
        'penalty_turn_spike': (0.2, 1.0), 'penalty_below_ma5': (0.2, 1.0),
    }"""

new_r2_mult_keys = """    MULT_KEYS = [
        'b_consistency', 'b_above_ma20', 'b_rsi_45_60',
        'b_sector_hot', 'b_rel_str',
        'p_below_ma20', 'p_high_vol', 'p_rsi_overbought',
        'p_big_move', 'p_streak_neg', 'p_vol_shrink',
        'p_turn_spike', 'p_below_ma5',
    ]
    MULT_RANGES = {
        'b_consistency': (0.05, 0.8), 'b_above_ma20': (0.05, 0.5),
        'b_rsi_45_60': (0.05, 0.5), 'b_sector_hot': (0.05, 0.6),
        'b_rel_str': (0.05, 0.5),
        'p_below_ma20': (0.05, 0.8), 'p_high_vol': (0.05, 0.8),
        'p_rsi_overbought': (0.05, 0.8), 'p_big_move': (0.05, 0.6),
        'p_streak_neg': (0.05, 0.5), 'p_vol_shrink': (0.05, 0.5),
        'p_turn_spike': (0.05, 0.5), 'p_below_ma5': (0.05, 0.5),
    }"""

assert old_r2_mult_keys in content, "Fix5: R2 mult keys not found"
content = content.replace(old_r2_mult_keys, new_r2_mult_keys)

# R3 params
old_r3_mult_keys = """    MULT_KEYS = [
        'consistency_boost_high', 'consistency_boost_mid',
        'uptrend_boost_full', 'uptrend_boost_partial',
        'ma20_above_mult', 'ma20_below_mult',
        'low_vol_mult_high', 'low_vol_mult_mid', 'high_vol_penalize',
        'rsi_overbought_mult', 'rsi_high_mult', 'rsi_sweet_mult',
        'sector_heat_strong', 'sector_heat_mild', 'sector_cold', 'sector_cool',
        'rel_str_strong', 'rel_str_mild',
        'big_move5_penalize', 'big_move3_penalize',
        'streak_penalize', 'vol_shrink_penalize', 'turn_spike_penalize',
        'ma5_below_penalize',
    ]
    MULT_RANGES = {
        'consistency_boost_high': (1.0, 2.5), 'consistency_boost_mid': (0.8, 1.8),
        'uptrend_boost_full': (1.0, 2.0), 'uptrend_boost_partial': (0.8, 1.5),
        'ma20_above_mult': (0.8, 1.8), 'ma20_below_mult': (0.2, 0.9),
        'low_vol_mult_high': (1.0, 1.8), 'low_vol_mult_mid': (0.8, 1.3),
        'high_vol_penalize': (0.05, 0.5),
        'rsi_overbought_mult': (0.05, 0.5), 'rsi_high_mult': (0.3, 1.0),
        'rsi_sweet_mult': (0.8, 1.8),
        'sector_heat_strong': (0.8, 1.5), 'sector_heat_mild': (0.8, 1.5),
        'sector_cold': (0.01, 0.5), 'sector_cool': (0.2, 0.8),
        'rel_str_strong': (1.0, 2.0), 'rel_str_mild': (0.8, 1.5),
        'big_move5_penalize': (0.05, 0.5), 'big_move3_penalize': (0.3, 1.0),
        'streak_penalize': (0.1, 0.8),
        'vol_shrink_penalize': (0.1, 0.8), 'turn_spike_penalize': (0.2, 1.0),
        'ma5_below_penalize': (0.2, 0.9),
    }"""

new_r3_mult_keys = """    MULT_KEYS = [
        'b_consistency_high', 'b_consistency_mid',
        'b_uptrend_full', 'b_uptrend_partial',
        'b_ma20_above', 'p_ma20_below',
        'b_low_vol_high', 'b_low_vol_mid', 'p_high_vol',
        'p_rsi_overbought', 'p_rsi_high', 'b_rsi_sweet',
        'b_sector_strong', 'b_sector_mild', 'p_sector_cold', 'p_sector_cool',
        'b_rel_str_strong', 'b_rel_str_mild',
        'p_big_move5', 'p_big_move3',
        'p_streak', 'p_vol_shrink', 'p_turn_spike',
        'p_ma5_below',
    ]
    MULT_RANGES = {
        'b_consistency_high': (0.05, 0.8), 'b_consistency_mid': (0.05, 0.5),
        'b_uptrend_full': (0.05, 0.6), 'b_uptrend_partial': (0.05, 0.4),
        'b_ma20_above': (0.05, 0.5), 'p_ma20_below': (0.05, 0.8),
        'b_low_vol_high': (0.05, 0.5), 'b_low_vol_mid': (0.05, 0.3), 'p_high_vol': (0.05, 0.8),
        'p_rsi_overbought': (0.05, 0.8), 'p_rsi_high': (0.05, 0.5), 'b_rsi_sweet': (0.05, 0.5),
        'b_sector_strong': (0.05, 0.5), 'b_sector_mild': (0.05, 0.3),
        'p_sector_cold': (0.05, 0.8), 'p_sector_cool': (0.05, 0.5),
        'b_rel_str_strong': (0.05, 0.6), 'b_rel_str_mild': (0.05, 0.4),
        'p_big_move5': (0.05, 0.8), 'p_big_move3': (0.05, 0.5),
        'p_streak': (0.05, 0.6),
        'p_vol_shrink': (0.05, 0.5), 'p_turn_spike': (0.05, 0.5),
        'p_ma5_below': (0.05, 0.6),
    }"""

assert old_r3_mult_keys in content, "Fix5: R3 mult keys not found"
content = content.replace(old_r3_mult_keys, new_r3_mult_keys)

# R45 params
old_r45_mult_keys = """    MULT_KEYS = [
        'penalty_beta_high', 'penalty_beta_mid', 'boost_beta_low',
        'boost_oversold', 'penalty_overbought',
        'penalty_high_beta_ind', 'boost_defensive_ind',
        'boost_rel_str_strong', 'boost_rel_str_very_strong',
        'boost_low_vol', 'penalty_big_drop', 'penalty_big_drop_3d',
        'penalty_big_jump', 'penalty_overextended', 'boost_streak_relstr',
    ]
    MULT_RANGES = {
        'penalty_beta_high': (0.05, 0.7), 'penalty_beta_mid': (0.2, 0.9),
        'boost_beta_low': (1.0, 1.8), 'boost_oversold': (0.8, 1.8),
        'penalty_overbought': (0.05, 0.5), 'penalty_high_beta_ind': (0.05, 0.7),
        'boost_defensive_ind': (1.0, 1.8), 'boost_rel_str_strong': (1.0, 1.8),
        'boost_rel_str_very_strong': (0.8, 1.8), 'boost_low_vol': (0.8, 1.8),
        'penalty_big_drop': (0.05, 0.5), 'penalty_big_drop_3d': (0.05, 0.5),
        'penalty_big_jump': (0.05, 0.5), 'penalty_overextended': (0.05, 0.7),
        'boost_streak_relstr': (0.8, 1.4),
    }"""

new_r45_mult_keys = """    MULT_KEYS = [
        'p_beta_high', 'p_beta_mid', 'b_beta_low',
        'b_oversold', 'p_overbought',
        'p_high_beta_ind', 'b_defensive_ind',
        'b_rel_str_strong', 'b_rel_str_very_strong',
        'b_low_vol', 'p_big_drop', 'p_big_drop_3d',
        'p_big_jump', 'p_overextended', 'b_streak_relstr',
    ]
    MULT_RANGES = {
        'p_beta_high': (0.05, 0.8), 'p_beta_mid': (0.05, 0.5),
        'b_beta_low': (0.05, 0.5), 'b_oversold': (0.05, 0.6),
        'p_overbought': (0.05, 0.8), 'p_high_beta_ind': (0.05, 0.8),
        'b_defensive_ind': (0.05, 0.6), 'b_rel_str_strong': (0.05, 0.6),
        'b_rel_str_very_strong': (0.05, 0.5), 'b_low_vol': (0.05, 0.5),
        'p_big_drop': (0.05, 0.8), 'p_big_drop_3d': (0.05, 0.6),
        'p_big_jump': (0.05, 0.6), 'p_overextended': (0.05, 0.8),
        'b_streak_relstr': (0.05, 0.4),
    }"""

assert old_r45_mult_keys in content, "Fix5: R45 mult keys not found"
content = content.replace(old_r45_mult_keys, new_r45_mult_keys)
print("Fix 5 applied: Optuna param keys updated")

# ============================================================
# Fix 6: Version strings
# ============================================================
content = content.replace('V17 - Robust Multi-Period Optimization (Anti-Overfitting)',
    'V20 - Fixed Backtest (T+1 + Additive Scoring + Real Static + Dynamic Sector)')
content = content.replace("'v19-sector-focused'", "'v20-fixed-backtest'")
content = content.replace("'Sector-focused multi-period optimization (AI/chip/semiconductor/solar/power)'",
    "'T+1 returns + additive scoring + real static scores + dynamic sector heat'")
content = content.replace("'backtest_v19_sector.json'", "'backtest_v20_fixed.json'")
content = content.replace("'optuna_v19_best_params.json'", "'optuna_v20_best_params.json'")
content = content.replace("print(\"V19 - Sector-Focused Multi-Period Optimization\")",
    "print(\"V20 - Fixed Backtest\")")

# Fix the comparison section
content = content.replace(
    "v19_full_bi = full_result['beat_idx_pct'] * 100\n    v17_full_bi = 73.5  # V17 known baseline",
    "v20_full_bi = full_result['beat_idx_pct'] * 100\n    v19_full_bi = 86.2  # V19 baseline (with issues)\n    v17_full_bi = 73.5")

content = content.replace("'v19_full_beat_idx': v19_full_bi,\n            'v17_beat_idx': v17_full_bi,",
    "'v20_full_beat_idx': v20_full_bi,\n            'v19_full_beat_idx': v19_full_bi,\n            'v17_beat_idx': v17_full_bi,")

content = content.replace("success = v19_full_bi > v17_full_bi",
    "success = v20_full_bi > v17_full_bi")

content = content.replace("print(f\"\\n  SUCCESS: {'YES!' if success else 'NO'} (V19={v19_full_bi:.1f}% vs V17={v17_full_bi:.1f}%)\")",
    "print(f\"\\n  RESULT: V20={v20_full_bi:.1f}% vs V19={v19_full_bi:.1f}% vs V17={v17_full_bi:.1f}%\")")

print("Fix 6 applied: Version strings updated")

# ============================================================
# Write result
# ============================================================
with open(SRC, 'w', encoding='utf-8') as f:
    f.write(content)

print("\nAll fixes applied successfully!")
print(f"File: {SRC}")

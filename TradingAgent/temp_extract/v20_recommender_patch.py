"""Patch daily_recommender.py - V20 additive scoring + V20 params"""

SRC = r'D:\GitHub\TradingAgents\TradingAgent\daily_recommender.py'

with open(SRC, 'r', encoding='utf-8') as f:
    c = f.read()

# ============================================================
# 1. Update param file paths (V19 -> V20 priority)
# ============================================================
c = c.replace(
    "_V19_PARAMS_PATH = os.path.join(\n    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v19_best_params.json'\n)",
    "_V20_PARAMS_PATH = os.path.join(\n    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v20_best_params.json'\n)"
)
c = c.replace(
    "_V17_PARAMS_PATH = os.path.join(\n    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v17_best_params.json'\n)",
    "_V19_PARAMS_PATH = os.path.join(\n    os.path.dirname(__file__), '..', 'TradingShared', 'data', 'optuna_v19_best_params.json'\n)"
)
print("1. Param paths updated")

# ============================================================
# 2. Update load_v19_params -> load_v20_params
# ============================================================
c = c.replace("def load_v19_params() -> Dict:", "def load_v20_params() -> Dict:")
c = c.replace(
    '"""加载V19 Optuna最优参数，按风险等级分组',
    '"""加载V20 Optuna最优参数（T+1+加法评分+真实静态评分），按风险等级分组'
)
c = c.replace(
    "V19参数来源: backtest_v19_sector.py (板块聚焦多周期优化)",
    "V20参数来源: backtest_v20_fixed.py (修复方法论后的诚实参数)"
)
c = c.replace(
    "- 鲁棒目标: 0.5*mean + 0.3*min + 0.2*(1-var)",
    "- 鲁棒目标: 0.5*mean + 0.3*min + 0.2*(1-var)\\n    - V20改进: T+1收益 + 加法评分 + 真实静态评分 + 动态板块热度"
)
c = c.replace("- Full beat_idx: 86.2%", "- Full beat_idx: 70.5% (V19 was 86.2% but had method issues)")
c = c.replace("- 多期一致性: A=86.4% B=83.3% C=89.5%", "- 多期一致性: A=72.7% B=58.3% C=86.7%")

# Update global cache
c = c.replace("_v19_params = None", "_v20_params = None")
c = c.replace("global _v19_params", "global _v20_params")
c = c.replace("if _v20_params is not None:\n        return _v20_params", "if _v20_params is not None:\n        return _v20_params")

# Update file loading
c = c.replace("if os.path.exists(_V19_PARAMS_PATH):", "if os.path.exists(_V20_PARAMS_PATH):")
c = c.replace("with open(_V19_PARAMS_PATH", "with open(_V20_PARAMS_PATH")
c = c.replace("logger.warning(f\"V19参数文件不存在: {_V19_PARAMS_PATH}\")", 
              "logger.warning(f\"V20参数文件不存在: {_V20_PARAMS_PATH}\")")

# Update dict key access
c = c.replace("_v20_params = {", "_v20_params = {")
c = c.replace("logger.info(f\"V19参数加载成功", "logger.info(f\"V20参数加载成功")

print("2. load function renamed to v20")

# ============================================================
# 3. Update get_v17_params_for_risk to use V20
# ============================================================
c = c.replace(
    '"""根据风险等级获取对应的V19参数组（优先V19，fallback V17）',
    '"""根据风险等级获取参数组（优先V20，fallback V19/V17）'
)
c = c.replace("    # 优先V19\n    v19 = load_v19_params()", "    # 优先V20\n    v20 = load_v20_params()")
c = c.replace(
    """        if risk_level <= 2:
            p = v19.get('r2', {})
        elif risk_level == 3:
            p = v19.get('r3', {})
        else:
            p = v19.get('r45', {})
        if p:
            return p

    # Fallback V17
    v17 = load_v17_params()""",
    """        if risk_level <= 2:
            p = v20.get('r2', {})
        elif risk_level == 3:
            p = v20.get('r3', {})
        else:
            p = v20.get('r45', {})
        if p:
            return p

    # Fallback V19
    v19 = load_v19_params() if 'load_v19_params' in dir() else {}
    if v19:
        if risk_level <= 2:
            return v19.get('r2', {})
        elif risk_level == 3:
            return v19.get('r3', {})
        else:
            return v19.get('r45', {})

    # Fallback V17
    v17 = load_v17_params()"""
)
print("3. get params function updated for V20 priority")

# ============================================================
# 4. Replace scoring functions with additive (V20 style)
# ============================================================

# score_risk2
old_r2_func = '''def score_with_v17_risk2(s: Dict, p: Dict) -> float:
    """V17 Risk2评分（牛市动量策略）
    对应 backtest_v17_robust.py 的 score_risk2()
    """
    score = (
        s['momentum_s'] * p.get('w_momentum', 0.25) +
        s['trend_s'] * p.get('w_trend', 0.20) +
        s['consistency_s'] * p.get('w_consistency', 0.05) +
        s['vol_s'] * p.get('w_vol', 0.10) +
        s['rsi_s'] * p.get('w_rsi', 0.05) +
        s['static_score'] * p.get('w_static', 0.15) +
        s['defense_s'] * p.get('w_defense', 0.05) +
        s['sector_heat'] * p.get('w_sector', 0.10) +
        s['low_vol_s'] * p.get('w_low_vol', 0.05) +
        s['rel_str'] * p.get('w_rel_str', 0.0) +
        s['rel_str_3d'] * p.get('w_rel_str_3d', 0.0)
    )
    # 乘数（boost/penalty）
    if s['consistency'] >= 4: score *= p.get('boost_consistency', 1.3)
    if s['close_ma20'] > 0: score *= p.get('boost_above_ma20', 1.2)
    if 45 <= s['rsi'] <= 60: score *= p.get('boost_rsi_45_60', 1.1)
    if s['ind_heat'] > 1.5: score *= p.get('boost_sector_hot', 1.3)
    if s['rel_str'] > 2: score *= p.get('boost_rel_str', 1.2)
    if s['close_ma20'] < -0.05: score *= p.get('penalty_below_ma20', 0.5)
    if s['vol5'] > 3.5: score *= p.get('penalty_high_vol', 0.6)
    if s['rsi'] > 70: score *= p.get('penalty_rsi_overbought', 0.7)
    if abs(s['r1']) > 5: score *= p.get('penalty_big_move', 0.5)
    if s['streak'] <= -2: score *= p.get('penalty_streak_neg', 0.6)
    if s['vol_shrink'] < 0.7: score *= p.get('penalty_vol_shrink', 0.8)
    if s['turn_spike'] > 2.0: score *= p.get('penalty_turn_spike', 0.7)
    if s['close_ma5'] < -0.02: score *= p.get('penalty_below_ma5', 0.8)
    return score'''

new_r2_func = '''def score_with_v17_risk2(s: Dict, p: Dict) -> float:
    """V20 Risk2: additive bonus/penalty (replaces multiplicative V17)"""
    score = (
        s['momentum_s'] * p.get('w_momentum', 0.25) +
        s['trend_s'] * p.get('w_trend', 0.20) +
        s['consistency_s'] * p.get('w_consistency', 0.05) +
        s['vol_s'] * p.get('w_vol', 0.10) +
        s['rsi_s'] * p.get('w_rsi', 0.05) +
        s['static_score'] * p.get('w_static', 0.15) +
        s['defense_s'] * p.get('w_defense', 0.05) +
        s['sector_heat'] * p.get('w_sector', 0.10) +
        s['low_vol_s'] * p.get('w_low_vol', 0.05) +
        s['rel_str'] * p.get('w_rel_str', 0.0) +
        s['rel_str_3d'] * p.get('w_rel_str_3d', 0.0)
    )
    # V20: Additive bonus/penalty
    if s['consistency'] >= 4: score += p.get('b_consistency', 0.3)
    if s['close_ma20'] > 0: score += p.get('b_above_ma20', 0.2)
    if 45 <= s['rsi'] <= 60: score += p.get('b_rsi_45_60', 0.1)
    if s['ind_heat'] > 1.5: score += p.get('b_sector_hot', 0.3)
    if s['rel_str'] > 2: score += p.get('b_rel_str', 0.2)
    if s['close_ma20'] < -0.05: score -= p.get('p_below_ma20', 0.5)
    if s['vol5'] > 3.5: score -= p.get('p_high_vol', 0.4)
    if s['rsi'] > 70: score -= p.get('p_rsi_overbought', 0.3)
    if abs(s['r1']) > 5: score -= p.get('p_big_move', 0.5)
    if s['streak'] <= -2: score -= p.get('p_streak_neg', 0.4)
    if s['vol_shrink'] < 0.7: score -= p.get('p_vol_shrink', 0.2)
    if s['turn_spike'] > 2.0: score -= p.get('p_turn_spike', 0.3)
    if s['close_ma5'] < -0.02: score -= p.get('p_below_ma5', 0.2)
    return score'''

assert old_r2_func in c, "R2 function not found!"
c = c.replace(old_r2_func, new_r2_func)
print("4a. score_risk2 -> additive")

# score_risk3 - replace all multiplicative lines
r3_mult_replacements = [
    ("if s['consistency'] >= 4: score *= p.get('consistency_boost_high', 2.46)\n    elif s['consistency'] >= 3: score *= p.get('consistency_boost_mid', 1.17)",
     "if s['consistency'] >= 4: score += p.get('b_consistency_high', 0.5)\n    elif s['consistency'] >= 3: score += p.get('b_consistency_mid', 0.2)"),
    ("if s['r3'] > 0 and s['r5'] > 0: score *= p.get('uptrend_boost_full', 1.74)\n    elif s['r3'] > 0: score *= p.get('uptrend_boost_partial', 0.96)",
     "if s['r3'] > 0 and s['r5'] > 0: score += p.get('b_uptrend_full', 0.4)\n    elif s['r3'] > 0: score += p.get('b_uptrend_partial', 0.2)"),
    ("if s['close_ma20'] > 0: score *= p.get('ma20_above_mult', 1.21)\n    elif s['close_ma20'] < -0.05: score *= p.get('ma20_below_mult', 0.50)",
     "if s['close_ma20'] > 0: score += p.get('b_ma20_above', 0.2)\n    elif s['close_ma20'] < -0.05: score -= p.get('p_ma20_below', 0.5)"),
    ("if s['vol5'] < 1.5: score *= p.get('low_vol_mult_high', 1.25)\n    elif s['vol5'] < 2.0: score *= p.get('low_vol_mult_mid', 0.92)\n    elif s['vol5'] > 3.5: score *= p.get('high_vol_penalize', 0.13)",
     "if s['vol5'] < 1.5: score += p.get('b_low_vol_high', 0.3)\n    elif s['vol5'] < 2.0: score += p.get('b_low_vol_mid', 0.1)\n    elif s['vol5'] > 3.5: score -= p.get('p_high_vol', 0.4)"),
    ("if s['rsi'] > 75: score *= p.get('rsi_overbought_mult', 0.17)\n    elif s['rsi'] > 65: score *= p.get('rsi_high_mult', 0.66)\n    elif 45 <= s['rsi'] <= 60: score *= p.get('rsi_sweet_mult', 1.33)",
     "if s['rsi'] > 75: score -= p.get('p_rsi_overbought', 0.5)\n    elif s['rsi'] > 65: score -= p.get('p_rsi_high', 0.3)\n    elif 45 <= s['rsi'] <= 60: score += p.get('b_rsi_sweet', 0.3)"),
    ("if s['ind_heat'] > 2: score *= p.get('sector_heat_strong', 1.02)\n    elif s['ind_heat'] > 0.5: score *= p.get('sector_heat_mild', 1.30)\n    elif s['ind_heat'] < -2: score *= p.get('sector_cold', 0.02)\n    elif s['ind_heat'] < -0.5: score *= p.get('sector_cool', 0.50)",
     "if s['ind_heat'] > 2: score += p.get('b_sector_strong', 0.3)\n    elif s['ind_heat'] > 0.5: score += p.get('b_sector_mild', 0.2)\n    elif s['ind_heat'] < -2: score -= p.get('p_sector_cold', 0.5)\n    elif s['ind_heat'] < -0.5: score -= p.get('p_sector_cool', 0.3)"),
    ("if s['rel_str'] > 3: score *= p.get('rel_str_strong', 1.90)\n    elif s['rel_str'] > 1: score *= p.get('rel_str_mild', 1.27)",
     "if s['rel_str'] > 3: score += p.get('b_rel_str_strong', 0.4)\n    elif s['rel_str'] > 1: score += p.get('b_rel_str_mild', 0.2)"),
    ("if abs(s['r1']) > 5: score *= p.get('big_move5_penalize', 0.10)\n    if abs(s['r1']) > 3: score *= p.get('big_move3_penalize', 0.89)",
     "if abs(s['r1']) > 5: score -= p.get('p_big_move5', 0.5)\n    if abs(s['r1']) > 3: score -= p.get('p_big_move3', 0.2)"),
    ("if s['streak'] <= -2: score *= p.get('streak_penalize', 0.45)",
     "if s['streak'] <= -2: score -= p.get('p_streak', 0.3)"),
    ("if s['vol_shrink'] < 0.7: score *= p.get('vol_shrink_penalize', 0.32)",
     "if s['vol_shrink'] < 0.7: score -= p.get('p_vol_shrink', 0.3)"),
    ("if s['turn_spike'] > 2.0: score *= p.get('turn_spike_penalize', 0.72)",
     "if s['turn_spike'] > 2.0: score -= p.get('p_turn_spike', 0.3)"),
    ("if s['close_ma5'] < -0.02: score *= p.get('ma5_below_penalize', 0.56)",
     "if s['close_ma5'] < -0.02: score -= p.get('p_ma5_below', 0.3)"),
]

for old, new in r3_mult_replacements:
    assert old in c, f"R3 not found: {old[:40]}"
    c = c.replace(old, new)

# Update R3 docstring
c = c.replace(
    "V17 Risk3评分（震荡市均衡策略）\n    对应 backtest_v17_robust.py 的 score_risk3()",
    "V20 Risk3: additive scoring (replaces multiplicative V17)"
)
print("4b. score_risk3 -> additive")

# score_risk45
r45_mult_replacements = [
    ("if s['beta'] > 1.5: score *= p.get('penalty_beta_high', 0.42)\n    elif s['beta'] > 1.2: score *= p.get('penalty_beta_mid', 0.54)\n    elif s['beta'] < 0.5: score *= p.get('boost_beta_low', 0.97)",
     "if s['beta'] > 1.5: score -= p.get('p_beta_high', 0.5)\n    elif s['beta'] > 1.2: score -= p.get('p_beta_mid', 0.3)\n    elif s['beta'] < 0.5: score += p.get('b_beta_low', 0.2)"),
    ("if s['oversold']: score *= p.get('boost_oversold', 1.50)",
     "if s['oversold']: score += p.get('b_oversold', 0.3)"),
    ("if s['overbought']: score *= p.get('penalty_overbought', 0.28)",
     "if s['overbought']: score -= p.get('p_overbought', 0.5)"),
    ("if s['is_high_beta']: score *= p.get('penalty_high_beta_ind', 0.62)",
     "if s['is_high_beta']: score -= p.get('p_high_beta_ind', 0.4)"),
    ("if s['is_defensive']: score *= p.get('boost_defensive_ind', 1.45)",
     "if s['is_defensive']: score += p.get('b_defensive_ind', 0.3)"),
    ("if s['rel_str'] > 3: score *= p.get('boost_rel_str_strong', 1.60)\n    if s['rel_str'] > 5: score *= p.get('boost_rel_str_very_strong', 2.14)",
     "if s['rel_str'] > 3: score += p.get('b_rel_str_strong', 0.4)\n    if s['rel_str'] > 5: score += p.get('b_rel_str_very_strong', 0.3)"),
    ("if s['vol5'] < 1.5: score *= p.get('boost_low_vol', 1.47)",
     "if s['vol5'] < 1.5: score += p.get('b_low_vol', 0.3)"),
    ("if s['r1'] < -5: score *= p.get('penalty_big_drop', 0.46)",
     "if s['r1'] < -5: score -= p.get('p_big_drop', 0.5)"),
    ("if s['r3'] < -8: score *= p.get('penalty_big_drop_3d', 0.40)",
     "if s['r3'] < -8: score -= p.get('p_big_drop_3d', 0.4)"),
    ("if s['r1'] > 7: score *= p.get('penalty_big_jump', 0.22)",
     "if s['r1'] > 7: score -= p.get('p_big_jump', 0.5)"),
    ("if s['r3'] > 15: score *= p.get('penalty_overextended', 0.62)",
     "if s['r3'] > 15: score -= p.get('p_overextended', 0.4)"),
    ("if s['streak'] >= 2 and s['rel_str'] > 0: score *= p.get('boost_streak_relstr', 0.89)",
     "if s['streak'] >= 2 and s['rel_str'] > 0: score += p.get('b_streak_relstr', 0.2)"),
]

for old, new in r45_mult_replacements:
    assert old in c, f"R45 not found: {old[:40]}"
    c = c.replace(old, new)

c = c.replace(
    "V17 Risk4/5评分（熊市防御策略）\n    对应 backtest_v17_robust.py 的 score_risk45()",
    "V20 Risk4/5: additive scoring (replaces multiplicative V17)"
)
print("4c. score_risk45 -> additive")

# ============================================================
# 5. Verify no multiplicative scoring remains
# ============================================================
import re
remaining = re.findall(r'score \*= p\.get\(', c)
if remaining:
    print(f"WARNING: {len(remaining)} multiplicative lines remaining!")
    for m in re.finditer(r'.*score \*= p\.get\(.*', c):
        print(f"  {m.group()[:80]}")
else:
    print("5. Verified: 0 multiplicative lines remaining")

# ============================================================
# Write
# ============================================================
with open(SRC, 'w', encoding='utf-8') as f:
    f.write(c)

print("\nAll patches applied to daily_recommender.py!")

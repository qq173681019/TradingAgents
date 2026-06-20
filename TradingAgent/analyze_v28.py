#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick analysis of V28 backtest results"""
import json, os

fpath = r'D:\GitHub\TradingAgents\TradingAgent\backtest_results\backtest_v28.json'
with open(fpath, 'r', encoding='utf-8') as f:
    d = json.load(f)

td = d.get('test_details', [])
wins = [x for x in td if x.get('beat') == True]
losses = [x for x in td if x.get('beat') == False]
skips = [x for x in td if x.get('action') == 'NO_TRADE']

print(f"=== V28 Test Period Analysis ===")
print(f"Total days: {len(td)}, Wins: {len(wins)}, Losses: {len(losses)}, No-trade: {len(skips)}")
print(f"Test beat_rate: {d['test_result']['beat_idx']*100:.1f}%")
print(f"No-trade signal days: {d['test_result'].get('no_trade_signal', 0)}")
print(f"No-trade regime days: {d['test_result'].get('no_trade_regime', 0)}")

print("\n=== WIN days ===")
for x in wins:
    top = x.get('top', [])
    names = ', '.join(f"{t.get('name','?')[:5]}({t.get('ret','?'):+.1f}%)" for t in top if t.get('ret') is not None)
    print(f"  {x['date']} avg={x.get('avg_ret','?'):+.2f}% idx={x.get('idx_ret','?'):+.2f}% | {names}")

print("\n=== LOSS days ===")
for x in losses:
    top = x.get('top', [])
    names = ', '.join(f"{t.get('name','?')[:5]}({t.get('ret','?'):+.1f}%)" for t in top if t.get('ret') is not None)
    print(f"  {x['date']} avg={x.get('avg_ret','?'):+.2f}% idx={x.get('idx_ret','?'):+.2f}% risk={x.get('risk','?')} | {names}")

print("\n=== NO-TRADE days ===")
for x in skips:
    sigs = x.get('signals', '')[:80]
    print(f"  {x['date']} idx={x.get('idx_ret','?'):+.2f}% | {sigs}")

# Period comparison
print("\n=== Walk-Forward Summary ===")
for p in ['A', 'B', 'C', 'D']:
    pr = d.get('period_results', {}).get(p, {})
    bi = pr.get('beat_rate', 0)
    bc = pr.get('beat_count', 0)
    bt = pr.get('total_days', 0)
    nt = pr.get('no_trade', 0)
    print(f"  Period {p}: {bc}/{bt} = {bi*100:.1f}% (no_trade={nt})")

# What sectors are we picking?
print("\n=== Sector distribution of picks ===")
sector_count = {}
for x in td:
    if x.get('action') == 'NO_TRADE':
        continue
    for t in x.get('top', []):
        # We don't have sector in top, just names
        pass

# Check verification feedback
vf_path = r'D:\GitHub\TradingAgents\TradingAgent\v28_verification_feedback.json'
if os.path.exists(vf_path):
    with open(vf_path, 'r', encoding='utf-8') as f:
        vf = json.load(f)
    print(f"\n=== Verification Feedback ===")
    total = len(vf.get('records', []))
    wins_v = sum(1 for r in vf.get('records', []) if r.get('result') == 'win')
    print(f"  Total verified: {total}, Wins: {wins_v}, Rate: {wins_v/max(total,1)*100:.1f}%")
else:
    print("\n  No verification feedback file found")

#!/usr/bin/env python3
import json

with open('backtest_results/final_validation_result_20260504_231425.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

v9d = data['v9d_result']
enhanced = data['enhanced_result']

print('=== V9d ===')
print(f"  beat_idx: {v9d['beat_idx_pct']*100:.1f}%")
print(f"  R1-R4: {v9d['ne_beat_pct']*100:.1f}%")
print(f"  avg return: {v9d['avg_daily_return']:.2f}%")
print(f"  index return: {v9d['avg_idx_return']:.2f}%")

print()
print('=== By Risk Level ===')
for risk in sorted(v9d['stats_by_risk'].keys()):
    s = v9d['stats_by_risk'][risk]
    total = s['total']
    beat = s['beat_idx']
    rate = beat/total*100 if total > 0 else 0
    print(f"  Risk {risk}: {beat}/{total} = {rate:.0f}%")

print()
print('=== Enhanced ===')
print(f"  beat_idx: {enhanced['beat_idx_pct']*100:.1f}%")
print(f"  R1-R4: {enhanced['ne_beat_pct']*100:.1f}%")

print()
print('=== Analysis ===')
diff = (v9d['beat_idx_pct']-enhanced['beat_idx_pct'])*100
print(f"  Enhanced is WORSE by {diff:.0f}pp")

print()
print('Risk breakdown:')
for risk in ['2','3','4','5']:
    v = v9d['stats_by_risk'].get(risk, {})
    e = enhanced['stats_by_risk'].get(risk, {})
    v_rate = v.get('beat_idx',0)/max(v.get('total',1),1)*100
    e_rate = e.get('beat_idx',0)/max(e.get('total',1),1)*100
    print(f"  Risk {risk}: V9d={v_rate:.0f}% Enhanced={e_rate:.0f}% diff={v_rate-e_rate:.0f}%")

# Key insight: where does V9d fail?
print()
print('=== V9d Failure Points ===')
total_beat = v9d['beat_idx_days']
total_days = v9d['total']
print(f"  Lost days: {total_days - total_beat}/{total_days}")
for risk in sorted(v9d['stats_by_risk'].keys()):
    s = v9d['stats_by_risk'][risk]
    lost = s['total'] - s['beat_idx']
    print(f"  Risk {risk}: lost {lost}/{s['total']} days")

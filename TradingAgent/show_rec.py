import json
d = json.load(open(r'D:\GitHub\TradingAgents\TradingAgent\recommendation_history\v28_recommendation_20260616_dryrun.json', encoding='utf-8'))
print(f"Date: {d['date']}, Regime: {d['market']['regime']}")
for r in d.get('recommendations', []):
    s = r.get('scores', {})
    print(f"  #{r['rank']} {r['code']} {r['name']} | {r['industry']} | total={r['final_score']} trend={s.get('trend',0)} money={s.get('money_flow',0)} sector={s.get('sector',0)} rs={s.get('relative_strength',0)}")

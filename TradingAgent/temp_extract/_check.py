import json, os
d = r'D:\GitHub\TradingAgents\TradingAgent\recommendation_history'
for f in sorted(os.listdir(d)):
    if f.startswith('rec') and f.endswith('.json'):
        data = json.load(open(os.path.join(d, f), 'r', encoding='utf-8'))
        rec = data.get('recommended', [])
        if isinstance(rec, list):
            codes = [(r.get('stock_code','?'), r.get('stock_name','?')) for r in rec]
        else:
            codes = [(rec.get('stock_code','?'), rec.get('stock_name','?'))]
        print(f'{f}: {len(codes)} stocks - {codes}')

import json
with open(r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_6m_2025-10-01_2026-04-07.json','r',encoding='utf-8') as f:
    raw = json.load(f)

for code in raw:
    if '600715' in code:
        print(f'Found: {code}, records: {len(raw[code])}')
        for r in raw[code][-10:]:
            print(f"  {r['date']} close={r['close']} pctChg={r.get('pctChg','?')} turn={r.get('turn','?')}")
        break

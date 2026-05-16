import json, numpy as np, pandas as pd, os
BASE = 'D:/GitHub/TradingAgents/TradingShared/data/kline_cache'
def parse_idx(fp):
    with open(fp,'r',encoding='utf-8') as f: raw=json.load(f)
    recs=[]
    if 'date' in raw and isinstance(raw['date'],dict):
        n=len(raw['date'])
        for i in range(n):
            ts=raw['date'].get(str(i)); cl=float(raw['close'].get(str(i),0))
            if ts is None or cl<=0: continue
            ds=pd.Timestamp(ts,unit='ms').strftime('%Y-%m-%d') if isinstance(ts,(int,float)) else str(ts)
            recs.append({'date':ds,'close':cl})
    return recs
old=os.path.join(BASE,'index_6m_2025-10-08_2026-04-07.json')
new=os.path.join(BASE,'index_full_latest.json')
seen=set(); all_r=[]
for r in parse_idx(old)+parse_idx(new):
    if r['date'] not in seen: seen.add(r['date']); all_r.append(r)
df=pd.DataFrame(all_r)
df['date']=pd.to_datetime(df['date']).dt.tz_localize(None)
df=df.dropna(subset=['close']).sort_values('date').drop_duplicates(subset='date',keep='last')
df['close']=df['close'].astype(float)

# Check for key dates
for td_str in ['2026-04-24','2026-04-28','2026-05-07']:
    test_date = pd.Timestamp(td_str)
    hist = df[df['date'] < test_date]
    closes = hist['close'].values
    n = len(closes)
    print(f'\n=== {td_str} ===')
    for i in range(max(0,n-6), n):
        d = hist.iloc[i]
        dt_str = str(d['date'].date())
        cl = float(d['close'])
        print(f'  {dt_str}: {cl:.2f}')
    if n >= 2:
        prev_ret = (closes[-1] - closes[-2]) / closes[-2] * 100
        print(f'  prev_ret = {prev_ret:+.2f}%  >3.0? {prev_ret > 3.0}')
    # Check consecutive up
    consec_up = 0
    for i in range(n-1, max(0,n-8), -1):
        if closes[i] > closes[i-1]:
            consec_up += 1
        else:
            break
    print(f'  consec_up = {consec_up}')

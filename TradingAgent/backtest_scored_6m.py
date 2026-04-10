#!/usr/bin/env python3
"""
Final strategy: Use scored 199-stock pool + fetch longer history from BaoStock
Key insight: Quality pool > Random pool
"""
import json, os, sys, time, warnings, traceback
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone

warnings.filterwarnings('ignore')

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(WORK_DIR, '..', 'TradingShared', 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'kline_cache')
RANDOM_STATE = 42

# The 199 scored stock codes from the existing cache
OLD_CACHE = os.path.join(CACHE_DIR, 'kline_data_2026-02-20_2026-04-07.json')

print("Loading scored stock codes...", flush=True)
with open(OLD_CACHE, 'r') as f:
    old_data = json.load(f)
scored_codes = list(old_data.keys())
# Add sh./sz. prefix for baostock
scored_codes = [f"sh.{c}" if c.startswith('6') else f"sz.{c}" for c in scored_codes]
print(f"  Scored stocks: {len(scored_codes)}", flush=True)

# Fetch longer history for these stocks
LONG_CACHE = os.path.join(CACHE_DIR, 'kline_scored_6m.json')
if os.path.exists(LONG_CACHE):
    print("Loading 6-month kline cache...", flush=True)
    with open(LONG_CACHE, 'r') as f:
        kline_raw = json.load(f)
    print(f"  Stocks: {len(kline_raw)}", flush=True)
else:
    print("Fetching 6-month K-line for scored stocks...", flush=True)
    import baostock as bs
    bs.login()
    kline_raw = {}
    for i, code in enumerate(scored_codes):
        try:
            rs = bs.query_history_k_data_plus(code,
                "date,open,high,low,close,volume,amount",
                start_date='2025-10-08', end_date='2026-04-07', frequency="d")
            rows = []
            while rs.error_code == '0' and rs.next():
                r = rs.get_row_data()
                if r[0] and float(r[2]) > 0:
                    rows.append({'date': r[0], 'open': float(r[1]),
                        'high': float(r[2]), 'low': float(r[3]),
                        'close': float(r[4]), 'volume': float(r[5]),
                        'amount': float(r[6])})
            if len(rows) >= 30:
                kline_raw[code] = rows
        except: pass
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(scored_codes)}", flush=True)
    bs.logout()
    with open(LONG_CACHE, 'w') as f:
        json.dump(kline_raw, f)
    print(f"  Got {len(kline_raw)} stocks", flush=True)

# Load 6-month index
idx = pd.read_json(os.path.join(DATA_DIR, 'index_6m.json'))
idx['date'] = pd.to_datetime(idx['date'])
idx = idx.sort_values('date').reset_index(drop=True)
print(f"  Index: {len(idx)} days", flush=True)

# Build features
def calc_feat(hist):
    if len(hist) < 20: return None
    c = hist['close'].values.astype(float)
    v = hist['volume'].values.astype(float)
    a = hist['amount'].values.astype(float)
    h = hist['high'].values.astype(float)
    l = hist['low'].values.astype(float)
    f = {}
    for n in [1,2,3,5]:
        if len(c)>n: f[f'r{n}']=(c[-1]-c[-n-1])/c[-n-1]*100
    for n in [5,10,20]:
        if len(c)>=n: f[f'cma{n}']=c[-1]/np.mean(c[-n:])-1
    for n in [5,10]:
        if len(c)>=n+2:
            mn=np.mean(c[-n:]);mp=np.mean(c[-n-2:-2])
            f[f'mas{n}']=(mn-mp)/max(abs(mp),0.01)*100
    if len(c)>=10: f['m5>m10']=int(np.mean(c[-5:])>np.mean(c[-10:]))
    if len(c)>=20:
        f['m5>m20']=int(np.mean(c[-5:])>np.mean(c[-20:]))
        f['m10>m20']=int(np.mean(c[-10:])>np.mean(c[-20:]))
    for w in [5,10]:
        if len(c)>=w+1: f[f'vol{w}']=np.std(np.diff(c[-w-1:])/c[-w-1:-1])*100
    if len(c)>=15:
        vs=np.std(np.diff(c[-6:])/c[-6:-1])*100
        vl=np.std(np.diff(c[-11:])/c[-11:-1])*100
        f['volreg']=vs/max(vl,0.01)
    ww=min(20,len(c))
    f['pos']=(c[-1]-np.min(c[-ww:]))/(np.max(c[-ww:])-np.min(c[-ww:])+0.01)*100
    gains,losses=[],[]
    for i in range(max(0,len(c)-14),len(c)-1):
        chg=(c[i+1]-c[i])/c[i]*100
        gains.append(max(chg,0));losses.append(max(-chg,0))
    f['rsi']=100-100/(1+np.mean(gains)/max(np.mean(losses),0.01))
    if len(v)>=10: f['vr']=np.mean(v[-5:])/max(np.mean(v[-10:]),1)
    streak=0
    for i in range(len(c)-1,max(0,len(c)-10),-1):
        if c[i]>c[i-1]: streak=streak+1 if streak>=0 else 1
        elif c[i]<c[i-1]: streak=streak-1 if streak<=0 else -1
        else: break
    f['streak']=streak
    obv=[0]
    for i in range(1,len(c)):
        if c[i]>c[i-1]: obv.append(obv[-1]+v[i])
        elif c[i]<c[i-1]: obv.append(obv[-1]-v[i])
        else: obv.append(obv[-1])
    obv=np.array(obv,dtype=float)
    if len(obv)>=10: f['obv_trend']=(obv[-1]-obv[-10])/max(abs(obv[-10]),1)
    if len(c)>=6:
        pc=np.sum(np.diff(c[-6:])/c[-6:-1])
        vc=np.mean(v[-5:])/max(np.mean(v[-10:]),1)
        f['vp_div']=pc*vc
    if len(a)>=10: f['amt_tr']=(np.mean(a[-5:])-np.mean(a[-10:-5]))/max(np.mean(a[-10:-5]),1)
    if len(c)>=2:
        body=abs(c[-1]-c[-2])
        f['lshadow']=(min(c[-1],c[-2])-l[-1])/max(body,0.01) if body>0 else 0
        f['ushadow']=(h[-1]-max(c[-1],c[-2]))/max(body,0.01) if body>0 else 0
    if len(c)>=20:
        ma20=np.mean(c[-20:]);std20=np.std(c[-20:])
        f['bb_pos']=(c[-1]-ma20)/(2*std20) if std20>0 else 0
    return f

print("Building dataset...", flush=True)
test_dates = list(pd.date_range('2026-01-05', '2026-04-07', freq='B'))
all_rows = []
for td in test_dates:
    ds = td.strftime('%Y-%m-%d')
    idx_day=idx[(idx['date']>=td)]; idx_prev=idx[(idx['date']<td)]
    if len(idx_day)==0 or len(idx_prev)==0: continue
    ir=(float(idx_day.iloc[0]['close'])-float(idx_prev.iloc[-1]['close']))/float(idx_prev.iloc[-1]['close'])*100
    for code, records in kline_raw.items():
        df=pd.DataFrame(records)
        df['date']=pd.to_datetime(df['date']); df=df.sort_values('date').reset_index(drop=True)
        hist=df[df['date']<td]
        if len(hist)<20: continue
        sd=df[(df['date']>=td)]; sp=df[(df['date']<td)]
        if len(sd)==0 or len(sp)==0: continue
        sr=(float(sd.iloc[0]['close'])-float(sp.iloc[-1]['close']))/float(sp.iloc[-1]['close'])*100
        feat=calc_feat(hist)
        if feat is None: continue
        feat['beat']=1 if sr>ir else 0
        feat['date']=ds; feat['code']=code; feat['ret']=sr; feat['idx']=ir
        all_rows.append(feat)

df=pd.DataFrame(all_rows)
if len(df) == 0:
    print("ERROR: No data! Check kline and index date ranges.", flush=True)
    sys.exit(1)
meta=['beat','date','code','ret','idx']
feat_cols=[c for c in df.columns if c not in meta]
df[feat_cols]=df[feat_cols].fillna(0)
udates=sorted(df['date'].unique())
print(f"Dataset: {len(df)} obs, {len(feat_cols)} features, {len(udates)} days", flush=True)
print(f"Beat rate: {df['beat'].mean()*100:.1f}%", flush=True)

# Walk-forward
def wf_test(model_tpl, top_n, train_window):
    wins,total=0,0
    details=[]
    for i in range(train_window,len(udates)):
        td=udates[i]; trd=udates[i-train_window:i]
        tr=df[df['date'].isin(trd)]; te=df[df['date']==td]
        if len(tr)<100 or len(te)<top_n: continue
        try:
            if len(tr)>3000: tr=tr.sample(3000,random_state=RANDOM_STATE)
            sc=StandardScaler()
            Xtr=sc.fit_transform(tr[feat_cols].values)
            m=clone(model_tpl)
            m.fit(Xtr,tr['beat'].values)
            Xte=sc.transform(te[feat_cols].values)
            if hasattr(m,'predict_proba'):
                p=m.predict_proba(Xte)[:,1]
            else:
                d=m.decision_function(Xte)
                p=(d-d.min())/(d.max()-d.min()+1e-10)
            tec=te.copy();tec['prob']=p
            top=tec.nlargest(min(top_n,len(tec)),'prob')
            ir=top['idx'].iloc[0]
            beat=(top['ret']>ir).sum()
            wr=beat/len(top)
            if wr>0.5: wins+=1
            total+=1
            details.append({'date':td,'wr':wr,'win':wr>0.5,'idx':ir})
        except Exception as e:
            traceback.print_exc()
    return wins,total,details

def ensemble_wf(top_n, train_window):
    models=[
        LogisticRegression(C=0.01,max_iter=500,random_state=RANDOM_STATE),
        LogisticRegression(C=0.1,max_iter=500,random_state=RANDOM_STATE),
        RandomForestClassifier(n_estimators=50,max_depth=3,random_state=RANDOM_STATE),
        GradientBoostingClassifier(n_estimators=30,max_depth=2,random_state=RANDOM_STATE),
    ]
    wins,total=0,0
    details=[]
    for i in range(train_window,len(udates)):
        td=udates[i]; trd=udates[i-train_window:i]
        tr=df[df['date'].isin(trd)]; te=df[df['date']==td]
        if len(tr)<100 or len(te)<top_n: continue
        try:
            if len(tr)>3000: tr=tr.sample(3000,random_state=RANDOM_STATE)
            sc=StandardScaler()
            Xtr=sc.fit_transform(tr[feat_cols].values)
            Xte=sc.transform(te[feat_cols].values)
            ps=np.zeros(len(te))
            for mt in models:
                m=clone(mt);m.fit(Xtr,tr['beat'].values)
                if hasattr(m,'predict_proba'): ps+=m.predict_proba(Xte)[:,1]
                else:
                    d=m.decision_function(Xte)
                    ps+=(d-d.min())/(d.max()-d.min()+1e-10)
            tec=te.copy();tec['prob']=ps/len(models)
            top=tec.nlargest(min(top_n,len(tec)),'prob')
            ir=top['idx'].iloc[0]
            beat=(top['ret']>ir).sum()
            wr=beat/len(top)
            if wr>0.5: wins+=1
            total+=1
            details.append({'date':td,'wr':wr,'win':wr>0.5,'idx':ir})
        except Exception as e:
            traceback.print_exc()
    return wins,total,details

print("\nRunning models (streamlined)...", flush=True)
# Only test most promising configs to save time
configs=[
    ('RF_d2',RandomForestClassifier(n_estimators=50,max_depth=2,random_state=RANDOM_STATE)),
    ('RF_d3',RandomForestClassifier(n_estimators=50,max_depth=3,random_state=RANDOM_STATE)),
    ('GB_d2',GradientBoostingClassifier(n_estimators=30,max_depth=2,random_state=RANDOM_STATE)),
    ('GB_d3',GradientBoostingClassifier(n_estimators=50,max_depth=3,random_state=RANDOM_STATE)),
]

best_acc=0; best_name=""; best_det=None
results = []

import gc

for cname,ctpl in configs:
    for tw in [10,15]:
        for tn in [3,5,7]:
            w,t,d=wf_test(ctpl,tn,tw)
            gc.collect()
            if t==0: continue
            a=w/t
            cfg=f"{cname}_tw{tw}_n{tn}"
            results.append((cfg, a, w, t, d))
            print(f"  {cfg:28s}: {a*100:5.1f}% ({w}/{t})",flush=True)
            if a>best_acc:
                best_acc=a;best_name=cfg;best_det=d

print("\nEnsembles...",flush=True)
for tw in [10,15]:
    for tn in [3,5,7]:
        w,t,d=ensemble_wf(tn,tw)
        gc.collect()
        if t==0: continue
        a=w/t
        cfg=f"ENS_tw{tw}_n{tn}"
        results.append((cfg, a, w, t, d))
        print(f"  {cfg:28s}: {a*100:5.1f}% ({w}/{t})",flush=True)
        if a>best_acc:
            best_acc=a;best_name=cfg;best_det=d

# Sort all results
results.sort(key=lambda x: x[1], reverse=True)
print(f"\n{'='*50}",flush=True)
print("TOP 10:", flush=True)
for cfg, a, w, t, d in results[:10]:
    print(f"  {cfg:28s}: {a*100:5.1f}% ({w}/{t})",flush=True)

print(f"\nBEST: {best_name} = {best_acc*100:.1f}%",flush=True)

if best_det:
    wins_l=[d for d in best_det if d['win']]
    loss_l=[d for d in best_det if not d['win']]
    print(f"Wins: {len(wins_l)}, Losses: {len(loss_l)}, Total: {len(best_det)}",flush=True)
    for d in loss_l[:10]:
        print(f"  LOSS {d['date']}: wr={d['wr']*100:.0f}%",flush=True)

# Save
report={'best':best_name,'accuracy':round(best_acc,4),'days':len(best_det) if best_det else 0,
        'features':len(feat_cols),'beat_rate':round(float(df['beat'].mean()),4),
        'top10':[(c,round(a,4),w,t) for c,a,w,t,_ in results[:10]]}
with open(os.path.join(WORK_DIR,'best_strategy_config.json'),'w') as f:
    json.dump(report,f,indent=2)
print("Saved config.",flush=True)

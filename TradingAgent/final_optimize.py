#!/usr/bin/env python3
"""
Expanded dataset: use Feb data for training, March-April for testing
"""
import json, os, sys, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

def load_data():
    cache = os.path.join(DATA_DIR, 'kline_cache', 'kline_data_2026-02-20_2026-04-07.json')
    with open(cache, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        kline[code] = df
    idx = pd.read_json(os.path.join(DATA_DIR, 'index_shanghai.json'))
    idx['date'] = pd.to_datetime(idx['date']).dt.tz_localize(None)
    idx = idx.sort_values('date')
    return kline, idx

def get_ret(df, date):
    t = pd.to_datetime(date)
    d = df[(df['date'] >= t)]; p = df[(df['date'] < t)]
    if len(d)==0 or len(p)==0: return None
    return (float(d.iloc[0]['close'])-float(p.iloc[-1]['close']))/float(p.iloc[-1]['close'])*100

def get_idx(idx_df, date):
    t = pd.to_datetime(date)
    d = idx_df[(idx_df['date'] >= t)]; p = idx_df[(idx_df['date'] < t)]
    if len(d)==0 or len(p)==0: return None
    return (float(d.iloc[0]['close'])-float(p.iloc[-1]['close']))/float(p.iloc[-1]['close'])*100

def calc_feat(df, td):
    h = df[df['date'] < td]
    if len(h) < 15: return None
    c = h['close'].values.astype(float)
    v = h['volume'].values.astype(float)
    hi = h['high'].values.astype(float)
    lo = h['low'].values.astype(float)
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
    w20=min(20,len(c))
    f['pos']=(c[-1]-np.min(c[-w20:]))/max(np.max(c[-w20:])-np.min(c[-w20:]),0.01)*100
    gains,losses=[],[]
    for i in range(max(0,len(c)-14),len(c)-1):
        chg=(c[i+1]-c[i])/c[i]*100
        gains.append(max(chg,0));losses.append(max(-chg,0))
    f['rsi']=100-100/(1+np.mean(gains)/max(np.mean(losses),0.01))
    if len(v)>=10: f['vr']=np.mean(v[-5:])/max(np.mean(v[-10:]),1)
    streak=0
    for i in range(len(c)-1,max(0,len(c)-8),-1):
        if c[i]>c[i-1]: streak=streak+1 if streak>=0 else 1
        elif c[i]<c[i-1]: streak=streak-1 if streak<=0 else -1
        else: break
    f['streak']=streak
    if len(c)>=2:
        body=abs(c[-1]-c[-2])
        f['lshadow']=(min(c[-1],c[-2])-lo[-1])/max(body,0.01) if body>0 else 0
        f['ushadow']=(hi[-1]-max(c[-1],c[-2]))/max(body,0.01) if body>0 else 0
    f['range']=(hi[-1]-lo[-1])/c[-1]*100
    f['cpos']=(c[-1]-lo[-1])/max(hi[-1]-lo[-1],0.01)*100
    if len(c)>=15:
        vs=np.std(np.diff(c[-6:])/c[-6:-1])*100
        vl=np.std(np.diff(c[-11:])/c[-11:-1])*100
        f['volreg']=vs/max(vl,0.01)
    return f

def build_dataset(kline, idx_df, start='2026-02-24', end='2026-04-07'):
    dates = list(pd.date_range(start, end, freq='B'))
    rows = []
    for td in dates:
        ds = td.strftime('%Y-%m-%d')
        ir = get_idx(idx_df, ds)
        if ir is None: continue
        for code, df in kline.items():
            feat = calc_feat(df, td)
            if feat is None: continue
            sr = get_ret(df, ds)
            if sr is None: continue
            feat['beat'] = 1 if sr > ir else 0
            feat['date'] = ds
            feat['code'] = code
            feat['ret'] = sr
            feat['idx'] = ir
            rows.append(feat)
    return pd.DataFrame(rows)

if __name__ == '__main__':
    kline, idx_df = load_data()
    df = build_dataset(kline, idx_df, start='2026-02-24')
    
    meta = ['beat','date','code','ret','idx']
    feat_cols = [c for c in df.columns if c not in meta]
    df[feat_cols] = df[feat_cols].fillna(0)
    
    udates = sorted(df['date'].unique())
    print(f"Dataset: {len(df)} obs, {len(feat_cols)} features, {len(udates)} days")
    print(f"Beat rate: {df['beat'].mean()*100:.1f}%")
    print(f"Date range: {udates[0]} to {udates[-1]}")
    
    models = {
        'LR_C001': LogisticRegression(C=0.01, max_iter=500, random_state=42),
        'LR_C01': LogisticRegression(C=0.1, max_iter=500, random_state=42),
        'RF_d2': RandomForestClassifier(n_estimators=100, max_depth=2, random_state=42),
        'RF_d3': RandomForestClassifier(n_estimators=100, max_depth=3, random_state=42),
        'GB_d2': GradientBoostingClassifier(n_estimators=50, max_depth=2, random_state=42),
        'GB_d3': GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
    }
    
    best_overall = 0
    best_config = ""
    best_details = None
    
    for mname, mtpl in models.items():
        for train_days in [5, 7, 10]:
            for top_n in [3, 5, 7, 10]:
                wins, total = 0, 0
                details = []
                
                for i in range(train_days, len(udates)):
                    test_date = udates[i]
                    train_d = udates[max(0,i-train_days):i]
                    
                    tr = df[df['date'].isin(train_d)]
                    te = df[df['date'] == test_date]
                    
                    if len(tr)<50 or len(te)<top_n: continue
                    
                    model = clone(mtpl)
                    sc = StandardScaler()
                    Xtr = sc.fit_transform(tr[feat_cols].values)
                    ytr = tr['beat'].values
                    model.fit(Xtr, ytr)
                    
                    Xte = sc.transform(te[feat_cols].values)
                    if hasattr(model,'predict_proba'):
                        probs = model.predict_proba(Xte)[:,1]
                    else:
                        d = model.decision_function(Xte)
                        probs = (d-d.min())/(d.max()-d.min()+1e-10)
                    
                    tec = te.copy(); tec['prob']=probs
                    top = tec.nlargest(min(top_n,len(tec)),'prob')
                    ir = top['idx'].iloc[0]
                    beat = (top['ret']>ir).sum()
                    wr = beat/len(top)
                    w = wr > 0.5
                    if w: wins += 1
                    total += 1
                    details.append({'date':test_date,'wr':wr,'win':w,'idx':ir})
                
                acc = wins/total if total > 0 else 0
                cfg = f"{mname}_tr{train_days}_n{top_n}"
                if acc >= 0.75 or acc > best_overall:
                    losses = [d for d in details if not d['win']]
                    lstr = ""
                    if losses:
                        lstr = " losses=" + ",".join(d['date'] for d in losses[:3])
                    print(f"  {cfg:30s}: {acc*100:5.1f}% ({wins}/{total}){lstr}")
                if acc > best_overall:
                    best_overall = acc
                    best_config = cfg
                    best_details = details
    
    print(f"\n>>> BEST: {best_config} = {best_overall*100:.1f}%")
    
    if best_details:
        losses = [d for d in best_details if not d['win']]
        print(f"\nLoss days ({len(losses)}):")
        for d in losses:
            print(f"  {d['date']}: wr={d['wr']*100:.0f}% idx={d['idx']:+.2f}%")
    
    # Final: try ensemble of top models
    print("\n=== Model Ensemble ===")
    for top_n in [3,5,7,10]:
        wins, total = 0, 0
        for i in range(10, len(udates)):
            test_date = udates[i]
            train_d = udates[i-10:i]
            tr = df[df['date'].isin(train_d)]
            te = df[df['date'] == test_date]
            if len(tr)<50 or len(te)<top_n: continue
            
            sc = StandardScaler()
            Xtr = sc.fit_transform(tr[feat_cols].values)
            ytr = tr['beat'].values
            
            # Train multiple models
            probs_sum = np.zeros(len(te))
            for mtpl in [LogisticRegression(C=0.1, max_iter=500),
                        RandomForestClassifier(n_estimators=100, max_depth=3),
                        GradientBoostingClassifier(n_estimators=50, max_depth=2)]:
                m = clone(mtpl); m.fit(Xtr, ytr)
                Xte = sc.transform(te[feat_cols].values)
                if hasattr(m,'predict_proba'):
                    probs_sum += m.predict_proba(Xte)[:,1]
            
            tec = te.copy(); tec['prob'] = probs_sum/3
            top = tec.nlargest(min(top_n,len(tec)),'prob')
            ir = top['idx'].iloc[0]
            beat = (top['ret']>ir).sum()
            if beat > len(top)/2: wins += 1
            total += 1
        
        acc = wins/total if total > 0 else 0
        print(f"  ensemble_tr10_n{top_n}: {acc*100:.1f}% ({wins}/{total})")

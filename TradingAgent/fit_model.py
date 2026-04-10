import os, pandas as pd, numpy as np
from backtest_data_prep import prepare_backtest_data
stocks_data, kline_data, index_data = prepare_backtest_data()
dates = list(pd.date_range('2026-02-20', '2026-04-07', freq='B'))

# Build feature matrix
rows = []
for d in dates[3:]:
    im=index_data['date']>=d; ip=index_data['date']<d
    if im.sum()<1 or ip.sum()<1: continue
    ic=float(index_data[im].iloc[0]['close']); ipc=float(index_data[ip].iloc[-1]['close'])
    idx_ret=(ic-ipc)/ipc*100
    
    for code, df in kline_data.items():
        hist = df[df['date'] < d]
        today_mask = df['date'] >= d
        if len(hist) < 5 or today_mask.sum() < 1: continue
        prev_mask = df['date'] < d
        c=float(df[today_mask].iloc[0]['close']); p=float(df[prev_mask].iloc[-1]['close'])
        if p<=0: continue
        stock_ret = (c-p)/p*100
        beat = 1.0 if stock_ret > idx_ret else 0.0
        
        close = hist['close'].values
        vol = hist['volume'].values
        ret_1d = (close[-1]-close[-2])/close[-2]*100 if len(close)>=2 else 0
        ret_3d = (close[-1]-close[-4])/close[-4]*100 if len(close)>=4 else 0
        ret_5d = (close[-1]-close[-6])/close[-6]*100 if len(close)>=6 else 0
        ma5 = np.mean(close[-5:]) if len(close)>=5 else close[-1]
        ma10 = np.mean(close[-10:]) if len(close)>=10 else close[-1]
        ma_ratio = ma5/ma10 if ma10>0 else 1
        if len(close)>=6:
            rets = np.diff(close[-6:])/close[-6:-1]
            vix = np.std(rets)*100
        else: vix = 2
        if len(vol)>=10 and np.mean(vol[-10:-5])>0:
            vr = np.mean(vol[-5:])/np.mean(vol[-10:-5])
        else: vr = 1
        
        sd = stocks_data.get(code, {})
        tech = float(sd.get('tech_score', sd.get('short_term_score', 5)))
        fund = float(sd.get('fund_score', sd.get('long_term_score', 5)))
        chip = float(sd.get('chip_score', 5))
        sector = float(sd.get('sector_score', sd.get('hot_sector_score', 5)))
        
        rows.append([beat, stock_ret, ret_1d, ret_3d, ret_5d, ma_ratio, vix, vr, tech, fund, chip, sector])

ddf = pd.DataFrame(rows, columns=['beat','ret','ret_1d','ret_3d','ret_5d','ma_ratio','vix','vr','tech','fund','chip','sector'])

# Fit simple logistic regression via least squares
from numpy.linalg import lstsq
features = ['ret_1d','ret_3d','ret_5d','ma_ratio','vix','vr','tech','fund','chip','sector']
X = ddf[features].values
X = np.column_stack([X, np.ones(len(X))])  # add intercept
y = ddf['beat'].values

# Replace NaN/Inf
X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)
y = np.nan_to_num(y, nan=0, posinf=0, neginf=0)
coefs, _, _, _ = lstsq(X, y, rcond=None)
print("Coefficients:")
for f, c in zip(features + ['intercept'], coefs):
    print(f"  {f}: {c:.6f}")

# Now simulate using these coefficients
from collections import Counter
wins = 0
total = 0
for d in dates[3:]:
    im=index_data['date']>=d; ip=index_data['date']<d
    if im.sum()<1 or ip.sum()<1: continue
    ic=float(index_data[im].iloc[0]['close']); ipc=float(index_data[ip].iloc[-1]['close'])
    idx_ret=(ic-ipc)/ipc*100
    
    candidates = []
    for code, df in kline_data.items():
        hist = df[df['date'] < d]
        today_mask = df['date'] >= d
        if len(hist) < 5 or today_mask.sum() < 1: continue
        prev_mask = df['date'] < d
        c=float(df[today_mask].iloc[0]['close']); p=float(df[prev_mask].iloc[-1]['close'])
        if p<=0: continue
        stock_ret = (c-p)/p*100
        
        close = hist['close'].values
        vol = hist['volume'].values
        ret_1d = (close[-1]-close[-2])/close[-2]*100 if len(close)>=2 else 0
        ret_3d = (close[-1]-close[-4])/close[-4]*100 if len(close)>=4 else 0
        ret_5d = (close[-1]-close[-6])/close[-6]*100 if len(close)>=6 else 0
        ma5 = np.mean(close[-5:]) if len(close)>=5 else close[-1]
        ma10 = np.mean(close[-10:]) if len(close)>=10 else close[-1]
        ma_ratio = ma5/ma10 if ma10>0 else 1
        if len(close)>=6:
            rets = np.diff(close[-6:])/close[-6:-1]
            vix = np.std(rets)*100
        else: vix = 2
        if len(vol)>=10 and np.mean(vol[-10:-5])>0:
            vr = np.mean(vol[-5:])/np.mean(vol[-10:-5])
        else: vr = 1
        
        sd = stocks_data.get(code, {})
        tech = float(sd.get('tech_score', sd.get('short_term_score', 5)))
        fund = float(sd.get('fund_score', sd.get('long_term_score', 5)))
        chip = float(sd.get('chip_score', 5))
        sector = float(sd.get('sector_score', sd.get('hot_sector_score', 5)))
        
        feats = np.array([ret_1d,ret_3d,ret_5d,ma_ratio,vix,vr,tech,fund,chip,sector,1])
        score = feats @ coefs
        
        industry = sd.get('industry', 'X')
        candidates.append((code, score, stock_ret, industry))
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = []
    ind_count = {}
    for code, sc, ret, ind in candidates:
        if len(selected) >= 3: break
        if ind_count.get(ind, 0) >= 1: continue
        selected.append(ret)
        ind_count[ind] = ind_count.get(ind, 0) + 1
    
    if len(selected) >= 2:
        daily_wins = sum(1 for r in selected if r > idx_ret)
        wr = daily_wins / len(selected)
        if wr > 0.5:
            wins += 1
        total += 1
        print(f"{d.strftime('%Y-%m-%d')}: idx={idx_ret:+.2f}% sel_rets={[f'{r:+.2f}' for r in selected]} wr={wr:.0%} {'W' if wr>0.5 else 'L'}")

acc = wins/total if total>0 else 0
print(f"\nAccuracy: {acc:.2%} ({wins}/{total})")

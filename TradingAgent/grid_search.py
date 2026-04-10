import os, pandas as pd, numpy as np
from backtest_data_prep import prepare_backtest_data
stocks_data, kline_data, index_data = prepare_backtest_data()
dates = list(pd.date_range('2026-02-20', '2026-04-07', freq='B'))

def calc_features(df, d):
    hist = df[df['date'] < d]
    if len(hist) < 5: return None
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
    return {'ret_1d':ret_1d,'ret_3d':ret_3d,'ret_5d':ret_5d,'ma_ratio':ma_ratio,'vix':vix,'vr':vr}

# Strategy: rank stocks by combined score, pick top 3 with industry diversification
# Try many weight combinations
best_weights = None
best_acc = 0

for w_vix in [0.2, 0.3, 0.4]:
    for w_ret3d in [0.1, 0.2, 0.3]:
        for w_vr in [0.1, 0.2, 0.3]:
            for w_ma in [0.1, 0.2]:
                w_sum = w_vix + w_ret3d + w_vr + w_ma
                if abs(w_sum - 1.0) > 0.01: continue
                
                wins = 0
                total = 0
                for d in dates[3:]:
                    # index return
                    im=index_data['date']>=d; ip=index_data['date']<d
                    if im.sum()<1 or ip.sum()<1: continue
                    ic=float(index_data[im].iloc[0]['close']); ipc=float(index_data[ip].iloc[-1]['close'])
                    idx_ret=(ic-ipc)/ipc*100
                    
                    # score each stock
                    candidates = []
                    for code, df in kline_data.items():
                        feat = calc_features(df, d)
                        if feat is None: continue
                        today_mask = df['date'] >= d
                        if today_mask.sum() < 1: continue
                        prev_mask = df['date'] < d
                        c=float(df[today_mask].iloc[0]['close']); p=float(df[prev_mask].iloc[-1]['close'])
                        if p<=0: continue
                        stock_ret = (c-p)/p*100
                        
                        # Score: high vix good, low ret_3d good (mean reversion), high vr good, low ma_ratio good
                        score = (w_vix * (feat['vix']/3) + 
                                w_ret3d * (1 - feat['ret_3d']/10) + 
                                w_vr * (feat['vr']/2) + 
                                w_ma * (2 - feat['ma_ratio']))
                        
                        industry = stocks_data.get(code, {}).get('industry', 'X')
                        candidates.append((code, score, stock_ret, industry, d))
                    
                    # Top 3 with diversification
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    selected = []
                    ind_count = {}
                    for code, sc, ret, ind, dd in candidates:
                        if len(selected) >= 3: break
                        if ind_count.get(ind, 0) >= 1: continue
                        selected.append(ret)
                        ind_count[ind] = ind_count.get(ind, 0) + 1
                    
                    if len(selected) >= 2:
                        daily_wins = sum(1 for r in selected if r > idx_ret)
                        if daily_wins / len(selected) > 0.5:
                            wins += 1
                        total += 1
                
                acc = wins/total if total>0 else 0
                if acc > best_acc:
                    best_acc = acc
                    best_weights = (w_vix, w_ret3d, w_vr, w_ma)
                    print(f'NEW BEST: acc={acc:.2%} w={best_weights} wins={wins}/{total}')

print(f'\nBest: acc={best_acc:.2%} weights={best_weights}')

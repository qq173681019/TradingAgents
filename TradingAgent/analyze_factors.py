import os, pandas as pd, numpy as np
from backtest_data_prep import prepare_backtest_data
stocks_data, kline_data, index_data = prepare_backtest_data()
dates = list(pd.date_range('2026-02-20', '2026-04-07', freq='B'))

rows = []
for d in dates[3:]:
    if index_data is not None:
        im=index_data['date']>=d; ip=index_data['date']<d
        if im.sum()<1 or ip.sum()<1: continue
        ic=float(index_data[im].iloc[0]['close']); ipc=float(index_data[ip].iloc[-1]['close'])
        idx_ret=(ic-ipc)/ipc*100
    else: continue
    
    for code, df in kline_data.items():
        hist = df[df['date'] < d]
        today_mask = df['date'] >= d
        if len(hist) < 5 or today_mask.sum() < 1: continue
        prev_mask = df['date'] < d
        c=float(df[today_mask].iloc[0]['close']); p=float(df[prev_mask].iloc[-1]['close'])
        if p<=0: continue
        ret = (c-p)/p*100
        beat = 1 if ret > idx_ret else 0
        
        close = hist['close'].values
        vol = hist['volume'].values
        
        ret_1d = (close[-1]-close[-2])/close[-2]*100 if len(close)>=2 else 0
        ret_3d = (close[-1]-close[-4])/close[-4]*100 if len(close)>=4 else 0
        ret_5d = (close[-1]-close[-6])/close[-6]*100 if len(close)>=6 else 0
        ma5 = np.mean(close[-5:]) if len(close)>=5 else close[-1]
        ma10 = np.mean(close[-10:]) if len(close)>=10 else close[-1]
        ma_ratio = ma5/ma10 if ma10>0 else 1
        
        sd = stocks_data.get(code, {})
        tech = float(sd.get('tech_score', sd.get('short_term_score', 5)))
        fund = float(sd.get('fund_score', sd.get('long_term_score', 5)))
        chip = float(sd.get('chip_score', 5))
        sector = float(sd.get('sector_score', sd.get('hot_sector_score', 5)))
        
        if len(close)>=6:
            rets = np.diff(close[-6:])/close[-6:-1]
            vix = np.std(rets)*100
        else: vix = 2
        
        if len(vol)>=10:
            vr = np.mean(vol[-5:])/np.mean(vol[-10:-5]) if np.mean(vol[-10:-5])>0 else 1
        else: vr = 1
        
        rows.append({'beat':beat, 'ret_1d':ret_1d, 'ret_3d':ret_3d, 'ret_5d':ret_5d,
                     'ma_ratio':ma_ratio, 'tech':tech, 'fund':fund, 'chip':chip,
                     'sector':sector, 'vix':vix, 'vr':vr, 'ret':ret})

ddf = pd.DataFrame(rows)
br = ddf['beat'].mean()
print(f'N={len(ddf)}, beat_rate={br:.2%}')

for col in ['ret_1d','ret_3d','ret_5d','ma_ratio','tech','fund','chip','sector','vix','vr']:
    corr = ddf[col].corr(ddf['beat'])
    print(f'  {col}: {corr:.4f}')

# Try quintile analysis for best features
for feat in ['ret_1d', 'ret_3d', 'ma_ratio', 'vix', 'vr']:
    try:
        ddf2 = ddf.copy()
        ddf2['q'] = pd.qcut(ddf2[feat], 5, labels=False, duplicates='drop')
        print(f'\n{feat} quintile analysis:')
        for qi in sorted(ddf2['q'].unique()):
            sub = ddf2[ddf2['q']==qi]
            print(f'  Q{qi}: beat_rate={sub["beat"].mean():.2%}, avg_ret={sub["ret"].mean():+.2f}%, n={len(sub)}')
    except Exception as e:
        print(f'{feat}: error - {e}')

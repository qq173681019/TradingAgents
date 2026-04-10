import os, pandas as pd, numpy as np
from backtest_data_prep import prepare_backtest_data
stocks_data, kline_data, index_data = prepare_backtest_data()
dates = list(pd.date_range('2026-02-20', '2026-04-07', freq='B'))

def get_ret(close, n):
    if len(close) < n+1: return 0
    return (close[-1]-close[-n-1])/close[-n-1]*100

def simulate(score_fn, top_n=3, max_per_industry=1, min_hist=3):
    wins = 0; total = 0
    for d in dates[min_hist:]:
        im=index_data['date']>=d; ip=index_data['date']<d
        if im.sum()<1 or ip.sum()<1: continue
        ic=float(index_data[im].iloc[0]['close']); ipc=float(index_data[ip].iloc[-1]['close'])
        idx_ret=(ic-ipc)/ipc*100
        cands = []
        for code, df in kline_data.items():
            hist = df[df['date'] < d]
            tm = df['date'] >= d
            if len(hist) < min_hist or tm.sum() < 1: continue
            pm = df['date'] < d
            c=float(df[tm].iloc[0]['close']); p=float(df[pm].iloc[-1]['close'])
            if p<=0: continue
            sr = (c-p)/p*100
            sd = stocks_data.get(code, {})
            ind = sd.get('industry', 'X')
            sc = score_fn(code, hist, sd, d)
            cands.append((sr, ind, sc, code))
        cands.sort(key=lambda x: x[2], reverse=True)
        sel = []; ic2 = {}
        for sr, ind, sc, code in cands:
            if len(sel) >= top_n: break
            if ic2.get(ind, 0) >= max_per_industry: continue
            sel.append(sr); ic2[ind] = ic2.get(ind, 0) + 1
        if len(sel) >= 2:
            dw = sum(1 for r in sel if r > idx_ret)
            if dw / len(sel) > 0.5: wins += 1
            total += 1
    return wins, total

# Exhaustive search over weight combos for momentum + static
best = (0, 0, '')
for w_r3 in np.arange(0, 1.01, 0.1):
    for w_r5 in np.arange(0, 1.01-w_r3+0.01, 0.1):
        for w_st in np.arange(0, 1.01-w_r3-w_r5+0.01, 0.1):
            w_r1 = round(1.0 - w_r3 - w_r5 - w_st, 1)
            if w_r1 < -0.01: continue
            w_r1 = max(0, w_r1)
            def make_fn(w_r1=w_r1, w_r3=w_r3, w_r5=w_r5, w_st=w_st):
                def fn(code, hist, sd, d):
                    close = hist['close'].values
                    r1 = get_ret(close, 1); r3 = get_ret(close, 3); r5 = get_ret(close, 5)
                    tech = float(sd.get('tech_score', sd.get('short_term_score', 5)))
                    chip = float(sd.get('chip_score', 5))
                    sector = float(sd.get('sector_score', sd.get('hot_sector_score', 5)))
                    st = tech*0.4+chip*0.3+sector*0.3
                    return r1*w_r1 + r3*w_r3 + r5*w_r5 + st*w_st
                return fn
            w, t = simulate(make_fn(), top_n=3, max_per_industry=1)
            if t > 0 and w/t > best[0]/max(best[1],1):
                best = (w, t, f'r1={w_r1:.1f} r3={w_r3:.1f} r5={w_r5:.1f} st={w_st:.1f}')
                if w/t >= 0.70:
                    print(f'  {w}/{t}={w/t:.2%} r1={w_r1:.1f} r3={w_r3:.1f} r5={w_r5:.1f} st={w_st:.1f}')

print(f'\nBest: {best[0]}/{best[1]}={best[0]/best[1]:.2%} {best[2]}')

# Also try top_n=5 and top_n=1 with best params
for tn in [1, 2, 5]:
    def make_fn2():
        def fn(code, hist, sd, d):
            close = hist['close'].values
            r3 = get_ret(close, 3); r5 = get_ret(close, 5)
            tech = float(sd.get('tech_score', sd.get('short_term_score', 5)))
            chip = float(sd.get('chip_score', 5))
            sector = float(sd.get('sector_score', sd.get('hot_sector_score', 5)))
            st = tech*0.4+chip*0.3+sector*0.3
            return r3*0.3 + r5*0.4 + st*0.3
        return fn
    w, t = simulate(make_fn2(), top_n=tn, max_per_industry=1 if tn<=3 else 2)
    print(f'top_n={tn}: {w}/{t}={w/t:.2%}')

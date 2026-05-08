"""Quick update index data via AKShare - handles both formats"""
import os, json, time
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

import requests
_orig_send = requests.Session.send
def _no_proxy(self, *a, **kw):
    self.trust_env = False
    return _orig_send(self, *a, **kw)
requests.Session.send = _no_proxy

import akshare as ak

print('Fetching Shanghai index...')
df = ak.stock_zh_index_daily(symbol='sh000001')
last_row = df.iloc[-1]
last_date = str(last_row['date'])[:10]
print(f'Got {len(df)} rows, AKShare last: {last_date}')

# Update index_full_latest.json (columnar format)
idx_file = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\index_full_latest.json'
with open(idx_file, 'r') as f:
    idx_data = json.load(f)

if isinstance(idx_data, dict) and 'date' in idx_data:
    # Columnar format: {"date": {0: "2026-01-05", ...}, "close": {0: 3300, ...}, ...}
    n = len(idx_data['date'])
    last_existing = list(idx_data['date'].values())[-1] if n > 0 else ''
    print(f'Columnar format, {n} entries, last: {last_existing}')
    
    # Find new dates not in existing data
    existing_dates = set(str(v) for v in idx_data['date'].values())
    new_count = 0
    for _, r in df.iterrows():
        ds = str(r['date'])[:10]
        if ds not in existing_dates:
            idx_data['date'][n + new_count] = ds
            idx_data['open'][n + new_count] = float(r['open'])
            idx_data['high'][n + new_count] = float(r['high'])
            idx_data['low'][n + new_count] = float(r['low'])
            idx_data['close'][n + new_count] = float(r['close'])
            idx_data['volume'][n + new_count] = float(r['volume'])
            new_count += 1
    
    with open(idx_file, 'w') as f:
        json.dump(idx_data, f)
    print(f'Added {new_count} new days')
    final_n = len(idx_data['date'])
    final_last = list(idx_data['date'].values())[-1]
    print(f'Total {final_n} entries, up to {final_last}')

# Also update index_shanghai_full.json (list format)
sh_file = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\index_shanghai_full.json'
if os.path.exists(sh_file):
    with open(sh_file, 'r') as f:
        sh_data = json.load(f)
    
    if isinstance(sh_data, list):
        sh_map = {d['date']: d for d in sh_data}
        added = 0
        for _, r in df.iterrows():
            ds = str(r['date'])[:10]
            entry = {'date': ds, 'open': float(r['open']), 'high': float(r['high']),
                     'low': float(r['low']), 'close': float(r['close']), 'volume': float(r['volume'])}
            if ds not in sh_map:
                sh_data.append(entry)
                added += 1
            else:
                sh_map[ds].update(entry)
        
        sh_data.sort(key=lambda x: x['date'])
        with open(sh_file, 'w') as f:
            json.dump(sh_data, f)
        print(f'index_shanghai_full.json: added {added} days, up to {sh_data[-1]["date"]}')

print('Done!')

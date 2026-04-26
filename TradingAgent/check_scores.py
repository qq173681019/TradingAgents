import json, os, glob

data_dir = r'C:\Users\admin\Documents\GitHub\TradingAgents\TradingShared\data'
files = glob.glob(os.path.join(data_dir, 'batch_stock_scores*'))
files.sort()
latest = files[-1]
print(f"Loading: {os.path.basename(latest)}")
d = json.load(open(latest, encoding='utf-8'))
print(f"Type: {type(d)}, Len: {len(d)}")
if isinstance(d, list):
    print(json.dumps(d[:2], ensure_ascii=False, indent=2))
elif isinstance(d, dict):
    keys = list(d.keys())[:3]
    for k in keys:
        print(k, str(d[k])[:300])

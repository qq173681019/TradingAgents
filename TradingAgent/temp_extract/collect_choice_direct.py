"""直接用 EmQuantAPI 批量采集 V19 池数据（不经过 wrapper）"""
import os, sys, json, time
import numpy as np

sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared\api')

from EmQuantAPI import c
from config import CHOICE_USERNAME, CHOICE_PASSWORD

# 加载 V19 股票池
with open(r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json', 'r', encoding='utf-8') as f:
    pool = json.load(f)
print(f"V19 pool: {len(pool)} stocks")

OUTPUT_FILE = r'D:\GitHub\TradingAgents\TradingShared\data\choice_fundamentals.json'
START_DATE = "2026-02-05"
END_DATE = "2026-05-09"

def to_choice_code(code):
    return code + '.SH' if code.startswith('6') else code + '.SZ'

# 断点续传
existing = {}
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    print(f"Existing: {len(existing)} stocks")

todo = [c for c in pool if c not in existing]
print(f"TODO: {len(todo)} stocks")

# 登录
print("Logging in...")
r = c.start(f"USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD}")
if r.ErrorCode != 0:
    print(f"Login failed: {r.ErrorMsg}")
    sys.exit(1)
print("Login OK")

# 逐只采集
t0 = time.time()
done = 0
fail = 0

for i, code in enumerate(todo):
    cc = to_choice_code(code)
    try:
        data = c.csd(cc, "OPEN,HIGH,LOW,CLOSE,VOLUME,TURN,CHGPCT,AMOUNT,PE,PB,PS",
                     START_DATE, END_DATE, "")
        
        if data.ErrorCode == 0 and cc in data.Data:
            stock_data = data.Data[cc]
            # 转换日期
            dates = []
            for d in data.Dates:
                parts = d.split('/')
                dates.append(f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}")
            
            indicators = data.Indicators
            result = {}
            for j, ind in enumerate(indicators):
                if j < len(stock_data):
                    result[ind] = stock_data[j]
            
            existing[code] = {'dates': dates, 'data': result}
            done += 1
        else:
            fail += 1
            if fail <= 5:
                print(f"  FAIL {cc}: {data.ErrorMsg}")
    except Exception as e:
        fail += 1
        if fail <= 5:
            print(f"  ERROR {cc}: {e}")
    
    # 进度
    if (i + 1) % 100 == 0:
        elapsed = time.time() - t0
        rate = (i + 1) / elapsed
        eta = (len(todo) - i - 1) / rate / 60
        print(f"  [{i+1}/{len(todo)}] done={done} fail={fail} rate={rate:.1f}/s ETA={eta:.0f}min")
        # 保存
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False)
        print(f"  [SAVED] {len(existing)} stocks")

# 最终保存
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(existing, f, ensure_ascii=False)

c.stop()
elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"Complete: {done} ok, {fail} fail")
print(f"Total in file: {len(existing)}")
print(f"Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
print(f"Output: {OUTPUT_FILE}")
print(f"{'='*60}")

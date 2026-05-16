"""用 Choice CSD 批量采集 V19 股票池的 PE/PB/TURN 数据
输出: choice_fundamentals.json - {code: {dates: [...], PE: [...], PB: [...], PS: [...], TURN: [...], AMOUNT: [...]}}
"""
import os, sys, json, time
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared\api')

from api.choice_api_wrapper import ChoiceAPIWrapper

# 加载 V19 股票池
POOL_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'
OUTPUT_FILE = r'D:\GitHub\TradingAgents\TradingShared\data\choice_fundamentals.json'

with open(POOL_FILE, 'r', encoding='utf-8') as f:
    pool = json.load(f)
print(f"V19 pool: {len(pool)} stocks")

# 代码转换: "000001" -> "000001.SZ", "600000" -> "600000.SH"
def to_choice_code(code):
    if code.startswith('6'):
        return code + '.SH'
    else:
        return code + '.SZ'

# 加载已有进度（断点续传）
existing = {}
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    print(f"Existing data: {len(existing)} stocks")

# 过滤已完成的
todo = [c for c in pool if c not in existing]
print(f"TODO: {len(todo)} stocks")

choice = ChoiceAPIWrapper(timeout=60)

START_DATE = "2026-02-05"  # 留几天buffer给MA计算
END_DATE = "2026-05-09"
INDICATORS = "OPEN,HIGH,LOW,CLOSE,VOLUME,TURN,CHGPCT,AMOUNT,PE,PB,PS"

BATCH_SIZE = 50
SAVE_INTERVAL = 100
total_done = len(existing)
total_fail = 0
t0 = time.time()

for i, code in enumerate(todo):
    choice_code = to_choice_code(code)
    
    try:
        r = choice.get_kline_data(choice_code, start_date=START_DATE, end_date=END_DATE,
                                  indicators=INDICATORS)
        
        if r.get('success'):
            # 转换日期格式: "2026/5/6" -> "2026-05-06"
            dates = []
            for d in r.get('dates', []):
                parts = d.split('/')
                dates.append(f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}")
            
            stock_data = {}
            for ind in r.get('indicators', []):
                vals = r.get('data', {}).get(ind, [])
                stock_data[ind] = vals
            
            existing[code] = {
                'dates': dates,
                'data': stock_data,
            }
            total_done += 1
        else:
            total_fail += 1
            if total_fail <= 10:
                err = repr(r.get('error', ''))[:100]
                print(f"  FAIL {code}: {err}")
    
    except Exception as e:
        total_fail += 1
        if total_fail <= 10:
            print(f"  ERROR {code}: {e}")
    
    # 进度
    if (i + 1) % 50 == 0:
        elapsed = time.time() - t0
        rate = (i + 1) / elapsed
        eta = (len(todo) - i - 1) / rate / 60
        print(f"  [{i+1}/{len(todo)}] done={total_done} fail={total_fail} "
              f"rate={rate:.1f}/s ETA={eta:.0f}min")
    
    # 定期保存
    if (i + 1) % SAVE_INTERVAL == 0:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False)
        print(f"  [SAVE] {total_done} stocks saved")

# 最终保存
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(existing, f, ensure_ascii=False)

elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"Complete: {total_done} success, {total_fail} fail")
print(f"Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
print(f"Output: {OUTPUT_FILE}")
print(f"{'='*60}")

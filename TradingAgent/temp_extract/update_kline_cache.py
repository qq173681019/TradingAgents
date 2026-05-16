"""
更新K线缓存 - 从4月25日到最新日期
用AKShare批量获取全市场股票K线
"""
import os, json, time, sys
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

# Patch requests to ignore system proxy
import requests
_original_send = requests.Session.send
def _patched_send(self, *args, **kwargs):
    self.trust_env = False
    return _original_send(self, *args, **kwargs)
requests.Session.send = _patched_send

import akshare as ak
import pandas as pd

KLINE_DIR = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache'
LATEST_FILE = os.path.join(KLINE_DIR, 'kline_full_latest.json')
START_DATE = '20260425'  # 现有数据到4月24日
END_DATE = time.strftime('%Y%m%d')

def load_existing():
    """加载现有K线缓存"""
    if os.path.exists(LATEST_FILE):
        with open(LATEST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(data):
    """保存K线缓存"""
    # 转换格式: {code: [kline_records]}
    with open(LATEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    sz = os.path.getsize(LATEST_FILE) / 1024 / 1024
    print(f"  Saved: {sz:.1f}MB, {len(data)} stocks")

def get_all_stock_codes():
    """获取全市场股票代码"""
    print("Fetching stock list...")
    df = ak.stock_zh_a_spot_em()
    codes = df['代码'].tolist()
    # 过滤ST和退市
    names = df['名称'].tolist()
    valid = [(c, n) for c, n in zip(codes, names) 
             if 'ST' not in n and '退' not in n]
    print(f"  Total valid stocks: {len(valid)}")
    return valid

def fetch_kline_batch(codes, batch_size=50):
    """批量获取K线数据"""
    new_data = {}
    total = len(codes)
    failed = 0
    
    for i in range(0, total, batch_size):
        batch = codes[i:i+batch_size]
        for code, name in batch:
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=START_DATE,
                    end_date=END_DATE,
                    adjust="qfq"
                )
                if df is not None and len(df) > 0:
                    records = []
                    for _, row in df.iterrows():
                        records.append({
                            'date': str(row['日期'])[:10],
                            'open': float(row['开盘']),
                            'high': float(row['最高']),
                            'low': float(row['最低']),
                            'close': float(row['收盘']),
                            'volume': float(row['成交量']),
                        })
                    new_data[f'sh{code}' if code.startswith('6') else f'sz{code}'] = records
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  Failed {code}: {e}")
        
        done = min(i + batch_size, total)
        print(f"  Progress: {done}/{total} ({done*100//total}%), got {len(new_data)} stocks, {failed} failed")
        time.sleep(1)  # 避免限流
    
    return new_data

def merge_kline(existing, new_data):
    """合并新旧K线数据"""
    merged = {}
    
    # 先复制existing
    for code, records in existing.items():
        merged[code] = list(records)  # copy
    
    # 合并new data
    for code, new_records in new_data.items():
        if code in merged:
            # 去重合并
            existing_dates = set(r['date'] for r in merged[code])
            for r in new_records:
                if r['date'] not in existing_dates:
                    merged[code].append(r)
            # 按日期排序
            merged[code].sort(key=lambda x: x['date'])
        else:
            merged[code] = new_records
    
    return merged

def main():
    print("=" * 60)
    print("  K线缓存更新工具")
    print(f"  日期范围: {START_DATE} ~ {END_DATE}")
    print("=" * 60)
    
    # 1. 加载现有数据
    print("\n[1] Loading existing cache...")
    existing = load_existing()
    print(f"  Existing: {len(existing)} stocks")
    
    # 2. 获取股票列表
    print("\n[2] Fetching stock list...")
    stocks = get_all_stock_codes()
    
    # 3. 获取新K线
    print(f"\n[3] Fetching klines from {START_DATE} to {END_DATE}...")
    new_data = fetch_kline_batch(stocks, batch_size=1)  # 逐个获取避免限流
    
    if not new_data:
        print("  WARNING: No new data fetched!")
        return
    
    print(f"\n  Fetched {len(new_data)} stocks with new data")
    
    # 4. 合并
    print("\n[4] Merging...")
    merged = merge_kline(existing, new_data)
    
    # 5. 保存
    print("\n[5] Saving...")
    save_cache(merged)
    
    # 6. 验证
    print("\n[6] Verification:")
    sample_codes = list(merged.keys())[:3]
    for code in sample_codes:
        records = merged[code]
        print(f"  {code}: {records[0]['date']} ~ {records[-1]['date']}, {len(records)} days")
    
    print("\nDone!")

if __name__ == '__main__':
    main()

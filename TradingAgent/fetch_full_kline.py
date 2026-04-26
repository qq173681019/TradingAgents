#!/usr/bin/env python3
"""拉取全A股K线数据 - 小呆版"""
import os, json, time, sys
from datetime import datetime, timedelta
from collections import defaultdict

KLINE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'TradingShared', 'data', 'kline_cache')
os.makedirs(KLINE_CACHE, exist_ok=True)

TUSHARE_TOKEN = '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28'

# 回测需要6个月特征期 + 2个月评估期 = 8个月
START_DATE = '20250901'
# 用昨天作为截止日，避免周末没数据
yesterday = datetime.now() - timedelta(days=1)
END_DATE = yesterday.strftime('%Y%m%d')

print(f"{'='*60}")
print(f"全A股K线数据拉取")
print(f"区间: {START_DATE} ~ {END_DATE}")
print(f"{'='*60}")

import tushare as ts
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 1. 获取交易日历
print("\n[1/4] 获取交易日历...")
try:
    cal = pro.trade_cal(exchange='SSE', start_date=START_DATE, end_date=END_DATE,
                        fields='cal_date,is_open')
    trade_dates = sorted(cal[cal['is_open'] == 1]['cal_date'].tolist())
    print(f"  交易日: {len(trade_dates)} 天 ({trade_dates[0]} ~ {trade_dates[-1]})")
except Exception as e:
    print(f"  交易日历获取失败: {e}")
    # Fallback: 手动生成日期列表
    print("  使用备用方案: 按日期逐个尝试...")
    trade_dates = None

# 2. 批量拉取日线数据 (按日拉取，每天返回全市场)
print(f"\n[2/4] 批量拉取日线数据...")
all_data = defaultdict(list)
total_records = 0
failed_days = 0

if trade_dates:
    dates_to_fetch = trade_dates
else:
    # Fallback: 遍历每一天
    from datetime import date
    start_dt = datetime.strptime(START_DATE, '%Y%m%d')
    end_dt = datetime.strptime(END_DATE, '%Y%m%d')
    dates_to_fetch = []
    d = start_dt
    while d <= end_dt:
        dates_to_fetch.append(d.strftime('%Y%m%d'))
        d += timedelta(days=1)

for i, td in enumerate(dates_to_fetch):
    try:
        df = pro.daily(trade_date=td)
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                ts_code = row['ts_code']
                record = {
                    'date': td,
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': float(row.get('vol', 0)),
                    'amount': float(row.get('amount', 0)),
                    'pctChg': float(row.get('pct_chg', 0)),
                }
                all_data[ts_code].append(record)
                total_records += 1
        else:
            failed_days += 1
    except Exception as e:
        failed_days += 1
        if i < 3:
            print(f"  {td} 失败: {e}")
    
    if (i + 1) % 20 == 0:
        print(f"  进度: {i+1}/{len(dates_to_fetch)} 天, {len(all_data)} 只股票, {total_records} 条记录")

print(f"  完成: {len(dates_to_fetch) - failed_days} 天成功, {len(all_data)} 只股票, {total_records} 条记录")

# 3. 过滤: 至少60个交易日数据的股票
print(f"\n[3/4] 过滤数据不足的股票...")
filtered = {code: records for code, records in all_data.items() if len(records) >= 60}
print(f"  过滤后: {len(filtered)} 只 (排除 {len(all_data) - len(filtered)} 只)")

# 4. 拉取上证指数数据
print(f"\n[4/4] 拉取上证指数...")
try:
    idx_df = pro.index_daily(ts_code='000001.SH', start_date=START_DATE, end_date=END_DATE)
    if idx_df is not None and len(idx_df) > 0:
        idx_records = []
        for _, row in idx_df.iterrows():
            idx_records.append({
                'trade_date': row['trade_date'],
                'close': float(row['close']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'vol': float(row.get('vol', 0)),
            })
        # Sort by date
        idx_records.sort(key=lambda x: x['trade_date'])
        
        # Convert to the format backtest expects
        n = len(idx_records)
        index_data = {
            'date': {str(i): idx_records[i]['trade_date'] for i in range(n)},
            'open': {str(i): idx_records[i]['open'] for i in range(n)},
            'high': {str(i): idx_records[i]['high'] for i in range(n)},
            'low': {str(i): idx_records[i]['low'] for i in range(n)},
            'close': {str(i): idx_records[i]['close'] for i in range(n)},
            'vol': {str(i): idx_records[i]['vol'] for i in range(n)},
        }
        print(f"  指数: {n} 天 ({idx_records[0]['trade_date']} ~ {idx_records[-1]['trade_date']})")
    else:
        print(f"  指数数据为空!")
        index_data = None
except Exception as e:
    print(f"  指数获取失败: {e}")
    index_data = None

# 5. 保存
end_str = END_DATE[:8]  # YYYYMMDD without time
kline_file = os.path.join(KLINE_CACHE, f'kline_full_{START_DATE}_{end_str}.json')
with open(kline_file, 'w', encoding='utf-8') as f:
    json.dump(filtered, f, ensure_ascii=False)
size_mb = os.path.getsize(kline_file) / 1024 / 1024
print(f"\n  K线已保存: {kline_file} ({size_mb:.1f} MB, {len(filtered)} 只)")

# Also save as latest
latest_file = os.path.join(KLINE_CACHE, 'kline_full_latest.json')
with open(latest_file, 'w', encoding='utf-8') as f:
    json.dump(filtered, f, ensure_ascii=False)
print(f"  最新版: {latest_file}")

if index_data:
    idx_file = os.path.join(KLINE_CACHE, f'index_full_{START_DATE}_{end_str}.json')
    with open(idx_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False)
    latest_idx = os.path.join(KLINE_CACHE, 'index_full_latest.json')
    with open(latest_idx, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False)
    print(f"  指数已保存: {idx_file}")

# 6. 验证
print(f"\n{'='*60}")
print("数据验证")
print(f"{'='*60}")
sh_count = sum(1 for c in filtered if c.endswith('.SH'))
sz_count = sum(1 for c in filtered if c.endswith('.SZ'))
print(f"  股票: {len(filtered)} (沪:{sh_count} 深:{sz_count})")

all_dates = set()
lens = []
for code, records in filtered.items():
    lens.append(len(records))
    for r in records:
        all_dates.add(r['date'])

if all_dates:
    sorted_dates = sorted(all_dates)
    print(f"  日期: {sorted_dates[0]} ~ {sorted_dates[-1]} ({len(all_dates)} 天)")
print(f"  每股记录: min={min(lens)}, max={max(lens)}, avg={sum(lens)/len(lens):.0f}")

print(f"\n✅ 数据拉取完成!")

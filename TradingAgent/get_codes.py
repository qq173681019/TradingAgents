#!/usr/bin/env python3
"""Get stock codes from baostock directly (no proxy needed)"""
import baostock as bs
import json, os, time

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')

lg = bs.login()
print("Login OK")

# Method 1: query_stock_basic
print("\nTrying query_stock_basic...")
rs = bs.query_stock_basic()
codes = []
while rs.next():
    row = rs.get_row_data()
    # row[0]=code, row[3]=status(1=active), row[1]=code_name
    code, name, status = row[0], row[1], row[3]
    if status == '1' and not any(t in name for t in ['ST', '退']):
        if code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3'):
            codes.append({'code': code, 'name': name})

print(f"Method 1 got {len(codes)} stocks")

# Method 2: query_all_stock if method 1 fails
if len(codes) == 0:
    print("\nTrying query_all_stock (date=2026-04-01)...")
    rs2 = bs.query_all_stock(day='2026-04-01')
    codes = []
    while rs2.next():
        row = rs2.get_row_data()
        code, name = row[0], row[1]
        if not any(t in name for t in ['ST', '退']):
            if code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3'):
                codes.append({'code': code, 'name': name})
    print(f"Method 2 got {len(codes)} stocks")

bs.logout()

# Save
out = os.path.join(DATA_DIR, 'all_stock_codes.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(codes, f, ensure_ascii=False)
print(f"Saved {len(codes)} codes to {out}")

# Show sample
for c in codes[:5]:
    print(f"  {c['code']} {c['name']}")
print(f"  ...")
for c in codes[-5:]:
    print(f"  {c['code']} {c['name']}")

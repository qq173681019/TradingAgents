"""Repair corrupted kline JSON by truncating to last valid entry"""
import json, re

CACHE = r"D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json"
REPAIRED = r"D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest_repaired.json"

with open(CACHE, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"File size: {len(content)} chars")

# Find the corruption point
try:
    json.loads(content)
    print("File is valid JSON!")
    exit(0)
except json.JSONDecodeError as e:
    print(f"Error at position {e.pos}: {e.msg}")
    error_pos = e.pos

# Strategy: find the last complete stock entry before the error
# Each stock looks like: "sh600000": [{...}, {...}]
# We need to find a point where we can close the JSON properly

# Find last complete entry: look for ']},' before error point
# Scan backwards from error for ']]' (end of array of arrays)  
search_chunk = content[:error_pos]

# Find last occurrence of a complete record ending with volume + }]}, or similar
# Pattern: , "volume": NUMBER}]},
# Actually simpler: find last "}]}, " which is end of a stock's array + comma
last_entry_end = search_chunk.rfind('}]},')
if last_entry_end == -1:
    last_entry_end = search_chunk.rfind('}]')
    
print(f"Last entry end at: {last_entry_end}")
print(f"Context: {repr(content[last_entry_end:last_entry_end+50])}")

# Truncate there and close the JSON
truncated = content[:last_entry_end + 2]  # include the }] 
truncated += '}}'  # close the outer object

# Verify
try:
    d = json.loads(truncated)
    print(f"Repaired JSON valid! {len(d)} stocks")
    
    # Sort all records
    for key in d:
        if d[key]:
            d[key].sort(key=lambda x: x['date'])
    
    # Save repaired file
    with open(REPAIRED, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)
    print(f"Saved repaired file: {REPAIRED}")
    
    from collections import Counter
    last_dates = Counter()
    for key, recs in d.items():
        if recs:
            last_dates[recs[-1]['date']] += 1
    
    up = sum(cnt for dt, cnt in last_dates.items() if dt >= '2026-05-06')
    print(f"Coverage 2026-05-06: {up}/{len(d)} ({up*100//len(d)}%)")
    for dt, cnt in sorted(last_dates.items()):
        tag = "OK" if dt >= "2026-05-06" else "OLD"
        print(f"  {dt}: {cnt} [{tag}]")
        
except json.JSONDecodeError as e2:
    print(f"Still invalid: {e2}")
    # Try harder: use incremental parsing
    print("Trying incremental repair...")
    
    # Find all stock keys
    import re
    keys = re.findall(r'"(s[hz]\d{6}|bj\d{6})":\s*\[', content[:error_pos])
    print(f"Found {len(keys)} stock keys before error")
    
    # Try progressively shorter truncations
    for offset in range(0, min(100000, error_pos), 100):
        chunk = content[:error_pos - offset]
        last = chunk.rfind('}]')
        if last > 0:
            attempt = chunk[:last + 2] + '}}'
            try:
                d = json.loads(attempt)
                print(f"Found valid JSON at offset -{offset}, stocks: {len(d)}")
                break
            except:
                continue
    else:
        print("Could not repair automatically")

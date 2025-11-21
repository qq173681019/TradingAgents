import json
import os

file_path = 'data/comprehensive_stock_data.json'

if not os.path.exists(file_path):
    print("File not found")
    exit(0)

print(f"Reading {file_path}...")
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Content length: {len(content)}")

# Find the last "high" which caused the error, or just the end of file
# The error said: Expecting ':' delimiter: line 147037 column 19
# We saw it ended with "high"

# Let's try to find the last occurrence of "}," which signifies the end of a valid record in the list
last_comma_brace = content.rfind('},')

if last_comma_brace == -1:
    print("Could not find '},' pattern. File might be too corrupted or empty.")
    exit(1)

print(f"Truncating at index {last_comma_brace + 1}")
truncated = content[:last_comma_brace + 1]

# We assume we are inside:
# root {
#   stocks {
#     CODE {
#       kline_data {
#         daily [
#           { ... },
#           { ... } <-- we just closed this one
#         ]
#       }
#     }
#   }
# }

# So we need to close:
# 1. daily list: ]
# 2. kline_data dict: }
# 3. CODE dict: }
# 4. stocks dict: }
# 5. root dict: }

candidates = [
    ']}}}}',      # Close list, kline, code, stocks, root
    ']}}}',       # Maybe not in kline?
    '}}}}}',      # Maybe not in list?
    '}}}}',
    ']}}',
    '}}',
    '}',
    ']',
    ']}}}}}',
    ']}}}}}}'
]

fixed = False
for suffix in candidates:
    try:
        attempt = truncated + suffix
        data = json.loads(attempt)
        print(f"Success! JSON parsed with suffix: {suffix}")
        
        # Verify structure slightly
        if 'stocks' in data:
            print(f"Recovered {len(data['stocks'])} stocks.")
            
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(attempt)
        fixed = True
        break
    except json.JSONDecodeError as e:
        # print(f"Failed with {suffix}: {e}")
        pass

if fixed:
    print("File repaired successfully.")
else:
    print("Could not repair file automatically.")

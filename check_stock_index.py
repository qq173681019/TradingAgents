#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json

data = json.load(open('data/stock_file_index.json', encoding='utf-8'))
codes = list(data.keys())[:5]
print(f'总计: {len(data)} 只股票')
print(f'前5个示例: {codes}')
print(f'605389是否在其中: {"605389" in data}')
if '605389' in data:
    print(f'605389的分片号: {data["605389"]}')

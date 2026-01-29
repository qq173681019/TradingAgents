#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据批量更新脚本
供 BAT 文件调用
"""
import os
import sys

# 添加路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SHARED_PATH = os.path.join(PARENT_DIR, 'TradingShared')
API_PATH = os.path.join(SHARED_PATH, 'api')

for path in [CURRENT_DIR, PARENT_DIR, SHARED_PATH, API_PATH]:
    if path not in sys.path:
        sys.path.insert(0, path)

from comprehensive_data_collector import ComprehensiveDataCollector

if __name__ == '__main__':
    collector = ComprehensiveDataCollector()
    collector.update_kline_data_only(batch_size=100, stock_type='主板', exclude_st=True)
    print('K线数据更新完成')

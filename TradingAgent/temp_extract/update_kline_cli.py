#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K线数据批量更新 - CLI版本"""
import os, sys

# BAT模式标记
os.environ['TA_RUN_FROM_BAT'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from TradingShared.api.comprehensive_data_collector import ComprehensiveDataCollector

collector = ComprehensiveDataCollector()
collector.update_kline_data_only(batch_size=100, stock_type='主板', exclude_st=True)
print('\n[DONE] K线数据更新完成')

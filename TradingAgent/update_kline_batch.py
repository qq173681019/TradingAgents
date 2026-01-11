#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据批量更新脚本
供 BAT 文件调用
"""
import os
import sys

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from TradingShared.api.comprehensive_data_collector import \
    ComprehensiveDataCollector

if __name__ == '__main__':
    collector = ComprehensiveDataCollector()
    collector.update_kline_data_only(batch_size=100, stock_type='主板', exclude_st=True)
    print('K线数据更新完成')

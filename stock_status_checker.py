#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票状态检测模块
用于判断股票是否已退市、代码是否有效等
"""

import baostock as bs
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta

class StockStatusChecker:
    """股票状态检测器"""
    
    def __init__(self):
        self.bs_logged_in = False
        
    def _ensure_baostock_login(self) -> bool:
        """确保BaoStock已登录"""
        if not self.bs_logged_in:
            try:
                lg = bs.login()
                if lg.error_code == '0':
                    self.bs_logged_in = True
                    return True
                else:
                    print(f"[ERROR] BaoStock login failed: {lg.error_msg}")
                    return False
            except Exception as e:
                print(f"[ERROR] BaoStock login exception: {e}")
                return False
        return True
    
    def check_single_stock(self, code: str) -> Dict[str, any]:
        """
        检测单只股票状态
        
        Args:
            code: 6位股票代码，如 '600000'
            
        Returns:
            {
                'code': 股票代码,
                'name': 股票名称,
                'status': 'active'|'delisted'|'invalid'|'suspended'|'unknown',
                'details': 详细信息,
                'is_valid': 布尔值，表示代码是否有效,
                'delisting_date': 退市日期（如果已退市）,
                'listing_date': 上市日期,
                'market': 所属市场
            }
        """
        result = {
            'code': code,
            'name': '',
            'status': 'unknown',
            'details': '',
            'is_valid': False,
            'delisting_date': '',
            'listing_date': '',
            'market': ''
        }
        
        # 1. 基本格式检查
        if not code or len(code) != 6 or not code.isdigit():
            result['status'] = 'invalid'
            result['details'] = '股票代码格式错误'
            return result
        
        # 2. 判断市场归属
        if code.startswith(('600', '601', '603', '605')):
            result['market'] = 'SH_MAIN'  # 上海主板
        elif code.startswith('688'):
            result['market'] = 'STAR'     # 科创板
        elif code.startswith(('000', '001')):
            result['market'] = 'SZ_MAIN'  # 深圳主板
        elif code.startswith('002'):
            result['market'] = 'SZ_SME'   # 中小板
        elif code.startswith('300'):
            result['market'] = 'CHINEXT'  # 创业板
        else:
            result['status'] = 'invalid'
            result['details'] = f'未知市场的股票代码: {code}'
            return result
        
        # 3. 使用BaoStock检测（最权威的数据源）
        if not self._ensure_baostock_login():
            result['details'] = 'BaoStock连接失败'
            return result
        
        try:
            # 转换为BaoStock格式
            bs_code = f"sh.{code}" if code.startswith(('600', '601', '603', '605', '688')) else f"sz.{code}"
            
            # 查询股票基础信息
            rs = bs.query_stock_basic(code=bs_code)
            
            if rs.error_code == '0':
                data_found = False
                while rs.next():
                    row = rs.get_row_data()
                    if len(row) >= 6:
                        # BaoStock返回格式: [code, name, ipoDate, outDate, type, status]
                        result['name'] = row[1]
                        result['listing_date'] = row[2]
                        result['delisting_date'] = row[3]
                        stock_type = row[4]
                        status = row[5]
                        
                        result['is_valid'] = True
                        data_found = True
                        
                        # 判断股票状态
                        if result['delisting_date'] and result['delisting_date'].strip():
                            result['status'] = 'delisted'
                            result['details'] = f"已退市，退市日期: {result['delisting_date']}"
                        elif status and ('停牌' in status or 'ST' in status):
                            result['status'] = 'suspended'
                            result['details'] = f"停牌或特殊处理，状态: {status}"
                        else:
                            result['status'] = 'active'
                            result['details'] = f"正常交易，上市日期: {result['listing_date']}"
                        break
                
                if not data_found:
                    result['status'] = 'invalid'
                    result['details'] = 'BaoStock数据库中无此股票记录，可能代码无效或股票从未上市'
            else:
                result['details'] = f'BaoStock查询失败: {rs.error_msg}'
                
        except Exception as e:
            result['details'] = f'BaoStock查询异常: {str(e)}'
        
        return result
    
    def batch_check_stocks(self, codes: List[str]) -> Dict[str, Dict]:
        """
        批量检测股票状态
        
        Args:
            codes: 股票代码列表
            
        Returns:
            {code: status_info} 的字典
        """
        results = {}
        
        print(f"[INFO] 批量检测股票状态: {len(codes)} 只...")
        
        if not self._ensure_baostock_login():
            print("[ERROR] BaoStock连接失败，无法进行批量检测")
            return results
        
        for i, code in enumerate(codes, 1):
            try:
                status_info = self.check_single_stock(code)
                results[code] = status_info
                
                # 显示进度和结果
                status_icon = {
                    'active': 'OK',
                    'delisted': 'DELISTED', 
                    'invalid': 'INVALID',
                    'suspended': 'SUSPENDED',
                    'unknown': 'UNKNOWN'
                }.get(status_info['status'], 'UNKNOWN')
                
                print(f"[{i}/{len(codes)}] {code} {status_icon} {status_info['name']}")
                
            except Exception as e:
                print(f"[{i}/{len(codes)}] {code} ERROR: {e}")
                results[code] = {
                    'code': code,
                    'status': 'unknown',
                    'details': f'检测异常: {str(e)}',
                    'is_valid': False
                }
        
        # 统计结果
        active_count = sum(1 for r in results.values() if r['status'] == 'active')
        delisted_count = sum(1 for r in results.values() if r['status'] == 'delisted')
        invalid_count = sum(1 for r in results.values() if r['status'] == 'invalid')
        suspended_count = sum(1 for r in results.values() if r['status'] == 'suspended')
        unknown_count = sum(1 for r in results.values() if r['status'] == 'unknown')
        
        print(f"\n[SUMMARY] 检测完成:")
        print(f"  正常交易: {active_count} 只")
        print(f"  已退市: {delisted_count} 只")
        print(f"  无效代码: {invalid_count} 只")
        print(f"  停牌/特处: {suspended_count} 只")
        print(f"  状态未知: {unknown_count} 只")
        
        return results
    
    def filter_active_stocks(self, codes: List[str]) -> List[str]:
        """
        过滤出正常交易的股票代码
        
        Args:
            codes: 股票代码列表
            
        Returns:
            正常交易的股票代码列表
        """
        results = self.batch_check_stocks(codes)
        active_codes = [code for code, info in results.items() if info['status'] == 'active']
        
        print(f"[INFO] 过滤结果: {len(active_codes)}/{len(codes)} 只股票正常交易")
        return active_codes
    
    def get_problematic_stocks(self, codes: List[str]) -> Dict[str, List[str]]:
        """
        获取有问题的股票分类
        
        Args:
            codes: 股票代码列表
            
        Returns:
            {
                'delisted': [退市股票列表],
                'invalid': [无效代码列表], 
                'suspended': [停牌股票列表]
            }
        """
        results = self.batch_check_stocks(codes)
        
        problematic = {
            'delisted': [],
            'invalid': [],
            'suspended': []
        }
        
        for code, info in results.items():
            if info['status'] in problematic:
                problematic[info['status']].append(code)
        
        return problematic
    
    def __del__(self):
        """析构函数，确保logout"""
        if self.bs_logged_in:
            try:
                bs.logout()
            except:
                pass

# 便捷函数
def check_stock_status(code: str) -> Dict[str, any]:
    """检测单只股票状态的便捷函数"""
    checker = StockStatusChecker()
    return checker.check_single_stock(code)

def is_stock_valid_and_active(code: str) -> bool:
    """快速检测股票是否有效且正常交易"""
    checker = StockStatusChecker()
    info = checker.check_single_stock(code)
    return info['status'] == 'active'

if __name__ == "__main__":
    # 测试功能
    print("=== 股票状态检测模块测试 ===")
    
    checker = StockStatusChecker()
    
    # 测试单只股票
    test_codes = ['600384', '600385', '600387', '600389', '000001', '123456']
    
    print("\n1. 单只股票检测:")
    for code in test_codes[:3]:
        info = checker.check_single_stock(code)
        print(f"{code}: {info['status']} - {info['name']} - {info['details']}")
    
    # 测试批量检测
    print(f"\n2. 批量检测:")
    results = checker.batch_check_stocks(test_codes)
    
    # 测试过滤功能
    print(f"\n3. 过滤正常股票:")
    active_stocks = checker.filter_active_stocks(test_codes)
    print(f"正常股票: {active_stocks}")
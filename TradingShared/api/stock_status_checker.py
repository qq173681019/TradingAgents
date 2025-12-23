#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票状态检测器 - 识别 ST 和 停牌股票
"""

import os
import time
from datetime import date, datetime

import pandas as pd

try:
    import tushare as ts
except ImportError:
    ts = None

class StockStatusChecker:
    def __init__(self, tushare_token=None):
        self.tushare_token = tushare_token
        self.pro = None
        if ts and tushare_token:
            try:
                self.pro = ts.pro_api(tushare_token)
            except Exception as e:
                print(f"[WARN] Tushare API 初始化失败: {e}")
        
        self.st_stocks = set()
        self.suspended_stocks = set()
        self.delisted_stocks = set()
        self.last_update_date = None

    def update_status(self, force=False):
        """更新 ST、停牌和退市股票列表"""
        today = date.today().isoformat()
        if not force and self.last_update_date == today and (self.st_stocks or self.suspended_stocks):
            return True
            
        print("[INFO] 正在更新全市场股票状态 (ST/停牌/退市)...")
        
        # 重置状态列表
        self.st_stocks = set()
        self.suspended_stocks = set()
        self.delisted_stocks = set()
        
        # 1. 优先使用 AKShare 获取全市场快照 (最快且包含 ST 和 实时停牌信息)
        ak_success = False
        try:
            import akshare as ak
            print("[INFO] 正在通过 AKShare 获取全市场快照...")
            df_spot = ak.stock_zh_a_spot_em()
            if not df_spot.empty:
                st_keywords = ['ST', '*ST', 'ST*', 'S*ST', 'SST', '退']
                for _, row in df_spot.iterrows():
                    code = str(row['代码'])
                    name = str(row['名称'])
                    
                    # 识别 ST
                    if any(kw in name.upper() for kw in st_keywords):
                        self.st_stocks.add(code)
                    
                    # 识别停牌 (成交量为0且在交易时间内)
                    vol = row.get('成交量')
                    if vol in [0, None, '', '-']:
                        self.suspended_stocks.add(code)
                
                print(f"[INFO] AKShare 识别完成: {len(self.st_stocks)} 只 ST, {len(self.suspended_stocks)} 只疑似停牌")
                ak_success = True
        except Exception as e:
            print(f"[WARN] AKShare 获取快照失败: {e}")

        # 2. 使用 Tushare 补充和校验
        if self.pro:
            try:
                print("[INFO] 正在通过 Tushare 校验股票状态...")
                # 获取上市中 (L)、暂停上市 (P) 和退市 (D)
                for status in ['L', 'P', 'D']:
                    try:
                        df = self.pro.stock_basic(exchange='', list_status=status, fields='ts_code,symbol,name')
                        if not df.empty:
                            codes = set(df['symbol'].tolist())
                            if status == 'D':
                                self.delisted_stocks.update(codes)
                            elif status == 'P':
                                self.suspended_stocks.update(codes)
                            
                            # 补充 ST 识别
                            st_keywords = ['ST', '*ST', 'ST*', 'S*ST', 'SST', '退']
                            for _, row in df.iterrows():
                                if any(kw in str(row['name']).upper() for kw in st_keywords):
                                    self.st_stocks.add(row['symbol'])
                    except:
                        continue
                
                # 尝试获取今日停牌列表 (需要2000积分)
                try:
                    trade_date = datetime.now().strftime('%Y%m%d')
                    df_suspend = self.pro.suspend_d(suspend_type='S', trade_date=trade_date)
                    if not df_suspend.empty:
                        for _, row in df_suspend.iterrows():
                            code = row['ts_code'].split('.')[0]
                            self.suspended_stocks.add(code)
                except:
                    pass
                    
            except Exception as e:
                print(f"[WARN] Tushare 校验失败: {e}")

        self.last_update_date = today
        # 只要有一种方式成功获取了数据，就返回 True
        success = ak_success or bool(self.st_stocks or self.suspended_stocks)
        if success:
            print(f"[INFO] 股票状态更新完成: ST={len(self.st_stocks)}, 停牌={len(self.suspended_stocks)}, 退市={len(self.delisted_stocks)}")
        else:
            print("[ERROR] 所有数据源均未能获取股票状态列表")
            
        return success
            
        except Exception as e:
            print(f"[ERROR] 更新股票状态时发生错误: {e}")
            return False

    def batch_check_stocks(self, codes):
        """批量检查股票状态，返回分类结果 (对接 ComprehensiveDataCollector)"""
        self.update_status()
        
        results = {}
        for code in codes:
            clean_code = code.split('.')[0] if '.' in code else code
            
            if clean_code in self.delisted_stocks:
                status = 'delisted'
            elif clean_code in self.suspended_stocks:
                status = 'suspended'
            elif clean_code in self.st_stocks:
                status = 'st'
            elif not clean_code.isdigit() or len(clean_code) != 6:
                status = 'invalid'
            else:
                status = 'active'
                
            results[code] = {'status': status}
            
        return results

    def is_st(self, code):
        """判断是否为 ST 股票"""
        # 兼容带后缀的代码
        clean_code = code.split('.')[0] if '.' in code else code
        return clean_code in self.st_stocks

    def is_suspended(self, code):
        """判断是否为停牌股票"""
        clean_code = code.split('.')[0] if '.' in code else code
        return clean_code in self.suspended_stocks

    def is_delisted(self, code):
        """判断是否为退市股票"""
        clean_code = code.split('.')[0] if '.' in code else code
        return clean_code in self.delisted_stocks

    def filter_codes(self, codes, exclude_st=True, exclude_suspended=True):
        """过滤股票代码列表"""
        if not exclude_st and not exclude_suspended:
            # 即使不排除 ST 和停牌，也应该排除退市股票
            filtered = [c for c in codes if not self.is_delisted(c)]
            return filtered
            
        filtered = []
        st_count = 0
        suspend_count = 0
        delisted_count = 0
        
        for code in codes:
            if self.is_delisted(code):
                delisted_count += 1
                continue
                
            is_st = self.is_st(code)
            is_sus = self.is_suspended(code)
            
            if exclude_st and is_st:
                st_count += 1
                continue
            if exclude_suspended and is_sus:
                suspend_count += 1
                continue
                
            filtered.append(code)
            
        if st_count > 0 or suspend_count > 0 or delisted_count > 0:
            print(f"[INFO] 过滤完成: 排除 {delisted_count} 只退市, {st_count} 只 ST, {suspend_count} 只停牌. 剩余 {len(filtered)} 只.")
            
        return filtered

if __name__ == "__main__":
    # 测试代码
    token = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"
    checker = StockStatusChecker(token)
    if checker.update_status():
        test_codes = ["000001", "600519", "000002", "ST大集", "000564"]
        filtered = checker.filter_codes(test_codes)
        print(f"原始: {test_codes}")
        print(f"过滤后: {filtered}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票状态检测器 - 识别 ST 和 停牌股票
"""

import json
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
        if tushare_token is None:
            # 尝试从环境变量或 config 导入
            tushare_token = os.environ.get('TUSHARE_TOKEN')
            if not tushare_token:
                try:
                    # 尝试从当前目录或上级目录的 config 导入
                    try:
                        from config import TUSHARE_TOKEN as token
                        tushare_token = token
                    except ImportError:
                        # 尝试从 TradingShared.config 导入
                        import sys
                        if 'TradingShared' not in sys.modules:
                            # 尝试寻找 TradingShared 路径
                            shared_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'TradingShared')
                            if os.path.exists(shared_path) and shared_path not in sys.path:
                                sys.path.insert(0, shared_path)
                        from config import TUSHARE_TOKEN as token
                        tushare_token = token
                except Exception:
                    pass
                    
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
        self.listed_stocks = set()  # 新增：记录所有在市股票
        self.last_update_date = None
        
        # 缓存文件路径
        shared_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        self.cache_file = os.path.join(shared_data_dir, 'stock_status_cache.json')
        self._load_cache()

    def _load_cache(self):
        """从文件加载状态缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                if cache_data.get('date') == date.today().isoformat():
                    self.st_stocks = set(cache_data.get('st_stocks', []))
                    self.suspended_stocks = set(cache_data.get('suspended_stocks', []))
                    self.delisted_stocks = set(cache_data.get('delisted_stocks', []))
                    self.listed_stocks = set(cache_data.get('listed_stocks', []))
                    self.last_update_date = cache_data.get('date')
                    # print(f"[INFO] 已从缓存加载股票状态: ST={len(self.st_stocks)}, 停牌={len(self.suspended_stocks)}")
            except Exception as e:
                print(f"[WARN] 加载股票状态缓存失败: {e}")

    def _save_cache(self):
        """保存状态到文件缓存"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            cache_data = {
                'date': self.last_update_date,
                'st_stocks': list(self.st_stocks),
                'suspended_stocks': list(self.suspended_stocks),
                'delisted_stocks': list(self.delisted_stocks),
                'listed_stocks': list(self.listed_stocks)
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 保存股票状态缓存失败: {e}")

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
        self.listed_stocks = set()
        
        # 1. 优先使用 AKShare 获取全市场快照 (最快且包含 ST 和 实时停牌信息)
        ak_success = False
        try:
            import akshare as ak
            print("[INFO] 正在通过 AKShare 获取全量股票列表...")
            # 获取全量 A 股列表作为基础
            try:
                df_all = ak.stock_info_a_code_name()
                if not df_all.empty:
                    self.listed_stocks = set(df_all['code'].tolist())
                    print(f"[INFO] AKShare 获取到 {len(self.listed_stocks)} 只在市股票")
            except Exception as e:
                print(f"[WARN] AKShare 获取全量列表失败: {e}")

            print("[INFO] 正在通过 AKShare 获取实时快照...")
            df_spot = ak.stock_zh_a_spot_em()
            if not df_spot.empty:
                st_keywords = ['ST', '*ST', 'ST*', 'S*ST', 'SST', '退']
                for _, row in df_spot.iterrows():
                    code = str(row['代码'])
                    name = str(row['名称'])
                    
                    # 记录在市股票
                    self.listed_stocks.add(code)
                    
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
                            else:
                                self.listed_stocks.update(codes)
                            
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
        success = ak_success or bool(self.st_stocks or self.suspended_stocks or self.listed_stocks)
        if success:
            print(f"[INFO] 股票状态更新完成: 在市={len(self.listed_stocks)}, ST={len(self.st_stocks)}, 停牌={len(self.suspended_stocks)}, 退市={len(self.delisted_stocks)}")
            self._save_cache()
        else:
            print("[ERROR] 所有数据源均未能获取股票状态列表")
            
        return success

    def batch_check_stocks(self, codes):
        """批量检查股票状态，返回分类结果 (对接 ComprehensiveDataCollector)"""
        self.update_status()
        
        results = {}
        for code in codes:
            results[code] = self.check_single_stock(code)
            
        return results

    def check_single_stock(self, code):
        """检查单只股票状态"""
        self.update_status()
        clean_code = code.split('.')[0] if '.' in code else code
        
        if self.is_delisted(code):
            status = 'delisted'
        elif clean_code in self.suspended_stocks:
            status = 'suspended'
        elif clean_code in self.st_stocks:
            status = 'st'
        elif not clean_code.isdigit() or len(clean_code) != 6:
            status = 'invalid'
        else:
            status = 'active'
            
        return {'status': status}

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
        # 如果在退市列表中，肯定是退市
        if clean_code in self.delisted_stocks:
            return True
        # 如果在市列表已加载，且不在在市列表中，也视为退市/无效
        if self.listed_stocks and clean_code not in self.listed_stocks:
            return True
        return False

    def filter_codes(self, codes, exclude_st=True, exclude_suspended=True):
        """过滤股票代码列表"""
        # 确保状态已更新
        self.update_status()
        
        filtered = []
        st_count = 0
        suspend_count = 0
        delisted_count = 0
        
        for code in codes:
            # 1. 首先排除退市/无效股票 (无论设置如何都排除)
            if self.is_delisted(code):
                delisted_count += 1
                continue
                
            # 2. 根据设置排除 ST 和 停牌
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
            print(f"[INFO] 过滤完成: 排除 {delisted_count} 只退市/无效, {st_count} 只 ST, {suspend_count} 只停牌. 剩余 {len(filtered)} 只.")
            
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

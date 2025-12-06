#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股全面数据采集器 - 轮询多数据源
支持 Tushare、akshare、yfinance、腾讯财经等多个数据源
每次采集10只股票，避免触发接口限制，排除创业板
"""

import json
import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# 数据源可用性检查
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    print("[INFO] akshare 已加载")
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[WARN] akshare 未安装")

# AKShare连通性测试
AKSHARE_CONNECTED = False

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
    print("[INFO] tushare 已加载")
except ImportError:
    TUSHARE_AVAILABLE = False
    print("[WARN] tushare 未安装")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    print("[INFO] yfinance 已加载")
except ImportError:
    YFINANCE_AVAILABLE = False
    print("[WARN] yfinance 未安装")

try:
    import requests
    REQUESTS_AVAILABLE = True
    print("[INFO] requests 已加载")
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WARN] requests 未安装")

try:
    from jina_api import JinaAPI
    JINA_AVAILABLE = True
    print("[INFO] JinaAPI 已加载")
except ImportError:
    JINA_AVAILABLE = False
    print("[WARN] JinaAPI 未加载")

try:
    from baostock_api import BaostockAPI
    BAOSTOCK_AVAILABLE = True
    print("[INFO] baostock 已加载")
except ImportError:
    BAOSTOCK_AVAILABLE = False
    print("[WARN] baostock 未安装")

# JoinQuant API 支持
try:
    from joinquant_api import JoinQuantAPI
    JOINQUANT_AVAILABLE = True
    print("[INFO] JoinQuant API 已加载")
except ImportError:
    JOINQUANT_AVAILABLE = False
    print("[WARN] JoinQuant API 未找到")

# Alpha Vantage API 支持
try:
    from alpha_vantage_api import AlphaVantageAPI
    ALPHA_VANTAGE_AVAILABLE = True
    ALPHA_VANTAGE_API_KEY = "52N6YLT15MUAA46B"
    print("[INFO] Alpha Vantage API 已加载")
except ImportError:
    ALPHA_VANTAGE_AVAILABLE = False
    print("[WARN] Alpha Vantage API 未找到")

# Polygon.io API 支持
try:
    from polygon_api import PolygonAPI
    POLYGON_AVAILABLE = True
    print("[INFO] Polygon.io API 已加载")
except ImportError:
    POLYGON_AVAILABLE = False
    print("[WARN] Polygon.io API 未安装")

# 腾讯K线API支持
try:
    from tencent_kline_api import TencentKlineAPI
    TENCENT_KLINE_AVAILABLE = True
    print("[INFO] 腾讯K线API 已加载")
except ImportError:
    TENCENT_KLINE_AVAILABLE = False
    print("[WARN] 腾讯K线API 未找到")

# BaoStock API 支持（免费K线数据兜底）
try:
    from baostock_api import BaoStockAPI
    BAOSTOCK_AVAILABLE = True
    print("[INFO] BaoStock API 已加载")
except ImportError:
    BAOSTOCK_AVAILABLE = False
    print("[WARN] BaoStock API 未找到，请安装: pip install baostock")

# 股票状态检测器
try:
    from stock_status_checker import StockStatusChecker
    STOCK_STATUS_CHECKER_AVAILABLE = True
    print("[INFO] 股票状态检测器已加载")
except ImportError:
    STOCK_STATUS_CHECKER_AVAILABLE = False
    print("[WARN] 股票状态检测器未找到")

# Choice金融终端
try:
    from config import CHOICE_PASSWORD, CHOICE_USERNAME, ENABLE_CHOICE
except ImportError:
    ENABLE_CHOICE = False
    CHOICE_USERNAME = ""
    CHOICE_PASSWORD = ""
    print("[WARN] Choice配置未找到")

print(f"[INFO] BaoStock分析: 免费稳定的A股K线数据源，作为最终兜底方案：")
print(f"       - K线数据: 免费稳定（日K线）")
print(f"       - 历史数据: 覆盖全面（A股全市场）")
print(f"       - 实时性: 适合历史分析，非实时")
print(f"       - 使用限制: 免费，但有频率限制")
print(f"       - 建议角色: K线数据的最终兜底方案")


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理日期和时间对象"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj):
            return None
        return super().default(obj)
    
    @staticmethod
    def clean_data_for_json(data):
        """清理数据中的不可序列化对象"""
        if isinstance(data, dict):
            return {k: DateTimeEncoder.clean_data_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [DateTimeEncoder.clean_data_for_json(item) for item in data]
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, pd.Timestamp):
            return data.isoformat()
        elif hasattr(data, 'dtype') and 'int' in str(data.dtype):
            return int(data)
        elif hasattr(data, 'dtype') and 'float' in str(data.dtype):
            return float(data)
        elif isinstance(data, np.ndarray):
            return data.tolist()
        elif pd.isna(data):
            return None
        else:
            return data

class ComprehensiveDataCollector:
    """全面数据采集器"""
    
    def __init__(self):
        self.tushare_token = os.environ.get('TUSHARE_TOKEN', '4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28')
        self.data_sources = ['tushare', 'baostock', 'yfinance', 'tencent', 'akshare']  # 移除choice API
        self.current_source_index = 0
        
        # 等待期间数据源策略
        self.wait_period_strategy = {
            'industry_concept': ['baostock', 'akshare'],  # 行业概念数据优先使用baostock
            'financial_data': ['tencent', 'baostock', 'akshare'],   # 财务数据：腾讯→baostock→akshare  
            'basic_info': ['tencent', 'yfinance', 'baostock', 'jina'], # 基础信息：腾讯→yfinance→baostock→jina
            'fund_flow': ['tencent', 'akshare']          # 资金流向使用腾讯/akshare
        }
        self.collected_data = {}
        self.output_file = 'data/comprehensive_stock_data.json'
        
        # 批量K线数据采集相关配置（基于测试优化）
        self.batch_kline_cache = {}  # 缓存批量获取的K线数据
        self.kline_batch_size = 15   # 每次批量获取15只股票（100%成功率）
        self.kline_batch_size_max = 20  # 最大批量20只股票（75%成功率但更快）
        self.kline_days = 50         # 获取50天的K线数据
        self.last_tushare_call = 0   # 上次tushare调用时间
        self.adaptive_batch = True   # 启用自适应批量大小
        
        # 等待期间数据收集优化
        self.wait_period_data = {}   # 在等待期间收集的其他数据
        self.enable_wait_period_collection = True  # 启用等待期间数据收集
        
        # K线数据收集策略优化
        self.kline_sources = ['tushare', 'yfinance']  # K线数据源轮换
        self.current_kline_source_index = 0
        self.last_yfinance_call = 0  # 上次yfinance调用时间
        self.yfinance_wait_seconds = 120  # yfinance等待时间(2分钟)
        
        # API轮换相关初始化
        self.last_api_switch_time = 0
        self.api_rotation_index = 0
        
        # AKShare动态监控机制
        self.akshare_call_count = 0      # AKShare调用次数
        self.akshare_success_count = 0   # AKShare成功次数
        self.akshare_fail_count = 0      # AKShare失败次数
        self.akshare_enabled = AKSHARE_AVAILABLE  # AKShare是否启用
        
        # 初始化 tushare
        if TUSHARE_AVAILABLE and self.tushare_token:
            try:
                ts.set_token(self.tushare_token)
                self.ts_pro = ts.pro_api()
                print("[INFO] tushare 初始化成功")
            except Exception as e:
                print(f"[WARN] tushare 初始化失败: {e}")
        
        # 初始化 JoinQuant API
        self.joinquant = None
        if JOINQUANT_AVAILABLE:
            try:
                self.joinquant = JoinQuantAPI()
                print("[INFO] JoinQuant API 初始化成功")
            except Exception as e:
                print(f"[WARN] JoinQuant API 初始化失败: {e}")

        # 初始化 Jina API
        self.jina_api_key = "YOUR_JINA_API_KEY" # 请替换为实际的API Key
        self.jina_api = JinaAPI(self.jina_api_key) if JINA_AVAILABLE else None
        if self.jina_api:
            print("[INFO] JinaAPI 初始化成功")

        # 初始化 Baostock API
        self.bs_login = False
        if BAOSTOCK_AVAILABLE:
            try:
                self.baostock = BaoStockAPI()
                if self.baostock.is_connected:
                    print("[INFO] BaoStock API 初始化成功（K线数据兜底）")
                    self.bs_login = True
                else:
                    print("[WARN] BaoStock API 连接失败")
                    self.baostock = None
            except Exception as e:
                print(f"[WARN] BaoStock API 初始化失败: {e}")
        else:
            print("[INFO] BaoStock 不可用，跳过初始化")
        
        # 初始化 Tencent Kline API
        self.tencent_kline = None
        if TENCENT_KLINE_AVAILABLE:
            try:
                self.tencent_kline = TencentKlineAPI()
                print("[INFO] 腾讯K线API 初始化成功")
            except Exception as e:
                print(f"[WARN] 腾讯K线API 初始化失败: {e}")
        
        # 初始化 Alpha Vantage API
        self.alpha_vantage = None
        if ALPHA_VANTAGE_AVAILABLE:
            try:
                self.alpha_vantage = AlphaVantageAPI(ALPHA_VANTAGE_API_KEY)
                print("[INFO] Alpha Vantage API 初始化成功")
            except Exception as e:
                print(f"[WARN] Alpha Vantage API 初始化失败: {e}")
        
        # 初始化 Polygon API
        self.polygon = None
        if POLYGON_AVAILABLE:
            try:
                self.polygon = PolygonAPI()
                print("[INFO] Polygon API 初始化成功")
            except Exception as e:
                print(f"[WARN] Polygon API 初始化失败: {e}")
        
        # 初始化股票状态检测器（如果可用）
        if STOCK_STATUS_CHECKER_AVAILABLE:
            try:
                self.status_checker = StockStatusChecker()
                print("[INFO] 股票状态检测器已初始化")
            except Exception as e:
                print(f"[WARN] 股票状态检测器初始化失败: {e}")
                self.status_checker = None
        else:
            self.status_checker = None
            print("[INFO] 股票状态检测器不可用，跳过初始化")

        # 确保输出目录存在
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        
        # 不在初始化时测试AKShare，改为动态监控
        if AKSHARE_AVAILABLE:
            print("[INFO] AKShare可用，将在实际使用中动态监控其成功率")
    
    def _get_next_api(self):
        """
        API轮换选择器 - 避免Alpha Vantage的12秒等待
        在Alpha Vantage和Polygon.io之间轮换使用
        """
        current_time = time.time()
        
        # 如果距离上次切换已经过了足够时间，可以切换API
        if current_time - self.last_api_switch_time > 1:  # 1秒间隔切换
            self.api_rotation_index = 1 - self.api_rotation_index  # 0<->1 切换
            self.last_api_switch_time = current_time
            print(f"[DEBUG] API轮换切换到索引: {self.api_rotation_index}")
            
        # 返回当前选择的API
        if self.api_rotation_index == 0 and self.alpha_vantage:
            return 'alpha_vantage', self.alpha_vantage
        elif self.api_rotation_index == 1 and self.polygon and self.polygon.is_available:
            return 'polygon', self.polygon
        
        # 如果首选API不可用，尝试另一个
        if self.alpha_vantage:
            return 'alpha_vantage', self.alpha_vantage
        elif self.polygon and self.polygon.is_available:
            return 'polygon', self.polygon
        
        return None, None
    
    def _is_us_stock(self, code: str) -> bool:
        """判断是否为美股代码"""
        if not code:
            return False
            
        # 美股代码通常是字母组合
        if code.isalpha() and len(code) >= 1:
            return True
        
        # 排除明显的A股代码格式
        if code.isdigit() and len(code) == 6:
            return False
            
        # 包含.的可能是美股或其他市场
        if '.' in code:
            return True
            
        return False
    
    def _detect_market(self, code: str) -> str:
        """
        检测股票代码所属市场
        
        Returns:
            'cn': 中国A股
            'us': 美股
            'other': 其他市场
        """
        if not code:
            return 'other'
        
        code = code.upper().strip()
        
        # A股代码模式：6位数字
        if code.isdigit() and len(code) == 6:
            return 'cn'
        
        # 带交易所后缀的代码
        if '.' in code:
            base_code, suffix = code.split('.', 1)
            suffix = suffix.upper()
            if suffix in ['SS', 'SZ', 'HK']:  # 上交所、深交所、港交所
                return 'cn'
            elif suffix in ['US', 'NASDAQ', 'NYSE']:  # 美股
                return 'us'
            # 如果后缀不明确，继续根据基础代码判断
            code = base_code
        
        # 美股代码模式：1-5位字母
        if code.isalpha() and 1 <= len(code) <= 5:
            return 'us'
        
        # 混合字母数字的复杂情况
        if code.isdigit():
            return 'cn'  # 纯数字倾向于A股
        elif code.isalpha():
            return 'us'  # 纯字母倾向于美股
        
        return 'other'
    
    def collect_multi_market_kline_data(self, codes: List[str], days: int = 30) -> Dict[str, Any]:
        """
        多市场K线数据收集（支持A股和美股）
        
        Args:
            codes: 股票代码列表，可包含A股和美股代码
            days: 获取天数
            
        Returns:
            包含K线数据的字典，按市场分类
        """
        print(f"[INFO] 多市场K线数据收集: {len(codes)} 只股票")
        
        # 按市场分类股票代码
        cn_stocks = []  # A股
        us_stocks = []  # 美股
        other_stocks = []  # 其他
        
        for code in codes:
            market = self._detect_market(code)
            if market == 'cn':
                cn_stocks.append(code)
            elif market == 'us':
                us_stocks.append(code)
            else:
                other_stocks.append(code)
        
        print(f"[INFO] 市场分类: A股 {len(cn_stocks)} 只, 美股 {len(us_stocks)} 只, 其他 {len(other_stocks)} 只")
        
        result = {
            'cn_data': {},  # A股数据
            'us_data': {},  # 美股数据
            'summary': {
                'total_codes': len(codes),
                'cn_count': len(cn_stocks),
                'us_count': len(us_stocks),
                'other_count': len(other_stocks),
                'cn_success': 0,
                'us_success': 0
            }
        }
        
        # 收集A股数据（使用现有方法）
        if cn_stocks:
            print(f"\n[INFO] 收集A股数据: {len(cn_stocks)} 只")
            try:
                cn_data = self.collect_batch_kline_data(cn_stocks)
                result['cn_data'] = cn_data
                result['summary']['cn_success'] = len(cn_data)
                print(f"[SUCCESS] A股数据收集完成: {len(cn_data)}/{len(cn_stocks)}")
            except Exception as e:
                print(f"[ERROR] A股数据收集异常: {e}")
        
        # 收集美股数据（Polygon.io作为备选）
        if us_stocks:
            print(f"\n[INFO] 收集美股数据: {len(us_stocks)} 只")
            us_data = {}
            
            # 使用Polygon.io补充
            remaining_stocks = [code for code in us_stocks if code not in us_data]
            if remaining_stocks and self.polygon and self.polygon.is_available:
                print(f"[INFO] 使用Polygon.io补充剩余 {len(remaining_stocks)} 只股票")
                try:
                    polygon_data = self.polygon.batch_get_us_klines(remaining_stocks, days)
                    us_data.update(polygon_data)
                    print(f"[SUCCESS] Polygon.io补充 {len(polygon_data)} 只股票数据")
                except Exception as e:
                    print(f"[ERROR] Polygon.io数据收集异常: {e}")
            
            result['us_data'] = us_data
            result['summary']['us_success'] = len(us_data)
            print(f"[SUCCESS] 美股数据收集完成: {len(us_data)}/{len(us_stocks)}")
        elif us_stocks:
            print(f"[WARN] 发现 {len(us_stocks)} 只美股代码，但美股API不可用")
        
        # 其他市场提示
        if other_stocks:
            print(f"[WARN] 发现 {len(other_stocks)} 只其他市场代码，暂不支持: {other_stocks[:5]}")
        
        # 生成总结报告
        total_success = result['summary']['cn_success'] + result['summary']['us_success']
        success_rate = total_success / len(codes) * 100 if codes else 0
        
        print(f"\n[SUMMARY] 多市场数据收集完成:")
        print(f"  总计: {total_success}/{len(codes)} ({success_rate:.1f}%)")
        print(f"  A股: {result['summary']['cn_success']}/{result['summary']['cn_count']}")
        print(f"  美股: {result['summary']['us_success']}/{result['summary']['us_count']}")
        
        return result
    
    def collect_multi_market_basic_info(self, codes: List[str]) -> Dict[str, Any]:
        """
        多市场基本信息收集（支持A股和美股）
        
        Args:
            codes: 股票代码列表，可包含A股和美股代码
            
        Returns:
            包含基本信息的字典，按市场分类
        """
        print(f"[INFO] 多市场基本信息收集: {len(codes)} 只股票")
        
        # 按市场分类
        cn_stocks = []
        us_stocks = []
        
        for code in codes:
            market = self._detect_market(code)
            if market == 'cn':
                cn_stocks.append(code)
            elif market == 'us':
                us_stocks.append(code)
        
        result = {
            'cn_data': {},
            'us_data': {},
            'summary': {
                'cn_success': 0,
                'us_success': 0
            }
        }
        
        # 收集A股基本信息
        if cn_stocks:
            print(f"[INFO] 收集A股基本信息: {len(cn_stocks)} 只")
            cn_info = self.collect_batch_basic_info(cn_stocks)
            result['cn_data'] = cn_info
            result['summary']['cn_success'] = len(cn_info)
        
        # 收集美股基本信息（Polygon.io作为备选）
        if us_stocks:
            print(f"[INFO] 收集美股基本信息: {len(us_stocks)} 只")
            us_info = {}
            
            # 使用Polygon.io补充
            remaining_stocks = [code for code in us_stocks if code not in us_info]
            if remaining_stocks and self.polygon and self.polygon.is_available:
                print(f"[INFO] 使用Polygon.io补充剩余 {len(remaining_stocks)} 只股票")
                for symbol in remaining_stocks:
                    try:
                        info = self.polygon.get_company_info(symbol)
                        if info:
                            us_info[symbol] = info
                    except Exception as e:
                        print(f"[WARN] Polygon.io获取 {symbol} 信息失败: {e}")
            
            result['us_data'] = us_info
            result['summary']['us_success'] = len(us_info)
            print(f"[SUCCESS] 美股信息收集完成: {len(us_info)}/{len(us_stocks)}")
        
        return result
            
        # A股代码模式
        if code.isdigit() and len(code) == 6:
            return 'cn'
            
        # 美股代码模式
        if code.isalpha() and 1 <= len(code) <= 5:
            return 'us'
            
        # 带交易所后缀的代码
        if '.' in code:
            suffix = code.split('.')[-1].upper()
            if suffix in ['SS', 'SZ', 'HK']:  # 上交所、深交所、港交所
                return 'cn'
            elif suffix in ['US', 'NASDAQ', 'NYSE']:  # 美股
                return 'us'
                
        # 默认按字母数字比例判断
        if code.isalpha():
            return 'us'
        elif code.isdigit():
            return 'cn'
            
        return 'other'
    
    def _check_akshare_health(self) -> None:
        """
        检查AKShare健康状况，如果失败率超过50%则禁用
        """
        if self.akshare_call_count < 10:  # 至少需要10次调用才能判断
            return
        
        fail_rate = self.akshare_fail_count / self.akshare_call_count
        
        if fail_rate > 0.5 and self.akshare_enabled:
            self.akshare_enabled = False
            print(f"[WARN] AKShare失败率过高 ({fail_rate*100:.1f}%)，已自动禁用")
            print(f"[INFO] 统计: 总调用{self.akshare_call_count}次，成功{self.akshare_success_count}次，失败{self.akshare_fail_count}次")
        elif fail_rate <= 0.3 and not self.akshare_enabled and self.akshare_call_count >= 20:
            # 如果失败率降至30%以下，且已有足够样本，重新启用
            self.akshare_enabled = True
            print(f"[INFO] AKShare失败率已降低 ({fail_rate*100:.1f}%)，重新启用")
    
    def _record_akshare_call(self, success: bool) -> None:
        """
        记录AKShare调用结果
        
        Args:
            success: 调用是否成功
        """
        self.akshare_call_count += 1
        if success:
            self.akshare_success_count += 1
        else:
            self.akshare_fail_count += 1
        
        # 每10次调用检查一次健康状况
        if self.akshare_call_count % 10 == 0:
            self._check_akshare_health()
    
    def _test_akshare_connectivity(self) -> bool:
        """
        【已废弃】测试AKShare连通性
        现在使用动态监控机制，不再在初始化时测试
        
        Returns:
            bool: True表示连接成功，False表示连接失败
        """
        global AKSHARE_CONNECTED
        
        if not AKSHARE_AVAILABLE:
            print("[INFO] AKShare未安装，跳过连通性测试")
            AKSHARE_CONNECTED = False
            return False
        
        print("[INFO] 开始测试AKShare连通性...")
        
        # 测试用例：简单的股票信息查询
        test_cases = [
            {
                'name': '股票代码列表',
                'function': lambda: ak.stock_info_a_code_name().head(1),
                'timeout': 10
            },
            {
                'name': '实时行情',
                'function': lambda: ak.stock_zh_a_spot_em().head(1), 
                'timeout': 8
            },
            {
                'name': '基本信息',
                'function': lambda: ak.stock_individual_info_em(symbol="000001"),
                'timeout': 8
            }
        ]
        
        success_count = 0
        total_tests = len(test_cases)
        
        for i, test_case in enumerate(test_cases):
            try:
                print(f"  [{i+1}/{total_tests}] 测试{test_case['name']}...", end="")
                
                # 设置超时机制
                import signal
                def timeout_handler(signum, frame):
                    raise TimeoutError("测试超时")
                
                # Windows系统使用线程超时
                if os.name == 'nt':
                    import threading
                    result = [None]
                    exception = [None]
                    
                    def test_thread():
                        try:
                            result[0] = test_case['function']()
                        except Exception as e:
                            exception[0] = e
                    
                    thread = threading.Thread(target=test_thread)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=test_case['timeout'])
                    
                    if thread.is_alive():
                        print(" ❌ 超时")
                        continue
                    elif exception[0]:
                        error_msg = str(exception[0])
                        error_type = type(exception[0]).__name__
                        print(f" ❌ 异常: {error_type}")
                        # 详细诊断AKShare常见错误
                        if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                            print(f"    [诊断] 网络超时 - 可能网络连接不稳定或AKShare服务器响应慢")
                        elif 'connection' in error_msg.lower() or 'network' in error_msg.lower():
                            print(f"    [诊断] 网络连接问题 - 请检查网络连接")
                        elif '502' in error_msg or '503' in error_msg or '504' in error_msg:
                            print(f"    [诊断] 服务器错误 - AKShare后端服务可能暂时不可用")
                        elif 'ssl' in error_msg.lower() or 'certificate' in error_msg.lower():
                            print(f"    [诊断] SSL证书问题 - 可能需要更新证书或关闭SSL验证")
                        elif 'forbidden' in error_msg.lower() or '403' in error_msg:
                            print(f"    [诊断] 访问被拒绝 - 可能IP被限制或需要更新AKShare版本")
                        continue
                    elif result[0] is not None and not result[0].empty:
                        print(" ✅ 成功")
                        success_count += 1
                    else:
                        print(" ❌ 无数据")
                else:
                    # Unix系统使用signal超时
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(test_case['timeout'])
                    
                    try:
                        result = test_case['function']()
                        signal.alarm(0)
                        
                        if result is not None and not result.empty:
                            print(" ✅ 成功")
                            success_count += 1
                        else:
                            print(" ❌ 无数据")
                    except TimeoutError:
                        print(" ❌ 超时")
                        signal.alarm(0)
                    except Exception as e:
                        print(f" ❌ 异常: {type(e).__name__}")
                        signal.alarm(0)
                        
            except Exception as e:
                print(f" ❌ 测试失败: {type(e).__name__}")
                continue
            
            # 测试间隔
            time.sleep(1)
        
        # 评估连通性
        success_rate = success_count / total_tests
        
        if success_rate >= 0.8:  # 80%以上测试成功才认为连接正常
            AKSHARE_CONNECTED = True
            print(f"[SUCCESS] AKShare连通性测试通过 ({success_count}/{total_tests}, {success_rate*100:.0f}%)")
            print("[INFO] AKShare将作为数据源使用")
            return True
        else:
            AKSHARE_CONNECTED = False
            print(f"[WARN] AKShare连通性测试失败 ({success_count}/{total_tests}, {success_rate*100:.0f}%)")
            print("[INFO] AKShare将被跳过，使用其他数据源")
            return False
    
    def get_stock_list_excluding_cyb(self, limit: int = 50) -> List[str]:
        """获取全部主板股票列表（排除创业板300、科创板688和ETF）"""
        stock_codes = []
        # 优先从 akshare 获取完整列表
        if AKSHARE_AVAILABLE and self.akshare_enabled:
            try:
                print("[INFO] 尝试从 akshare 获取股票列表...")
                df = ak.stock_info_a_code_name()
                all_codes = df['code'].astype(str).tolist()
                self._record_akshare_call(True)  # 记录成功
                # 只保留主板股票：沪市主板(60开头) + 深市主板(000开头) + 深市中小板(002开头)
                main_board_codes = [code for code in all_codes 
                                  if (code.startswith('60') or code.startswith('000') or code.startswith('002'))
                                  and not code.startswith('688') and not code.startswith('300') and not code.startswith('ETF')]
                stock_codes = main_board_codes
                print(f"[SUCCESS] 从 akshare 获取 {len(stock_codes)} 只主板股票（已排除创业板300、科创板688和ETF）")
                return stock_codes
            except Exception as e:
                self._record_akshare_call(False)  # 记录失败
                print(f"[ERROR] akshare 获取股票列表失败: {type(e).__name__}: {e}")
        # 尝试从 Baostock 获取
        if BAOSTOCK_AVAILABLE:
            try:
                print(f"[INFO] 尝试从 Baostock 获取股票列表...")
                import baostock as bs
                lg = bs.login()
                rs = bs.query_all_stock(day=datetime.now().strftime('%Y-%m-%d'))
                if rs.error_code == '0':
                    all_codes = []
                    while rs.next():
                        row = rs.get_row_data()
                        if len(row) > 0:
                            full_code = row[0]
                            if '.' in full_code:
                                code = full_code.split('.')[1]
                                all_codes.append(code)
                    main_board_codes = [code for code in all_codes 
                                      if (code.startswith('60') or code.startswith('000') or code.startswith('002'))
                                      and not code.startswith('688') and not code.startswith('300') and not code.startswith('ETF')]
                    stock_codes = main_board_codes
                    if stock_codes:
                        print(f"[SUCCESS] 从 Baostock 获取 {len(stock_codes)} 只主板股票")
                        return stock_codes
            except Exception as e:
                print(f"[ERROR] Baostock 获取股票列表失败: {e}")
        print(f"[INFO] 切换到备用主板股票池...")
        print(f"[WARN] akshare 和 Baostock 均获取失败，使用扩展备用股票池（1000+只主板股票）")
        fallback_codes = []
        for i in range(1000):
            code = f"60{i:04d}"
            fallback_codes.append(code)
        for i in range(1000, 2000):
            code = f"60{i:04d}"
            fallback_codes.append(code)
        for i in range(1, 1000):
            code = f"000{i:03d}"
            fallback_codes.append(code)
        for i in range(1, 1000):
            code = f"002{i:03d}"
            fallback_codes.append(code)
        # 过滤创业板、科创板、ETF
        fallback_codes = [code for code in fallback_codes if not code.startswith('688') and not code.startswith('300') and not code.startswith('ETF')]
        print(f"[INFO] 备用股票池共生成 {len(fallback_codes)} 只主板股票代码")
        return fallback_codes
    
    def get_stock_list_by_type(self, stock_type: str = "主板", limit: int = 50) -> List[str]:
        """根据股票类型获取股票列表"""
        if stock_type == "主板":
            # 主板股票：60/000/002开头，排除30创业板和688科创板
            return self.get_stock_list_excluding_cyb(limit)
        elif stock_type == "全部":
            # 获取所有股票（包括创业板和科创板）
            return self.get_all_stock_list(limit)
        elif stock_type == "ETF":
            # 获取ETF列表
            return self.get_etf_list(limit)
        else:
            # 默认返回主板
            return self.get_stock_list_excluding_cyb(limit)
    
    def get_etf_list(self, limit: int = 50) -> List[str]:
        """获取ETF列表"""
        etf_codes = []
        
        if AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
            try:
                print("[INFO] 尝试从 akshare 获取ETF列表...")
                df = ak.fund_etf_spot_em()
                all_codes = df['代码'].astype(str).tolist()
                etf_codes = all_codes[:limit]
                print(f"[SUCCESS] 从 akshare 获取 {len(etf_codes)} 只ETF")
                return etf_codes
            except Exception as e:
                print(f"[ERROR] akshare 获取ETF列表失败: {e}")
        
        # 备选ETF列表
        fallback_etf = [
            '510050', '510300', '510500', '510880', '512100', '512690', '512880',
            '513050', '515050', '515790', '516160', '518880', '159915', '159919',
            '159949', '159995', '159996'
        ]
        return fallback_etf[:limit]
    
    def get_all_stock_list(self, limit: int = 5500) -> List[str]:
        """获取完整股票列表，排除创业板和科创板"""
        stock_codes = []
        
        # 优先从 akshare 获取完整列表
        if AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
            try:
                df = ak.stock_info_a_code_name()
                all_codes = df['code'].astype(str).tolist()
                # 排除创业板(300)和科创板(688)
                filtered_codes = [code for code in all_codes if not (code.startswith('300') or code.startswith('688'))]
                stock_codes = filtered_codes[:limit]
                print(f"[INFO] 从 akshare 获取 {len(stock_codes)} 只主板股票（已排除创业板和科创板）")
                return stock_codes
            except Exception as e:
                print(f"[WARN] akshare 获取股票列表失败: {e}")
        
        # 备选：从 BaoStock 获取完整股票列表
        if BAOSTOCK_AVAILABLE and hasattr(self, 'bs'):
            try:
                print("[INFO] 尝试从 BaoStock 获取完整股票列表...")
                
                # 获取所有股票（排除创业板和科创板）
                rs = bs.query_all_stock()
                if rs.error_code != '0':
                    raise Exception(f"BaoStock 查询错误: {rs.error_msg}")
                
                all_stocks = []
                while rs.next():
                    code = rs.get_row_data()[0]
                    if code and '.' in code:
                        # 转换格式：sh.600000 -> 600000
                        clean_code = code.split('.')[1]
                        if len(clean_code) == 6 and clean_code.isdigit():
                            # 排除创业板(300)和科创板(688)
                            if not (clean_code.startswith('300') or clean_code.startswith('688')):
                                all_stocks.append(clean_code)
                
                stock_codes = all_stocks[:limit]
                print(f"[SUCCESS] 从 BaoStock 获取 {len(stock_codes)} 只主板股票（已排除创业板和科创板）")
                return stock_codes
                
            except Exception as e:
                print(f"[WARN] BaoStock 获取完整股票列表失败: {e}")
        
        # 最后备选：从现有数据文件中获取股票列表
        try:
            import json

            # 使用相对路径，因为data_dir可能未初始化
            index_file = "data/stock_file_index.json"
            if os.path.exists(index_file):
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                    # 排除创业板(300)和科创板(688)
                    filtered_codes = [code for code in index_data.keys() if not (code.startswith('300') or code.startswith('688'))]
                    stock_codes = filtered_codes[:limit]
                    print(f"[INFO] 从现有数据文件获取 {len(stock_codes)} 只主板股票（已排除创业板和科创板）")
                    return stock_codes
        except Exception as e:
            print(f"[WARN] 从数据文件获取股票列表失败: {e}")
        
        # 最终备选：内置主板股票池（排除创业板和科创板）
        fallback_codes = [
            # 沪市主板
            '600000', '600036', '600519', '600276', '600887', '600585', '600309', '600028',
            '601318', '601166', '601328', '601398', '601288', '601939', '601988', '601012',
            '600031', '600048', '600196', '600688', '600745', '600547', '600900', '600660',
            
            # 深市主板
            '000001', '000002', '000063', '000100', '000157', '000166', '000568', '000596',
            '000625', '000651', '000725', '000858', '000876', '000895', '000938', '000977',
            '002001', '002027', '002050', '002120', '002129', '002142', '002304', '002352',
            '002714', '002415', '002594', '002174', '002475'
        ]
        print(f"[INFO] 使用内置主板股票池 {len(fallback_codes)} 只股票（已排除创业板和科创板）")
        return fallback_codes[:limit]
    
    def standardize_kline_columns(self, df: pd.DataFrame, source: str = 'unknown') -> pd.DataFrame:
        """标准化K线数据DataFrame的列名"""
        if df is None or df.empty:
            return df
        
        # 定义标准列名映射
        column_mappings = {
            'tushare': {
                'trade_date': 'date', 'ts_code': 'code', 
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'vol': 'volume'
            },
            'akshare': {
                '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume',
                'date': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'
            },
            'yfinance': {
                'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            },
            'alpha_vantage': {
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'
            },
            'joinquant': {
                '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume',
                'date': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume',
                'code': 'code'
            }
        }
        
        try:
            # 尝试获取对应数据源的映射
            mapping = column_mappings.get(source, {})
            
            # 如果没有映射，尝试自动检测
            if not mapping:
                for src, map_dict in column_mappings.items():
                    if any(col in df.columns for col in map_dict.keys()):
                        mapping = map_dict
                        source = src
                        break
            
            # 应用列名映射
            if mapping:
                df = df.rename(columns=mapping)
                print(f"[DEBUG] {source}数据列名已标准化: {list(df.columns)}")
            
            # 确保必须的列存在
            required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            existing_columns = [col for col in required_columns if col in df.columns]
            
            if len(existing_columns) >= 4:  # 至少有基础的OHLC数据
                return df[existing_columns].copy()
            else:
                print(f"[WARN] 数据列不足，现有列: {list(df.columns)}")
                return df
                
        except Exception as e:
            print(f"[ERROR] 列名标准化失败: {e}")
            return df
    
    def collect_batch_kline_data(self, codes: List[str], source: str = 'auto') -> Dict[str, pd.DataFrame]:
        """批量采集K线数据 - 新策略: 基于时间控制的TUSHARE优先 → AKShare替代 → 腾讯K线兜底"""
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 开始采集K线数据，共 {total_codes} 只股票")
        print(f"[INFO] 新采集策略: Choice金融终端优先 → TUSHARE → AKShare → 腾讯K线兜底")
        
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.kline_days)
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        start_iso = start_date.strftime('%Y-%m-%d')
        end_iso = end_date.strftime('%Y-%m-%d')
        
        print(f"[INFO] 获取日期范围: {start_iso} 到 {end_iso} ({self.kline_days}天)")
        
        # 不使用 Choice API，直接使用其他数据源
        primary_source = None
        primary_codes = codes.copy()
        
        # 使用其他数据源
        if primary_source is None:
            # 检查上次TUSHARE调用时间，决定使用哪个数据源
            current_time = time.time()
            time_since_last_tushare = current_time - self.last_tushare_call
            can_use_tushare = time_since_last_tushare >= 60  # 1分钟间隔
            
            if can_use_tushare:
                print(f"[INFO] 距离上次TUSHARE调用已过 {time_since_last_tushare:.1f} 秒，使用TUSHARE获取剩余 {len(primary_codes)} 只")
                primary_source = 'tushare'
            elif AKSHARE_AVAILABLE and self.akshare_enabled:
                wait_time = 60 - time_since_last_tushare
                print(f"[INFO] TUSHARE需等待 {wait_time:.1f} 秒，使用AKShare获取剩余 {len(primary_codes)} 只")
                primary_source = 'akshare'
            else:
                # 如果AKShare不可用，使用腾讯API
                wait_time = 60 - time_since_last_tushare
                print(f"[INFO] TUSHARE需等待 {wait_time:.1f} 秒，AKShare不可用，使用腾讯API获取剩余 {len(primary_codes)} 只")
                primary_source = 'tencent'
        
        print(f"[INFO] 备用数据源: {primary_source.upper()}处理 {len(primary_codes)} 只")
        
        # 1. 主要数据源处理
        primary_success = []
        if primary_source == 'tushare' and TUSHARE_AVAILABLE and self.tushare_token:
            print(f"[INFO] TUSHARE 批量处理 {len(primary_codes)} 只股票...")
            try:
                pro = ts.pro_api(self.tushare_token)
                
                # 更新TUSHARE调用时间
                self.last_tushare_call = time.time()
                
                for code in primary_codes:
                    try:
                        ts_code = f"{code}.SZ" if code.startswith(('000', '002', '300')) else f"{code}.SH"
                        df = pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
                        if not df.empty:
                            df = self.standardize_kline_columns(df, 'tushare')
                            result[code] = df
                            primary_success.append(code)
                        time.sleep(0.1)  # TUSHARE请求间隔
                    except Exception as e:
                        error_msg = str(e)
                        error_type = type(e).__name__
                        
                        # 详细诊断Tushare常见错误
                        if 'no data' in error_msg.lower() or 'empty' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: 无数据 - 可能该股票在指定时间范围内无交易数据")
                        elif 'permission' in error_msg.lower() or 'not authorized' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: 权限不足 - 可能需要更高权限的Token或该数据需要付费")
                        elif 'frequency' in error_msg.lower() or 'limit' in error_msg.lower() or 'too many' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: 频率限制 - API调用过于频繁，已触发限流")
                        elif 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: 网络超时 - 可能网络连接不稳定")
                        elif 'invalid' in error_msg.lower() and 'symbol' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: 股票代码无效 - {ts_code}可能不存在或已退市")
                        elif '40001' in error_msg or '40002' in error_msg or '40003' in error_msg:
                            print(f"[WARN] TUSHARE获取{code}失败: API错误({error_msg}) - Tushare服务端问题")
                        elif 'token' in error_msg.lower() or 'invalid token' in error_msg.lower():
                            print(f"[WARN] TUSHARE获取{code}失败: Token无效 - 请检查Tushare Token是否正确")
                        else:
                            print(f"[WARN] TUSHARE获取{code}失败: {error_type}: {error_msg}")
                        
                        fallback_codes.append(code)
                        continue
                
                print(f"[SUCCESS] TUSHARE 成功: {len(primary_success)}/{len(primary_codes)} 只")
            except Exception as e:
                print(f"[ERROR] TUSHARE 批量处理异常: {e}")
                fallback_codes.extend(primary_codes)
        
        elif primary_source == 'akshare' and AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
            print(f"[INFO] AKShare 批量处理 {len(primary_codes)} 只股票...")
            try:
                for code in primary_codes:
                    try:
                        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_iso, end_date=end_iso)
                        if not df.empty:
                            df = self.standardize_kline_columns(df, 'akshare')
                            result[code] = df
                            primary_success.append(code)
                        time.sleep(0.2)  # AKShare请求间隔
                    except Exception as e:
                        print(f"[WARN] AKShare获取{code}失败: {e}")
                        fallback_codes.append(code)
                        continue
                
                print(f"[SUCCESS] AKShare 成功: {len(primary_success)}/{len(primary_codes)} 只")
            except Exception as e:
                print(f"[ERROR] AKShare 批量处理异常: {e}")
                fallback_codes.extend(primary_codes)
        
        elif primary_source == 'tencent' and TENCENT_KLINE_AVAILABLE and self.tencent_kline:
            print(f"[INFO] 腾讯K线API 批量处理 {len(primary_codes)} 只股票...")
            try:
                # 使用腾讯K线API批量获取
                tencent_results = self.tencent_kline.batch_get_klines(primary_codes, start_iso, end_iso)
                
                for code in primary_codes:
                    if code in tencent_results:
                        df = tencent_results[code]
                        if df is not None and not df.empty:
                            df = self.standardize_kline_columns(df, 'tencent')
                            if not df.empty:
                                result[code] = df
                                primary_success.append(code)
                                continue
                    fallback_codes.append(code)
                
                print(f"[SUCCESS] 腾讯K线API 成功: {len(primary_success)}/{len(primary_codes)} 只")
            except Exception as e:
                print(f"[ERROR] 腾讯K线API 批量处理异常: {e}")
                fallback_codes.extend(primary_codes)
        else:
            print(f"[WARN] {primary_source.upper()} 不可用，将所有股票转为后备处理")
            fallback_codes.extend(primary_codes)
        
        # 2. 失败股票的多级后备处理：腾讯K线 → AlphaVantage → yfinance
        if fallback_codes:
            print(f"[INFO] 有 {len(fallback_codes)} 只股票需要后备数据源处理")
            print(f"[INFO] 后备处理顺序: 腾讯K线 → AlphaVantage → yfinance")
            remaining_codes = fallback_codes.copy()
            
            # 第一级：腾讯K线替代处理
            tencent_success = []
            if remaining_codes and self.tencent_kline:
                print(f"[INFO] 腾讯K线API 替代处理 {len(remaining_codes)} 只失败股票...")
                try:
                    # 使用腾讯K线API批量获取
                    tencent_results = self.tencent_kline.batch_get_klines(remaining_codes, start_iso, end_iso)
                    
                    temp_remaining = []
                    for code in remaining_codes:
                        if code in tencent_results:
                            df = tencent_results[code]
                            if df is not None and not df.empty:
                                df = self.standardize_kline_columns(df, 'tencent')
                                if not df.empty:
                                    result[code] = df
                                    tencent_success.append(code)
                                    continue
                        temp_remaining.append(code)
                    
                    remaining_codes = temp_remaining
                    print(f"[SUCCESS] 腾讯K线API 替代成功: {len(tencent_success)}/{len(fallback_codes)} 只")
                except Exception as e:
                    print(f"[ERROR] 腾讯K线API 替代处理异常: {e}")
            elif remaining_codes and not self.tencent_kline:
                print(f"[WARN] 腾讯K线API未初始化，跳过处理 {len(remaining_codes)} 只股票")
            
            # 第二级：API轮换替代处理 (Alpha Vantage + Polygon.io)
            api_rotation_success = []
            if remaining_codes and (self.alpha_vantage or (self.polygon and self.polygon.is_available)):
                print(f"[INFO] API轮换替代处理 {len(remaining_codes)} 只失败股票...")
                try:
                    temp_remaining = []
                    for code in remaining_codes:
                        try:
                            # 获取下一个可用API
                            api_name, api_instance = self._get_next_api()
                            
                            if not api_instance:
                                temp_remaining.append(code)
                                continue
                            
                            df = None
                            
                            # 根据API类型调用相应方法
                            if api_name == 'alpha_vantage':
                                print(f"[INFO] {code}: 使用 Alpha Vantage")
                                df = api_instance.get_daily_kline(code, outputsize='compact')
                            elif api_name == 'polygon':
                                print(f"[INFO] {code}: 使用 Polygon.io") 
                                df = api_instance.get_us_stock_kline(code, days=30)  # Polygon.io使用正确的方法名
                            
                            if df is not None and not df.empty:
                                # 处理数据格式
                                df = df.reset_index()
                                if 'index' in df.columns:
                                    df = df.rename(columns={'index': 'date'})
                                
                                # 按日期范围过滤
                                if 'date' in df.columns:
                                    df['date'] = pd.to_datetime(df['date'])
                                    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
                                    df = df[mask]
                                
                                if not df.empty:
                                    df = self.standardize_kline_columns(df, api_name)
                                    result[code] = df
                                    api_rotation_success.append(code)
                                    print(f"[SUCCESS] {code}: {api_name}获取成功")
                                    continue
                            
                            temp_remaining.append(code)
                            
                        except Exception as e:
                            print(f"[WARN] API轮换获取{code}失败: {e}")
                            temp_remaining.append(code)
                            time.sleep(0.5)  # 减少等待时间
                    
                    remaining_codes = temp_remaining
                    print(f"[SUCCESS] API轮换替代成功: {len(api_rotation_success)}/{len(fallback_codes)} 只")
                except Exception as e:
                    print(f"[ERROR] API轮换替代处理异常: {e}")
            elif remaining_codes and not (self.alpha_vantage or (self.polygon and self.polygon.is_available)):
                print(f"[WARN] API轮换不可用，跳过处理 {len(remaining_codes)} 只股票")
            
            # 第三级：yfinance最终兜底处理
            yfinance_success = []
            if remaining_codes:
                print(f"[INFO] yfinance 最终兜底处理 {len(remaining_codes)} 只失败股票...")
                try:
                    # 使用yfinance批量获取
                    yf_results = self._collect_batch_basic_info_with_yfinance(remaining_codes)
                    
                    temp_remaining = []
                    for code in remaining_codes:
                        if code in yf_results and 'kline_data' in yf_results[code]:
                            df = yf_results[code]['kline_data']
                            if df is not None and not df.empty:
                                # 按日期范围过滤
                                if 'date' in df.columns:
                                    df['date'] = pd.to_datetime(df['date'])
                                    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
                                    df = df[mask]
                                
                                if not df.empty:
                                    result[code] = df
                                    yfinance_success.append(code)
                                    continue
                        temp_remaining.append(code)
                    
                    remaining_codes = temp_remaining
                    print(f"[SUCCESS] yfinance 兜底成功: {len(yfinance_success)}/{len(fallback_codes)} 只")
                except Exception as e:
                    print(f"[ERROR] yfinance 兜底处理异常: {e}")
            
            final_failed_codes = remaining_codes
        else:
            baostock_success = []
            alpha_success = []
            yfinance_success = []
            final_failed_codes = []
            
            # 先尝试用另一个数据源
            secondary_source = 'akshare' if primary_source == 'tushare' else 'tushare'
            secondary_success = []
            remaining_codes = fallback_codes.copy()
            
            if secondary_source == 'akshare' and AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
                print(f"[INFO] AKShare 替代处理 {len(remaining_codes)} 只失败股票...")
                temp_remaining = []
                for code in remaining_codes:
                    try:
                        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_iso, end_date=end_iso)
                        if not df.empty:
                            df = self.standardize_kline_columns(df, 'akshare')
                            result[code] = df
                            secondary_success.append(code)
                        else:
                            temp_remaining.append(code)
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"[WARN] AKShare替代获取{code}失败: {e}")
                        temp_remaining.append(code)
                remaining_codes = temp_remaining
                print(f"[SUCCESS] AKShare 替代成功: {len(secondary_success)}/{len(fallback_codes)} 只")
            
            elif secondary_source == 'tushare' and TUSHARE_AVAILABLE and self.tushare_token:
                # 检查是否需要等待，如果需要等待则跳过TUSHARE，直接进入下一级
                current_time = time.time()
                if current_time - self.last_tushare_call < 60:
                    wait_time = 60 - (current_time - self.last_tushare_call)
                    print(f"[INFO] TUSHARE需等待 {wait_time:.1f} 秒，跳过直接使用yfinance替代...")
                    # 不等待，直接将codes加入remaining_codes进入下一级处理
                    remaining_codes = fallback_codes.copy()
                else:
                    print(f"[INFO] TUSHARE 替代处理 {len(remaining_codes)} 只失败股票...")
                    pro = ts.pro_api(self.tushare_token)
                    self.last_tushare_call = time.time()
                    
                    temp_remaining = []
                    for code in remaining_codes:
                        try:
                            ts_code = f"{code}.SZ" if code.startswith(('000', '002', '300')) else f"{code}.SH"
                            df = pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
                            if not df.empty:
                                df = self.standardize_kline_columns(df, 'tushare')
                                result[code] = df
                                secondary_success.append(code)
                            else:
                                temp_remaining.append(code)
                        except Exception as e:
                            print(f"[WARN] TUSHARE替代获取{code}失败: {e}")
                            temp_remaining.append(code)
                    remaining_codes = temp_remaining
                    print(f"[SUCCESS] TUSHARE 替代成功: {len(secondary_success)}/{len(fallback_codes)} 只")
            
            # 最后尝试JoinQuant
            final_failed_codes = remaining_codes
        
        # 现在所有处理逻辑已完成，统计最终结果
        if not 'baostock_success' in locals():
            baostock_success = []
        if not 'alpha_success' in locals():
            alpha_success = []  
        if not 'yfinance_success' in locals():
            yfinance_success = []
        
        # 3. AKShare兜底处理（优先于Alpha Vantage）
        akshare_fallback_success = []
        if final_failed_codes and AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
            print(f"[INFO] AKShare 兜底处理 {len(final_failed_codes)} 只失败股票...")
            try:
                temp_remaining = []
                for code in final_failed_codes:
                    try:
                        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_iso, end_date=end_iso)
                        if df is not None and not df.empty:
                            df = self.standardize_kline_columns(df, 'akshare')
                            if not df.empty:
                                result[code] = df
                                akshare_fallback_success.append(code)
                        else:
                            temp_remaining.append(code)
                    except Exception as e:
                        print(f"[WARN] AKShare兜底 {code} 失败: {type(e).__name__}: {e}")
                        temp_remaining.append(code)
                    time.sleep(0.2)
                final_failed_codes = temp_remaining
                print(f"[SUCCESS] AKShare 兜底成功: {len(akshare_fallback_success)}/{len(final_failed_codes) + len(akshare_fallback_success)} 只")
            except Exception as e:
                print(f"[ERROR] AKShare 兜底处理异常: {type(e).__name__}: {e}")
        elif final_failed_codes and not (AKSHARE_AVAILABLE and AKSHARE_CONNECTED):
            print(f"[WARN] AKShare 不可用，无法兜底处理 {len(final_failed_codes)} 只股票")
            
        # 4. 腾讯K线兜底处理
        tencent_fallback_success = []
        if final_failed_codes and self.tencent_kline:
            print(f"[INFO] 腾讯K线 兜底处理 {len(final_failed_codes)} 只失败股票...")
            try:
                temp_remaining = []
                for code in final_failed_codes:
                    try:
                        df = self.tencent_kline.get_stock_kline(code, start_iso, end_iso)
                        if df is not None and not df.empty:
                            df = self.standardize_kline_columns(df, 'tencent')
                            if not df.empty:
                                result[code] = df
                                tencent_fallback_success.append(code)
                        else:
                            temp_remaining.append(code)
                    except Exception as e:
                        print(f"[WARN] 腾讯K线兜底 {code} 失败: {e}")
                        temp_remaining.append(code)
                    time.sleep(0.1)
                final_failed_codes = temp_remaining
                print(f"[SUCCESS] 腾讯K线 兜底成功: {len(tencent_fallback_success)}/{len(final_failed_codes) + len(tencent_fallback_success)} 只")
            except Exception as e:
                print(f"[ERROR] 腾讯K线 兜底处理异常: {e}")
        
        # 5. BaoStock兜底处理（稳定性好）
        baostock_success = []
        if final_failed_codes and self.baostock and self.baostock.is_connected:
            print(f"[INFO] BaoStock 兜底处理 {len(final_failed_codes)} 只最终失败股票...")
            try:
                # 计算获取天数
                days = max(30, self.kline_days)
                
                # 使用BaoStock批量获取
                bs_results = self.baostock.batch_get_klines(final_failed_codes, days)
                
                temp_remaining = []
                for code in final_failed_codes:
                    if code in bs_results and bs_results[code] is not None and not bs_results[code].empty:
                        df = self.standardize_kline_columns(bs_results[code], 'baostock')
                        if not df.empty:
                            result[code] = df
                            baostock_success.append(code)
                    else:
                        temp_remaining.append(code)
                final_failed_codes = temp_remaining
                
                print(f"[SUCCESS] BaoStock 兜底成功: {len(baostock_success)}/{len(final_failed_codes) + len(baostock_success)} 只")
            except Exception as e:
                print(f"[ERROR] BaoStock 兜底处理异常: {e}")
        elif final_failed_codes and not (self.baostock and getattr(self.baostock, 'is_connected', False)):
            print(f"[WARN] BaoStock API未连接，无法兜底处理 {len(final_failed_codes)} 只股票")
        
        # 6. Alpha Vantage最后兜底处理（仅限美股/ADR）
        still_failed = [code for code in codes if code not in result]
        # 过滤A股代码，Alpha Vantage主要支持美股/ADR
        alpha_candidate_codes = [code for code in still_failed 
                               if not (code.startswith(('00', '30', '60', '68')) and code.isdigit())]
        a_stock_codes = [code for code in still_failed if code not in alpha_candidate_codes]
        
        alpha_success = []
        if alpha_candidate_codes and self.alpha_vantage:
            print(f"[INFO] Alpha Vantage 最终兜底处理 {len(alpha_candidate_codes)} 只可能的美股/ADR代码...")
            if a_stock_codes:
                print(f"[SKIP] 跳过 {len(a_stock_codes)} 只A股代码（Alpha Vantage不支持）")
            try:
                for code in alpha_candidate_codes:
                    try:
                        df = self.alpha_vantage.get_daily_kline(code, outputsize='compact')
                        if df is not None and not df.empty:
                            # 处理Alpha Vantage数据格式
                            df = df.reset_index()
                            df = df.rename(columns={'index': 'date'})
                            
                            # 按日期范围过滤
                            if 'date' in df.columns:
                                df['date'] = pd.to_datetime(df['date'])
                                mask = (df['date'] >= start_date) & (df['date'] <= end_date)
                                df = df[mask]
                            
                            df = self.standardize_kline_columns(df, 'alpha_vantage')
                            if not df.empty:
                                result[code] = df
                                alpha_success.append(code)
                                print(f"[SUCCESS] Alpha Vantage兜底 {code}: {len(df)} 行")
                        
                    except Exception as e:
                        print(f"[WARN] Alpha Vantage兜底{code}失败: {e}")
                        continue
                
                print(f"[SUCCESS] Alpha Vantage 兜底成功: {len(alpha_success)}/{len(still_failed)}")
            except Exception as e:
                print(f"[ERROR] Alpha Vantage 兜底处理异常: {e}")
        elif still_failed and not self.alpha_vantage:
            print(f"[WARN] Alpha Vantage API未初始化，无法兜底处理 {len(still_failed)} 只股票")
        
        # 统计最终结果
        success_count = len(result)
        success_rate = (success_count / total_codes) * 100 if total_codes > 0 else 0
        
        print(f"[SUMMARY] K线数据采集完成: {success_count}/{total_codes} 只成功 ({success_rate:.1f}%)")
        
        # 按数据源统计成功情况
        print(f"[DETAIL] 各数据源表现:")
        if primary_source == 'tushare':
            print(f"  TUSHARE(主): {len(primary_success)}/{len(primary_codes)} ({len(primary_success)/len(primary_codes)*100:.1f}%)" if primary_codes else "  TUSHARE(主): 0/0")
            if 'secondary_success' in locals():
                print(f"  AKShare(备): {len(secondary_success)}/{len(fallback_codes)} ({len(secondary_success)/len(fallback_codes)*100:.1f}%)" if fallback_codes else "  AKShare(备): 0/0")
        else:
            print(f"  AKShare(主): {len(primary_success)}/{len(primary_codes)} ({len(primary_success)/len(primary_codes)*100:.1f}%)" if primary_codes else "  AKShare(主): 0/0")
            if 'secondary_success' in locals():
                print(f"  TUSHARE(备): {len(secondary_success)}/{len(fallback_codes)} ({len(secondary_success)/len(fallback_codes)*100:.1f}%)" if fallback_codes else "  TUSHARE(备): 0/0")
        
        if 'final_failed_codes' in locals() and final_failed_codes:
            print(f"  BaoStock(兜底): {len(baostock_success)}/{len(final_failed_codes)}")
        if 'still_failed' in locals() and still_failed:
            print(f"  Alpha Vantage(最终): {len(alpha_success)}/{len(still_failed)}")
        
        return result
    
    def collect_batch_other_data(self, codes: List[str]) -> Dict[str, Dict]:
        """批量采集其他信息 - 新策略: 数据源专业化分工 + 批量优化 + 兜底保障"""
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 开始采集其他信息，共 {total_codes} 只股票")
        print(f"[INFO] 数据分工策略: baostock(基础+财务) → 腾讯(实时+资金) → yfinance(国际化) → akshare(兜底)")
        
        # 数据分配策略：按数据类型分工，避免重复请求
        baostock_codes = codes.copy()  # baostock处理所有基础信息+财务数据
        tencent_codes = codes.copy()   # 腾讯处理实时数据+资金流向
        yfinance_codes = []            # yfinance作为国际化补充
        failed_codes = []              # 失败股票用akshare兜底
        
        # 1. Baostock批量获取：基础信息 + 财务数据（专业强项）
        baostock_success = []
        if BAOSTOCK_AVAILABLE and self.bs_login:
            print(f"[INFO] Baostock专项：基础信息+财务数据 {len(baostock_codes)} 只...")
            try:
                for code in baostock_codes:
                    try:
                        bs_code = f"sz.{code}" if code.startswith(('000', '002', '300')) else f"sh.{code}"
                        
                        # 基础信息
                        basic_info = {'code': code, 'source': 'baostock'}
                        rs_basic = bs.query_stock_basic(code=bs_code)
                        if rs_basic.error_code == '0':
                            while rs_basic.next():
                                row = rs_basic.get_row_data()
                                if len(row) > 6:
                                    basic_info.update({
                                        'name': row[1],
                                        'type': row[2],
                                        'status': row[3],
                                        'industry': row[4],
                                        'listing_date': row[6]
                                    })
                                    break
                        
                        # 财务数据（最新季度）
                        financial_info = {}
                        rs_profit = bs.query_profit_data(code=bs_code, year="2024", quarter=3)
                        if rs_profit.error_code == '0':
                            while rs_profit.next():
                                row = rs_profit.get_row_data()
                                if len(row) > 7:
                                    financial_info.update({
                                        'revenue': self._safe_float(row[4]),
                                        'net_profit': self._safe_float(row[5]),
                                        'eps': self._safe_float(row[6]),
                                        'roe': self._safe_float(row[7])
                                    })
                                    break
                        
                        # 估值数据
                        rs_dupont = bs.query_dupont_data(code=bs_code, year="2024", quarter=3)
                        if rs_dupont.error_code == '0':
                            while rs_dupont.next():
                                row = rs_dupont.get_row_data()
                                if len(row) > 5:
                                    financial_info.update({
                                        'roa': self._safe_float(row[4]),
                                        'gross_profit_rate': self._safe_float(row[5])
                                    })
                                    break
                        
                        result[code] = {**basic_info, **financial_info}
                        baostock_success.append(code)
                        time.sleep(0.05)  # baostock控频
                        
                    except Exception as e:
                        print(f"[WARN] Baostock {code} 失败: {e}")
                        continue
                
                print(f"[SUCCESS] Baostock完成: {len(baostock_success)}/{len(baostock_codes)} 只")
            except Exception as e:
                print(f"[ERROR] Baostock批量处理异常: {e}")
        
        # 2. 腾讯批量获取：实时价格 + 资金流向（速度优势）
        tencent_success = []
        if REQUESTS_AVAILABLE:
            print(f"[INFO] 腾讯专项：实时价格+资金流向 {len(tencent_codes)} 只...")
            try:
                # 批量获取实时价格（腾讯支持批量查询）
                batch_symbols = ','.join([f's_{code}' for code in tencent_codes])
                url = f'https://qt.gtimg.cn/q={batch_symbols}'
                
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    lines = response.text.split('\n')
                    for i, line in enumerate(lines):
                        if i >= len(tencent_codes) or not line.strip():
                            continue
                        
                        code = tencent_codes[i]
                        try:
                            parts = line.split('~')
                            if len(parts) > 10:
                                if code not in result:
                                    result[code] = {'code': code}
                                
                                result[code].update({
                                    'name': parts[1],
                                    'current_price': self._safe_float(parts[3]),
                                    'price_change': self._safe_float(parts[4]),
                                    'price_change_pct': self._safe_float(parts[5]),
                                    'volume': self._safe_float(parts[6]),
                                    'turnover': self._safe_float(parts[7]),
                                    'market_value': self._safe_float(parts[45]) if len(parts) > 45 else None,
                                    'tencent_source': True
                                })
                                tencent_success.append(code)
                        except Exception as e:
                            print(f"[WARN] 腾讯解析 {code} 失败: {e}")
                            continue
                
                print(f"[SUCCESS] 腾讯完成: {len(tencent_success)}/{len(tencent_codes)} 只")
            except Exception as e:
                print(f"[ERROR] 腾讯批量处理异常: {e}")
        
        # 3. YFinance补充：国际化数据（对港股通等有优势）
        international_codes = [code for code in codes if code.startswith('00') or code in ['000001', '000002']]  # 选择性使用
        if international_codes and YFINANCE_AVAILABLE:
            print(f"[INFO] YFinance补充：国际化数据 {len(international_codes)} 只...")
            try:
                for code in international_codes:
                    try:
                        symbol = f"{code}.SZ" if code.startswith(('000', '002', '300')) else f"{code}.SS"
                        ticker = yf.Ticker(symbol)
                        info = ticker.info
                        
                        if info and code not in result:
                            result[code] = {'code': code}
                        
                        if info:
                            result[code].update({
                                'market_cap': info.get('marketCap'),
                                'pe_ratio': info.get('trailingPE'),
                                'pb_ratio': info.get('priceToBook'),
                                'dividend_yield': info.get('dividendYield'),
                                'beta': info.get('beta'),
                                'yfinance_source': True
                            })
                        
                        time.sleep(0.2) # yfinance控频
                    except Exception as e:
                        print(f"[WARN] YFinance {code} 失败: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] YFinance处理异常: {e}")
        
        # 4. AKShare兜底：处理前面数据源失败的股票
        failed_codes = [code for code in codes if code not in result or not result[code].get('name')]
        if failed_codes and AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
            print(f"[INFO] AKShare兜底：处理失败股票 {len(failed_codes)} 只...")
            try:
                for code in failed_codes:
                    try:
                        # 基础信息
                        df_info = ak.stock_individual_info_em(symbol=code)
                        if df_info is not None and not df_info.empty:
                            info_dict = dict(zip(df_info['item'], df_info['value']))
                            
                            if code not in result:
                                result[code] = {'code': code}
                            
                            result[code].update({
                                'name': info_dict.get('股票简称', f'股票{code}'),
                                'industry': info_dict.get('行业'),
                                'concept': info_dict.get('概念'),
                                'area': info_dict.get('地区'),
                                'market_cap': self._safe_float(info_dict.get('总市值')),
                                'pe_ratio': self._safe_float(info_dict.get('市盈率')),
                                'pb_ratio': self._safe_float(info_dict.get('市净率')),
                                'akshare_source': True
                            })
                        
                        time.sleep(0.3)  # akshare控频
                    except Exception as e:
                        print(f"[WARN] AKShare兜底 {code} 失败: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] AKShare兜底处理异常: {e}")
        
        # 2. 对失败的股票使用腾讯API
        failed_codes = [code for code in codes if code not in result]
        if failed_codes:
            print(f"[INFO] 使用腾讯API处理剩余 {len(failed_codes)} 只股票...")
            tencent_success = []
            try:
                # 腾讯API支持批量查询，每次最多20只
                for i in range(0, len(failed_codes), 20):
                    batch_codes = failed_codes[i:i+20]
                    try:
                        # 构造腾讯API批量查询URL
                        code_str = ','.join([f"{'sz' if c.startswith(('000', '002', '300')) else 'sh'}{c}" for c in batch_codes])
                        url = f"http://qt.gtimg.cn/q={code_str}"
                        
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            lines = response.text.strip().split('\n')
                            for j, line in enumerate(lines):
                                if j < len(batch_codes):
                                    code = batch_codes[j]
                                    try:
                                        # 解析腾讯返回数据
                                        data_parts = line.split('~')
                                        if len(data_parts) > 10:
                                            result[code] = {
                                                'code': code,
                                                'name': data_parts[1],
                                                'price': data_parts[3],
                                                'change': data_parts[5],
                                                'change_pct': data_parts[6],
                                                'volume': data_parts[36],
                                                'source': 'tencent'
                                            }
                                            tencent_success.append(code)
                                    except Exception as e:
                                        print(f"[WARN] 腾讯数据解析失败 {code}: {e}")
                        
                        time.sleep(0.5)  # 批量请求间隔
                        
                    except Exception as e:
                        print(f"[WARN] 腾讯API批量请求失败: {e}")
                        continue
                
                print(f"[SUCCESS] 腾讯API 成功获取 {len(tencent_success)} 只股票信息")
            except Exception as e:
                print(f"[ERROR] 腾讯API 批量处理失败: {e}")
        
        success_count = len(result)
        print(f"[SUMMARY] 其他信息采集完成: {success_count}/{total_codes} 只成功")
        return result
    
    def _collect_batch_kline_legacy(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """批量采集K线数据 - tushare → akshare轮流，yfinance兜底（遗留方法）"""
        result = {}
        total_codes = len(codes)
        batch_size = 15  # 每批15只股票
        
        print(f"[INFO] 开始批量K线数据采集，总计 {total_codes} 只股票，{batch_size}只/批")
        
        # 将股票分批
        batches = [codes[i:i + batch_size] for i in range(0, len(codes), batch_size)]
        failed_codes = []  # 记录失败的股票代码
        
        for batch_num, batch_codes in enumerate(batches):
            print(f"\n=== 第 {batch_num + 1} 批 / 共 {len(batches)} 批 ===")
            print(f"股票代码: {', '.join(batch_codes)}")
            
            # 轮流使用tushare和akshare
            if batch_num % 2 == 0:  # 偶数批使用tushare
                batch_result = self._collect_batch_kline_with_tushare(batch_codes)
                print(f"[INFO] 第{batch_num + 1}批使用tushare获取K线数据: {len(batch_result)}/{len(batch_codes)} 成功")
            else:  # 奇数批使用akshare
                batch_result = self._collect_batch_kline_with_akshare(batch_codes)
                print(f"[INFO] 第{batch_num + 1}批使用akshare获取K线数据: {len(batch_result)}/{len(batch_codes)} 成功")
            
            # 合并成功的结果
            result.update(batch_result)
            
            # 检查是否有失败的股票
            batch_failed = [code for code in batch_codes if code not in batch_result]
            if batch_failed:
                failed_codes.extend(batch_failed)
                print(f"[WARN] 第{batch_num + 1}批失败股票: {batch_failed}")
        
        # 如果有失败的股票，使用yfinance兜底
        if failed_codes:
            print(f"\n[INFO] 使用yfinance兜底采集 {len(failed_codes)} 只失败股票...")
            fallback_result = self._collect_batch_kline_with_yfinance(failed_codes)
            result.update(fallback_result)
            print(f"[INFO] yfinance兜底完成: {len(fallback_result)}/{len(failed_codes)} 成功")
            
            # 检查最终仍然失败的股票
            final_failed = [code for code in failed_codes if code not in fallback_result]
            if final_failed:
                print(f"[WARN] 最终失败的股票 ({len(final_failed)}): {final_failed}")
        
        print(f"\n[INFO] K线数据采集完成: {len(result)}/{total_codes} 总体成功率 {len(result)/total_codes*100:.1f}%")
        return result
    
    def _select_optimal_kline_source(self) -> str:
        """选择最佳K线数据源"""
        current_time = time.time()
        
        # 检查tushare是否可以使用
        tushare_ready = (current_time - self.last_tushare_call) >= 60
        
        # 检查yfinance是否可以使用
        yfinance_ready = (current_time - self.last_yfinance_call) >= self.yfinance_wait_seconds
        
        # 轮换策略
        if tushare_ready and yfinance_ready:
            # 两个都可用，按轮换顺序选择
            source = self.kline_sources[self.current_kline_source_index]
            self.current_kline_source_index = (self.current_kline_source_index + 1) % len(self.kline_sources)
            return source
        elif tushare_ready:
            return 'tushare'
        elif yfinance_ready:
            return 'yfinance'
        else:
            # 都不可用，选择等待时间较短的
            tushare_wait = max(0, 60 - (current_time - self.last_tushare_call))
            yfinance_wait = max(0, self.yfinance_wait_seconds - (current_time - self.last_yfinance_call))
            
            if tushare_wait <= yfinance_wait:
                print(f"[INFO] tushare需要等待{tushare_wait:.0f}秒")
                return 'tushare'
            else:
                print(f"[INFO] yfinance需要等待{yfinance_wait:.0f}秒")
                return 'yfinance'
    
    def _collect_batch_kline_with_tushare(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用tushare批量采集K线数据"""
        result = {}
        
        try:
            # 检查是否需要等待频率限制
            current_time = time.time()
            if current_time - self.last_tushare_call < 60:
                wait_time = 60 - (current_time - self.last_tushare_call)
                print(f"[INFO] 等待{wait_time:.1f}秒避免tushare频率限制")
                time.sleep(wait_time)
            
            # 设置时间范围 - 50天
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.kline_days)
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')
            
            # 将股票代码转换为tushare格式
            ts_codes = []
            code_mapping = {}  # 映射关系: ts_code -> original_code
            
            for code in codes:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                ts_codes.append(ts_code)
                code_mapping[ts_code] = code
            
            # 自适应批量大小选择
            if self.adaptive_batch:
                if len(codes) > 100:
                    actual_batch_size = self.kline_batch_size_max  # 大量股票用大批量
                    print(f"[INFO] 大批量模式: {actual_batch_size}只/批 (总量{len(codes)}只)")
                else:
                    actual_batch_size = self.kline_batch_size      # 少量股票用标准批量
                    print(f"[INFO] 标准模式: {actual_batch_size}只/批 (总量{len(codes)}只)")
            else:
                actual_batch_size = self.kline_batch_size
                
            # 按批量大小分组采集
            batches = [ts_codes[i:i + actual_batch_size] for i in range(0, len(ts_codes), actual_batch_size)]
            
            print(f"[INFO] 将{len(codes)}只股票分为{len(batches)}个批次采集K线数据")
            
            for batch_idx, batch_codes in enumerate(batches):
                try:
                    print(f"[INFO] 正在采集第{batch_idx + 1}/{len(batches)}批，{len(batch_codes)}只股票")
                    
                    # 批量获取
                    codes_str = ','.join(batch_codes)
                    df = self.ts_pro.daily(ts_code=codes_str, start_date=start_str, end_date=end_str)
                    
                    self.last_tushare_call = time.time()
                    
                    if df is not None and not df.empty:
                        # 按股票代码分组
                        for ts_code in batch_codes:
                            code_data = df[df['ts_code'] == ts_code].copy()
                            if not code_data.empty:
                                # 数据处理
                                code_data['trade_date'] = pd.to_datetime(code_data['trade_date'])
                                code_data = code_data.sort_values('trade_date')
                                code_data = code_data.rename(columns={
                                    'trade_date': 'date', 'open': 'open', 'high': 'high',
                                    'low': 'low', 'close': 'close', 'vol': 'volume', 'amount': 'amount'
                                })
                                
                                original_code = code_mapping[ts_code]
                                result[original_code] = code_data
                                print(f"[SUCCESS] {original_code}: {len(code_data)}天K线数据")
                    
                    # 如果不是最后一批，等待频率限制
                    if batch_idx < len(batches) - 1:
                        print(f"[INFO] 等待60秒避免频率限制...")
                        
                        # 在等待期间收集其他数据和K线数据
                        if self.enable_wait_period_collection:
                            remaining_codes = []
                            for remaining_batch in batches[batch_idx+1:]:
                                remaining_codes.extend([code_mapping.get(ts_code.replace('.SH', '').replace('.SZ', ''), ts_code.replace('.SH', '').replace('.SZ', '')) 
                                                      for ts_code in remaining_batch])
                            
                            if remaining_codes:
                                print(f"[INFO] 等待期间并行收集数据...")
                                self._collect_parallel_data_during_wait(remaining_codes[:15], codes, 60, result, start_str, end_str)
                        
                        time.sleep(60)
                        
                except Exception as e:
                    print(f"[WARN] 第{batch_idx + 1}批K线数据采集失败: {e}")
                    continue
            
            print(f"[SUCCESS] 批量K线采集完成，获取{len(result)}只股票数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] tushare批量K线数据采集失败: {e}")
            return result
    
    def _collect_batch_kline_with_yfinance(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用yfinance批量采集K线数据"""
        result = {}
        
        try:
            # 检查yfinance频率限制
            current_time = time.time()
            if current_time - self.last_yfinance_call < self.yfinance_wait_seconds:
                wait_time = self.yfinance_wait_seconds - (current_time - self.last_yfinance_call)
                print(f"[INFO] 等待{wait_time:.1f}秒避免yfinance频率限制")
                time.sleep(wait_time)
            
            print(f"[INFO] 使用yfinance批量获取{len(codes)}只股票K线数据")
            
            # yfinance支持批量获取，但需要转换股票代码格式
            yf_symbols = []
            code_mapping = {}
            
            for code in codes:
                # 转换为yfinance格式
                if code.startswith(('60', '68')):  # 沪市
                    yf_symbol = f"{code}.SS"
                else:  # 深市
                    yf_symbol = f"{code}.SZ"
                
                yf_symbols.append(yf_symbol)
                code_mapping[yf_symbol] = code
            
            # 批量下载
            symbols_str = ' '.join(yf_symbols[:self.kline_batch_size])  # 限制批量大小
            
            import yfinance as yf
            data = yf.download(symbols_str, period="3mo", interval="1d", 
                             group_by='ticker', progress=False)
            
            self.last_yfinance_call = time.time()
            
            if not data.empty:
                # 处理单个股票的情况
                if len(yf_symbols) == 1:
                    symbol = yf_symbols[0]
                    original_code = code_mapping[symbol]
                    if not data.empty:
                        df = data.reset_index()
                        df = df.rename(columns={
                            'Date': 'date', 'Open': 'open', 'High': 'high',
                            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                        })
                        # 安全计算成交额
                        if 'close' in df.columns and 'volume' in df.columns:
                            df['amount'] = df['close'] * df['volume']  # 估算成交额
                        result[original_code] = df
                        print(f"[SUCCESS] {original_code}: {len(df)}天K线数据 (yfinance)")
                
                # 处理多个股票的情况
                else:
                    for symbol in yf_symbols:
                        original_code = code_mapping[symbol]
                        try:
                            if symbol in data.columns.levels[0]:
                                stock_data = data[symbol].dropna()
                                if not stock_data.empty:
                                    df = stock_data.reset_index()
                                    df = df.rename(columns={
                                        'Date': 'date', 'Open': 'open', 'High': 'high',
                                        'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                                    })
                                    # 安全计算成交额
                                    if 'close' in df.columns and 'volume' in df.columns:
                                        df['amount'] = df['close'] * df['volume']  # 估算成交额
                                    result[original_code] = df
                                    print(f"[SUCCESS] {original_code}: {len(df)}天K线数据 (yfinance)")
                        except Exception as e:
                            print(f"[WARN] {original_code}: yfinance数据处理失败 - {e}")
            
            print(f"[INFO] yfinance批量采集完成，获取{len(result)}只股票K线数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] yfinance批量K线数据采集失败: {e}")
            return result
    
    def _collect_batch_kline_with_akshare(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """使用akshare批量采集K线数据"""
        result = {}
        
        if not AKSHARE_AVAILABLE or not AKSHARE_CONNECTED:
            print(f"[WARN] akshare不可用或连接失败，跳过批量K线采集")
            return result
        
        print(f"[INFO] 使用akshare获取{len(codes)}只股票K线数据")
        
        try:
            # akshare需要单独股票获取，但可以控制频率
            for i, code in enumerate(codes):
                try:
                    # 获取日K线数据
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                    
                    if df is not None and not df.empty:
                        # 标准化列名
                        df = df.rename(columns={
                            '日期': 'date',
                            '开盘': 'open', 
                            '收盘': 'close',
                            '最高': 'high',
                            '最低': 'low', 
                            '成交量': 'volume',
                            '成交额': 'amount'
                        })
                        
                        # 确保数据类型正确
                        df['date'] = pd.to_datetime(df['date'])
                        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        # 只保留最近50天数据
                        df = df.tail(self.kline_days)
                        result[code] = df
                        print(f"[SUCCESS] {code}: {len(df)}天K线数据 (akshare)")
                    
                    # akshare频率控制 - 每只股票间隔0.5秒
                    if i < len(codes) - 1:
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"[WARN] {code}: akshare K线数据获取失败 - {e}")
                    continue
            
            print(f"[INFO] akshare批量采集完成，获取{len(result)}/{len(codes)}只股票K线数据")
            return result
            
        except Exception as e:
            print(f"[ERROR] akshare批量K线数据采集失败: {e}")
            return result
    
    def _collect_kline_individually(self, codes: List[str]) -> Dict[str, pd.DataFrame]:
        """单独采集K线数据（回退方案）"""
        result = {}
        print(f"[INFO] 使用单独采集模式获取{len(codes)}只股票K线数据")
        
        for code in codes:
            try:
                # 尝试使用可用的数据源
                kline_data = None
                
                if AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
                    kline_data = self.collect_kline_data(code, 'akshare')
                elif YFINANCE_AVAILABLE:
                    kline_data = self.collect_kline_data(code, 'yfinance')
                
                if kline_data is not None and not kline_data.empty:
                    result[code] = kline_data
                    print(f"[SUCCESS] {code}: {len(kline_data)}天K线数据 (单独采集)")
                
                time.sleep(1)  # 避免频率限制
                
            except Exception as e:
                print(f"[WARN] {code}: 单独K线采集失败 - {e}")
        
        return result
    
    def get_next_data_source(self) -> str:
        """轮询获取下一个数据源"""
        source = self.data_sources[self.current_source_index]
        self.current_source_index = (self.current_source_index + 1) % len(self.data_sources)
        return source
    
    def collect_basic_info(self, code: str, source: str) -> Dict[str, Any]:
        """采集基础信息"""
        basic_info = {
            'code': code,
            'name': f'股票{code}',
            'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
            'industry': None,
            'area': None,
            'concept': None,
            'source': source
        }
        
        try:
            if source == 'yfinance' and YFINANCE_AVAILABLE:
                symbol = f"{code}.SS" if code.startswith(('60', '68')) else f"{code}.SZ"
                try:
                    stock = yf.Ticker(symbol)
                    info = stock.info
                    if info:
                        basic_info.update({
                            'name': info.get('shortName', info.get('longName', basic_info['name'])),
                            'industry': info.get('industry'),
                            'sector': info.get('sector')
                        })
                except Exception as e:
                    print(f"[WARN] yfinance基础信息获取失败: {e}")
            
            elif source == 'tencent' and REQUESTS_AVAILABLE:
                try:
                    url = f'https://qt.gtimg.cn/q=s_{code}'
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.text.split('~')
                        if len(data) > 1:
                            basic_info['name'] = data[1]
                except Exception as e:
                    print(f"[WARN] 腾讯API基础信息获取失败: {e}")
            
            elif source == 'akshare' and AKSHARE_AVAILABLE and AKSHARE_CONNECTED:
                df = ak.stock_individual_info_em(symbol=code)
                if df is not None and not df.empty:
                    info = dict(zip(df['item'], df['value']))
                    basic_info.update({
                        'name': info.get('股票简称', basic_info['name']),
                        'industry': info.get('行业'),
                        'area': info.get('地区'),
                        'concept': info.get('概念')
                    })
            
            elif source == 'baostock' and BAOSTOCK_AVAILABLE and self.bs_login:
                # baostock获取基础信息（最终兜底）
                bs_code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                try:
                    # 获取股票基本信息
                    rs = bs.query_stock_basic(code=bs_code)
                    if rs.error_code == '0' and rs.next():
                        row_data = rs.get_row_data()
                        if len(row_data) >= 3:
                            basic_info.update({
                                'name': row_data[1] if len(row_data) > 1 else basic_info['name'],
                                'industry': row_data[2] if len(row_data) > 2 else None,
                                'type': row_data[3] if len(row_data) > 3 else None
                            })
                except Exception as e:
                    print(f"[DEBUG] baostock基础信息获取失败: {e}")
            
            elif source == 'jina' and JINA_AVAILABLE and self.jina_api and self.jina_api.api_key and self.jina_api.api_key != "YOUR_JINA_API_KEY":
                try:
                    info = self.jina_api.get_company_info_fallback(code, basic_info['name'])
                    if info:
                        basic_info.update(info)
                except Exception as e:
                    print(f"[WARN] Jina API 基础信息获取失败: {e}")
        
        except Exception as e:
            print(f"[WARN] {code} 基础信息采集失败 ({source}): {e}")
        
        return basic_info
    
    def collect_batch_basic_info(self, codes: List[str], source: str = 'auto') -> Dict[str, Dict[str, Any]]:
        """批量采集基础信息 - 新策略：Baostock为主 → JoinQuant为辅 → 腾讯补充 → AKShare兜底"""
        # 预检股票状态，过滤退市股票
        if STOCK_STATUS_CHECKER_AVAILABLE and self.status_checker:
            print(f"[INFO] 基础信息采集前检查股票状态...")
            try:
                validity_check = self.pre_check_stock_validity(codes)
                original_count = len(codes)
                codes = validity_check['valid_codes']
                
                filtered_count = original_count - len(codes)
                if filtered_count > 0:
                    print(f"[INFO] 基础信息采集已过滤 {filtered_count} 只退市/无效股票")
                    
            except Exception as e:
                print(f"[WARN] 基础信息采集前状态检查异常: {e}，继续处理")
        
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 批量采集基础信息，共 {total_codes} 只股票")
        print(f"[INFO] 基础信息策略: Baostock(主) → JoinQuant(辅) → 腾讯(补充) → AKShare(兜底)")
        
        # 1. Baostock主力：标准行业分类和基础信息
        baostock_success = []
        if BAOSTOCK_AVAILABLE and self.bs_login:
            print(f"[INFO] Baostock基础信息采集 {total_codes} 只...")
            try:
                # 确保baostock已导入
                import baostock as bs

                # 确保已登录
                lg = bs.login()
                if lg.error_code != '0':
                    print(f"[WARN] Baostock登录失败: {lg.error_msg}")
                
                for code in codes:
                    try:
                        bs_code = f"sz.{code}" if code.startswith(('000', '002', '300')) else f"sh.{code}"
                        
                        rs = bs.query_stock_basic(code=bs_code)
                        if rs.error_code == '0':
                            data_found = False
                            while rs.next():
                                row = rs.get_row_data()
                                # Baostock query_stock_basic 返回: code, code_name, ipoDate, outDate, type, status
                                if len(row) >= 6:
                                    result[code] = {
                                        'code': code,
                                        'name': row[1],
                                        'type': row[4],
                                        'status': row[5],
                                        'industry': '未知',  # query_stock_basic 不包含行业信息
                                        'listing_date': row[2],
                                        'source': 'baostock'
                                    }
                                    baostock_success.append(code)
                                    data_found = True
                                    break
                            
                            if not data_found:
                                print(f"[WARN] BaoStock {code} 无数据：可能已退市或代码无效")
                        else:
                            print(f"[WARN] BaoStock {code} 查询失败: {rs.error_msg}")
                        
                        time.sleep(0.05)
                    except Exception as e:
                        print(f"[DEBUG] Baostock {code}: {e}")
                        continue
                
                # 保持登录状态供后续步骤使用
                # bs.logout()
                
                print(f"[SUCCESS] Baostock基础信息: {len(baostock_success)}/{total_codes}")
            except Exception as e:
                print(f"[ERROR] Baostock基础信息异常: {e}")
        
        # 2. JoinQuant为辅：获取失败股票的基础信息
        failed_codes = [code for code in codes if code not in result]
        joinquant_success = []
        if failed_codes and self.joinquant:
            print(f"[INFO] JoinQuant为辅基础信息采集 {len(failed_codes)} 只...")
            try:
                for code in failed_codes:
                    try:
                        # JoinQuant获取基础信息
                        stock_info = self._get_joinquant_stock_info(code)
                        if stock_info:
                            result[code] = stock_info
                            joinquant_success.append(code)
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"[DEBUG] JoinQuant {code}: {e}")
                        continue
                
                print(f"[SUCCESS] JoinQuant基础信息: {len(joinquant_success)}/{len(failed_codes)} 只")
            except Exception as e:
                print(f"[ERROR] JoinQuant基础信息异常: {e}")
        elif failed_codes and not self.joinquant:
            print(f"[WARN] JoinQuant API未初始化，跳过 {len(failed_codes)} 只股票")
        
        # 3. 腾讯补充：实时价格和市场数据
        still_failed = [code for code in codes if code not in result]
        tencent_success = []
        if still_failed and REQUESTS_AVAILABLE:
            print(f"[INFO] 腾讯补充基础信息 {len(still_failed)} 只...")
            try:
                # 腾讯支持批量查询
                batch_symbols = ','.join([f's_{code}' for code in still_failed])
                url = f'https://qt.gtimg.cn/q={batch_symbols}'
                
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    lines = response.text.split('\\n')
                    for i, line in enumerate(lines):
                        if i >= len(still_failed) or not line.strip():
                            continue
                        
                        code = still_failed[i]
                        try:
                            parts = line.split('~')
                            if len(parts) > 5:
                                result[code] = {
                                    'code': code,
                                    'name': parts[1],
                                    'current_price': self._safe_float(parts[3]),
                                    'change_pct': self._safe_float(parts[5]),
                                    'volume': self._safe_float(parts[6]),
                                    'source': 'tencent'
                                }
                                tencent_success.append(code)
                        except Exception as e:
                            print(f"[DEBUG] 腾讯解析 {code}: {e}")
                            continue
                            
                print(f"[SUCCESS] 腾讯补充基础信息: {len(tencent_success)}/{len(still_failed)} 只")
            except Exception as e:
                print(f"[ERROR] 腾讯批量补充异常: {e}")
        
        # 4. AKShare兜底：完整信息获取
        final_failed = [code for code in codes if code not in result]
        akshare_success = []
        if final_failed and AKSHARE_AVAILABLE:
            print(f"[INFO] AKShare兜底基础信息 {len(final_failed)} 只...")
            try:
                for code in final_failed:
                    try:
                        df = ak.stock_individual_info_em(symbol=code)
                        if df is not None and not df.empty:
                            info_dict = dict(zip(df['item'], df['value']))
                            result[code] = {
                                'code': code,
                                'name': info_dict.get('股票简称', f'股票{code}'),
                                'industry': info_dict.get('行业'),
                                'concept': info_dict.get('概念'),
                                'area': info_dict.get('地区'),
                                'source': 'akshare'
                            }
                            akshare_success.append(code)
                        time.sleep(0.3)
                    except Exception as e:
                        print(f"[DEBUG] AKShare {code}: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] AKShare兜底异常: {e}")
        
        # 统计结果
        success_count = len(result)
        success_rate = success_count / total_codes * 100 if total_codes > 0 else 0
        
        print(f"[SUMMARY] 基础信息采集完成: {success_count}/{total_codes} 只 ({success_rate:.1f}%)")
        print(f"[DETAIL] Baostock: {len(baostock_success)}, JoinQuant: {len(joinquant_success)}, 腾讯: {len(tencent_success)}, AKShare: {len(akshare_success)}")
        
        return result
    
    def _collect_batch_basic_info_legacy(self, codes: List[str], source: str = 'auto') -> Dict[str, Dict[str, Any]]:
        """批量采集基础信息，优化频次限制问题（遗留方法）"""
        result = {}
        
        if source == 'tencent' and REQUESTS_AVAILABLE:
            try:
                # 腾讯API支持批量查询，一次最多15只股票
                batch_size = min(15, len(codes))
                for i in range(0, len(codes), batch_size):
                    batch_codes = codes[i:i+batch_size]
                    
                    # 构造批量查询URL
                    query_params = ','.join([f's_{code}' for code in batch_codes])
                    url = f'https://qt.gtimg.cn/q={query_params}'
                    
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        lines = response.text.strip().split('\n')
                        for line, code in zip(lines, batch_codes):
                            try:
                                data = line.split('~')
                                if len(data) > 1 and data[1].strip():  # 确保有有效的股票名称
                                    result[code] = {
                                        'code': code,
                                        'name': data[1] if len(data) > 1 else f'股票{code}',
                                        'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                        'current_price': float(data[3]) if len(data) > 3 and data[3] else None,
                                        'change_pct': float(data[32]) if len(data) > 32 and data[32] else None,
                                        'volume': float(data[36]) if len(data) > 36 and data[36] else None,
                                        'source': 'tencent'
                                    }
                                    print(f"[SUCCESS] {code}: 腾讯基础信息获取成功")
                                else:
                                    print(f"[WARN] {code}: 腾讯返回空数据，跳过")
                            except (ValueError, IndexError) as e:
                                print(f"[WARN] 解析股票{code}数据失败: {e}")
                                # 失败时不添加到result中，让后续兜底机制处理
                    
                    print(f"[INFO] 腾讯批量基础信息: {len([c for c in batch_codes if c in result])}/{len(batch_codes)} 成功")
                    
                    # 避免频率限制
                    if i + batch_size < len(codes):
                        time.sleep(1)
                        
            except Exception as e:
                print(f"[WARN] 腾讯批量基础信息采集失败: {e}")
        
        # 如果腾讯API失败，使用yfinance兜底（更可靠的基础信息）
        if len(result) < len(codes) * 0.8:  # 如果成功率低于80%，使用yfinance兜底
            print(f"[INFO] 腾讯批量采集成功率较低，使用yfinance兜底补充")
            missing_codes = [code for code in codes if code not in result]
            
            # 使用yfinance批量获取基础信息
            yfinance_result = self._collect_batch_basic_info_with_yfinance(missing_codes)
            result.update(yfinance_result)
            
            # 如果yfinance也失败较多，最后使用baostock兜底
            still_missing = [code for code in missing_codes if code not in yfinance_result]
            if still_missing:
                print(f"[INFO] yfinance采集不完整，使用baostock最终兜底 {len(still_missing)} 只股票")
                for code in still_missing:
                    try:
                        result[code] = self.collect_basic_info(code, 'baostock')
                        time.sleep(0.3)  # baostock频率控制
                    except Exception as e:
                        print(f"[WARN] baostock最终兜底失败 {code}: {e}")
                        result[code] = {
                            'code': code,
                            'name': f'股票{code}',
                            'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                            'source': 'fallback'
                        }
        
        return result
    
    def _get_joinquant_stock_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        使用JoinQuant获取单只股票的基础信息
        
        Args:
            code: 股票代码，如 '000001'
            
        Returns:
            股票基础信息字典，失败返回None
        """
        if not self.joinquant:
            return None
        
        try:
            # JoinQuant可能的基础信息获取端点
            endpoints = [
                "/data/stock/info",
                "/data/stock/basic",
                "/stock/info",
                "/stock/basic_info"
            ]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.joinquant.base_url}{endpoint}"
                    params = {
                        'code': code,
                        'symbol': code
                    }
                    
                    response = self.joinquant.session.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200 and len(response.text) > 50:
                        # 尝试解析响应
                        stock_info = self._parse_joinquant_basic_info(response.text, code)
                        if stock_info:
                            return stock_info
                            
                except Exception as e:
                    print(f"[DEBUG] JoinQuant端点{endpoint}失败{code}: {e}")
                    continue
            
            # 如果所有端点都失败，返回基本信息
            return {
                'code': code,
                'name': f'股票{code}',
                'source': 'joinquant_fallback'
            }
            
        except Exception as e:
            print(f"[ERROR] JoinQuant获取{code}基础信息异常: {e}")
            return None
    
    def _parse_joinquant_basic_info(self, content: str, code: str) -> Optional[Dict[str, Any]]:
        """
        解析JoinQuant基础信息响应
        
        Args:
            content: API响应内容
            code: 股票代码
            
        Returns:
            解析后的基础信息字典
        """
        try:
            import json

            # 尝试JSON解析
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    data = json.loads(content)
                    
                    # 处理不同的JSON结构
                    if isinstance(data, dict):
                        if 'data' in data:
                            stock_data = data['data']
                        elif 'result' in data:
                            stock_data = data['result']
                        else:
                            stock_data = data
                        
                        # 提取基础信息
                        if isinstance(stock_data, dict):
                            return {
                                'code': code,
                                'name': stock_data.get('name', stock_data.get('display_name', f'股票{code}')),
                                'industry': stock_data.get('industry'),
                                'sector': stock_data.get('sector'),
                                'exchange': stock_data.get('exchange'),
                                'listing_date': stock_data.get('start_date', stock_data.get('listing_date')),
                                'source': 'joinquant'
                            }
                        
                except json.JSONDecodeError:
                    pass
            
            # 尝试从HTML中提取信息
            if '股票' in content or 'stock' in content.lower():
                # 简单的文本解析
                return {
                    'code': code,
                    'name': f'股票{code}',
                    'source': 'joinquant_html'
                }
            
            return None
            
        except Exception as e:
            print(f"[DEBUG] JoinQuant响应解析失败{code}: {e}")
            return None
    
    def _get_joinquant_financial_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        使用JoinQuant获取单只股票的财务数据
        
        Args:
            code: 股票代码，如 '000001'
            
        Returns:
            股票财务数据字典，失败返回None
        """
        if not self.joinquant:
            return None
        
        try:
            # JoinQuant可能的财务数据获取端点
            endpoints = [
                "/data/stock/fundamental",
                "/data/stock/financial",
                "/stock/fundamental",
                "/stock/finance"
            ]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.joinquant.base_url}{endpoint}"
                    params = {
                        'code': code,
                        'symbol': code,
                        'period': 'quarter'  # 季报
                    }
                    
                    response = self.joinquant.session.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200 and len(response.text) > 50:
                        # 尝试解析响应
                        financial_info = self._parse_joinquant_financial_info(response.text, code)
                        if financial_info:
                            return financial_info
                            
                except Exception as e:
                    print(f"[DEBUG] JoinQuant财务端点{endpoint}失败{code}: {e}")
                    continue
            
            # 如果所有端点都失败，返回基本财务信息
            return {
                'code': code,
                'source': 'joinquant_fallback'
            }
            
        except Exception as e:
            print(f"[ERROR] JoinQuant获取{code}财务数据异常: {e}")
            return None
    
    def _parse_joinquant_financial_info(self, content: str, code: str) -> Optional[Dict[str, Any]]:
        """
        解析JoinQuant财务数据响应
        
        Args:
            content: API响应内容
            code: 股票代码
            
        Returns:
            解析后的财务数据字典
        """
        try:
            import json

            # 尝试JSON解析
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    data = json.loads(content)
                    
                    # 处理不同的JSON结构
                    if isinstance(data, dict):
                        if 'data' in data:
                            financial_data = data['data']
                        elif 'result' in data:
                            financial_data = data['result']
                        else:
                            financial_data = data
                        
                        # 提取财务信息
                        if isinstance(financial_data, dict):
                            return {
                                'code': code,
                                'revenue': financial_data.get('total_operating_revenue'),
                                'net_income': financial_data.get('net_profit'),
                                'total_assets': financial_data.get('total_assets'),
                                'total_equity': financial_data.get('total_owner_equities'),
                                'market_cap': financial_data.get('market_cap'),
                                'pe_ratio': financial_data.get('pe_ratio'),
                                'pb_ratio': financial_data.get('pb_ratio'),
                                'roe': financial_data.get('roe'),
                                'source': 'joinquant'
                            }
                        
                except json.JSONDecodeError:
                    pass
            
            # 如果包含财务关键词，返回基础信息
            financial_keywords = ['revenue', 'profit', 'asset', 'equity', '营收', '利润', '资产']
            if any(keyword in content.lower() for keyword in financial_keywords):
                return {
                    'code': code,
                    'source': 'joinquant_partial'
                }
            
            return None
            
        except Exception as e:
            print(f"[DEBUG] JoinQuant财务响应解析失败{code}: {e}")
            return None
    
    def _collect_batch_basic_info_with_yfinance(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """使用yfinance批量采集基础信息"""
        result = {}
        
        if not YFINANCE_AVAILABLE:
            print(f"[WARN] yfinance不可用，跳过基础信息采集")
            return result
        
        print(f"[INFO] 使用yfinance批量获取{len(codes)}只股票基础信息")
        
        # yfinance频率控制 - 初始等待
        print(f"[INFO] yfinance频率控制，等待2秒...")
        time.sleep(2)
        
        try:
            # yfinance批量获取 (15只/批)
            batch_size = min(15, len(codes))
            for i in range(0, len(codes), batch_size):
                batch_codes = codes[i:i+batch_size]
                
                # 转换为yfinance格式
                yf_symbols = []
                code_mapping = {}
                
                for code in batch_codes:
                    if code.startswith(('60', '68')):  # 沪市
                        yf_symbol = f"{code}.SS"
                    else:  # 深市
                        yf_symbol = f"{code}.SZ"
                    yf_symbols.append(yf_symbol)
                    code_mapping[yf_symbol] = code
                
                # 批量获取基础信息
                try:
                    symbols_str = ' '.join(yf_symbols)
                    tickers = yf.Tickers(symbols_str)
                    
                    for yf_symbol in yf_symbols:
                        code = code_mapping[yf_symbol]
                        try:
                            ticker = tickers.tickers[yf_symbol]
                            info = ticker.info
                            
                            if info and info.get('symbol'):
                                result[code] = {
                                    'code': code,
                                    'name': info.get('shortName', info.get('longName', f'股票{code}')),
                                    'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                    'industry': info.get('industry'),
                                    'sector': info.get('sector'),
                                    'market_cap': info.get('marketCap'),
                                    'employee_count': info.get('fullTimeEmployees'),
                                    'source': 'yfinance'
                                }
                                print(f"[SUCCESS] {code}: yfinance基础信息获取成功")
                            else:
                                result[code] = {
                                    'code': code,
                                    'name': f'股票{code}',
                                    'exchange': 'SZ' if code.startswith(('00', '30')) else 'SH',
                                    'source': 'yfinance'
                                }
                        except Exception as e:
                            print(f"[WARN] {code}: yfinance基础信息获取失败 - {e}")
                            # 失败时不添加到result中，让baostock来兜底
                
                except Exception as e:
                    print(f"[WARN] yfinance批量获取第{i//batch_size + 1}批失败: {e}")
                
                actual_success = len([c for c in batch_codes if c in result])
                print(f"[INFO] yfinance批量基础信息: 第{i//batch_size + 1}批完成 ({actual_success}/{len(batch_codes)} 成功)")
                
                # yfinance频率限制较严格，增加等待时间
                if i + batch_size < len(codes):
                    time.sleep(3)  # 增加到3秒
                    
        except Exception as e:
            print(f"[WARN] yfinance批量基础信息采集失败: {e}")
        
        # 统计有效成功数（只计算有有效数据的）
        valid_results = {code: data for code, data in result.items() 
                        if data.get('name') and data.get('name') != f'股票{code}'}
        print(f"[INFO] yfinance基础信息采集完成: {len(valid_results)}/{len(codes)} 有效成功")
        return result
    
    def _has_valid_financial_data(self, data: Dict[str, Any]) -> bool:
        """检查财务数据是否有效"""
        if not data:
            return False
        
        # 至少包含一些关键指标
        key_metrics = ['revenue', 'net_profit', 'pe_ratio', 'pb_ratio', 'roe', 'market_cap']
        valid_count = 0
        for metric in key_metrics:
            if metric in data and data[metric] is not None:
                valid_count += 1
        
        return valid_count >= 1

    def collect_batch_financial_data(self, codes: List[str], source: str = 'auto') -> Dict[str, Dict[str, Any]]:
        """批量采集财务数据 - 新策略：Baostock专业财务为主 → JoinQuant为辅 → YFinance补充 → 腾讯估值"""
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 批量采集财务数据，共 {total_codes} 只股票")
        print(f"[INFO] 财务数据策略: Baostock(主) → JoinQuant(辅) → YFinance(补充) → 腾讯(估值) → AKShare(兜底)")
        
        # 1. Baostock主力：专业的中国A股财务数据
        baostock_success = []
        if BAOSTOCK_AVAILABLE and self.bs_login:
            print(f"[INFO] Baostock专业财务数据 {total_codes} 只...")
            try:
                import baostock as bs
                for code in codes:
                    try:
                        bs_code = f"sz.{code}" if code.startswith(('000', '002', '300')) else f"sh.{code}"
                        financial_data = {'code': code, 'source': 'baostock'}
                        
                        # 利润表数据
                        rs_profit = bs.query_profit_data(code=bs_code, year="2024", quarter=3)
                        if rs_profit.error_code == '0':
                            while rs_profit.next():
                                row = rs_profit.get_row_data()
                                if len(row) > 10:
                                    financial_data.update({
                                        'revenue': self._safe_float(row[4]),          # 营业收入
                                        'net_profit': self._safe_float(row[5]),       # 净利润
                                        'eps': self._safe_float(row[6]),              # 每股收益
                                        'roe': self._safe_float(row[7]),              # 净资产收益率
                                        'total_profit': self._safe_float(row[8])      # 利润总额
                                    })
                                    break
                        
                        # 杜邦数据（财务比率）
                        rs_dupont = bs.query_dupont_data(code=bs_code, year="2024", quarter=3)
                        if rs_dupont.error_code == '0':
                            while rs_dupont.next():
                                row = rs_dupont.get_row_data()
                                if len(row) > 8:
                                    financial_data.update({
                                        'roa': self._safe_float(row[4]),              # 总资产收益率
                                        'gross_profit_rate': self._safe_float(row[5]), # 毛利率
                                        'net_profit_rate': self._safe_float(row[6]),   # 净利率
                                        'debt_ratio': self._safe_float(row[7])         # 资产负债率
                                    })
                                    break
                        
                        if self._has_valid_financial_data(financial_data):
                            result[code] = financial_data
                            baostock_success.append(code)
                        
                        time.sleep(0.08)  # Baostock适度控频
                    except Exception as e:
                        print(f"[DEBUG] Baostock {code}: {e}")
                        continue
                
                print(f"[SUCCESS] Baostock财务数据: {len(baostock_success)}/{total_codes} 只")
            except Exception as e:
                print(f"[ERROR] Baostock财务数据异常: {e}")
        else:
            print(f"[WARN] Baostock不可用，跳过财务数据采集")
        
        # 2. JoinQuant为辅：获取失败股票的财务数据
        failed_codes = [code for code in codes if code not in result]
        joinquant_success = []
        if failed_codes and self.joinquant:
            print(f"[INFO] JoinQuant为辅财务数据采集 {len(failed_codes)} 只...")
            try:
                for code in failed_codes:
                    try:
                        # JoinQuant获取财务数据
                        financial_info = self._get_joinquant_financial_info(code)
                        if financial_info and self._has_valid_financial_data(financial_info):
                            result[code] = financial_info
                            joinquant_success.append(code)
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"[DEBUG] JoinQuant财务 {code}: {e}")
                        continue
                
                print(f"[SUCCESS] JoinQuant财务数据: {len(joinquant_success)}/{len(failed_codes)} 只")
            except Exception as e:
                print(f"[ERROR] JoinQuant财务数据异常: {e}")
        elif failed_codes and not self.joinquant:
            print(f"[WARN] JoinQuant API未初始化，跳过财务数据采集 {len(failed_codes)} 只股票")
        
        # 3. YFinance补充：国际化估值指标
        still_failed = [code for code in codes if code not in result]
        yfinance_success = []
        if still_failed and YFINANCE_AVAILABLE:
            print(f"[INFO] YFinance估值补充 {len(still_failed)} 只...")
            try:
                for code in still_failed:
                    try:
                        symbol = f"{code}.SZ" if code.startswith(('000', '002', '300')) else f"{code}.SS"
                        ticker = yf.Ticker(symbol)
                        info = ticker.info
                        
                        if info:
                            financial_data = {
                                'code': code,
                                'source': 'yfinance',
                                'market_cap': info.get('marketCap'),
                                'pe_ratio': info.get('trailingPE'),
                                'pb_ratio': info.get('priceToBook'),
                                'ps_ratio': info.get('priceToSalesTrailing12Months'),
                                'dividend_yield': info.get('dividendYield'),
                                'beta': info.get('beta'),
                                'profit_margins': info.get('profitMargins'),
                                'revenue_growth': info.get('revenueGrowth')
                            }
                            
                            if self._has_valid_financial_data(financial_data):
                                result[code] = financial_data
                        
                        time.sleep(0.25)  # YFinance控频
                    except Exception as e:
                        print(f"[DEBUG] YFinance {code}: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] YFinance补充异常: {e}")
        
        # 3. 腾讯实时：市场实时估值数据
        still_failed = [code for code in codes if code not in result]
        if still_failed and REQUESTS_AVAILABLE:
            print(f"[INFO] 腾讯实时估值 {len(still_failed)} 只...")
            try:
                # 腾讯批量获取实时数据
                batch_symbols = ','.join([f's_{code}' for code in still_failed])
                url = f'https://qt.gtimg.cn/q={batch_symbols}'
                
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    lines = response.text.split('\\n')
                    for i, line in enumerate(lines):
                        if i >= len(still_failed) or not line.strip():
                            continue
                        
                        code = still_failed[i]
                        try:
                            parts = line.split('~')
                            if len(parts) > 40:
                                financial_data = {
                                    'code': code,
                                    'source': 'tencent',
                                    'current_price': self._safe_float(parts[3]),
                                    'pe_ratio': self._safe_float(parts[39]) if len(parts) > 39 else None,
                                    'pb_ratio': self._safe_float(parts[46]) if len(parts) > 46 else None,
                                    'market_cap': self._safe_float(parts[45]) if len(parts) > 45 else None,
                                    'turnover_rate': self._safe_float(parts[38]) if len(parts) > 38 else None
                                }
                                
                                if self._has_valid_financial_data(financial_data):
                                    result[code] = financial_data
                        except Exception as e:
                            print(f"[DEBUG] 腾讯解析 {code}: {e}")
                            continue
            except Exception as e:
                print(f"[ERROR] 腾讯实时数据异常: {e}")
        
        # 4. AKShare最终兜底：少量失败股票
        final_failed = [code for code in codes if code not in result]
        if final_failed and AKSHARE_AVAILABLE and len(final_failed) <= 5:
            print(f"[INFO] AKShare最终兜底 {len(final_failed)} 只...")
            try:
                for code in final_failed:
                    try:
                        df = ak.stock_individual_info_em(symbol=code)
                        if df is not None and not df.empty:
                            info_dict = dict(zip(df['item'], df['value']))
                            
                            financial_data = {
                                'code': code,
                                'source': 'akshare',
                                'pe_ratio': self._safe_float(info_dict.get('市盈率')),
                                'pb_ratio': self._safe_float(info_dict.get('市净率')),
                                'market_cap': self._safe_float(info_dict.get('总市值')),
                                'revenue': self._safe_float(info_dict.get('营业收入')),
                                'net_profit': self._safe_float(info_dict.get('净利润'))
                            }
                            
                            if self._has_valid_financial_data(financial_data):
                                result[code] = financial_data
                        
                        time.sleep(0.5)  # AKShare严格控频
                    except Exception as e:
                        print(f"[DEBUG] AKShare {code}: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] AKShare兜底异常: {e}")
        
        success_count = len(result)
        success_rate = success_count / total_codes * 100 if total_codes > 0 else 0
        print(f"[SUMMARY] 财务数据采集完成: {success_count}/{total_codes} ({success_rate:.1f}%)")
        
        return result
    
    def collect_batch_industry_concept(self, codes: List[str], source: str = 'auto') -> Dict[str, Dict[str, Any]]:
        """批量采集行业概念数据 - 新策略：Baostock行业分类为主，AKShare概念补充"""
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 批量采集行业概念数据，共 {total_codes} 只股票")
        print(f"[INFO] 行业概念策略: Baostock(标准行业) → AKShare(热门概念) → 默认分类")
        
        # 1. Baostock主力：标准行业分类（一次性获取全量映射）
        baostock_success = []
        if BAOSTOCK_AVAILABLE and self.bs_login:
            print(f"[INFO] Baostock标准行业分类映射...")
            try:
                import baostock as bs

                # 获取完整行业分类映射表（效率更高）
                rs = bs.query_stock_industry()
                industry_mapping = {}
                
                if rs.error_code == '0':
                    while rs.next():
                        row = rs.get_row_data()
                        if len(row) >= 3:
                            stock_code = row[0].split('.')[-1]  # 移除sh./sz.前缀
                            industry_mapping[stock_code] = {
                                'industry': row[1],
                                'industry_name': row[2] if len(row) > 2 else row[1],
                                'update_date': row[3] if len(row) > 3 else None
                            }
                
                print(f"[INFO] Baostock行业映射获取完成: {len(industry_mapping)} 只股票")
                
                # 批量匹配目标股票
                for code in codes:
                    if code in industry_mapping:
                        industry_info = industry_mapping[code]
                        result[code] = {
                            'code': code,
                            'source': 'baostock',
                            'industry': industry_info['industry'],
                            'industry_name': industry_info['industry_name'],
                            'sector': self._classify_sector(industry_info['industry']),
                            'concepts': [],  # 后续补充
                            'industry_update_date': industry_info['update_date']
                        }
                        baostock_success.append(code)
                    else:
                        # 无映射的股票设置默认值
                        result[code] = {
                            'code': code,
                            'source': 'baostock_default',
                            'industry': self._guess_industry_by_code(code),
                            'industry_name': None,
                            'sector': None,
                            'concepts': []
                        }
                
                print(f"[SUCCESS] Baostock行业分类: {len(baostock_success)}/{total_codes}")
            except Exception as e:
                print(f"[ERROR] Baostock行业分类异常: {e}")
        
        # 2. AKShare补充：热门概念和详细分类
        concept_codes = codes.copy()  # 所有股票都需要概念补充
        if concept_codes and AKSHARE_AVAILABLE and len(concept_codes) <= 10: # 限制数量
            print(f"[INFO] AKShare热门概念补充 {len(concept_codes)} 只...")
            try:
                for code in concept_codes:
                    try:
                        # 获取个股概念信息
                        df_concept = ak.stock_board_concept_cons_em(symbol=code)
                        if df_concept is not None and not df_concept.empty:
                            concepts = df_concept['板块名称'].tolist()[:5]  # 最多5个概念
                            
                            if code not in result:
                                result[code] = {'code': code}
                            
                            result[code].update({
                                'concepts': concepts,
                                'hot_concepts': [c for c in concepts if '新' in c or '热' in c or '龙头' in c],
                                'concept_source': 'akshare'
                            })
                        
                        time.sleep(0.8)  # AKShare概念查询控频
                    except Exception as e:
                        print(f"[DEBUG] AKShare概念 {code}: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] AKShare概念补充异常: {e}")
        
        # 3. 默认分类：为无数据股票提供基础分类
        unclassified_codes = [code for code in codes if code not in result or not result[code].get('industry')]
        for code in unclassified_codes:
            default_industry = self._guess_industry_by_code(code)
            default_sector = self._classify_sector(default_industry)
            
            result[code] = {
                'code': code,
                'source': 'default',
                'industry': default_industry,
                'industry_name': default_industry,
                'sector': default_sector,
                'concepts': [],
                'message': '使用默认行业分类'
            }
        
        success_count = len([r for r in result.values() if r.get('source') not in ['default', 'baostock_default']])
        success_rate = success_count / total_codes * 100 if total_codes > 0 else 0
        print(f"[SUMMARY] 行业概念采集完成: {success_count}/{total_codes} ({success_rate:.1f}%)")
        
        return result
    
    def _classify_sector(self, industry: str) -> str:
        """根据行业分类推断板块"""
        if not industry:
            return None
        
        sector_mapping = {
            '银行': '金融业', '保险': '金融业', '证券': '金融业',
            '房地产': '房地产业', '建筑': '建筑业', '工程': '建筑业',
            '电力': '电力、热力、燃气', '煤炭': '采矿业', '石油': '采矿业',
            '钢铁': '制造业', '有色': '制造业', '化工': '制造业',
            '医药': '制造业', '食品': '制造业', '纺织': '制造业',
            '汽车': '制造业', '电子': '制造业', '机械': '制造业',
            '计算机': '信息技术业', '通信': '信息技术业', '软件': '信息技术业',
            '传媒': '文化、体育和娱乐业', '教育': '教育业',
            '交通': '交通运输业', '物流': '交通运输业',
            '商贸': '批发和零售业', '零售': '批发和零售业'
        }
        
        for key, sector in sector_mapping.items():
            if key in industry:
                return sector
        
        return '其他'
    
    def _guess_industry_by_code(self, code: str) -> str:
        """根据股票代码推测行业（简单规则）"""
        if code.startswith('60'):
            if code.startswith('600'):
                return '传统制造业'
            elif code.startswith('601'):
                return '大型国企'
            elif code.startswith('603'):
                return '新上市企业'
        elif code.startswith('000'):
            return '深圳主板'
        elif code.startswith('002'):
            return '中小板企业'
        elif code.startswith('300'):
            return '创业板/科技'
        
        return '未分类行业'
    
    def collect_batch_fund_flow(self, codes: List[str], source: str = 'auto') -> Dict[str, Dict[str, Any]]:
        """批量采集资金流向数据 - 新策略：腾讯为主(实时准确)，AKShare补充"""
        result = {}
        total_codes = len(codes)
        
        print(f"[INFO] 批量采集资金流向数据，共 {total_codes} 只股票")
        print(f"[INFO] 资金流向策略: 腾讯(实时主力+超大单) → AKShare(个股资金流)")
        
        # 1. 腾讯主力：实时资金流向数据（优势明显）
        tencent_success = []
        if REQUESTS_AVAILABLE:
            print(f"[INFO] 腾讯实时资金流向 {total_codes} 只...")
            try:
                # 腾讯支持单独查询，但批量效果更好
                for code in codes:
                    try:
                        # 主力资金流向API
                        url = f'https://qt.gtimg.cn/q=ff_{code}'
                        response = requests.get(url, timeout=10)
                        
                        if response.status_code == 200:
                            parts = response.text.split('~')
                            if len(parts) > 8:
                                fund_flow_data = {
                                    'code': code,
                                    'source': 'tencent',
                                    'main_fund_inflow': self._safe_float(parts[1]),      # 主力净流入
                                    'super_fund_inflow': self._safe_float(parts[2]),     # 超大单净流入
                                    'large_fund_inflow': self._safe_float(parts[3]),     # 大单净流入
                                    'medium_fund_inflow': self._safe_float(parts[4]),    # 中单净流入
                                    'small_fund_inflow': self._safe_float(parts[5]),     # 小单净流入
                                    'main_fund_inflow_pct': self._safe_float(parts[6]),  # 主力净流入占比
                                    'fund_flow_score': self._safe_float(parts[7])        # 资金流向评分
                                }
                                
                                # 验证数据有效性
                                if any(fund_flow_data[key] is not None for key in ['main_fund_inflow', 'super_fund_inflow', 'large_fund_inflow']):
                                    result[code] = fund_flow_data
                                    tencent_success.append(code)
                        
                        time.sleep(0.1)  # 腾讯适度控频
                    except Exception as e:
                        print(f"[DEBUG] 腾讯资金流向 {code}: {e}")
                        continue
                
                print(f"[SUCCESS] 腾讯资金流向: {len(tencent_success)}/{total_codes}")
            except Exception as e:
                print(f"[ERROR] 腾讯资金流向异常: {e}")
        
        # 2. AKShare补充：个股详细资金流向
        failed_codes = [code for code in codes if code not in result]
        if failed_codes and AKSHARE_AVAILABLE and AKSHARE_CONNECTED and len(failed_codes) <= 8: # 限制数量避免频率问题
            print(f"[INFO] AKShare资金流向补充 {len(failed_codes)} 只...")
            try:
                for code in failed_codes:
                    try:
                        # AKShare个股资金流向
                        market = "sh" if code.startswith('6') else "sz"
                        df_fund = ak.stock_individual_fund_flow(stock=code, market=market)
                        
                        if df_fund is not None and not df_fund.empty:
                            latest_data = df_fund.iloc[-1]
                            fund_flow_data = {
                                'code': code,
                                'source': 'akshare',
                                'main_fund_inflow': self._safe_float(latest_data.get('主力净流入-净流入')),
                                'super_fund_inflow': self._safe_float(latest_data.get('超大单净流入-净流入')),
                                'large_fund_inflow': self._safe_float(latest_data.get('大单净流入-净流入')),
                                'medium_fund_inflow': self._safe_float(latest_data.get('中单净流入-净流入')),
                                'small_fund_inflow': self._safe_float(latest_data.get('小单净流入-净流入')),
                                'main_fund_inflow_pct': self._safe_float(latest_data.get('主力净流入-净流入占比')),
                                'date': str(latest_data.get('日期', ''))
                            }
                            
                            if any(fund_flow_data[key] is not None for key in ['main_fund_inflow', 'super_fund_inflow']):
                                result[code] = fund_flow_data
                        
                        time.sleep(0.6)  # AKShare严格控频
                    except Exception as e:
                        print(f"[DEBUG] AKShare资金流向 {code}: {e}")
                        continue
            except Exception as e:
                print(f"[ERROR] AKShare资金流向异常: {e}")
        
        # 3. 为无数据股票提供默认结构
        final_failed = [code for code in codes if code not in result]
        for code in final_failed:
            result[code] = {
                'code': code,
                'source': 'default',
                'main_fund_inflow': None,
                'super_fund_inflow': None,
                'large_fund_inflow': None,
                'medium_fund_inflow': None,
                'small_fund_inflow': None,
                'main_fund_inflow_pct': None,
                'message': '资金流向数据暂无'
            }
        
        success_count = len([r for r in result.values() if r.get('source') != 'default'])
        success_rate = success_count / total_codes * 100 if total_codes > 0 else 0
        print(f"[SUMMARY] 资金流向采集完成: {success_count}/{total_codes} ({success_rate:.1f}%)")
        
        return result
    
    def collect_news_announcements(self, code: str, source: str) -> Dict[str, Any]:
        """采集新闻公告数据"""
        news_data = {
            'recent_announcements': [],
            'news_sentiment': None,
            'important_events': [],
            'source': source
        }
        
        try:
            # 优先使用 Jina API 获取新闻
            if JINA_AVAILABLE and self.jina_api and self.jina_api.api_key and self.jina_api.api_key != "YOUR_JINA_API_KEY":
                try:
                    # 获取股票名称
                    name = f"股票{code}"
                    # 尝试从已收集的数据中获取名称
                    if code in self.collected_data and 'name' in self.collected_data[code]:
                        name = self.collected_data[code]['name']
                    elif code in self.wait_period_data and 'basic_info' in self.wait_period_data[code]:
                        name = self.wait_period_data[code]['basic_info'].get('name', name)
                        
                    jina_news = self.jina_api.get_stock_news(code, name)
                    if jina_news:
                        news_data['recent_announcements'] = jina_news
                        news_data['source'] = 'jina_search'
                        # 简单的关键词情感分析
                        sentiment_score = 0
                        for item in jina_news:
                            title = item.get('title', '')
                            if '利好' in title or '上涨' in title or '增长' in title:
                                sentiment_score += 1
                            if '利空' in title or '下跌' in title or '亏损' in title:
                                sentiment_score -= 1
                        
                        if sentiment_score > 0:
                            news_data['news_sentiment'] = 'positive'
                        elif sentiment_score < 0:
                            news_data['news_sentiment'] = 'negative'
                        else:
                            news_data['news_sentiment'] = 'neutral'
                            
                        return news_data
                except Exception as e:
                    print(f"[WARN] Jina API 新闻采集失败: {e}")

            if source == 'akshare' and AKSHARE_AVAILABLE:
                # 获取公司公告
                try:
                    announcement_df = ak.stock_notice_report(symbol=code)
                    if announcement_df is not None and not announcement_df.empty:
                        recent = announcement_df.head(10)  # 最近10条公告
                        news_data['recent_announcements'] = [
                            {
                                'date': row.get('公告日期', ''),
                                'title': row.get('公告标题', ''),
                                'type': row.get('公告类型', '')
                            }
                            for _, row in recent.iterrows()
                        ]
                except:
                    pass
        
        except Exception as e:
            print(f"[WARN] {code} 新闻公告数据采集失败 ({source}): {e}")
        
        return news_data
    
    def _collect_non_kline_data_during_wait(self, codes: List[str], wait_seconds: int) -> None:
        """在等待期间收集非K线数据以提高效率 - 使用分层数据源策略"""
        print(f"[INFO] 等待期间使用分层数据源策略收集{len(codes)}只股票的其他数据...")
        
        start_time = time.time()
        collected_count = 0
        
        for code in codes:
            if time.time() - start_time >= wait_seconds - 5:  # 预留5秒缓冲
                break
                
            try:
                if code not in self.wait_period_data:
                    self.wait_period_data[code] = {}
                
                # 1. 基础信息 - 优先yfinance, tencent, 兜底akshare
                if 'basic_info' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['basic_info']:
                        if time.time() - start_time >= wait_seconds - 10:
                            break
                        
                        basic_info = self.collect_basic_info(code, source)
                        if basic_info and basic_info.get('name') and basic_info['name'] != f'股票{code}':
                            self.wait_period_data[code]['basic_info'] = basic_info
                            print(f"    ✓ {code}: 基础信息 ({source})")
                            break
                
                # 2. 行业概念 - 优先baostock, 兜底akshare
                if time.time() - start_time < wait_seconds - 15 and 'industry_concept' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['industry_concept']:
                        if time.time() - start_time >= wait_seconds - 20:
                            break
                        
                        industry_concept = self.collect_industry_concept_info(code, source)
                        if industry_concept and (industry_concept.get('industry') or industry_concept.get('concepts')):
                            self.wait_period_data[code]['industry_concept'] = industry_concept
                            print(f"    ✓ {code}: 行业概念 ({source})")
                            break
                
                # 3. 财务数据 - 优先baostock, 兜底akshare
                if time.time() - start_time < wait_seconds - 25 and 'financial_data' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['financial_data']:
                        if time.time() - start_time >= wait_seconds - 30:
                            break
                        
                        financial_data = self.collect_financial_data(code, source)
                        if financial_data and any(v is not None for v in financial_data.values() if v != source):
                            self.wait_period_data[code]['financial_data'] = financial_data
                            print(f"    ✓ {code}: 财务数据 ({source})")
                            break
                
                # 4. 资金流向 - 优先tencent, 兜底akshare
                if time.time() - start_time < wait_seconds - 35 and 'fund_flow' not in self.wait_period_data[code]:
                    for source in self.wait_period_strategy['fund_flow']:
                        if time.time() - start_time >= wait_seconds - 40:
                            break
                        
                        fund_flow = self.collect_fund_flow_data(code, source)
                        if fund_flow and any(v is not None for v in fund_flow.values() if v != source):
                            self.wait_period_data[code]['fund_flow'] = fund_flow
                            print(f"    ✓ {code}: 资金流向 ({source})")
                            break
                
                collected_count += 1
                time.sleep(1)  # 避免请求过快
                
            except Exception as e:
                print(f"    ⚠️ {code}: 等待期间数据收集失败 - {e}")
                continue
        
        elapsed = time.time() - start_time
        print(f"[INFO] 等待期间已收集{collected_count}只股票的其他数据，用时{elapsed:.1f}秒")
        print(f"[INFO] 数据源使用策略: 基础信息({self.wait_period_strategy['basic_info']})")
        print(f"[INFO]                行业概念({self.wait_period_strategy['industry_concept']})")
        print(f"[INFO]                财务数据({self.wait_period_strategy['financial_data']})")
        print(f"[INFO]                资金流向({self.wait_period_strategy['fund_flow']})")
    
    def _collect_parallel_data_during_wait(self, remaining_codes: List[str], all_codes: List[str], 
                                         wait_seconds: int, result: Dict, start_str: str, end_str: str) -> None:
        """在等待期间并行收集K线数据和其他数据"""
        print(f"[INFO] 等待期间并行收集策略: K线数据(akshare) + 其他数据(分层源)")
        
        start_time = time.time()
        akshare_kline_count = 0
        other_data_count = 0
        
        # 获取还没有K线数据的股票
        missing_kline_codes = [code for code in all_codes if code not in result][:10]  # 最多10只
        
        for i, code in enumerate(remaining_codes):
            if time.time() - start_time >= wait_seconds - 5:  # 预留5秒缓冲
                break
            
            try:
                # 1. 如果还有股票没有K线数据，优先用akshare获取K线
                if i < len(missing_kline_codes) and time.time() - start_time < wait_seconds - 15:
                    kline_code = missing_kline_codes[i]
                    print(f"    [K线] 使用akshare获取 {kline_code} K线数据...")
                    
                    kline_data = self._collect_kline_with_akshare(kline_code, start_str, end_str)
                    if kline_data is not None and not kline_data.empty:
                        result[kline_code] = kline_data
                        akshare_kline_count += 1
                        print(f"    ✓ [K线] {kline_code}: {len(kline_data)}天K线数据 (akshare)")
                    else:
                        print(f"    ✗ [K线] {kline_code}: akshare获取失败")
                
                # 2. 并行收集其他数据
                if code not in self.wait_period_data:
                    self.wait_period_data[code] = {}
                
                # 快速收集基础信息
                if 'basic_info' not in self.wait_period_data[code] and time.time() - start_time < wait_seconds - 20:
                    for source in self.wait_period_strategy['basic_info']:
                        if time.time() - start_time >= wait_seconds - 25:
                            break
                        basic_info = self.collect_basic_info(code, source)
                        if basic_info and basic_info.get('name') and basic_info['name'] != f'股票{code}':
                            self.wait_period_data[code]['basic_info'] = basic_info
                            other_data_count += 1
                            print(f"    ✓ [其他] {code}: 基础信息 ({source})")
                            break
                
                # 收集财务数据（如果时间充足）
                if ('financial_data' not in self.wait_period_data[code] and 
                    time.time() - start_time < wait_seconds - 30):
                    for source in self.wait_period_strategy['financial_data']:
                        if time.time() - start_time >= wait_seconds - 35:
                            break
                        financial_data = self.collect_financial_data(code, source)
                        if financial_data and any(v is not None for v in financial_data.values() if v != source):
                            self.wait_period_data[code]['financial_data'] = financial_data
                            print(f"    ✓ [其他] {code}: 财务数据 ({source})")
                            break
                
                time.sleep(0.5)  # 短暂延时避免请求过快
                
            except Exception as e:
                print(f"    ⚠️ {code}: 并行数据收集失败 - {e}")
                continue
        
        elapsed = time.time() - start_time
        print(f"[INFO] 等待期间并行收集完成，用时{elapsed:.1f}秒")
        print(f"[INFO]   - akshare K线数据: {akshare_kline_count}只股票")
        print(f"[INFO]   - 其他数据: {other_data_count}项")
    
    def _collect_kline_with_akshare(self, code: str, start_str: str, end_str: str) -> Optional[pd.DataFrame]:
        """使用akshare获取K线数据"""
        try:
            if not AKSHARE_AVAILABLE or not AKSHARE_CONNECTED:
                return None
            
            import akshare as ak
            df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                   start_date=start_str, end_date=end_str, adjust="qfq")
            if df is not None and not df.empty:
                # 数据格式标准化，与tushare保持一致
                df['trade_date'] = pd.to_datetime(df['日期'])
                df = df.sort_values('trade_date')
                df = df.rename(columns={
                    'trade_date': 'date', '开盘': 'open', '最高': 'high',
                    '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount'
                })
                # 只保留需要的列
                return df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
            
        except Exception as e:
            print(f"[DEBUG] akshare K线获取失败 {code}: {e}")
        
        return None

    def collect_kline_data(self, code: str, source: str = 'auto', days: int = None) -> Optional[pd.DataFrame]:
        """收集单个股票的K线数据"""
        # 检查股票状态，如果已退市则跳过
        if STOCK_STATUS_CHECKER_AVAILABLE and self.status_checker:
            try:
                status_info = self.status_checker.check_single_stock(code)
                if status_info['status'] in ['delisted', 'invalid']:
                    print(f"[SKIP] {code} 已{status_info['status']}，跳过K线数据收集")
                    return None
            except Exception as e:
                print(f"[DEBUG] {code} 状态检查异常: {e}，继续收集")
        
        if days is None:
            days = self.kline_days
            
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 准备不同格式的日期
        start_compact = start_date.strftime('%Y%m%d')
        end_compact = end_date.strftime('%Y%m%d')
        start_iso = start_date.strftime('%Y-%m-%d')
        end_iso = end_date.strftime('%Y-%m-%d')
        
        # 1. AKShare
        if source == 'akshare' or (source == 'auto' and AKSHARE_AVAILABLE):
            return self._collect_kline_with_akshare(code, start_compact, end_compact)
            
        # 2. Tushare
        if source == 'tushare' or (source == 'auto' and TUSHARE_AVAILABLE and self.tushare_token):
            try:
                pro = ts.pro_api(self.tushare_token)
                ts_code = f"{code}.SZ" if code.startswith(('000', '002', '300')) else f"{code}.SH"
                df = pro.daily(ts_code=ts_code, start_date=start_compact, end_date=end_compact)
                if not df.empty:
                    return self.standardize_kline_columns(df, 'tushare')
            except Exception as e:
                print(f"[WARN] Tushare获取单股K线失败 {code}: {e}")
        
        # 3. Tencent (作为兜底)
        if self.tencent_kline:
            return self.tencent_kline.get_stock_kline(code, start_iso, end_iso)
            
        return None

    def pre_check_stock_validity(self, codes: List[str], filter_invalid: bool = True) -> Dict[str, List[str]]:
        """
        预检股票有效性，过滤退市和无效股票
        
        Args:
            codes: 股票代码列表
            filter_invalid: 是否过滤无效股票
            
        Returns:
            {
                'valid_codes': 有效且活跃的股票代码,
                'delisted': 已退市的股票,
                'invalid': 无效的股票代码,
                'suspended': 停牌的股票
            }
        """
        print(f"[INFO] 开始股票有效性预检: {len(codes)} 只股票...")
        
        try:
            # 批量检测股票状态
            status_results = self.status_checker.batch_check_stocks(codes)
            
            # 分类结果
            categorized = {
                'valid_codes': [],
                'delisted': [],
                'invalid': [],
                'suspended': []
            }
            
            for code, info in status_results.items():
                if info['status'] == 'active':
                    categorized['valid_codes'].append(code)
                elif info['status'] == 'delisted':
                    categorized['delisted'].append(code)
                elif info['status'] == 'invalid':
                    categorized['invalid'].append(code)
                elif info['status'] == 'suspended':
                    categorized['suspended'].append(code)
            
            # 报告结果
            print(f"[SUCCESS] 股票预检完成:")
            print(f"  OK 有效活跃: {len(categorized['valid_codes'])} 只")
            print(f"  DELISTED 已退市: {len(categorized['delisted'])} 只 {categorized['delisted'][:5]}{'...' if len(categorized['delisted']) > 5 else ''}")
            print(f"  INVALID 无效代码: {len(categorized['invalid'])} 只 {categorized['invalid'][:5]}{'...' if len(categorized['invalid']) > 5 else ''}")
            print(f"  SUSPENDED 停牌特处: {len(categorized['suspended'])} 只 {categorized['suspended'][:5]}{'...' if len(categorized['suspended']) > 5 else ''}")
            
            return categorized
            
        except Exception as e:
            print(f"[ERROR] 股票预检异常: {e}")
            # 如果预检失败，返回原始代码列表
            return {
                'valid_codes': codes,
                'delisted': [],
                'invalid': [],
                'suspended': []
            }
    
    def clean_delisted_stocks_from_data(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理数据中的退市股票
        
        Args:
            data_dict: 包含股票数据的字典
            
        Returns:
            清理后的数据字典
        """
        if not STOCK_STATUS_CHECKER_AVAILABLE or not self.status_checker:
            return data_dict
        
        print(f"[INFO] 开始清理数据中的退市股票...")
        
        try:
            # 获取所有股票代码
            all_codes = list(data_dict.keys())
            if not all_codes:
                return data_dict
            
            # 检查股票状态
            validity_check = self.pre_check_stock_validity(all_codes)
            
            # 需要移除的股票（退市和无效）
            codes_to_remove = validity_check['delisted'] + validity_check['invalid']
            
            if codes_to_remove:
                print(f"[INFO] 发现 {len(codes_to_remove)} 只退市/无效股票，正在清理...")
                
                cleaned_data = {}
                removed_count = 0
                
                for code, data in data_dict.items():
                    if code not in codes_to_remove:
                        cleaned_data[code] = data
                    else:
                        removed_count += 1
                        print(f"[CLEAN] 移除退市股票数据: {code}")
                
                print(f"[SUCCESS] 数据清理完成，移除 {removed_count} 只退市股票")
                print(f"[INFO] 清理后数据: {len(cleaned_data)}/{len(data_dict)} 只股票")
                
                return cleaned_data
            else:
                print(f"[INFO] 数据中无退市股票，无需清理")
                return data_dict
                
        except Exception as e:
            print(f"[ERROR] 清理退市股票数据时异常: {e}")
            return data_dict
    
    def auto_clean_all_data(self):
        """
        自动清理所有已收集数据中的退市股票
        """
        print(f"[INFO] 开始自动清理所有数据中的退市股票...")
        
        # 清理主要数据
        if hasattr(self, 'collected_data') and self.collected_data:
            print(f"[INFO] 清理主要收集数据...")
            self.collected_data = self.clean_delisted_stocks_from_data(self.collected_data)
        
        # 清理等待期数据
        if hasattr(self, 'wait_period_data') and self.wait_period_data:
            print(f"[INFO] 清理等待期数据...")
            self.wait_period_data = self.clean_delisted_stocks_from_data(self.wait_period_data)
        
        # 清理其他可能的数据字典
        for attr_name in ['kline_data_cache', 'financial_data_cache', 'basic_info_cache']:
            if hasattr(self, attr_name):
                attr_data = getattr(self, attr_name)
                if isinstance(attr_data, dict) and attr_data:
                    print(f"[INFO] 清理{attr_name}...")
                    cleaned = self.clean_delisted_stocks_from_data(attr_data)
                    setattr(self, attr_name, cleaned)
        
        print(f"[SUCCESS] 自动清理完成")

    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value in (None, "", "--", "-", "NaN"):
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '').strip()
            return float(value)
        except:
            return None
    
    def collect_technical_indicators(self, kline_df: pd.DataFrame) -> Dict[str, Any]:
        """根据K线数据计算技术指标"""
        try:
            if kline_df is None or kline_df.empty:
                return {'status': 'no_data'}
            
            # 确保按日期排序
            if 'date' in kline_df.columns:
                df = kline_df.sort_values('date')
            else:
                df = kline_df
            
            # 获取收盘价序列
            # 兼容不同的列名
            close_col = next((col for col in ['close', '收盘', 'Close'] if col in df.columns), None)
            volume_col = next((col for col in ['volume', '成交量', 'Volume'] if col in df.columns), None)
            
            if not close_col:
                return {'status': 'missing_close_price'}
                
            closes = df[close_col]
            current_price = float(closes.iloc[-1])
            
            # 计算移动平均线
            ma5 = float(closes.rolling(window=5).mean().iloc[-1]) if len(closes) >= 5 else current_price
            ma10 = float(closes.rolling(window=10).mean().iloc[-1]) if len(closes) >= 10 else current_price
            ma20 = float(closes.rolling(window=20).mean().iloc[-1]) if len(closes) >= 20 else current_price
            ma60 = float(closes.rolling(window=60).mean().iloc[-1]) if len(closes) >= 60 else current_price
            
            # 计算RSI
            delta = closes.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
            
            # 计算MACD
            exp12 = closes.ewm(span=12, adjust=False).mean()
            exp26 = closes.ewm(span=26, adjust=False).mean()
            macd_line = exp12 - exp26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_val = float(macd_line.iloc[-1])
            signal_val = float(signal_line.iloc[-1])
            
            # 计算量比
            volume_ratio = 1.0
            if volume_col and len(df) >= 6:
                volumes = df[volume_col]
                current_vol = float(volumes.iloc[-1])
                avg_vol = float(volumes.iloc[-6:-1].mean())
                if avg_vol > 0:
                    volume_ratio = current_vol / avg_vol
            
            return {
                'current_price': current_price,
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'ma60': ma60,
                'rsi': rsi_val,
                'macd': macd_val,
                'signal': signal_val,
                'volume_ratio': volume_ratio,
                'status': 'calculated'
            }
            
        except Exception as e:
            print(f"[ERROR] 计算技术指标失败: {e}")
            return {'status': 'calculation_error', 'error': str(e)}

    def collect_comprehensive_data(self, codes: List[str], batch_size: int = 15) -> Dict[str, Any]:
        """采集综合数据 - 专门化数据源分配策略"""
        results = {}
        
        print(f"[INFO] 开始采集 {len(codes)} 只股票的综合数据 (专门化API分配策略)")
        
        # 预检股票有效性（过滤退市和无效股票）
        if STOCK_STATUS_CHECKER_AVAILABLE and self.status_checker:
            print(f"[INFO] 步骤0: 股票有效性预检...")
            try:
                validity_check = self.pre_check_stock_validity(codes)
                original_count = len(codes)
                codes = validity_check['valid_codes']  # 只使用有效的股票
                
                # 记录被过滤的股票
                filtered_count = original_count - len(codes)
                if filtered_count > 0:
                    print(f"[INFO] 已过滤 {filtered_count} 只问题股票:")
                    if validity_check['delisted']:
                        print(f"  - 退市股票: {len(validity_check['delisted'])} 只")
                    if validity_check['invalid']:
                        print(f"  - 无效代码: {len(validity_check['invalid'])} 只")
                    if validity_check['suspended']:
                        print(f"  - 停牌股票: {len(validity_check['suspended'])} 只")
                        
                print(f"[INFO] 预检后有效股票: {len(codes)} 只")
            except Exception as e:
                print(f"[WARN] 股票预检异常: {e}，将继续使用原始列表")
        else:
            print(f"[INFO] 股票状态检测器不可用，跳过预检")
        
        print(f"[INFO] 数据源策略: Baostock基本面 | Tencent实时资金 | YFinance估值 | AKShare兜底")
        
        # 1. 批量采集K线数据 (保持原有轮换策略: tushare ↔ akshare → JoinQuant → Alpha Vantage)
        print(f"[INFO] 步骤1: 批量采集K线数据 (轮换策略)...")
        try:
            batch_kline_data = self.collect_batch_kline_data(codes, 'auto')
            print(f"[INFO] K线数据采集完成，获得 {len(batch_kline_data)} 只股票 (多源轮换)")
        except Exception as e:
            print(f"[ERROR] 批量采集K线数据失败: {e}")
            batch_kline_data = {}
        
        # 2. 批量采集基础信息 - 专门化分配：Baostock → Tencent → AKShare
        print(f"[INFO] 步骤2: 批量采集基础信息 (Baostock专业 → Tencent实时 → AKShare兜底)...")
        try:
            batch_basic_info = self.collect_batch_basic_info(codes, 'baostock')
            print(f"[INFO] 基础信息采集完成，获得 {len(batch_basic_info)} 只股票 (专业数据源)")
        except Exception as e:
            print(f"[ERROR] 批量采集基础信息失败: {e}")
            batch_basic_info = {}
        
        # 3. 批量采集财务数据 - 专门化分配：Baostock → YFinance → Tencent → AKShare
        print(f"[INFO] 步骤3: 批量采集财务数据 (Baostock基本面 → YFinance估值 → Tencent → AKShare)...")
        try:
            batch_financial_data = self.collect_batch_financial_data(codes, 'baostock')
            print(f"[INFO] 财务数据采集完成，获得 {len(batch_financial_data)} 只股票 (多层专业源)")
        except Exception as e:
            print(f"[ERROR] 批量采集财务数据失败: {e}")
            batch_financial_data = {}
        
        # 4. 批量采集行业概念数据 - 专门化分配：Baostock映射 → AKShare热点概念
        print(f"[INFO] 步骤4: 批量采集行业概念 (Baostock标准分类 → AKShare概念热点)...")
        try:
            batch_industry_data = self.collect_batch_industry_concept(codes, 'baostock')
            print(f"[INFO] 行业概念采集完成，获得 {len(batch_industry_data)} 只股票 (标准+热点)")
        except Exception as e:
            print(f"[ERROR] 批量采集行业概念失败: {e}")
            batch_industry_data = {}
        
        # 5. 批量采集资金流向数据 - 专门化分配：Tencent → AKShare
        print(f"[INFO] 步骤5: 批量采集资金流向 (Tencent实时流向 → AKShare个股资金)...")
        try:
            batch_fund_flow_data = self.collect_batch_fund_flow(codes, 'tencent')
            print(f"[INFO] 资金流向采集完成，获得 {len(batch_fund_flow_data)} 只股票 (实时专业)")
        except Exception as e:
            print(f"[ERROR] 批量采集资金流向失败: {e}")
            batch_fund_flow_data = {}
        
        # 6. 整合数据并补充其他信息
        print(f"[INFO] 步骤6: 整合专门化数据并补充实时信息...")
        for i, code in enumerate(codes[:batch_size]):
            print(f"\n[{i+1}/{min(batch_size, len(codes))}] 正在整合 {code} 的专门化数据...")
            
            stock_data = {
                'code': code,
                'timestamp': datetime.now().isoformat(),
                'collection_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_source': 'specialized_distribution_v2',
                'api_strategy': {
                    'kline': 'tushare_akshare_rotation',
                    'basic_info': 'baostock_tencent_akshare',
                    'financial': 'baostock_yfinance_tencent_akshare', 
                    'industry': 'baostock_akshare_mapping',
                    'fund_flow': 'tencent_akshare_realtime',
                    'news': 'akshare_realtime'
                },
                'basic_info': batch_basic_info.get(code, {'code': code, 'name': f'股票{code}', 'source': 'fallback'}),
                'kline_data': None,
                'financial_data': batch_financial_data.get(code, {'code': code, 'source': 'fallback'}),
                'technical_indicators': {},
                'industry_concept': batch_industry_data.get(code, {'industry': '其他制造业', 'source': 'fallback'}),
                'fund_flow': batch_fund_flow_data.get(code, {'source': 'fallback'}),
                'news_announcements': {}
            }
            
            # 处理K线数据 - 从批量采集结果获取 (多源轮换策略)
            if code in batch_kline_data:
                kline_df = batch_kline_data[code]
                if kline_df is not None and not kline_df.empty:
                    # 安全获取最新价格
                    latest_price = None
                    for col in ['close', '收盘', 'Close']:
                        if col in kline_df.columns:
                            try:
                                latest_price = float(kline_df[col].iloc[-1])
                                break
                            except (IndexError, ValueError, TypeError):
                                continue
                    
                    stock_data['kline_data'] = {
                        'daily': kline_df.to_dict('records'),
                        'latest_price': latest_price,
                        'data_points': len(kline_df),
                        'source': 'batch_rotation'
                    }
                    print(f"    ✓ K线数据: {len(kline_df)}天 (轮换策略)")
                else:
                    kline_df = None
            else:
                print(f"    ⚠️ 未在批量K线数据中，尝试AKShare兜底")
                kline_df = self.collect_kline_data(code, 'akshare')
                if kline_df is not None and not kline_df.empty:
                    # 安全获取最新价格
                    latest_price = None
                    for col in ['close', '收盘', 'Close']:
                        if col in kline_df.columns:
                            try:
                                latest_price = float(kline_df[col].iloc[-1])
                                break
                            except (IndexError, ValueError, TypeError):
                                continue
                    
                    stock_data['kline_data'] = {
                        'daily': kline_df.to_dict('records'),
                        'latest_price': latest_price,
                        'data_points': len(kline_df),
                        'source': 'akshare_fallback'
                    }
            
            # 技术指标计算 - 基于K线数据
            if kline_df is not None and not kline_df.empty:
                stock_data['technical_indicators'] = self.collect_technical_indicators(kline_df)
                print(f"    ✓ 技术指标: 基于K线数据计算完成")
            else:
                stock_data['technical_indicators'] = {'status': 'no_kline_data'}
                print(f"    ⚠️ 技术指标: 无K线数据，跳过")
            
            # 数据源追踪 - 记录实际使用的数据源
            data_sources_used = {
                'basic_info': stock_data['basic_info'].get('source', 'unknown'),
                'financial_data': stock_data['financial_data'].get('source', 'unknown'),
                'industry_concept': stock_data['industry_concept'].get('source', 'unknown'),
                'fund_flow': stock_data['fund_flow'].get('source', 'unknown'),
                'kline_data': stock_data['kline_data'].get('source', 'unknown') if stock_data['kline_data'] else 'none'
            }
            
            # 输出批量采集结果汇总
            print(f"    ✓ 基础信息: {data_sources_used['basic_info']}")
            print(f"    ✓ 财务数据: {data_sources_used['financial_data']}")
            print(f"    ✓ 行业概念: {data_sources_used['industry_concept']}")
            print(f"    ✓ 资金流向: {data_sources_used['fund_flow']}")
            
            # 新闻公告 - 实时收集（时效性重要，使用AKShare）
            try:
                stock_data['news_announcements'] = self.collect_news_announcements(code, 'akshare')
                print(f"    ✓ 新闻公告: AKShare实时收集")
            except Exception as e:
                stock_data['news_announcements'] = {'status': 'failed', 'error': str(e)}
                print(f"    ⚠️ 新闻公告: 收集失败 - {e}")
            
            # 记录完整数据源信息
            stock_data['data_sources_used'] = data_sources_used
            stock_data['collection_summary'] = {
                'strategy': 'specialized_api_distribution',
                'timestamp': datetime.now().isoformat(),
                'success_rate': len([v for v in data_sources_used.values() if v not in ('unknown', 'none', 'fallback')]) / len(data_sources_used)
            }
            
            results[code] = stock_data
            
            # 短暂延时避免请求过频
            time.sleep(0.3)
        
        # 输出批量采集统计
        total_stocks = len(results)
        successful_collections = {
            'kline': len([r for r in results.values() if r['kline_data'] is not None]),
            'basic_info': len([r for r in results.values() if r['basic_info'].get('source') != 'fallback']),
            'financial': len([r for r in results.values() if r['financial_data'].get('source') != 'fallback']),
            'industry': len([r for r in results.values() if r['industry_concept'].get('source') != 'fallback']),
            'fund_flow': len([r for r in results.values() if r['fund_flow'].get('source') != 'fallback'])
        }
        
        print(f"\n[INFO] 专门化数据采集完成统计:")
        print(f"  总股票数: {total_stocks}")
        print(f"  K线数据: {successful_collections['kline']}/{total_stocks} ({successful_collections['kline']/total_stocks*100:.1f}%)")
        print(f"  基础信息: {successful_collections['basic_info']}/{total_stocks} ({successful_collections['basic_info']/total_stocks*100:.1f}%)")
        print(f"  财务数据: {successful_collections['financial']}/{total_stocks} ({successful_collections['financial']/total_stocks*100:.1f}%)")
        print(f"  行业概念: {successful_collections['industry']}/{total_stocks} ({successful_collections['industry']/total_stocks*100:.1f}%)")
        print(f"  资金流向: {successful_collections['fund_flow']}/{total_stocks} ({successful_collections['fund_flow']/total_stocks*100:.1f}%)")
        
        # 确保Baostock登出，释放资源
        if BAOSTOCK_AVAILABLE and self.bs_login:
            try:
                import baostock as bs
                bs.logout()
            except:
                pass
        
        return results
    
    def save_data(self, data: Dict[str, Any], filename: Optional[str] = None) -> None:
        """保存数据到JSON文件 - 分卷存储模式 (每卷最多200只股票)"""
        # 忽略传入的 filename，使用分卷逻辑
        base_filename = self.output_file # data/comprehensive_stock_data.json
        base_dir = os.path.dirname(base_filename)
        base_name = os.path.basename(base_filename).replace('.json', '')
        index_file = os.path.join(base_dir, 'stock_file_index.json')
        
        # 确保目录存在
        os.makedirs(base_dir, exist_ok=True)
        
        # 加载索引
        stock_index = {}
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    stock_index = json.load(f)
            except:
                pass
        
        # 清理待保存数据
        cleaned_data = DateTimeEncoder.clean_data_for_json(data)
        
        # 按目标文件分组待保存的数据
        files_to_update = {} # filename -> {code: data}
        
        # 查找现有的分卷文件
        import glob
        part_files = glob.glob(os.path.join(base_dir, f"{base_name}_part_*.json"))
        part_files.sort(key=lambda x: int(x.split('_part_')[-1].replace('.json', '')))
        
        # 确定当前最新的分卷文件
        current_file = None
        current_file_count = 0
        
        if part_files:
            current_file = part_files[-1]
            # 简单读取一下数量，或者我们信任索引？
            # 为了准确，读取一下最后这个文件
            try:
                with open(current_file, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if 'stocks' in content:
                        current_file_count = len(content['stocks'])
            except:
                current_file_count = 0
        else:
            # 初始化第一个文件
            current_file = os.path.join(base_dir, f"{base_name}_part_1.json")
            current_file_count = 0
            
        # 分配数据到文件
        for code, stock_info in cleaned_data.items():
            target_file = None
            
            # 1. 检查是否已存在于某个文件中 (更新)
            if code in stock_index:
                # 索引中存储的是相对路径或文件名，我们需要确保它是完整的路径
                indexed_file = stock_index[code]
                # 如果索引只存了文件名
                if os.path.dirname(indexed_file) == '':
                    target_file = os.path.join(base_dir, indexed_file)
                else:
                    target_file = indexed_file
            else:
                # 2. 新增数据
                # 检查当前文件是否已满
                if current_file_count >= 200:
                    # 创建新分卷
                    next_part = 1
                    if part_files:
                        try:
                            last_part_num = int(part_files[-1].split('_part_')[-1].replace('.json', ''))
                            next_part = last_part_num + 1
                        except:
                            pass
                    elif current_file:
                         try:
                            last_part_num = int(current_file.split('_part_')[-1].replace('.json', ''))
                            next_part = last_part_num + 1
                         except:
                            pass

                    new_file = os.path.join(base_dir, f"{base_name}_part_{next_part}.json")
                    part_files.append(new_file) # 更新列表
                    current_file = new_file
                    current_file_count = 0
                
                target_file = current_file
                current_file_count += 1
                # 更新索引 (存文件名即可，方便移植)
                stock_index[code] = os.path.basename(target_file)
            
            if target_file not in files_to_update:
                files_to_update[target_file] = {}
            files_to_update[target_file][code] = stock_info
            
        # 执行保存
        for filepath, stocks_data in files_to_update.items():
            file_content = {'stocks': {}}
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        file_content = json.load(f)
                except:
                    pass
            
            if 'stocks' not in file_content:
                file_content['stocks'] = {}
                
            file_content['stocks'].update(stocks_data)
            file_content['last_updated'] = datetime.now().isoformat()
            file_content['total_stocks'] = len(file_content['stocks'])
            
            # 原子写入
            temp_filename = filepath + '.tmp'
            try:
                with open(temp_filename, 'w', encoding='utf-8') as f:
                    json.dump(file_content, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                
                if os.path.exists(filepath):
                    os.replace(temp_filename, filepath)
                else:
                    os.rename(temp_filename, filepath)
                print(f"[SUCCESS] 数据已保存到 {os.path.basename(filepath)}")
            except Exception as e:
                print(f"[ERROR] 保存分卷 {os.path.basename(filepath)} 失败: {e}")
                if os.path.exists(temp_filename):
                    try: os.remove(temp_filename) 
                    except: pass

        # 保存索引
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(stock_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 保存索引失败: {e}")
    
    def update_kline_data_only(self, batch_size: int = 20, total_batches: int = None, stock_type: str = "主板", progress_callback=None):
        """只更新K线数据和技术指标（高效模式）"""
        
        # 首先获取股票列表来确定实际数量
        if stock_type == "全部":
            # 全部股票：先获取全量股票列表
            all_codes = self.get_stock_list_by_type(stock_type, limit=6000)  # 获取更多股票
        else:
            # 其他类型：根据预估数量获取
            estimated_limit = (total_batches * batch_size) if total_batches else 5000
            all_codes = self.get_stock_list_by_type(stock_type, limit=estimated_limit)
        
        actual_total = len(all_codes)
        
        # 根据实际股票数量动态计算批次
        if total_batches is None:
            total_batches = (actual_total + batch_size - 1) // batch_size  # 向上取整
        
        print(f"[INFO] 开始K线数据更新 (每批 {batch_size} 只股票，共 {total_batches} 批)")
        print(f"[INFO] 股票类型: {stock_type}")
        print(f"[INFO] 实际股票数量: {actual_total} 只")
        print(f"[INFO] 更新策略: 只更新K线数据和技术指标，保留其他数据不变")
        
        if progress_callback:
            progress_callback("获取股票列表...", 1, f"获得 {actual_total} 只{stock_type}股票，将分 {total_batches} 批处理")
        
        if actual_total == 0:
            msg = f"错误：没有找到{stock_type}类型的股票！"
            print(f"[ERROR] {msg}")
            if progress_callback:
                progress_callback("错误", 0, msg)
                return
        
        if progress_callback:
            progress_callback("开始K线更新...", 2, f"获得 {actual_total} 只股票，开始K线数据更新...")
        
        # 加载现有数据
        existing_data = self.load_existing_data()
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch_codes = all_codes[start_idx:end_idx]
            
            if not batch_codes:
                break
            
            # 计算进度
            progress_pct = ((batch_num + 1) / total_batches) * 100
            completed_count = min((batch_num + 1) * batch_size, actual_total)
            current_batch_info = f"第 {batch_num + 1}/{total_batches} 批"
            stock_info = f"处理股票: {', '.join(batch_codes[:3])}{'...' if len(batch_codes) > 3 else ''}"
            progress_text = f"{completed_count}/{actual_total}"
            
            if progress_callback:
                progress_callback(f"K线更新中 ({progress_text})", progress_pct, f"{current_batch_info} - {stock_info}")
            
            print(f"\n{'='*50}")
            print(f"第 {batch_num + 1} 批 / 共 {total_batches} 批 (K线更新)")
            print(f"股票代码: {', '.join(batch_codes)}")
            print(f"{'='*50}")
            
            # 批量采集K线数据
            try:
                batch_kline_data = self.collect_batch_kline_data(batch_codes, 'auto')
                print(f"[INFO] 本批K线数据采集完成，获得 {len(batch_kline_data)} 只股票")
                
                # 更新每只股票的K线数据
                for code in batch_codes:
                    if code in batch_kline_data:
                        kline_df = batch_kline_data[code]
                        if kline_df is not None and not kline_df.empty:
                            # 计算技术指标
                            tech_indicators = self.collect_technical_indicators(kline_df)
                            
                            # 获取最新价格
                            latest_price = None
                            for col in ['close', '收盘', 'Close']:
                                if col in kline_df.columns:
                                    try:
                                        latest_price = float(kline_df[col].iloc[-1])
                                        break
                                    except:
                                        continue
                            
                            # 更新K线数据
                            if code in existing_data:
                                # 保留原有数据，只更新K线和技术指标
                                existing_data[code]['kline_data'] = {
                                    'daily': kline_df.to_dict('records'),
                                    'latest_price': latest_price,
                                    'data_points': len(kline_df),
                                    'source': 'updated',
                                    'update_time': datetime.now().isoformat()
                                }
                                existing_data[code]['technical_indicators'] = tech_indicators
                                existing_data[code]['last_kline_update'] = datetime.now().isoformat()
                                print(f"    ✓ {code}: 更新K线 {len(kline_df)}天")
                            else:
                                # 如果是新股票，创建基本结构
                                existing_data[code] = {
                                    'code': code,
                                    'name': f'股票{code}',
                                    'kline_data': {
                                        'daily': kline_df.to_dict('records'),
                                        'latest_price': latest_price,
                                        'data_points': len(kline_df),
                                        'source': 'new',
                                        'update_time': datetime.now().isoformat()
                                    },
                                    'technical_indicators': tech_indicators,
                                    'last_kline_update': datetime.now().isoformat(),
                                    'timestamp': datetime.now().isoformat()
                                }
                                print(f"    + {code}: 新增K线 {len(kline_df)}天")
                
                # 批次保存
                self.save_data(existing_data)
                
                if progress_callback:
                    detail_info = f"{current_batch_info} 完成 - 已保存 {len(batch_kline_data)} 只K线数据"
                    progress_callback(f"K线更新中 ({progress_text})", progress_pct, detail_info)
                
            except Exception as e:
                error_msg = f"{current_batch_info} 失败: {str(e)}"
                print(f"[ERROR] {error_msg}")
                if progress_callback:
                    progress_callback("K线更新出错", progress_pct, error_msg)
            
            # 批次间休息
            if batch_num < total_batches - 1:
                if progress_callback:
                    progress_callback("批次间休息...", progress_pct, f"{current_batch_info} 完成，休息3秒后继续...")
                print(f"\n[INFO] 批次完成，休息 3 秒后继续...")
                time.sleep(3)
        
        if progress_callback:
            progress_callback("K线更新完成", 100, f"所有 {total_batches} 批次K线数据更新完成！")
        
        print(f"\n[SUCCESS] 所有批次K线数据更新完成！")
    
    def load_existing_data(self):
        """加载现有数据"""
        import json
        import os

        # 尝试从分卷文件加载
        data_dir = 'data'
        all_data = {}
        
        if os.path.exists(data_dir):
            for i in range(1, 6):
                part_file = os.path.join(data_dir, f'comprehensive_stock_data_part_{i}.json')
                if os.path.exists(part_file):
                    try:
                        with open(part_file, 'r', encoding='utf-8') as f:
                            content = json.load(f)
                            if 'stocks' in content:
                                all_data.update(content['stocks'])
                                print(f"[INFO] 加载分卷 {i}: {len(content['stocks'])} 只股票")
                    except Exception as e:
                        print(f"[WARN] 加载 {part_file} 失败: {e}")
        
        print(f"[INFO] 加载现有数据: {len(all_data)} 只股票")
        return all_data
    
    def run_batch_collection_with_progress(self, batch_size: int = 15, total_batches: int = None, stock_type: str = "主板", progress_callback=None):
        """运行专门化数据源分配批量采集，支持进度回调"""
        
        # 首先获取股票列表来确定实际数量
        if stock_type == "全部":
            # 全部股票：先获取全量股票列表
            all_codes = self.get_stock_list_by_type(stock_type, limit=6000)  # 获取更多股票
        else:
            # 其他类型：根据预估数量获取
            estimated_limit = (total_batches * batch_size) if total_batches else 5000
            all_codes = self.get_stock_list_by_type(stock_type, limit=estimated_limit)
        
        actual_total = len(all_codes)
        
        # 根据实际股票数量动态计算批次
        if total_batches is None:
            total_batches = (actual_total + batch_size - 1) // batch_size  # 向上取整
        
        print(f"[INFO] 开始专门化数据源分配批量采集 (每批 {batch_size} 只股票，共 {total_batches} 批)")
        print(f"[INFO] 股票类型: {stock_type}")
        print(f"[INFO] 实际股票数量: {actual_total} 只")
        print(f"[INFO] 数据源策略: Baostock基本面 | Tencent实时资金 | YFinance估值 | AKShare兜底")
        
        if progress_callback:
            progress_callback("获取股票列表...", 1, f"获得 {actual_total} 只{stock_type}股票，将分 {total_batches} 批处理")
        
        if actual_total == 0:
            msg = f"错误：没有找到{stock_type}类型的股票！"
            print(f"[ERROR] {msg}")
            if progress_callback:
                progress_callback("错误", 0, msg)
                return
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch_codes = all_codes[start_idx:end_idx]
            
            if not batch_codes:
                break
            
            # 计算进度百分比和已完成数量
            progress_pct = ((batch_num + 1) / total_batches) * 100
            completed_count = min((batch_num + 1) * batch_size, actual_total)
            current_batch_info = f"第 {batch_num + 1}/{total_batches} 批"
            stock_info = f"处理股票: {', '.join(batch_codes[:3])}{'...' if len(batch_codes) > 3 else ''}"
            progress_text = f"{completed_count}/{actual_total}"
            
            if progress_callback:
                progress_callback(f"采集中 ({progress_text})", progress_pct, f"{current_batch_info} - {stock_info}")
            
            print(f"\n{'='*50}")
            print(f"第 {batch_num + 1} 批 / 共 {total_batches} 批 (专门化API分配)")
            print(f"股票代码: {', '.join(batch_codes)}")
            print(f"{'='*50}")
            
            # 采集数据
            try:
                batch_data = self.collect_comprehensive_data(batch_codes, batch_size)
                
                # 保存数据
                self.save_data(batch_data)
                
                if progress_callback:
                    detail_info = f"{current_batch_info} 完成 - 已保存 {len(batch_data)} 只股票专门化数据"
                    progress_callback("专门化采集中...", progress_pct, detail_info)
                
            except Exception as e:
                error_msg = f"{current_batch_info} 失败: {str(e)}"
                print(f"[ERROR] {error_msg}")
                if progress_callback:
                    progress_callback("采集出现错误", progress_pct, error_msg)
            
            # 批次间休息
            if batch_num < total_batches - 1:
                if progress_callback:
                    progress_callback("批次间休息...", progress_pct, f"{current_batch_info} 完成，休息5秒后继续...")
                print(f"\n[INFO] 批次完成，休息 5 秒后继续...")
                time.sleep(5)
        
        if progress_callback:
            progress_callback("专门化采集完成", 100, f"所有 {total_batches} 批次专门化数据采集完成！")
        
        print(f"\n[SUCCESS] 所有批次专门化数据采集完成！")
    
    def run_batch_collection(self, batch_size: int = 15, total_batches: int = 166):
        """运行专门化数据源分配批量采集"""
        print(f"[INFO] 开始专门化数据源分配批量采集 (每批 {batch_size} 只股票，共 {total_batches} 批)")
        print(f"[INFO] 优化策略: 每个API专注其专长领域，智能批量，频次控制")
        
        # 获取股票列表（只包含主板股票）
        all_codes = self.get_stock_list_excluding_cyb(limit=batch_size * total_batches)
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch_codes = all_codes[start_idx:end_idx]
            
            if not batch_codes:
                break
            
            print(f"\n{'='*50}")
            print(f"第 {batch_num + 1} 批 / 共 {total_batches} 批 (专门化策略)")
            print(f"股票代码: {', '.join(batch_codes)}")
            print(f"{'='*50}")
            
            # 采集数据
            batch_data = self.collect_comprehensive_data(batch_codes, batch_size)
            
            # 保存数据
            self.save_data(batch_data)
            
            # 批次间休息
            if batch_num < total_batches - 1:
                print(f"\n[INFO] 批次完成，休息 5 秒后继续...")
                time.sleep(5)
        
        print(f"\n[SUCCESS] 所有批次专门化数据采集完成！")


def main():
    """主函数 - 专门化数据源分配批量处理模式"""
    collector = ComprehensiveDataCollector()
    
    print("A股全面数据采集器 - 专门化API分配策略")
    print("=" * 60)
    print("配置: 每批15只股票，专门化数据源分配")
    print("数据源分配策略:")
    print("  • K线数据: Tushare ↔ AKShare轮换 → JoinQuant → Alpha Vantage")
    print("  • 基础信息: Baostock专业 → Tencent实时 → AKShare兜底")
    print("  • 财务数据: Baostock基本面 → YFinance估值 → Tencent → AKShare")
    print("  • 行业概念: Baostock标准分类 → AKShare概念热点")
    print("  • 资金流向: Tencent实时流向 → AKShare个股资金")
    print("  • 新闻公告: AKShare实时收集")
    print("=" * 60)
    
    # 使用专门化批量处理，每批15只
    try:
        collector.run_batch_collection(batch_size=15, total_batches=80)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断采集")
    except Exception as e:
        print(f"\n[ERROR] 采集过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
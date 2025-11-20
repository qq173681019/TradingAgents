"""
Alpha Vantage API集成模块
提供股票数据获取功能，主要支持美股和部分国际股票
"""

import requests
import pandas as pd
import time
from typing import Dict, Any, Optional
import json

class AlphaVantageAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        self.last_request_time = 0
        self.min_interval = 12  # 每分钟最多5次请求，所以至少间隔12秒
        
    def _make_request(self, params: Dict[str, str]) -> Optional[Dict]:
        """发起API请求，包含频率控制"""
        # 频率控制
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            print(f"[INFO] Alpha Vantage 频率控制，等待 {sleep_time:.1f} 秒...")
            time.sleep(sleep_time)
        
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                data = response.json()
                
                # 检查错误信息
                if "Error Message" in data:
                    print(f"[ERROR] Alpha Vantage API错误: {data['Error Message']}")
                    return None
                elif "Note" in data:
                    print(f"[WARN] Alpha Vantage 请求频率限制: {data['Note']}")
                    return None
                
                return data
            else:
                print(f"[ERROR] Alpha Vantage HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Alpha Vantage 请求失败: {e}")
            return None
    
    def get_daily_kline(self, symbol: str, outputsize: str = "compact") -> Optional[pd.DataFrame]:
        """获取日K线数据"""
        # A股需要添加后缀，尝试不同的格式
        test_symbols = [
            symbol,  # 原始代码
            f"{symbol}.SS",  # 上海证券交易所
            f"{symbol}.SZ",  # 深圳证券交易所
            f"SHA:{symbol}",  # 另一种格式
            f"SHZ:{symbol}"   # 另一种格式
        ]
        
        for test_symbol in test_symbols:
            print(f"[INFO] Alpha Vantage 尝试获取 {test_symbol} 的K线数据...")
            
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': test_symbol,
                'outputsize': outputsize  # compact (100 days) or full
            }
            
            data = self._make_request(params)
            if not data:
                continue
            
            # 检查是否有时间序列数据
            time_series_key = 'Time Series (Daily)'
            if time_series_key in data:
                time_series = data[time_series_key]
                
                if time_series:
                    # 转换为DataFrame
                    df = pd.DataFrame.from_dict(time_series, orient='index')
                    df.index = pd.to_datetime(df.index)
                    df = df.sort_index()
                    
                    # 重命名列
                    df.columns = ['open', 'high', 'low', 'close', 'volume']
                    
                    # 转换数据类型
                    for col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    print(f"[SUCCESS] Alpha Vantage 成功获取 {test_symbol} 数据，{len(df)} 行")
                    return df
            
            print(f"[WARN] Alpha Vantage {test_symbol} 无数据")
        
        print(f"[ERROR] Alpha Vantage 所有格式都无法获取 {symbol} 数据")
        return None
    
    def get_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取公司基本信息"""
        test_symbols = [symbol, f"{symbol}.SS", f"{symbol}.SZ"]
        
        for test_symbol in test_symbols:
            print(f"[INFO] Alpha Vantage 尝试获取 {test_symbol} 的公司信息...")
            
            params = {
                'function': 'OVERVIEW',
                'symbol': test_symbol
            }
            
            data = self._make_request(params)
            if data and 'Symbol' in data and data['Symbol']:
                print(f"[SUCCESS] Alpha Vantage 成功获取 {test_symbol} 公司信息")
                return {
                    'symbol': data.get('Symbol'),
                    'name': data.get('Name'),
                    'sector': data.get('Sector'),
                    'industry': data.get('Industry'),
                    'market_cap': self._safe_float(data.get('MarketCapitalization')),
                    'pe_ratio': self._safe_float(data.get('PERatio')),
                    'pb_ratio': self._safe_float(data.get('PriceToBookRatio')),
                    'dividend_yield': self._safe_float(data.get('DividendYield')),
                    'eps': self._safe_float(data.get('EPS')),
                    'revenue': self._safe_float(data.get('RevenueTTM')),
                    'gross_profit': self._safe_float(data.get('GrossProfitTTM')),
                    'source': 'alpha_vantage'
                }
            
            print(f"[WARN] Alpha Vantage {test_symbol} 无公司信息")
        
        print(f"[ERROR] Alpha Vantage 无法获取 {symbol} 公司信息")
        return None
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == 'None' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def test_api_key(self) -> bool:
        """测试API Key是否有效"""
        print("[INFO] 测试Alpha Vantage API Key...")
        
        params = {
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': 'AAPL',
            'interval': '1min',
            'outputsize': 'compact'
        }
        
        data = self._make_request(params)
        if data and 'Time Series (1min)' in data:
            print("[SUCCESS] Alpha Vantage API Key 有效")
            return True
        else:
            print("[ERROR] Alpha Vantage API Key 无效或已达到请求限制")
            return False
    
    def test_a_share_support(self, test_codes: list = None) -> Dict[str, bool]:
        """测试A股支持情况"""
        if test_codes is None:
            test_codes = ['000001', '600000', '002001']  # 测试不同板块的股票
        
        results = {}
        print("[INFO] 测试Alpha Vantage A股数据支持...")
        
        for code in test_codes:
            print(f"\n测试股票代码: {code}")
            
            # 测试K线数据
            kline_data = self.get_daily_kline(code)
            kline_success = kline_data is not None and len(kline_data) > 0
            
            # 测试公司信息
            company_info = self.get_company_overview(code)
            company_success = company_info is not None
            
            results[code] = {
                'kline_data': kline_success,
                'company_info': company_success,
                'overall_success': kline_success or company_success
            }
            
            print(f"结果: K线数据={kline_success}, 公司信息={company_success}")
        
        return results

def test_alpha_vantage_integration():
    """测试Alpha Vantage集成"""
    api_key = "52N6YLT15MUAA46B"
    av_api = AlphaVantageAPI(api_key)
    
    # 测试API Key
    if not av_api.test_api_key():
        print("API Key测试失败，停止测试")
        return False
    
    # 测试A股支持
    results = av_api.test_a_share_support(['000001', '600000', '002001'])
    
    print("\n=== Alpha Vantage A股支持测试结果 ===")
    success_count = 0
    for code, result in results.items():
        status = "✅" if result['overall_success'] else "❌"
        print(f"{status} {code}: 总体={'支持' if result['overall_success'] else '不支持'}")
        if result['overall_success']:
            success_count += 1
    
    support_rate = (success_count / len(results)) * 100
    print(f"\nA股支持率: {support_rate:.1f}% ({success_count}/{len(results)})")
    
    return support_rate > 0

if __name__ == "__main__":
    test_alpha_vantage_integration()
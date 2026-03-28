"""
Polygon.io API集成模块
支持美股数据获取，可集成到现有数据收集系统
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests


class PolygonAPI:
    """Polygon.io API集成类，支持美股和部分国际股票数据"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化Polygon.io API
        
        Args:
            api_key: Polygon.io API密钥
                   免费版: 每分钟5次请求
                   付费版: 更高频率限制
        """
        # 设置API密钥，优先使用传入的密钥
        self.api_key = api_key or "yb5xBES96DRleQzip9kKgCWbkc3E6N58" or os.environ.get('POLYGON_API_KEY')
        self.base_url = "https://api.polygon.io"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TradingAgents/1.0',
            'Accept': 'application/json'
        })
        
        # 请求频率控制
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit_per_minute = 5  # 免费版限制
        
        # 检查API密钥状态
        self.is_available = bool(self.api_key and self.api_key != 'DEMO_KEY')
        if not self.is_available:
            print("[WARN] Polygon.io: 无有效API密钥，功能受限")
        else:
            print(f"[INFO] Polygon.io: API密钥已配置")
    
    def _check_rate_limit(self) -> bool:
        """检查请求频率限制"""
        if not self.is_available:
            return False
            
        current_time = time.time()
        
        # 重置每分钟计数
        if current_time - self.last_request_time > 60:
            self.request_count = 0
        
        # 检查是否超过限制
        if self.request_count >= self.rate_limit_per_minute:
            wait_time = 60 - (current_time - self.last_request_time)
            if wait_time > 0:
                print(f"[INFO] Polygon.io达到频率限制，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
                self.request_count = 0
        
        self.last_request_time = current_time
        self.request_count += 1
        return True
    
    def test_connection(self) -> bool:
        """测试API连接状态"""
        if not self.is_available:
            return False
        
        try:
            if not self._check_rate_limit():
                return False
                
            # 使用简单的API调用测试连接
            url = f"{self.base_url}/v3/reference/tickers"
            params = {
                'apikey': self.api_key,
                'limit': 1
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('status') == 'OK'
            elif response.status_code == 401:
                print("[ERROR] Polygon.io: API密钥无效")
                self.is_available = False
                return False
            else:
                print(f"[WARN] Polygon.io: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Polygon.io连接测试失败: {e}")
            return False
    
    def get_us_stock_kline(self, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        获取美股K线数据
        
        Args:
            symbol: 美股代码 (如 'AAPL', 'MSFT')
            days: 获取天数
        """
        if not self.is_available or not self._check_rate_limit():
            return None
        
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
            params = {
                'apikey': self.api_key,
                'adjusted': 'true',
                'sort': 'asc'
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # 兼容免费版API返回的DELAYED状态
                if data.get('status') in ['OK', 'DELAYED'] and 'results' in data:
                    results = data['results']
                    
                    # 转换为标准DataFrame格式
                    kline_data = []
                    for item in results:
                        kline_data.append({
                            'date': pd.to_datetime(item['t'], unit='ms').date(),
                            'open': float(item.get('o', 0)),
                            'high': float(item.get('h', 0)),
                            'low': float(item.get('l', 0)),
                            'close': float(item.get('c', 0)),
                            'volume': int(item.get('v', 0)),
                            'amount': float(item.get('o', 0)) * int(item.get('v', 0))
                        })
                    
                    if kline_data:
                        df = pd.DataFrame(kline_data)
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.sort_values('date').reset_index(drop=True)
                        
                        print(f"[SUCCESS] Polygon.io获取{symbol}K线: {len(df)}天")
                        return df
                
                print(f"[WARN] Polygon.io {symbol}: 无K线数据")
                return None
                
            else:
                print(f"[ERROR] Polygon.io {symbol}: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Polygon.io获取{symbol}K线失败: {e}")
            return None
    
    def get_company_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取公司基本信息"""
        if not self.is_available or not self._check_rate_limit():
            return None
        
        try:
            url = f"{self.base_url}/v3/reference/tickers/{symbol}"
            params = {'apikey': self.api_key}
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'OK':
                    results = data.get('results', {})
                    
                    return {
                        'code': symbol,
                        'name': results.get('name'),
                        'description': results.get('description'),
                        'market': results.get('market'),
                        'locale': results.get('locale'),
                        'type': results.get('type'),
                        'currency': results.get('currency_name'),
                        'homepage': results.get('homepage_url'),
                        'employees': results.get('total_employees'),
                        'market_cap': results.get('market_cap'),
                        'source': 'polygon'
                    }
                    
            return None
            
        except Exception as e:
            print(f"[ERROR] Polygon.io获取{symbol}公司信息失败: {e}")
            return None
    
    def batch_get_us_klines(self, symbols: List[str], days: int = 30) -> Dict[str, pd.DataFrame]:
        """批量获取美股K线数据"""
        results = {}
        
        if not self.is_available:
            print("[WARN] Polygon.io不可用，跳过批量K线获取")
            return results
        
        print(f"[INFO] Polygon.io批量获取美股K线: {len(symbols)}只股票")
        
        for i, symbol in enumerate(symbols):
            print(f"[{i+1}/{len(symbols)}] 处理美股 {symbol}...")
            
            df = self.get_us_stock_kline(symbol, days)
            if df is not None and not df.empty:
                results[symbol] = df
            
            # 避免频率限制
            time.sleep(1)
        
        success_rate = len(results) / len(symbols) * 100 if symbols else 0
        print(f"[SUMMARY] Polygon.io批量获取完成: {len(results)}/{len(symbols)} ({success_rate:.1f}%)")
        
        return results

    def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取市场新闻 (Polygon.io 强项)
        
        Args:
            limit: 获取新闻条数
        """
        if not self.is_available or not self._check_rate_limit():
            return []
            
        try:
            url = f"{self.base_url}/v2/reference/news"
            params = {
                'apikey': self.api_key,
                'limit': limit,
                'order': 'desc',
                'sort': 'published_utc'
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK':
                    return data.get('results', [])
            
            return []
        except Exception as e:
            print(f"[ERROR] Polygon.io获取新闻失败: {e}")
            return []

def demonstrate_polygon_integration():
    """演示Polygon.io集成效果"""
    print("=== Polygon.io API集成演示 ===")
    print()
    
    print("📋 Polygon.io API特性:")
    print("• 主要支持: 美股、加密货币、外汇")
    print("• 数据质量: 高质量实时和历史数据")
    print("• 免费版本: 每分钟5次请求")
    print("• 付费版本: 更高频率限制和更多功能")
    print()
    
    # 初始化API
    api = PolygonAPI()
    
    print(f"🔗 API状态: {'可用' if api.is_available else '不可用 (需要API密钥)'}")
    print()
    
    if api.is_available:
        # 测试连接
        print("🔍 测试连接...")
        if api.test_connection():
            print("[OK] Polygon.io连接成功")
            
            # 演示功能
            print("\n[CHART] 功能演示:")
            
            # 美股测试
            test_symbols = ['AAPL', 'MSFT']
            print(f"1. 美股K线数据获取: {test_symbols}")
            
            kline_data = api.batch_get_us_klines(test_symbols[:1], days=5)
            for symbol, df in kline_data.items():
                print(f"   {symbol}: {len(df)}天数据")
            
            # 公司信息
            print(f"\n2. 公司基本信息获取:")
            company_info = api.get_company_info('AAPL')
            if company_info:
                print(f"   公司: {company_info.get('name')}")
                print(f"   市场: {company_info.get('market')}")
        else:
            print("[FAIL] 连接失败")
    
    print("\n[TARGET] 集成到现有系统的建议:")
    print("1. 作为美股数据的补充数据源")
    print("2. 国际化扩展时的主要美股API")
    print("3. 可与现有A股API形成互补")
    print()
    
    print("⚙️ 集成方案:")
    print("• 在 comprehensive_data_collector.py 中添加 PolygonAPI")
    print("• 为美股代码添加专门的处理逻辑")
    print("• 配置API密钥环境变量 POLYGON_API_KEY")
    print()
    
    print("🔑 获取API密钥:")
    print("1. 访问 https://polygon.io/")
    print("2. 注册免费账户")
    print("3. 获取API密钥")
    print("4. 设置环境变量: POLYGON_API_KEY=your_api_key")

if __name__ == "__main__":
    demonstrate_polygon_integration()
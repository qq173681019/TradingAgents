#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试价格获取
"""

import urllib.request

def test_simple_price_fetch():
    """简单测试价格获取"""
    print("=== 简单测试新浪财经API ===")
    
    test_stocks = ["600519", "159915"]  # 茅台和创业板ETF
    
    for ticker in test_stocks:
        try:
            print(f"\n测试 {ticker}:")
            
            if ticker.startswith(('60', '68')):
                code = f"sh{ticker}"
            else:
                code = f"sz{ticker}"
            
            url = f"http://hq.sinajs.cn/list={code}"
            print(f"请求URL: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://finance.sina.com.cn'
            }
            
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req, timeout=5)
            data = response.read().decode('gbk', errors='ignore')
            
            print(f"API响应: {data[:100]}...")
            
            if 'var hq_str_' in data:
                parts = data.split('="')[1].split('",')[0].split(',')
                if len(parts) > 3 and parts[3]:
                    price = float(parts[3])
                    print(f"✅ 获取到价格: {price}")
                else:
                    print(f"❌ 价格字段为空")
            else:
                print(f"❌ 未找到有效数据")
                
        except Exception as e:
            print(f"❌ 获取失败: {e}")

if __name__ == "__main__":
    test_simple_price_fetch()
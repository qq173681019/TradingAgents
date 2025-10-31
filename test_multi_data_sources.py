#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试多数据源股票价格获取
"""

import urllib.request
import time

def test_sina_api(ticker):
    """测试新浪财经API"""
    try:
        if ticker.startswith(('60', '68')):
            code = f"sh{ticker}"
        else:
            code = f"sz{ticker}"
        
        url = f"http://hq.sinajs.cn/list={code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'http://finance.sina.com.cn'
        }
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk', errors='ignore')
        
        if 'var hq_str_' in data:
            parts = data.split('="')[1].split('",')[0].split(',')
            if len(parts) > 3 and parts[3]:
                price = float(parts[3])
                return price, "新浪财经"
    except Exception as e:
        print(f"新浪财经失败: {e}")
    return None, "新浪财经"

def test_tencent_api(ticker):
    """测试腾讯财经API"""
    try:
        if ticker.startswith(('60', '68')):
            code = f"sh{ticker}"
        else:
            code = f"sz{ticker}"
        
        url = f"http://qt.gtimg.cn/q={code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://finance.qq.com'
        }
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk', errors='ignore')
        
        if f'v_{code}=' in data:
            parts = data.split('="')[1].split('"')[0].split('~')
            if len(parts) > 3 and parts[3]:
                price = float(parts[3])
                return price, "腾讯财经"
    except Exception as e:
        print(f"腾讯财经失败: {e}")
    return None, "腾讯财经"

def test_netease_api(ticker):
    """测试网易财经API"""
    try:
        market = '0' if ticker.startswith(('60', '68')) else '1'
        url = f"http://api.money.126.net/data/feed/{market}{ticker}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://money.163.com'
        }
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('utf-8', errors='ignore')
        
        import json
        if data.startswith('_ntes_quote_callback(') and data.endswith(');'):
            json_str = data[21:-2]
            stock_data = json.loads(json_str)
            
            code_key = f"{market}{ticker}"
            if code_key in stock_data and 'price' in stock_data[code_key]:
                price = float(stock_data[code_key]['price'])
                return price, "网易财经"
    except Exception as e:
        print(f"网易财经失败: {e}")
    return None, "网易财经"

def test_all_apis():
    """测试所有API"""
    test_stocks = ["600519", "000001", "300750", "159915"]
    
    print("=== 多数据源股票价格获取测试 ===\n")
    
    for ticker in test_stocks:
        print(f"--- 测试股票: {ticker} ---")
        
        apis = [
            ("新浪财经", test_sina_api),
            ("腾讯财经", test_tencent_api),
            ("网易财经", test_netease_api)
        ]
        
        success_count = 0
        prices = []
        
        for api_name, api_func in apis:
            price, source = api_func(ticker)
            if price:
                print(f"✅ {api_name}: ¥{price:.2f}")
                prices.append(price)
                success_count += 1
            else:
                print(f"❌ {api_name}: 获取失败")
            
            time.sleep(0.3)  # 避免请求过快
        
        if prices:
            avg_price = sum(prices) / len(prices)
            print(f"📊 成功率: {success_count}/3, 平均价格: ¥{avg_price:.2f}")
            
            # 检查价格一致性
            if len(set([round(p, 1) for p in prices])) == 1:
                print("✅ 价格一致性良好")
            else:
                print("⚠️ 价格存在差异，可能是时间延迟")
        else:
            print("❌ 所有数据源都失败")
        
        print()

if __name__ == "__main__":
    test_all_apis()
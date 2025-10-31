#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试实时股票价格获取功能
"""

import urllib.request
import sys

def test_real_stock_price(ticker):
    """测试获取真实股票价格"""
    try:
        print(f"正在获取 {ticker} 的实时价格...")
        
        # 新浪财经API获取实时价格
        if ticker.startswith(('60', '68')):
            code = f"sh{ticker}"
        else:
            code = f"sz{ticker}"
        
        url = f"http://hq.sinajs.cn/list={code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk', errors='ignore')
        
        print(f"API返回数据: {data[:200]}...")
        
        # 解析价格数据
        if 'var hq_str_' in data:
            parts = data.split('="')[1].split('",')[0].split(',')
            if len(parts) > 3:
                print(f"解析到的数据字段: {len(parts)} 个")
                print(f"股票名称: {parts[0] if len(parts) > 0 else 'N/A'}")
                print(f"今日开盘价: {parts[1] if len(parts) > 1 else 'N/A'}")
                print(f"昨日收盘价: {parts[2] if len(parts) > 2 else 'N/A'}")
                print(f"当前价格: {parts[3] if len(parts) > 3 else 'N/A'}")
                print(f"今日最高价: {parts[4] if len(parts) > 4 else 'N/A'}")
                print(f"今日最低价: {parts[5] if len(parts) > 5 else 'N/A'}")
                
                if parts[3]:
                    price = float(parts[3])
                    print(f"✅ 成功获取 {ticker} 实时价格: {price} 元")
                    return price
                else:
                    print(f"❌ 价格字段为空")
            else:
                print(f"❌ 数据格式不正确，字段数量: {len(parts)}")
        else:
            print(f"❌ 未找到有效数据")
            
        return None
        
    except Exception as e:
        print(f"❌ 获取股票价格失败: {e}")
        return None

def main():
    """测试主函数"""
    test_stocks = [
        "600519",  # 贵州茅台
        "000001",  # 平安银行
        "300750",  # 宁德时代
        "688981",  # 中芯国际
        "002594",  # 比亚迪
    ]
    
    print("=== 股票实时价格获取测试 ===\n")
    
    for ticker in test_stocks:
        print(f"--- 测试股票: {ticker} ---")
        price = test_real_stock_price(ticker)
        print()
    
    print("=== 测试完成 ===")

if __name__ == "__main__":
    main()
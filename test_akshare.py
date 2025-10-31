#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试akshare获取实时股票数据
"""

try:
    import akshare as ak
    print("✅ akshare导入成功")
except ImportError as e:
    print(f"❌ akshare导入失败: {e}")
    exit(1)

def test_akshare_data():
    """测试akshare获取股票数据"""
    test_stocks = ["000001", "600519", "300750"]
    
    print("=== 测试akshare获取股票数据 ===\n")
    
    for stock in test_stocks:
        try:
            print(f"获取 {stock} 的实时数据...")
            
            # 获取实时行情数据
            df = ak.stock_zh_a_spot_em()
            
            # 查找指定股票
            stock_data = df[df['代码'] == stock]
            
            if not stock_data.empty:
                name = stock_data.iloc[0]['名称']
                price = stock_data.iloc[0]['最新价']
                print(f"✅ {stock} {name}: {price} 元")
            else:
                print(f"❌ 未找到股票 {stock}")
                
        except Exception as e:
            print(f"❌ 获取 {stock} 数据失败: {e}")
        
        print()

if __name__ == "__main__":
    test_akshare_data()
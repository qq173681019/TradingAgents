#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股分析系统 - 数据诊断脚本
检查数据文件完整性和格式
"""

import json
import os

def check_comprehensive_data():
    """检查综合数据文件"""
    file_path = "comprehensive_stock_data.json"
    
    print("🔍 检查comprehensive_stock_data.json文件...")
    print("=" * 50)
    
    if not os.path.exists(file_path):
        print("❌ 文件不存在")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 文件读取成功")
        print(f"📄 文件大小: {os.path.getsize(file_path)} 字节")
        
        if 'data' in data:
            stock_data = data['data']
            print(f"📊 股票数量: {len(stock_data)}")
            
            # 检查几个股票的数据结构
            sample_count = 0
            for code, stock_info in stock_data.items():
                if sample_count < 3:
                    print(f"\n📋 示例股票 {code}:")
                    print(f"  名称: {stock_info.get('name', '未知')}")
                    print(f"  是否有短期数据: {'short_term' in stock_info}")
                    print(f"  是否有中期数据: {'medium_term' in stock_info}")
                    print(f"  是否有长期数据: {'long_term' in stock_info}")
                    
                    if 'short_term' in stock_info:
                        print(f"  短期评分: {stock_info['short_term'].get('score', '无')}")
                    
                    sample_count += 1
            
            # 检查数据完整性
            complete_count = 0
            for code, stock_info in stock_data.items():
                if all(period in stock_info for period in ['short_term', 'medium_term', 'long_term']):
                    complete_count += 1
            
            print(f"\n📈 完整数据股票: {complete_count}/{len(stock_data)}")
            
            if complete_count == len(stock_data):
                print("✅ 所有股票数据完整")
                return True
            else:
                print("⚠️ 部分股票数据不完整")
                return False
        else:
            print("❌ 数据格式错误：缺少'data'字段")
            return False
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False

def check_batch_scores():
    """检查批量评分文件"""
    file_path = "batch_stock_scores.json"
    
    print("\n🔍 检查batch_stock_scores.json文件...")
    print("=" * 50)
    
    if not os.path.exists(file_path):
        print("❌ 文件不存在")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 文件读取成功")
        print(f"📄 文件大小: {os.path.getsize(file_path)} 字节")
        print(f"📊 数据条目: {len(data)}")
        
        return True
            
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False

def main():
    """主函数"""
    print("🔧 A股分析系统 - 数据诊断")
    print("=" * 60)
    
    # 检查文件
    comprehensive_ok = check_comprehensive_data()
    batch_ok = check_batch_scores()
    
    print("\n📋 诊断总结:")
    print("=" * 30)
    print(f"综合数据文件: {'✅ 正常' if comprehensive_ok else '❌ 异常'}")
    print(f"批量评分文件: {'✅ 正常' if batch_ok else '❌ 异常'}")
    
    if comprehensive_ok and batch_ok:
        print("\n🎉 所有数据文件正常！")
        print("💡 如果仍有问题，请尝试重新运行批量分析")
    else:
        print("\n⚠️  发现数据问题！")
        print("💡 建议重新运行批量分析来修复数据")

if __name__ == "__main__":
    main()
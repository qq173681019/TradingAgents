#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
退市股票检测和清理工具
为主程序提供便捷的退市检测功能
"""

from typing import List, Dict, Any
import json

def enable_delisting_protection(data_collector):
    """
    为数据收集器启用退市保护功能
    
    Args:
        data_collector: 综合数据收集器实例
    """
    print("[INFO] ===== Enable Delisting Protection =====")
    
    # 检查是否有股票状态检测器
    if hasattr(data_collector, 'status_checker') and data_collector.status_checker:
        print("[INFO] OK Stock Status Checker Available")
        print("[INFO] OK Auto Delisting Detection: Enabled")
        print("[INFO] OK Data Cleaning Function: Enabled")
        print("[INFO] OK Real-time Status Check: Enabled")
        
        # 设置标志
        data_collector.delisting_protection_enabled = True
        
        print("[INFO] ------------------------------------")
        print("[INFO] Protection Features:")
        print("[INFO] 1. Auto detect delisting before data collection")
        print("[INFO] 2. Skip delisted/invalid stocks automatically")
        print("[INFO] 3. Clean existing data of delisted stocks")
        print("[INFO] 4. Support batch and single stock detection")
        print("[INFO] ====================================")
        
        return True
    else:
        print("[WARN] ERROR Stock Status Checker Not Available")
        print("[WARN] Delisting protection cannot be enabled")
        return False

def quick_check_delisted_stocks(codes: List[str]) -> Dict[str, List[str]]:
    """
    快速检查股票列表中的退市情况
    
    Args:
        codes: 股票代码列表
        
    Returns:
        分类后的股票字典
    """
    try:
        from stock_status_checker import StockStatusChecker
        
        print(f"[INFO] 快速检查 {len(codes)} 只股票的退市状态...")
        
        checker = StockStatusChecker()
        results = checker.batch_check_stocks(codes)
        
        # 分类结果
        categorized = {
            'active': [],
            'delisted': [],
            'invalid': [],
            'suspended': [],
            'unknown': []
        }
        
        for code, info in results.items():
            status = info.get('status', 'unknown')
            if status in categorized:
                categorized[status].append(code)
            else:
                categorized['unknown'].append(code)
        
        # 打印摘要
        print(f"[RESULT] 检查结果摘要:")
        print(f"  正常交易: {len(categorized['active'])} 只")
        print(f"  已退市: {len(categorized['delisted'])} 只")
        print(f"  无效代码: {len(categorized['invalid'])} 只")
        print(f"  停牌特处: {len(categorized['suspended'])} 只")
        print(f"  状态未知: {len(categorized['unknown'])} 只")
        
        return categorized
        
    except ImportError:
        print("[ERROR] 股票状态检测器模块未找到")
        return {'active': codes, 'delisted': [], 'invalid': [], 'suspended': [], 'unknown': []}
    except Exception as e:
        print(f"[ERROR] 快速检查异常: {e}")
        return {'active': codes, 'delisted': [], 'invalid': [], 'suspended': [], 'unknown': []}

def save_problematic_stocks_report(codes: List[str], filename: str = "problematic_stocks_report.json"):
    """
    生成有问题股票的详细报告并保存
    
    Args:
        codes: 股票代码列表
        filename: 保存的文件名
    """
    try:
        from stock_status_checker import StockStatusChecker
        import os
        
        print(f"[INFO] 生成有问题股票报告...")
        
        checker = StockStatusChecker()
        results = checker.batch_check_stocks(codes)
        
        # 筛选有问题的股票
        problematic_stocks = {}
        
        for code, info in results.items():
            if info['status'] in ['delisted', 'invalid', 'suspended']:
                problematic_stocks[code] = {
                    'name': info.get('name', ''),
                    'status': info['status'],
                    'details': info.get('details', ''),
                    'delisting_date': info.get('delisting_date', ''),
                    'listing_date': info.get('listing_date', ''),
                    'market': info.get('market', '')
                }
        
        # 生成报告
        report = {
            'generated_time': str(datetime.now()),
            'total_checked': len(codes),
            'problematic_count': len(problematic_stocks),
            'summary': {
                'delisted': len([s for s in problematic_stocks.values() if s['status'] == 'delisted']),
                'invalid': len([s for s in problematic_stocks.values() if s['status'] == 'invalid']),
                'suspended': len([s for s in problematic_stocks.values() if s['status'] == 'suspended'])
            },
            'problematic_stocks': problematic_stocks
        }
        
        # 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"[SUCCESS] 报告已保存至: {filename}")
        print(f"[INFO] 发现有问题股票 {len(problematic_stocks)} 只:")
        print(f"  - 已退市: {report['summary']['delisted']} 只")
        print(f"  - 无效代码: {report['summary']['invalid']} 只") 
        print(f"  - 停牌特处: {report['summary']['suspended']} 只")
        
        return problematic_stocks
        
    except Exception as e:
        print(f"[ERROR] 生成报告异常: {e}")
        return {}

def clean_data_file(data_file_path: str, backup: bool = True):
    """
    清理数据文件中的退市股票
    
    Args:
        data_file_path: 数据文件路径
        backup: 是否备份原文件
    """
    try:
        import os
        import shutil
        from datetime import datetime
        
        print(f"[INFO] 开始清理数据文件: {data_file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(data_file_path):
            print(f"[ERROR] 文件不存在: {data_file_path}")
            return False
        
        # 备份原文件
        if backup:
            backup_path = f"{data_file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(data_file_path, backup_path)
            print(f"[INFO] 原文件已备份至: {backup_path}")
        
        # 读取数据
        with open(data_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            print(f"[ERROR] 数据文件格式不正确，需要是字典格式")
            return False
        
        # 获取股票代码列表
        codes = list(data.keys())
        print(f"[INFO] 文件中包含 {len(codes)} 只股票数据")
        
        # 检查股票状态
        categorized = quick_check_delisted_stocks(codes)
        
        # 需要移除的股票
        codes_to_remove = categorized['delisted'] + categorized['invalid']
        
        if codes_to_remove:
            print(f"[INFO] 发现 {len(codes_to_remove)} 只退市/无效股票，正在清理...")
            
            # 移除退市股票
            cleaned_data = {}
            removed_count = 0
            
            for code, stock_data in data.items():
                if code not in codes_to_remove:
                    cleaned_data[code] = stock_data
                else:
                    removed_count += 1
                    print(f"[CLEAN] 移除退市股票: {code}")
            
            # 保存清理后的数据
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
            
            print(f"[SUCCESS] 数据清理完成:")
            print(f"  - 移除股票: {removed_count} 只")
            print(f"  - 保留股票: {len(cleaned_data)} 只")
            print(f"  - 清理后文件: {data_file_path}")
            
            return True
        else:
            print(f"[INFO] 数据文件中无需清理的股票")
            return True
            
    except Exception as e:
        print(f"[ERROR] 清理数据文件异常: {e}")
        return False

if __name__ == "__main__":
    # 演示功能
    from datetime import datetime
    
    print("=== 退市股票检测和清理工具演示 ===")
    
    # 示例股票列表
    test_codes = ['600384', '600385', '600387', '600389', '000001', '000002']
    
    print(f"\n1. 快速检查股票状态:")
    result = quick_check_delisted_stocks(test_codes)
    
    print(f"\n2. 生成问题股票报告:")
    problematic = save_problematic_stocks_report(test_codes, "test_report.json")
    
    print(f"\n=== 演示完成 ===")
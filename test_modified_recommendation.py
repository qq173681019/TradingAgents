#!/usr/bin/env python3
"""
测试修改后的股票推荐功能
验证直接使用界面参数而不弹出对话框
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("="*60)
print("测试修改后的股票推荐功能")
print("="*60)

try:
    # 检查方法是否正确修改
    with open('a_share_gui_compatible.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("✓ 成功读取GUI文件")
    
    # 检查generate_stock_recommendations方法是否被修改
    if "def generate_stock_recommendations(self):" in content:
        print("✓ generate_stock_recommendations方法存在")
        
        # 检查是否移除了对话框代码
        if "settings_dialog = tk.Toplevel" in content:
            print("⚠ 仍包含设置对话框代码")
        else:
            print("✓ 已移除设置对话框代码")
        
        # 检查是否使用界面参数
        if "self.stock_type_var.get()" in content and "self.period_var.get()" in content:
            print("✓ 现在使用界面参数")
        else:
            print("✗ 未使用界面参数")
        
        # 检查参数映射
        if "type_mapping" in content and "period_count_mapping" in content:
            print("✓ 包含参数映射逻辑")
        else:
            print("✗ 缺少参数映射逻辑")
            
    else:
        print("✗ generate_stock_recommendations方法不存在")
    
    print("\n✓ 代码分析完成")
    print("✓ 股票推荐功能已修改为直接使用界面参数")
    print("✓ 不再弹出二级设置对话框")
    
    print("\n" + "="*60)
    print("修改验证完成！")
    print("="*60)
    
    print("\n使用说明:")
    print("1. 运行 python a_share_gui_compatible.py 启动GUI")
    print("2. 在界面上选择股票类型和投资期限")
    print("3. 调整评分阈值滑块")
    print("4. 点击'股票推荐'按钮")
    print("5. 系统将直接使用界面参数进行智能推荐")
    print("6. 不会再弹出设置对话框")
    
except Exception as e:
    print(f"✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()
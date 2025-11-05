#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股智能分析系统 - 应急启动器
解决tkinter缺失问题，直接启动命令行版本
"""

import os
import sys
import subprocess

def main():
    """主函数"""
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("🚀 A股智能分析系统 - 应急启动器")
    print("=" * 50)
    print()
    
    # 检查tkinter
    try:
        import tkinter
        print("✅ tkinter可用，但推荐使用命令行版本")
        print("   (避免GUI显示问题)")
    except ImportError:
        print("❌ tkinter不可用，自动使用命令行版本")
    
    print()
    print("🔧 问题诊断:")
    print("   GUI版本报错: ModuleNotFoundError: No module named 'tkinter'")
    print()
    print("✅ 解决方案:")
    print("   使用功能完整的命令行版本")
    print()
    
    input("按回车键启动命令行版本...")
    
    try:
        print("💻 启动命令行版本...")
        subprocess.run([sys.executable, "cli_launcher.py"])
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        input("按回车键退出...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 启动器异常: {e}")
        input("按回车键退出...")
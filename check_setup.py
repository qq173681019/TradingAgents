#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingAgents - 配置检查和验证脚本
检查所有必要的配置是否正确设置
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_environment():
    """检查Python环境和依赖"""
    print("🐍 检查Python环境...")
    
    # 检查Python版本
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"   Python版本: {python_version}")
    
    if sys.version_info >= (3, 8):
        print("   ✅ Python版本满足要求 (>=3.8)")
    else:
        print("   ❌ Python版本过低，请升级到3.8+")
        return False
    
    # 检查关键依赖
    required_packages = [
        'langchain', 'langchain_openai', 'langgraph', 
        'openai', 'yfinance', 'requests', 'pandas'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - 未安装")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ 缺少依赖包: {', '.join(missing_packages)}")
        print("🔧 请运行: pip install -r requirements.txt")
        return False
    
    return True

def check_config_files():
    """检查配置文件"""
    print("\n📁 检查配置文件...")
    
    # 检查.env文件
    env_file = Path(".env")
    if env_file.exists():
        print("   ✅ .env 文件存在")
        
        load_dotenv()
        
        # 检查Alpha Vantage API密钥
        av_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if av_key and av_key != "your_alpha_vantage_key_here":
            print(f"   ✅ Alpha Vantage API密钥已设置")
        else:
            print("   ⚠️ Alpha Vantage API密钥未设置")
        
        # 检查DeepSeek API密钥
        ds_key = os.getenv("DEEPSEEK_API_KEY")
        if ds_key and ds_key != "your_deepseek_api_key_here":
            print(f"   ✅ DeepSeek API密钥已设置")
        else:
            print("   ❌ DeepSeek API密钥未设置")
            print("      请访问 https://platform.deepseek.com/ 获取API密钥")
            return False
            
    else:
        print("   ❌ .env 文件不存在")
        print("      请复制 .env.example 到 .env 并填写API密钥")
        return False
    
    # 检查核心配置文件
    config_files = [
        "tradingagents/default_config.py",
        "tradingagents/graph/trading_graph.py",
        "tradingagents/dataflows/openai.py"
    ]
    
    for file_path in config_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - 文件缺失")
            return False
    
    return True

def check_deepseek_config():
    """检查DeepSeek配置"""
    print("\n🤖 检查DeepSeek配置...")
    
    try:
        # 检查default_config.py中的DeepSeek配置
        with open("tradingagents/default_config.py", "r", encoding="utf-8") as f:
            config_content = f.read()
        
        if '"llm_provider": "deepseek"' in config_content:
            print("   ✅ LLM提供商设置为deepseek")
        else:
            print("   ❌ LLM提供商未设置为deepseek")
            return False
        
        if '"deep_think_llm": "deepseek-chat"' in config_content:
            print("   ✅ 深度思考模型设置为deepseek-chat")
        else:
            print("   ❌ 深度思考模型配置错误")
            return False
        
        if 'https://api.deepseek.com/v1' in config_content:
            print("   ✅ API端点设置正确")
        else:
            print("   ❌ API端点配置错误")
            return False
            
    except Exception as e:
        print(f"   ❌ 配置文件检查失败: {e}")
        return False
    
    return True

def run_basic_test():
    """运行基本功能测试"""
    print("\n🧪 运行基本功能测试...")
    
    try:
        # 测试配置导入
        from tradingagents.default_config import DEFAULT_CONFIG
        print("   ✅ 配置导入成功")
        
        # 检查配置内容
        if DEFAULT_CONFIG["llm_provider"] == "deepseek":
            print("   ✅ DeepSeek配置正确")
        else:
            print(f"   ❌ LLM提供商配置错误: {DEFAULT_CONFIG['llm_provider']}")
            return False
        
        # 测试TradingAgentsGraph导入
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        print("   ✅ TradingAgentsGraph导入成功")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 基本功能测试失败: {e}")
        return False

def print_summary():
    """打印总结和下一步操作"""
    print("\n" + "="*60)
    print("📋 配置检查完成")
    print("="*60)
    
    print("\n🚀 如果所有检查都通过，你可以：")
    print("1. 运行完整分析:")
    print("   python main_deepseek.py")
    print("\n2. 使用CLI界面:")
    print("   python -m cli.main")
    print("\n3. 测试DeepSeek API:")
    print("   python test_deepseek_api.py")
    
    print("\n📖 详细配置说明请查看:")
    print("   DEEPSEEK_SETUP.md")
    
    print("\n💰 成本预估:")
    print("   - 单次分析: ¥0.05-0.20")
    print("   - 日常使用: ¥10-50/月")
    
    print("\n🔧 如果遇到问题:")
    print("   1. 检查API密钥是否正确设置")
    print("   2. 确认DeepSeek账户有余额")
    print("   3. 查看错误日志获取详细信息")

def main():
    """主检查流程"""
    print("🔍 TradingAgents - 配置检查工具")
    print("="*60)
    
    all_checks_passed = True
    
    # 运行各项检查
    checks = [
        ("环境检查", check_environment),
        ("配置文件检查", check_config_files), 
        ("DeepSeek配置检查", check_deepseek_config),
        ("基本功能测试", run_basic_test)
    ]
    
    for check_name, check_func in checks:
        if not check_func():
            all_checks_passed = False
            break
    
    print_summary()
    
    if all_checks_passed:
        print("\n🎉 所有检查通过！系统已准备就绪！")
        return 0
    else:
        print("\n❌ 检查未通过，请修复上述问题后重试")
        return 1

if __name__ == "__main__":
    exit(main())
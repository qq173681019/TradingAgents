#!/usr/bin/env python3
"""
快速配置 Groq 作为 OpenRouter 的替代方案
"""
import os

def setup_groq_config():
    """设置 Groq 配置"""
    print("=== 配置 Groq 作为免费替代方案 ===\n")
    
    # 读取当前 main.py
    try:
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 创建 Groq 配置版本
        groq_content = content.replace(
            'config["llm_provider"] = "openrouter"',
            'config["llm_provider"] = "openai"'
        ).replace(
            'config["backend_url"] = "https://openrouter.ai/api/v1"',
            'config["backend_url"] = "https://api.groq.com/openai/v1"'
        ).replace(
            'config["deep_think_llm"] = "deepseek/deepseek-chat-v3.1:free"',
            'config["deep_think_llm"] = "llama3-8b-8192"'
        ).replace(
            'config["quick_think_llm"] = "deepseek/deepseek-chat-v3.1:free"',
            'config["quick_think_llm"] = "llama3-8b-8192"'
        )
        
        # 保存备份
        with open("main_groq.py", "w", encoding="utf-8") as f:
            f.write(groq_content)
        
        print("✅ 已创建 main_groq.py 配置文件")
        print("使用方法:")
        print("1. 访问 https://console.groq.com/keys 获取免费 API 密钥")
        print("2. 更新 .env 文件中的 OPENAI_API_KEY 为 Groq 密钥")
        print("3. 运行: python main_groq.py")
        
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    setup_groq_config()
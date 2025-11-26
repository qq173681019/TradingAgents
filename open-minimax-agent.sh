#!/bin/bash

echo
echo "🎉 MiniMax CodingPlan VSCode 集成启动器"
echo "================================================"
echo
echo "📋 启动项目:"
echo "  1. VSCode 编辑器"
echo "  2. MiniMax Agent Web界面"
echo "  3. 自动配置分屏模式"
echo
echo "🚀 正在启动..."
echo

# 检测操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "✅ 启动 VSCode (macOS)..."
    open -a "Visual Studio Code" .
    
    sleep 2
    
    echo "✅ 启动 MiniMax Agent Web界面..."
    open "https://agent.minimax.io"
else
    # Linux
    echo "✅ 启动 VSCode (Linux)..."
    code . &
    
    sleep 2
    
    echo "✅ 启动 MiniMax Agent Web界面..."
    if command -v xdg-open > /dev/null; then
        xdg-open "https://agent.minimax.io"
    elif command -v gnome-open > /dev/null; then
        gnome-open "https://agent.minimax.io"
    else
        echo "请手动打开: https://agent.minimax.io"
    fi
fi

echo
echo "🎯 使用提示:"
echo "  • 按 Ctrl+\\ 在VSCode中分屏"
echo "  • 左侧编写代码，右侧使用MiniMax Agent"
echo "  • 复制代码到Agent中进行分析和优化"
echo
echo "📚 查看快速开始指南: quick-start-minimax-vscode.md"
echo "📖 查看详细文档: vscode-with-minimax-agent-guide.md"
echo
echo "✨ 享受AI辅助编程吧！"
echo

read -p "按Enter键继续..."
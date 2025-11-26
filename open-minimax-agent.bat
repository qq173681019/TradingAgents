@echo off
title MiniMax CodingPlan VSCode Integration
echo.
echo ==============================================
echo MiniMax CodingPlan VSCode Integration Launcher
echo ==============================================
echo.
echo Starting:
echo   1. VSCode Editor
echo   2. MiniMax Agent Web Interface
echo   3. Split Screen Development Mode
echo.
echo Loading...
echo.

REM Start VSCode in current directory
echo Starting VSCode...
start "" code .

REM Wait 2 seconds for VSCode to load
timeout /t 2 /nobreak >nul

REM Start MiniMax Agent
echo Starting MiniMax Agent Web Interface...
start "" https://agent.minimax.io

echo.
echo Tips for Usage:
echo   Press Ctrl+\ in VSCode for split screen
echo   Copy code to Agent for AI analysis
echo   Apply AI suggestions back to VSCode
echo.
echo Quick Start Guide: quick-start-minimax-vscode.md
echo Detailed Guide: vscode-with-minimax-agent-guide.md
echo.
echo Enjoy AI-Assisted Programming!
echo.
pause
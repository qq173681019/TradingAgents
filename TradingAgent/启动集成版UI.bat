@echo off
chcp 65001 > nul
echo ========================================
echo    TradingAgents 集成版现代化UI
echo    包含完整功能：K线更新、评分生成等
echo ========================================
echo.

cd /d "%~dp0"
C:\Users\ext.jgu\AppData\Local\Programs\Python\Python39\python.exe ui_integrated.py

pause

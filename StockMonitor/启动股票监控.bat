@echo off
chcp 65001 > nul
echo ====================================
echo   启动 StockMonitor 股票监控系统
echo ====================================
echo.

cd /d "%~dp0"
python stock_monitor.py

if errorlevel 1 (
    echo.
    echo [错误] 程序运行失败
    pause
) else (
    echo.
    echo [完成] 程序已退出
)

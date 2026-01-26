@echo off
REM 交易仪表盘快速启动脚本
REM 在浏览器中打开交易分析仪表盘

echo.
echo ╔════════════════════════════════════════════════╗
echo ║     TradingAgents - 交易分析仪表盘             ║
echo ╚════════════════════════════════════════════════╝
echo.

REM 获取脚本目录
set SCRIPT_DIR=%~dp0

REM 检查文件是否存在
if not exist "%SCRIPT_DIR%trading_dashboard.html" (
    echo ❌ 错误: 未找到 trading_dashboard.html
    echo 请确保在 TradingAgent 目录下运行此脚本
    pause
    exit /b 1
)

echo ✓ 正在启动仪表盘...
echo.

REM 启动后端服务 (可选)
echo 选项 1: 使用默认浏览器打开仪表盘 (推荐)
echo 选项 2: 启动本地Python服务器
echo.

set /p choice="请选择 (1/2, 默认1): "
if "%choice%"=="" set choice=1

if "%choice%"=="1" (
    echo 正在打开浏览器...
    start "" "%SCRIPT_DIR%trading_dashboard.html"
    echo ✓ 仪表盘已打开！
) else if "%choice%"=="2" (
    echo 正在启动Python服务器 (http://localhost:8000)...
    cd /d "%SCRIPT_DIR%"
    python -m http.server 8000
    echo.
    echo ✓ 服务器已启动！
    echo 在浏览器中访问: http://localhost:8000/trading_dashboard.html
) else (
    echo ❌ 无效选择
    exit /b 1
)

pause

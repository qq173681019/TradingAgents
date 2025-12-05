@echo off
chcp 65001 >nul
title A股分析系统（支持Choice）
color 0A
echo ========================================
echo    A股智能分析系统
echo    支持 Choice 金融终端数据源
echo ========================================
echo.

cd /d "%~dp0"

REM 清理调试器环境变量
set PYTHONPATH=
set VSCODE_PID=
set DEBUGPY_LAUNCHER_PORT=

echo [1/2] 检测Python环境...

REM 尝试多个Python路径
set PYTHON_FOUND=0

REM 1. 尝试标准安装路径
if exist "C:\Python313\python.exe" (
    echo ✅ 使用 C:\Python313\python.exe
    "C:\Python313\python.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

if exist "C:\Python312\python.exe" (
    echo ✅ 使用 C:\Python312\python.exe
    "C:\Python312\python.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

if exist "C:\Python311\python.exe" (
    echo ✅ 使用 C:\Python311\python.exe
    "C:\Python311\python.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

REM 2. 尝试Anaconda
if exist "C:\ProgramData\Anaconda3\python.exe" (
    echo ✅ 使用 Anaconda Python
    "C:\ProgramData\Anaconda3\python.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

if exist "C:\Users\%USERNAME%\Anaconda3\python.exe" (
    echo ✅ 使用 Anaconda Python
    "C:\Users\%USERNAME%\Anaconda3\python.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

REM 3. 尝试VS Code使用的Python（通常有tkinter）
if exist "C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe" (
    echo ✅ 使用 Python 3.13 (直接启动，不经过调试器)
    "C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe" a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

REM 4. 最后尝试系统PATH中的python
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  使用系统Python（可能缺少tkinter）
    python a_share_gui_compatible.py
    set PYTHON_FOUND=1
    goto :end_python_check
)

REM 如果都找不到，显示错误
echo.
echo ❌ 未找到合适的Python环境
echo.
echo 💡 解决方案：
echo    1. 安装Python 3.11-3.13 从 https://www.python.org/downloads/
echo       ⚠️  安装时勾选 "Add Python to PATH"
echo       ⚠️  安装时勾选 "tcl/tk and IDLE"
echo.
echo    2. 或使用Anaconda: https://www.anaconda.com/download
echo.
echo    3. 或使用VS Code的F5调试（Choice功能会被禁用）
echo.
pause
exit /b 1

:end_python_check

if errorlevel 1 (
    echo.
    echo ❌ 程序异常退出
    pause
) else (
    echo.
    echo ✅ 程序正常退出
)
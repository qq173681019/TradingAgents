@echo off
chcp 65001 >nul
echo 启动A股分析系统...
cd /d "%~dp0"

REM 使用pyenv配置的Python 3.11.4
set PYTHON_EXE=c:\Users\ext.jgu\.pyenv\pyenv-win\versions\3.11.4\python.exe

REM 检查Python是否存在
if not exist "%PYTHON_EXE%" (
    echo 错误: 未找到Python 3.11.4
    echo 请确保已安装pyenv并配置了Python 3.11.4
    pause
    exit /b 1
)

REM 启动主程序
echo 正在启动 a_share_gui_compatible.py ...
"%PYTHON_EXE%" a_share_gui_compatible.py

REM 如果程序异常退出，显示错误信息
if errorlevel 1 (
    echo.
    echo 程序异常退出，错误代码: %errorlevel%
    pause
)
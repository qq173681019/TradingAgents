@echo off
chcp 65001 >nul
echo ======================================
echo Choice数据采集 - A股主板股票
echo ======================================
echo.
echo 正在启动数据采集...
echo.

python ..\TradingShared\api\get_choice_data.py

echo.
echo ======================================
echo 按任意键关闭窗口...
pause >nul
setlocal
cd /d "%~dp0"
set PY_EXE=C:\veighna_studio\python.exe
"%PY_EXE%" get_choice_data.py
endlocal

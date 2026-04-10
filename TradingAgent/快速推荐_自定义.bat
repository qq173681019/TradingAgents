@echo off
chcp 65001 >nul
title Stock Recommendation Tool

echo ==========================================
echo   Stock Recommendation Tool
echo ==========================================
echo.
echo  Usage:
echo    1. Short-term (default 3 stocks)
echo    2. Long-term (default 3 stocks)
echo    3. Custom number
echo.
set /p choice="Select option (1/2/3): "

cd /d "%~dp0"

if "%choice%"=="1" (
    echo.
    echo [Short-term] Top 3 recommendations...
    python quick_recommend.py -t short -n 3
) else if "%choice%"=="2" (
    echo.
    echo [Long-term] Top 3 recommendations...
    python quick_recommend.py -t long -n 3
) else if "%choice%"=="3" (
    set /p num="Enter number of stocks (1-10): "
    set /p type="Enter type (short/long): "
    echo.
    echo [Custom] Top %num% recommendations (%type%-term)...
    python quick_recommend.py -t %type% -n %num% -v
) else (
    echo.
    echo [INFO] Using default settings...
    python quick_recommend.py
)

echo.
echo ==========================================
echo   Recommendation complete!
echo ==========================================
pause

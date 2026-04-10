@echo off
chcp 65001 >nul
title Quick Recommend - Top 3 Stocks

echo ==========================================
echo   Quick Stock Recommendation (Top 3)
echo ==========================================
echo.

cd /d "%~dp0"

echo [INFO] Generating recommendations...
echo.

python quick_recommend.py

echo.
echo ==========================================
echo   Press any key to exit...
echo ==========================================
pause >nul

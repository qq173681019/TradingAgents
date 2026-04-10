@echo off
chcp 65001 >nul 2>&1
title Daily Stock Recommender

echo ==========================================
echo   Daily Stock Recommender Engine
echo   Run Time: %date% %time%
echo ==========================================
echo.

cd /d "%~dp0"

echo [INFO] Starting recommendation engine...
echo.

python daily_recommender.py

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Recommendation complete! Please check your email.
) else (
    echo.
    echo [ERROR] Engine failed. Please check logs.
)

echo.
echo ==========================================
echo   Press any key to exit...
echo ==========================================
pause >nul

@echo off
chcp 65001 >nul
title Stock Backtest - Quick Validation

echo ==========================================
echo   Stock Recommendation Backtest System
echo   Quick Validation Mode
echo ==========================================
echo.
echo Target: 85% accuracy
echo Period: 2026-02-20 to 2026-04-07
echo Mode: Simplified simulation
echo.
echo [INFO] Starting backtest...
echo.

cd /d "%~dp0"

python backtest_simple.py

if errorlevel 1 (
    echo.
    echo ==========================================
    echo   [RESULT] Did not meet target
    echo ==========================================
    echo.
    echo Check backtest_results/final_result.json
    echo.
) else (
    echo.
    echo ==========================================
    echo   [RESULT] Validation PASSED!
    echo ==========================================
    echo.
    echo Algorithm is ready for production!
    echo.
)

echo Press any key to exit...
pause >nul

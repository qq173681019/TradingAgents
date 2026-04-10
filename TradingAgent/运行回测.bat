@echo off
chcp 65001 >nul
title Stock Recommendation Backtest System

echo ==========================================
echo   Stock Recommendation Backtest System
echo   Verifying algorithm accuracy
echo ==========================================
echo.
echo Target: 85% accuracy
echo Period: 2026-02-20 to 2026-04-07
echo.
echo [INFO] Starting backtest...
echo.

cd /d "%~dp0"

python run_backtest.py

if errorlevel 1 (
    echo.
    echo [FAIL] Backtest failed or did not meet target
    echo Check backtest_results/final_result.json for details
) else (
    echo.
    echo [SUCCESS] Backtest passed!
)

echo.
echo ==========================================
echo   Press any key to exit...
echo ==========================================
pause >nul

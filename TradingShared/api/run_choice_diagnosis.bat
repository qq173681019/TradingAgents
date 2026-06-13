@echo off
chcp 65001 >nul
title Choice API 诊断测试
cd /d D:\GitHub\TradingAgents\TradingShared\api
echo ============================================================
echo Choice API 全面诊断
echo ============================================================
echo.
C:\veighna_studio\python.exe choice_full_diagnosis.py
echo.
echo ============================================================
echo 按任意键退出...
pause >nul
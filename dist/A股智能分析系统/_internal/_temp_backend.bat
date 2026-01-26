@echo off 
title A股智能分析系�?- Flask后端服务 
cd /d "C:\Users\ext.jgu\Documents\GitHub\TradingAgents\TradingAgent\" 
echo. 
echo 🚀 Flask后端启动�?.. 
echo. 
python flask_backend.py 
if errorlevel 1 ( 
    echo �?后端启动失败 
    pause 
) 

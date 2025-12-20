@echo off
cd /d %~dp0
:: 启动python脚本，%1 接收传入的股票代码
start python sell_script.py %1
exit
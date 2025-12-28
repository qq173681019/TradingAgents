@echo off
chcp 65001 >nul
echo ======================================
echo Choice数据采集 - A股竞价排行
echo ======================================
echo.
echo 正在启动竞价排行分析...
echo 提示: 请在交易日 9:15 - 9:30 之间运行以获得最佳效果
echo.

set PY_EXE=C:\veighna_studio\python.exe
"%PY_EXE%" ..\TradingShared\api\get_call_auction_ranking.py

echo.
echo ======================================
echo 分析完成，按任意键关闭窗口...
pause >nul

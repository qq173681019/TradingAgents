@echo off
echo ========================================
echo A股智能分析系统 - EXE测试
echo ========================================
echo.
echo 测试信息：
echo 文件位置：%~dp0A股智能分析系统.exe
echo 文件大小：~225MB
echo.
echo 正在启动程序...
echo 提示：首次启动可能需要10-20秒
echo.
start "" "%~dp0A股智能分析系统.exe"
echo.
echo 程序已启动！
echo 如果程序无法正常运行，请检查：
echo 1. 网络连接是否正常
echo 2. 系统是否安装了最新的Visual C++运行库
echo.
pause
@echo off
chcp 65001 >nul

:: ==============================================================================
:: 使用修复后的算法生成推荐
:: ==============================================================================

cd /d "%~dp0"
set TA_RUN_FROM_BAT=1
set PYTHON_EXE=C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe

REM Check Python environment
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_EXE=python
)

cls
echo ============================================   
echo  生成推荐（修复版）
echo  使用优化后的评分算法和权重配置
echo ============================================   
echo. 

echo [正在执行] 使用修复后的算法生成推荐...
echo.
echo 改进内容：
echo   1. 热门板块评分使用对数映射（涨幅越大分数越高）
echo   2. 短线热门板块权重提升到40%%
echo   3. 长线热门板块权重提升到15%%
echo   4. 综合评分上限提升到15分
echo.

"%PYTHON_EXE%" "%~dp0run_export_with_old_data.py"

if errorlevel 1 (
    echo.
    echo [错误] 推荐生成失败！   
    pause
    exit /b 1
)

echo.
echo ============================================   
echo  推荐生成完成！
echo  查看桌面上的文件：
echo    1. 推荐_短线.csv
echo    2. 推荐_长线.csv
echo ============================================   
echo.
echo 按任意键退出...   
pause >nul

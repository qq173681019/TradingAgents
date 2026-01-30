@echo off
chcp 65001 >nul

:: ==============================================================================
:: WARNING: CMD has a byte-offset bug with UTF-8. 
:: TRICK: Each line with Chinese characters MUST end with extra spaces.
:: TRICK: Use UTF-8 with BOM encoding for maximum compatibility.
:: ==============================================================================

REM ------------------------------------------------------------------------------
REM  Environment Settings
REM ------------------------------------------------------------------------------
cd /d "%~dp0"
set TA_RUN_FROM_BAT=1
set PYTHON_EXE=C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe

REM Check Python environment
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_EXE=python
)

REM ------------------------------------------------------------------------------
REM  Main Execution Flow
REM ------------------------------------------------------------------------------
cls
echo ============================================   
echo  TradingAgent 自动化流程   
echo  1. 更新K线数据   
echo  2. 整理主板基础评分数据   
echo  3. 计算权重评分并导出到桌面   
echo ============================================   
echo. 

echo [步骤 1/3] 正在更新K线数据...   
echo.
echo 增大批次大小以触发 BURST 模式，提升效率...   
"%PYTHON_EXE%" "%~dp0update_kline_batch.py"
 
if errorlevel 1 (
     echo [错误] K线数据更新失败！   
     pause
     exit /b 1
 )
echo [步骤 1/3] K线数据更新完成。   

echo.
echo ============================================   
echo [步骤 2/3] 正在整理主板基础评分数据...   
echo.

"%PYTHON_EXE%" "%~dp0generate_mainboard_scores.py"

if errorlevel 1 (
    echo [错误] 主板评分获取失败！   
    pause
    exit /b 1
)

echo.
echo ============================================   
echo [步骤 3/3] 正在计算4种权重配置并导出到桌面...   
echo.

"%PYTHON_EXE%" "%~dp0export_recommendations.py"

if errorlevel 1 (
    echo [错误] CSV导出失败！   
    pause
    exit /b 1
)

echo.
echo ============================================   
echo  全部流程执行完成！   
echo ============================================   
echo  - K线数据已更新   
echo  - 主板基础评分已整理   
echo  - 推荐CSV已导出到桌面：   
echo    1. 推荐_综合.csv   
echo    2. 推荐_基本.csv   
echo    3. 推荐_筹码.csv   
echo    4. 推荐_技术.csv   
echo ============================================   
echo.
echo 按任意键退出...   
pause >nul

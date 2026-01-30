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
REM  Main Execution Flow - Step 3 Only
REM ------------------------------------------------------------------------------
cls
echo ============================================   
echo  TradingAgent - 仅导出推荐到桌面   
echo  步骤 3/3: 生成推荐CSV并导出   
echo ============================================   
echo. 
echo 说明：此脚本仅执行第3步（计算权重并导出）   
echo 前提：需要已存在主板基础评分JSON文件   
echo 输出：4个推荐CSV文件到桌面   
echo       （综合、基本、筹码、技术各10只）   
echo ============================================   
echo.

echo [步骤 3/3] 正在生成推荐并导出CSV到桌面...   
echo.

"%PYTHON_EXE%" "%~dp0export_recommendations.py"

if errorlevel 1 (
    echo [错误] CSV导出失败！   
    echo.
    echo 可能原因：   
    echo   1. 未找到主板评分JSON文件   
    echo   2. 请先运行「仅生成主板评分.bat」   
    echo   3. Python环境问题   
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================   
echo  导出完成！   
echo ============================================   
echo  推荐CSV已导出到桌面：   
echo.
echo    1. 推荐_综合.csv （技术35%%+基本20%%+筹码40%%+热门5%%）   
echo    2. 推荐_基本.csv （技术10%%+基本45%%+筹码40%%+热门5%%）   
echo    3. 推荐_筹码.csv （技术10%%+基本10%%+筹码70%%+热门10%%）   
echo    4. 推荐_技术.csv （技术80%%+基本10%%+筹码10%%）   
echo.
echo  每个文件包含前10只股票及其详细评分   
echo ============================================   
echo.
echo 按任意键退出...   
pause >nul

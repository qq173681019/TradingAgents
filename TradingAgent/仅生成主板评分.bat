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
REM  Main Execution Flow - Step 2 Only
REM ------------------------------------------------------------------------------
cls
echo ============================================   
echo  TradingAgent - 仅生成主板评分   
echo  步骤 2/3: 计算主板股票评分   
echo ============================================   
echo. 
echo 说明：此脚本仅执行第2步（生成评分）   
echo 前提：需要已存在 batch_stock_scores_none.json   
echo 输出：   
echo   - 4个不同权重的CSV文件   
echo   - 1个JSON评分文件   
echo ============================================   
echo.

echo [步骤 2/3] 正在获取主板评分...   
echo.

"%PYTHON_EXE%" "%~dp0generate_mainboard_scores.py"

if errorlevel 1 (
    echo [错误] 主板评分获取失败！   
    echo.
    echo 可能原因：   
    echo   1. 未找到 batch_stock_scores_none.json 文件   
    echo   2. 数据格式错误   
    echo   3. Python环境问题   
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================   
echo  评分生成完成！   
echo ============================================   
echo  已生成以下文件（位于 TradingShared\data\）：   
echo.
echo  CSV文件：   
echo    - 主板推荐_综合_[时间戳].csv   
echo    - 主板推荐_基本_[时间戳].csv   
echo    - 主板推荐_筹码_[时间戳].csv   
echo    - 主板推荐_技术_[时间戳].csv   
echo.
echo  JSON文件：   
echo    - batch_stock_scores_optimized_主板_[时间戳].json   
echo ============================================   
echo.
echo 按任意键退出...   
pause >nul

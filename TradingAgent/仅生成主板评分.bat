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
echo  TradingAgent - 仅整理主板基础评分   
echo  步骤 2/3: 整理主板股票基础评分数据   
echo ============================================   
echo. 
echo 说明：此脚本仅执行第2步（整理基础评分）   
echo 前提：需要已存在 batch_stock_scores_none.json   
echo 输出：   
echo   - 1个包含基础评分的JSON文件   
echo   - 不计算权重，不导出CSV   
echo ============================================   
echo.

echo [步骤 2/3] 正在整理主板基础评分数据...   
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
echo  基础评分数据整理完成！   
echo ============================================   
echo  已生成以下文件（位于 TradingShared\data\）：   
echo.
echo  JSON文件：   
echo    - batch_stock_scores_optimized_主板_[时间戳].json   
echo.
echo  下一步：运行「仅导出推荐到桌面.bat」   
echo  将根据4种权重配置计算并导出CSV   
echo ============================================   
echo.
echo 按任意键退出...   
pause >nul

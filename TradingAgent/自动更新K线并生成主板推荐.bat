@echo off
chcp 65001 >nul
echo ============================================
echo  TradingAgent 自动化流程
echo  1. 更新K线数据
echo  2. 获取主板评分
echo  3. 生成推荐CSV并导出到下载文件夹
echo ============================================
echo.

REM 设置路径
cd /d "%~dp0"

REM 标记：从 BAT 调用，供 Python 代码切换为批处理优化策略
set TA_RUN_FROM_BAT=1

REM 修复：使用GUI相同的Python环境
set PYTHON_EXE=C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe

REM 检查Python是否可用
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到Python 3.13环境！
    echo 正在尝试使用系统默认Python...
    set PYTHON_EXE=python
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 找不到任何Python环境！
        echo 请确保已安装Python并添加到系统PATH。
        pause
        exit /b 1
    )
)

REM echo [步骤 1/3] 正在更新K线数据...
REM echo.
REM 增大批次大小以触发 BURST 模式，提升效率（每批 100 只，触发 >50 不等待逻辑）
REM "%PYTHON_EXE%" update_kline_batch.py
REM 
REM if errorlevel 1 (
REM     echo [错误] K线数据更新失败！
REM     pause
REM     exit /b 1
REM )
echo [步骤 1/3] 跳过K线数据更新（已注释）

echo.
echo ============================================
echo [步骤 2/3] 正在获取主板评分...
echo.

REM 使用新的评分脚本（复用 GUI 的评分逻辑）
"%PYTHON_EXE%" "%~dp0generate_mainboard_scores.py"

if errorlevel 1 (
    echo [错误] 主板评分获取失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo [步骤 3/3] 正在生成推荐并导出CSV到下载文件夹...
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
echo  - 主板评分已获取
echo  - 推荐CSV已导出到下载文件夹
echo ============================================
echo.
echo 按任意键退出...
pause >nul

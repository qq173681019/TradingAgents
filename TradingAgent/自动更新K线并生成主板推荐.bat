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

echo [步骤 1/3] 正在更新K线数据...
echo.
REM 增大批次大小以触发 BURST 模式，提升效率（每批 100 只，触发 >50 不等待逻辑）
"%PYTHON_EXE%" update_kline_batch.py

if errorlevel 1 (
    echo [错误] K线数据更新失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo [步骤 2/3] 正在获取主板评分...
echo.

REM 这里需要调用主板评分的功能
"%PYTHON_EXE%" -c "import sys, os, json; sys.path.insert(0, '.'); sys.path.insert(0, '..'); from TradingShared.api.comprehensive_data_collector import ComprehensiveDataCollector; from datetime import datetime; collector = ComprehensiveDataCollector(); data_dir = os.path.join('..', 'TradingShared', 'data'); stock_files = [f for f in os.listdir(data_dir) if f.startswith('comprehensive_stock_data_part_') and f.endswith('.json')]; all_stocks = {}; [all_stocks.update(json.load(open(os.path.join(data_dir, f), encoding='utf-8')).get('stocks', {})) for f in stock_files]; main_board_stocks = {k: v for k, v in all_stocks.items() if k.startswith(('600', '601', '603', '000', '001', '002'))}; print(f'主板股票总数: {len(main_board_stocks)} 只'); output_file = os.path.join(data_dir, f'batch_stock_scores_optimized_主板_{datetime.now().strftime(\"%%Y%%m%%d_%%H%%M%%S\")}.json'); json.dump(main_board_stocks, open(output_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2); print(f'主板评分数据已保存到: {os.path.basename(output_file)}')"

if errorlevel 1 (
    echo [错误] 主板评分获取失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo [步骤 3/3] 正在生成推荐并导出CSV到下载文件夹...
echo.

"%PYTHON_EXE%" -c "import sys, os, json, csv; sys.path.insert(0, '.'); sys.path.insert(0, '..'); from datetime import datetime; data_dir = os.path.join('..', 'TradingShared', 'data'); score_files = sorted([f for f in os.listdir(data_dir) if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')], reverse=True); latest_score_file = score_files[0] if score_files else None; print(f'使用评分文件: {latest_score_file}'); scores = json.load(open(os.path.join(data_dir, latest_score_file), encoding='utf-8')) if latest_score_file else {}; sorted_stocks = sorted(scores.items(), key=lambda x: x[1].get('综合得分', 0) if isinstance(x[1], dict) else 0, reverse=True)[:100]; download_folder = os.path.join(os.path.expanduser('~'), 'Downloads'); csv_filename = f'主板推荐股票_{datetime.now().strftime(\"%%Y%%m%%d_%%H%%M%%S\")}.csv'; csv_path = os.path.join(download_folder, csv_filename); f = open(csv_path, 'w', encoding='utf-8-sig', newline=''); writer = csv.writer(f); writer.writerow(['股票代码', '股票名称', '综合得分', '短线评分', '长线评分', '筹码评分', '推荐类型']); [writer.writerow([code, data.get('名称', ''), data.get('综合得分', 0), data.get('短线评分', 0), data.get('长线评分', 0), data.get('筹码评分', 0), data.get('推荐类型', '')]) for code, data in sorted_stocks if isinstance(data, dict)]; f.close(); print(f'CSV文件已导出到: {csv_path}')"

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

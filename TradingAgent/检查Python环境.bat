@echo off
chcp 65001 >nul
echo ============================================
echo  Python环境诊断工具
echo ============================================
echo.

set PYTHON_EXE=C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python3.13.exe

echo [1] 检查Python版本...
"%PYTHON_EXE%" --version
echo.

echo [2] 检查Python路径...
"%PYTHON_EXE%" -c "import sys; print(f'Python路径: {sys.executable}')"
echo.

echo [3] 检查必需的包...
"%PYTHON_EXE%" -c "import sys; from importlib import util; packages = ['tushare', 'akshare', 'baostock', 'yfinance', 'pandas', 'requests']; missing = []; [missing.append(pkg) if util.find_spec(pkg) is None else print(f'✓ {pkg}') for pkg in packages]; [print(f'✗ {pkg} - 未安装') for pkg in missing]; sys.exit(len(missing))"

if errorlevel 1 (
    echo.
    echo [警告] 发现缺失的包！
    echo.
    echo 请运行以下命令安装：
    echo.
    echo "%PYTHON_EXE%" -m pip install tushare akshare baostock yfinance pandas requests
    echo.
)

echo.
echo ============================================
echo  诊断完成
echo ============================================
pause

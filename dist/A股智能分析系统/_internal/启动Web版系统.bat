@echo off
REM A股智能分析系统 - Web版启动脚本
REM 同时启动Flask后端和Web前端

echo.
echo ╔══════════════════════════════════════════════════════════════════════════════╗
echo ║                  A股智能分析系统 - Web版启动脚本                            ║
echo ║                                                                              ║
echo ║  这个脚本将:                                                                 ║
echo ║  1. 启动Flask后端服务 (http://localhost:5000)                               ║
echo ║  2. 打开Web前端界面 (web_interface.html)                                    ║
echo ║                                                                              ║
echo ║  按 Ctrl+C 退出服务                                                         ║
echo ║                                                                              ║
echo ╚══════════════════════════════════════════════════════════════════════════════╝
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python
    echo.
    echo 请先安装Python 3.7或更高版本
    pause
    exit /b 1
)

REM 检查Flask
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Flask未安装，正在安装...
    pip install flask flask-cors -q
    if errorlevel 1 (
        echo ❌ 安装失败，请手动运行:
        echo pip install flask flask-cors
        pause
        exit /b 1
    )
    echo ✅ Flask安装成功
)

REM 创建临时批文件来启动后端
echo @echo off > _temp_backend.bat
echo title A股智能分析系统 - Flask后端服务 >> _temp_backend.bat
echo cd /d "%~dp0" >> _temp_backend.bat
echo echo. >> _temp_backend.bat
echo echo 🚀 Flask后端启动中... >> _temp_backend.bat
echo echo. >> _temp_backend.bat
echo python flask_backend.py >> _temp_backend.bat
echo if errorlevel 1 ( >> _temp_backend.bat
echo     echo ❌ 后端启动失败 >> _temp_backend.bat
echo     pause >> _temp_backend.bat
echo ) >> _temp_backend.bat

REM 启动Flask后端
echo 🚀 启动Flask后端服务...
start "A股智能分析系统 - Flask后端" cmd /k "_temp_backend.bat"

REM 等待后端启动
echo ⏳ 等待后端服务启动 (5秒)...
timeout /t 5 /nobreak

REM 打开Web界面
echo 📱 打开Web前端界面...
set "web_file=%~dp0web_interface.html"
if exist "%web_file%" (
    start "" "%web_file%"
    echo ✅ Web界面已打开
) else (
    echo ❌ web_interface.html 未找到
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════════════════════════════╗
echo ║ ✅ 系统启动完成                                                              ║
echo ║                                                                              ║
echo ║ 📱 Web界面: 浏览器已自动打开 (web_interface.html)                           ║
echo ║ 🚀 后端服务: http://localhost:5000                                          ║
echo ║                                                                              ║
echo ║ 功能列表:                                                                    ║
echo ║ ✓ 单只股票深度分析                                                          ║
echo ║ ✓ 批量股票评分                                                              ║
echo ║ ✓ 投资推荐系统                                                              ║
echo ║ ✓ 实时数据更新                                                              ║
echo ║                                                                              ║
echo ║ ⚠️  提示:                                                                   ║
echo ║ • 如果Web界面无法连接后端，请检查防火墙设置                                  ║
echo ║ • 关闭Flask窗口即可停止服务                                                 ║
echo ║ • 更多文档见 WEB_VERSION_README.md                                          ║
echo ║                                                                              ║
echo ╚══════════════════════════════════════════════════════════════════════════════╝
echo.

pause

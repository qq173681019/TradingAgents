@echo off
chcp 65001 >nul
title Choice数据更新服务
color 0B
echo ========================================
echo    Choice金融数据更新服务
echo ========================================
echo.

cd /d "%~dp0"

echo [1/1] 启动Choice数据更新...
echo.

"C:\veighna_studio\python.exe" choice_background_service.py

if errorlevel 1 (
    echo.
    echo ❌ 数据更新失败
    echo.
    pause
    exit /b 1
) else (
    echo.
    echo ========================================
    echo ✅ 数据更新完成
    echo ========================================
    echo.
    echo 💡 提示：
    echo    - 数据已保存到 data\choice_cache.json
    echo    - 现在可以启动主程序查看数据
    echo    - 建议设置为定时任务，每小时自动运行
    echo.
    pause
)

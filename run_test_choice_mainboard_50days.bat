@echo off
setlocal
cd /d "%~dp0"
set PY_EXE=C:\veighna_studio\python.exe
"%PY_EXE%" test_choice_mainboard_50days.py
endlocal

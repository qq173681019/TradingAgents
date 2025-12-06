@echo off
setlocal
cd /d "%~dp0"
set PY_EXE=C:\veighna_studio\python.exe
"%PY_EXE%" get_choice_data.py
endlocal

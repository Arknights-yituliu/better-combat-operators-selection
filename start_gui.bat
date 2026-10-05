@echo off
rem 一键启动干员 TAG 维护面板（双击运行；GUI 仅依赖 Python 标准库）
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% -X utf8 recommend_gui.py %*
if errorlevel 1 pause
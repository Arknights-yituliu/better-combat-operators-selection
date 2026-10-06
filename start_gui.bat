@echo off
rem One-click launcher for the TAG maintenance panel (stdlib-only GUI).
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% -X utf8 recommend_gui.py %*
if errorlevel 1 pause

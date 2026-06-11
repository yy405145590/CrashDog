@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "PYEXE=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

cd /d "%ROOT%"
echo Root: %CD%
echo Python: %PYEXE%
echo.

"%PYEXE%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend
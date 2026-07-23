@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "PYEXE=%ROOT%runtime\python\python.exe"
if not exist "%PYEXE%" set "PYEXE=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
set "LOG_DIR=%ROOT%logs"
set "CONSOLE_LOG=%LOG_DIR%\backend-console.log"
set "PYTHONFAULTHANDLER=1"
set "PYTHONUNBUFFERED=1"

cd /d "%ROOT%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo Root: %CD%
echo Python: %PYEXE%
echo Mode: stable
echo Console log: %CONSOLE_LOG%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start-backend.ps1" -PythonExe "%PYEXE%" -ConsoleLog "%CONSOLE_LOG%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Backend stopped with exit code %EXIT_CODE%.
echo See logs: %CONSOLE_LOG% and %ROOT%logs\crashdog.log
exit /b %EXIT_CODE%
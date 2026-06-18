@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "PYEXE=%ROOT%.venv\Scripts\python.exe"
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

powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $log = '%CONSOLE_LOG%'; Write-Output ('===== Backend stable start {0} =====' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) | Tee-Object -FilePath $log -Append; & '%PYEXE%' -m uvicorn backend.main:app --host 0.0.0.0 --port 18000 2>&1 | Tee-Object -FilePath $log -Append; $code = $LASTEXITCODE; Write-Output ('===== Backend stable stopped {0}; exit code {1} =====' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $code) | Tee-Object -FilePath $log -Append; exit $code }"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Backend stopped with exit code %EXIT_CODE%.
echo See logs: %CONSOLE_LOG% and %ROOT%logs\crashdog.log
exit /b %EXIT_CODE%
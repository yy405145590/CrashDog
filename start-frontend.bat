@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%frontend"
echo Root: %CD%
echo.

npm run dev
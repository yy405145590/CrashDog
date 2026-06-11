@echo off
setlocal
chcp 65001 >nul
title CrashDog

echo ============================================
echo   CrashDog One-Click Start
echo ============================================
echo.

set "ROOT=%~dp0"

echo [1/2] Starting backend (FastAPI :18000) ...
start "CrashDog-Backend" cmd /k ""%ROOT%start-backend.bat""

echo [2/2] Starting frontend (Vite :5174) ...
start "CrashDog-Frontend" cmd /k ""%ROOT%start-frontend.bat""

echo.
echo ============================================
echo   Backend:  http://localhost:18000
echo   Frontend: http://localhost:5174
echo   Close the service windows to stop.
echo ============================================

pause

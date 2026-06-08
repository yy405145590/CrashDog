@echo off
setlocal
chcp 65001 >nul
title CrashDog

echo ============================================
echo   CrashDog One-Click Start
echo ============================================
echo.

set "ROOT=%~dp0"
set "PYEXE=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo [1/2] Starting backend (FastAPI :8000) ...
start "CrashDog-Backend" cmd /k "cd /d ""%ROOT%"" && ""%PYEXE%"" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend"

echo [2/2] Starting frontend (Vite :5174) ...
start "CrashDog-Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm run dev"

echo.
echo ============================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5174
echo   Close the service windows to stop.
echo ============================================

pause

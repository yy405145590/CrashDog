@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "NODEEXE=%ROOT%runtime\node\node.exe"
cd /d "%ROOT%frontend"
echo Root: %CD%
if exist "%NODEEXE%" (
	echo Node: %NODEEXE%
	echo.
	"%NODEEXE%" "%CD%\node_modules\vite\bin\vite.js" --host 0.0.0.0 --port 5174
	exit /b %ERRORLEVEL%
)

where node >nul 2>nul
if %ERRORLEVEL% equ 0 (
	echo Node: PATH
	echo.
	node "%CD%\node_modules\vite\bin\vite.js" --host 0.0.0.0 --port 5174
	exit /b %ERRORLEVEL%
)

echo.
echo ERROR: Node.js was not found. Rebuild the offline package or install Node.js.
exit /b 1
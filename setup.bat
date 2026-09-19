@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo            Starting JaneConverter Automated Setup
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

if not errorlevel 1 exit /b 0
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
echo Setup encountered an error. The window will close automatically in 10 seconds.
timeout /t 10 /nobreak >nul
exit /b %SETUP_EXIT%

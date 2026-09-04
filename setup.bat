@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo            Starting JaneConverter Automated Setup
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Setup encountered an error.
    pause
)

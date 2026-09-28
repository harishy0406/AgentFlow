@echo off
setlocal
title AgentFlow Launcher
cd /d "%~dp0"
set PYTHONUNBUFFERED=1

if exist "backend\venv\Scripts\python.exe" (
    "backend\venv\Scripts\python.exe" start.py %*
) else (
    python start.py %*
)

echo.
echo [AgentFlow] Session ended. Press any key to exit...
pause >nul

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

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AgentFlow] Process ended with exit code %ERRORLEVEL%.
    pause
)

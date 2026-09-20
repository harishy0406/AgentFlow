# AgentFlow PowerShell Launcher
Set-Location $PSScriptRoot

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   Launching AgentFlow via PowerShell..." -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

$python = if (Test-Path "backend\venv\Scripts\python.exe") { "backend\venv\Scripts\python.exe" } else { "python" }

& $python start.py @args

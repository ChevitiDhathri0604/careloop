# CareLoop 1-Click PowerShell Launcher
Set-Location -Path $PSScriptRoot
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " Starting CareLoop Multi-Agent Control Plane & Ops Console..." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan

Start-Process "http://127.0.0.1:8000"
python run_demo.py --serve

@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AZOR - Limpar residuos antigos

echo Fechando engines e janelas antigas do AZOR...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'azor_server\.py|azor_agent\.py|run_agent_hidden\.vbs|AZOR_ABRIR_CLIENTE\.cmd') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-CimInstance Win32_Process | Where-Object { $_.Name -ieq 'msedge.exe' -and $_.CommandLine -and $_.CommandLine -match 'AzorOptimization[\\/]edge_profile' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; $h=Join-Path $env:LOCALAPPDATA 'AzorOptimization'; Remove-Item (Join-Path $h 'app') -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item (Join-Path $h 'runtime') -Recurse -Force -ErrorAction SilentlyContinue; Get-ChildItem $h -Directory -Filter 'edge_profile*' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item (Join-Path $h 'user\data\server_runtime.json') -Force -ErrorAction SilentlyContinue"
schtasks /Delete /TN "AzorGuardianWatchdog" /F >nul 2>&1
schtasks /Delete /TN "AzorDailyMaintenance" /F >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AzorGuardian" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AzorOptimization" /f >nul 2>&1

echo [OK] Residuos antigos removidos. Seus dados de usuario e relatorios foram preservados.
timeout /t 2 >nul

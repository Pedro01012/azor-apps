@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title AZOR Optimization
set "AZOR_PY=%~dp0runtime\python.exe"
set "AZOR_PYW=%~dp0runtime\pythonw.exe"
if not exist "%AZOR_PY%" (
  echo O AZOR nao encontrou a pasta runtime. Extraia o ZIP inteiro antes de abrir.
  pause
  exit /b 20
)
if not exist "%AZOR_PYW%" set "AZOR_PYW=%AZOR_PY%"

rem Ja esta como administrador? ("net session" so responde elevado)
net session >nul 2>&1
if not errorlevel 1 goto run
if /i "%~1"=="--sem-admin" goto run

rem Conta de administrador: pede a permissao do Windows UMA vez e o AZOR aplica
rem tudo sem perguntar de novo. Conta comum (sem grupo Administradores): abre
rem normal e o Windows pede a senha so nas operacoes que precisam.
whoami /groups | find "S-1-5-32-544" >nul 2>&1
if errorlevel 1 goto run
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath $env:ComSpec -ArgumentList '/c','\"\"%~f0\" --sem-admin\"' -Verb RunAs -WindowStyle Minimized -ErrorAction Stop; exit 0 } catch { exit 1 }"
if not errorlevel 1 exit /b 0
rem Permissao recusada: abre assim mesmo, sem administrador.

:run
"%AZOR_PY%" "%~dp0tools\check_startup.py"
if errorlevel 1 (
  echo.
  echo Os arquivos do AZOR estao incompletos. Extraia o ZIP de novo, inteiro.
  pause
  exit /b 31
)
start "" "%AZOR_PYW%" "%~dp0app\azor_launcher.py"
exit /b 0

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

"%AZOR_PY%" "%~dp0tools\check_startup.py"
if errorlevel 1 (
  echo.
  echo Os arquivos do AZOR estao incompletos. Extraia o ZIP de novo, inteiro.
  pause
  exit /b 31
)

rem Chamado por esta mesma copia, ja elevada: sobe so o motor (a janela abre
rem como usuario comum, pela copia que pediu a permissao).
if /i "%~1"=="--motor" (
  start "" "%AZOR_PYW%" "%~dp0app\azor_launcher.py" --no-window
  exit /b 0
)

rem Ja esta como administrador? ("net session" so responde elevado)
net session >nul 2>&1
if not errorlevel 1 goto run

rem Conta de administrador: pede a permissao do Windows UMA vez; o motor roda
rem como administrador e aplica tudo sem perguntar de novo. Conta comum (sem o
rem grupo Administradores): abre normal e o Windows pede a senha so nas
rem operacoes que precisam.
whoami /groups | find "S-1-5-32-544" >nul 2>&1
if errorlevel 1 goto run
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath $env:ComSpec -ArgumentList '/c','\"\"%~f0\" --motor\"' -Verb RunAs -WindowStyle Hidden -ErrorAction Stop; exit 0 } catch { exit 1 }"
if errorlevel 1 goto run
start "" "%AZOR_PYW%" "%~dp0app\azor_launcher.py" --ui-only
exit /b 0

:run
rem Permissao recusada, conta comum ou ja elevado: abre tudo neste processo.
start "" "%AZOR_PYW%" "%~dp0app\azor_launcher.py"
exit /b 0

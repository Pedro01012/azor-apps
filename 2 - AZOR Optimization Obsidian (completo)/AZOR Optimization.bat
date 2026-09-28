@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title AZOR Optimization
set "AZOR_PY=%~dp0runtime\python.exe"
set "AZOR_PYW=%~dp0runtime\pythonw.exe"
if not exist "%AZOR_PY%" (
  echo O runtime do AZOR nao foi encontrado. Extraia o pacote completo.
  pause
  exit /b 20
)
if not exist "%AZOR_PYW%" set "AZOR_PYW=%AZOR_PY%"
"%AZOR_PY%" "%~dp0tools\check_startup.py"
if errorlevel 1 (
  echo Os arquivos do aplicativo precisam ser conferidos.
  pause
  exit /b 31
)
rem Abrir nao eleva, nao mata processos, nao apaga dados e nao aplica ajustes.
start "" "%AZOR_PYW%" "%~dp0payload\azor_launcher.py" %*
exit /b 0

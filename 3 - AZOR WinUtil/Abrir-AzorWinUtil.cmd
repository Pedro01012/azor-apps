@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0azorwinutil.ps1" goto missing

echo Abrindo o Azor WinUtil...
echo O Windows vai pedir permissao de administrador: clique em Sim.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0azorwinutil.ps1"
endlocal
exit /b 0

:missing
echo O arquivo azorwinutil.ps1 nao esta nesta pasta.
echo Extraia o ZIP inteiro e abra este arquivo de dentro da pasta extraida.
pause
endlocal
exit /b 1

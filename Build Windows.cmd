@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
set "resultado=%ERRORLEVEL%"
if not "%resultado%"=="0" echo O build falhou. Confira a mensagem acima.
pause
exit /b %resultado%

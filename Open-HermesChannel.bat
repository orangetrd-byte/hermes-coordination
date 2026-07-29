@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-HermesChannel.ps1"
exit /b %errorlevel%

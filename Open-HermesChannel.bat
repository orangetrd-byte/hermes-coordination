@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "URL=https://127.0.0.1:%HERMES_CHANNEL_PORT%"
set "RELAY=%~dp0relay.py"
set "PYTHON="

where python >nul 2>&1
if %errorlevel%==0 (
  for /f "delims=" %%i in ('where python') do set "PYTHON=%%i"
)

if not "%PYTHON%"=="" (
  powershell -NoProfile -Command "try { invoke-webrequest -UseBasicParsing -Uri '%URL%/api/health' -TimeoutSec 2 | out-null } catch { exit 0 }"
  if %errorlevel% neq 0 (
    start /b "" "%PYTHON%" "%RELAY%"
    powershell -NoProfile -Command "Start-Sleep -Seconds 2"
  )
) else (
  msg * "Python not found"
  pause
  exit /b 1
)

start "" "%URL%"

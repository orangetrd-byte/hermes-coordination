@echo off
set "URL=http://192.168.10.196:8787"
set "RELAY=%~dp0relay.py"
set "PYTHON="

where python >nul 2>&1
if %errorlevel%==0 (
  for /f "delims=" %%i in ('where python') do set "PYTHON=%%i"
)

if not "%PYTHON%"=="" (
  powershell -NoProfile -Command "try { invoke-webrequest -Uri '%URL%' -UseBasicParsing -timeout 2 | out-null } catch { exit 0 }"
  if %errorlevel% neq 0 (
    set "HERMES_CHANNEL_HOST=0.0.0.0"
    start /b "" "%PYTHON%" "%RELAY%"
    powershell -NoProfile -Command "Start-Sleep -Milliseconds 700"
  )
) else (
  msg * "Python not found"
  pause
  exit /b 1
)

start "" "%URL%"

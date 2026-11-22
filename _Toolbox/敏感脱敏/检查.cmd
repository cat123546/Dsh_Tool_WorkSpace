@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Rule Check
set "PY="
set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if exist "%DSHPY%" set "PY=%DSHPY%"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%i"
if not defined PY (
  echo.
  echo [ERROR] Python not found. Start DeepSeek Harness once, then retry.
  echo.
  pause
  exit /b 1
)
echo.
"%PY%" "%~dp0check.py"
echo.
"%PY%" "%~dp0evaluate.py"
echo.
pause

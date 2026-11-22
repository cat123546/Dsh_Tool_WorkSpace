@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Rule Check
set "PY=C:\Users\CAT\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" (
  for /f "delims=" %%i in ('where python 2^>nul') do if not defined ALT set "ALT=%%i"
  if defined ALT set "PY=%ALT%"
)
if not exist "%PY%" (
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

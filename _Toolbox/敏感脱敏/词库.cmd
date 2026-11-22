@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Vocabulary
set "PY="
for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%i"
if not defined PY set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PY if exist "%DSHPY%" set "PY=%DSHPY%"
if not defined PY (
  echo.
  echo [ERROR] Python not found.
  echo Start DeepSeek Harness once, then double-click this file again.
  echo.
  pause
  exit /b 1
)
"%PY%" "%~dp0vocab.py" %*
if "%~1"=="" pause

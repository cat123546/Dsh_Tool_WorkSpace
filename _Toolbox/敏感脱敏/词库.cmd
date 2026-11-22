@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Vocabulary
set "PY=C:\Users\CAT\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" (
  for /f "delims=" %%i in ('where python 2^>nul') do if not defined ALT set "ALT=%%i"
  if defined ALT set "PY=%ALT%"
)
if not exist "%PY%" (
  echo.
  echo [ERROR] Python not found.
  echo Start DeepSeek Harness once, then double-click this file again.
  echo.
  pause
  exit /b 1
)
"%PY%" "%~dp0vocab.py" %*
if "%~1"=="" pause

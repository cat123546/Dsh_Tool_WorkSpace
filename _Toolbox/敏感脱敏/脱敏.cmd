@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Document Masking
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
set "SRC=%~1"
if not "%SRC%"=="" goto :run
echo.
echo   Drag the folder you want to process into this window,
echo   or paste its path, then press Enter.
echo   Output goes to _scratch\ ; original files are never modified.
echo.
set /p SRC=
:run
if "%SRC%"=="" (
  echo.
  echo Cancelled: no path given.
  pause
  exit /b 1
)
echo.
echo Processing: %SRC%
echo.
"%PY%" "%~dp0mask.py" --src "%SRC%" --auto
echo.
pause

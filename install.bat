@echo off
set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Please install Python 3.10+ and check "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% "%~dp0tools\install_helper.py"

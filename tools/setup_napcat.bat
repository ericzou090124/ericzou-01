@echo off
chcp 65001 >nul 2>&1
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH".
  pause
  exit /b 1
)
"%PY%" "%~dp0setup_napcat.py" --qr

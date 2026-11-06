@echo off
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
echo Starting Resource Manager setup...
"%PY%" "%~dp0tools\install_helper.py"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" ( echo [Setup exited with code %RC%] ) else ( echo [Setup finished] )
echo If you see an error above, screenshot it and send it to me.
pause

@echo off
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
echo Starting Resource Manager service...
"%PY%" "%~dp0tools\start_helper.py"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" ( echo [Exited with code %RC%] ) else ( echo [Finished] )
echo If you see an error above, screenshot it and send it to me.
pause

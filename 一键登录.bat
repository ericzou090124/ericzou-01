@echo off
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
echo Opening QQ web login page...
"%PY%" "%~dp0tools\open_login.py"
set "RC=%errorlevel%"
echo.
echo The browser should open: http://127.0.0.1:8787/login
echo If it did not open, open that address manually.
if not "%RC%"=="0" ( echo [Exited with code %RC%] )
pause

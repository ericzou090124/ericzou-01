@echo off
setlocal
set "PY=python"
where python >nul 2>nul || set "PY=py"
echo Starting NapCat (QQ bot gateway)...
echo The QR code and refresh are handled on the Resource Manager login page.
"%PY%" "%~dp0napcat_ctl.py" start
echo.
if errorlevel 1 ( echo [NapCat failed to start - see error above] )
echo If it still says not connected, open the login page and click "Refresh QR code":
echo   http://127.0.0.1:8787/login
echo Or run tools\setup_napcat.bat for a full self-check.
pause

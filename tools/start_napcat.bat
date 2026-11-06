@echo off
setlocal
set "PY=python"
where python >nul 2>nul || set "PY=py"
echo Starting NapCat (QQ bot gateway)...
echo After it starts, wait ~10-40s, then go back to Resource Manager and click "refresh source".
"%PY%" "%~dp0napcat_ctl.py" start
echo.
if errorlevel 1 ( echo [NapCat failed to start - see error above] )
echo If the page still says not connected, open in browser:
echo   http://127.0.0.1:6099/webui
echo Log in to QQ there, then back in Resource Manager click "refresh source".
pause

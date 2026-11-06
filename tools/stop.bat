@echo off
echo Stopping Resource Manager service on port 8787...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8787" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
echo Done. If the page still won't open, close the python server window.
pause

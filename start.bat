@echo off
chcp 65001 >nul 2>&1
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)

rem Locate start_helper.py. The release zip is flat, so tools\ is a sibling of this bat.
set "HERE=%~dp0"
set "HELPER="
if exist "%HERE%tools\start_helper.py" set "HELPER=%HERE%tools\start_helper.py"
if not defined HELPER if exist "%HERE%start_helper.py" set "HELPER=%HERE%start_helper.py"

if not defined HELPER (
  echo ============================================================
  echo  ERROR: start_helper.py was not found ^(expected under tools^).
  echo  Most likely you double-clicked start.bat INSIDE the .zip.
  echo  Windows then extracts only this one .bat to a temp folder,
  echo  without the rest of the program, so it cannot run.
  echo.
  echo  Fix ^(one time only^):
  echo   1^) Extract the whole zip into an empty folder
  echo      ^(right-click the zip -^> "Extract All" / unzip it^).
  echo   2^) Open that folder and double-click start.bat inside it.
  echo  The folder must contain server.py and a tools\ subfolder.
  echo  See 新手必读.txt for the Chinese step-by-step guide.
  echo ============================================================
  pause
  exit /b 2
)

echo Starting Resource Manager service...
"%PY%" "%HELPER%"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" ( echo [Exited with code %RC%] ) else ( echo [Finished] )
echo If you see an error above, screenshot it and send it to me.
pause

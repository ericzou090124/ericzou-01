@echo off
chcp 65001 >nul 2>&1
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and check "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)

rem Locate open_login.py. The release zip is flat, so tools\ is a sibling of this bat.
set "HERE=%~dp0"
set "HELPER="
if exist "%HERE%tools\open_login.py" set "HELPER=%HERE%tools\open_login.py"
if not defined HELPER if exist "%HERE%open_login.py" set "HELPER=%HERE%open_login.py"

if not defined HELPER (
  echo ============================================================
  echo  ERROR: open_login.py was not found ^(expected under tools^).
  echo  Most likely you double-clicked this .bat INSIDE the .zip.
  echo  Windows then extracts only this one .bat to a temp folder,
  echo  without the rest of the program, so it cannot run.
  echo.
  echo  Fix ^(one time only^):
  echo   1^) Extract the whole zip into an empty folder
  echo      ^(right-click the zip -^> "Extract All" / unzip it^).
  echo   2^) Open that folder and double-click this .bat inside it.
  echo  The folder must contain server.py and a tools\ subfolder.
  echo  See 新手必读.txt for the Chinese step-by-step guide.
  echo ============================================================
  pause
  exit /b 2
)

echo Opening QQ web login page...
"%PY%" "%HELPER%"
set "RC=%errorlevel%"
echo.
echo The browser should open: http://127.0.0.1:8787/login
echo If it did not open, open that address manually.
if not "%RC%"=="0" ( echo [Exited with code %RC%] )
pause

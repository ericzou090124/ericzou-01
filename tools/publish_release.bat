@echo off
set "PY=python"
%PY% --version >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1 || (
  echo Python not found. Please install Python 3.10+ and add it to PATH, then run this file again.
  pause
  exit /b 1
)
echo Pushing to GitHub...
"%PY%" -c "import subprocess,sys; sys.exit(subprocess.run('git push origin main --tags', shell=True).returncode)"
if not "%errorlevel%"=="0" (
  echo [Warning] git push failed or already up to date. Continuing to publish release...
)
echo Publishing GitHub Release with attachment...
"%PY%" "%~dp0tools\publish_release.py"
echo.
echo If you see an error above, screenshot it and send it to me.
pause

@echo off
set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py"
%PY% "%~dp0tools\start_helper.py"

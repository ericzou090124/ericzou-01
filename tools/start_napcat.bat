@echo off
setlocal
set "PY=python"
where python >nul 2>nul || set "PY=py"
"%PY%" "%~dp0napcat_ctl.py" start
echo.
echo 若窗口闪退且仍提示未连接，请手动打开浏览器访问：
echo   http://127.0.0.1:6099/webui
echo 在控制台里登录 QQ 后，回到资源管理器点「刷新来源」即可。
pause

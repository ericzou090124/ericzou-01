@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动「资源管理」本地服务…
echo 统一资源库：%USERPROFILE%\Desktop\资源管理
echo 界面地址：  http://127.0.0.1:8787
echo （关闭本窗口即停止服务；本服务仅监听 127.0.0.1）
echo.
python server.py
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  QQ 一键登录（网页扫码，不需要桌面二维码图片）
echo ============================================
echo.
python tools\open_login.py
echo.
echo 浏览器已打开登录页；扫码确认后会自动恢复在线下载。
echo 本窗口 5 秒后自动关闭，服务继续在后台运行。
timeout /t 5 >nul

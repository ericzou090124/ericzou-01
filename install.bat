@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   资源管理 · 一键安装与启动
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo [错误] 没有检测到 Python。
  echo 请先到 https://www.python.org/downloads/ 下载安装 Python 3.10+，
  echo 安装时务必勾选 "Add python.exe to PATH"（添加到 PATH）。
  echo 装好后再双击本文件。
  pause
  exit /b 1
)

echo [1/2] 依赖检查：核心功能只用 Python 标准库，无需安装任何包。
echo.
set "OPT=N"
set /p OPT=是否安装可选增强（PDF 正文抽取 / 本机渲染二维码）？建议装 [Y/n]：
if /i "%OPT%"=="Y" (
  echo 正在安装可选增强（可能需要一两分钟，请耐心等待）…
  python -m pip install -r requirements-optional.txt
) else (
  echo 已跳过可选增强。程序可正常运行（PDF 只登记元数据，二维码用 NapCat 缓存图）。
)

echo.
echo [2/2] 启动本地服务并打开界面…
echo 界面地址： http://127.0.0.1:8787
echo （关闭本窗口即停止服务；本服务仅监听本机 127.0.0.1）
echo.
python server.py
pause

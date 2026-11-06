#!/usr/bin/env bash
# 资源管理 · 一键安装与启动（macOS / Linux）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  资源管理 · 一键安装与启动"
echo "============================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 没有检测到 python3。请先安装 Python 3.10+ 后再运行本脚本。"
  exit 1
fi

echo "[1/2] 依赖检查：核心功能只用 Python 标准库，无需安装任何包。"
echo
read -r -p "是否安装可选增强（PDF 正文抽取 / 本机渲染二维码）？建议装 [Y/n]：" OPT
if [ "$OPT" = "Y" ] || [ "$OPT" = "y" ] || [ -z "$OPT" ]; then
  echo "正在安装可选增强…"
  python3 -m pip install -r requirements-optional.txt
else
  echo "已跳过可选增强。程序可正常运行。"
fi

echo
echo "[2/2] 启动本地服务并打开界面： http://127.0.0.1:8787"
echo
python3 server.py

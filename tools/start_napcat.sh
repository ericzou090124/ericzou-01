#!/usr/bin/env bash
# 拉起本机 NapCat（WebUI 与 OneBot 同一进程）
cd "$(dirname "$0")/.." || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 tools/napcat_ctl.py start
else
  echo "python3 not found"
fi
read -r -p "Press Enter to exit"

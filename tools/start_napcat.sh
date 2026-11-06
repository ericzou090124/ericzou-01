#!/usr/bin/env bash
# 拉起本机 NapCat（WebUI 与 OneBot 同一进程）
cd "$(dirname "$0")/.." || exit 1
python3 tools/napcat_ctl.py start

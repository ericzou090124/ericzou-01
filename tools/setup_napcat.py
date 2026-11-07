# -*- coding: utf-8 -*-
"""NapCat 网关一键自检 / 修复 / 启动（可单独双击 tools/setup_napcat.bat）。

用法：
    python tools/setup_napcat.py             # 体检 + 自动修配置（不启动）
    python tools/setup_napcat.py --check    # 纯只读体检
    python tools/setup_napcat.py --start    # 体检 + 修配置 + 拉起 NapCat
    python tools/setup_napcat.py --qr       # 修配置 + 拉起并等二维码出现
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import napcat_launch, napcat_setup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只体检，不修改任何配置")
    ap.add_argument("--start", action="store_true", help="体检后拉起 NapCat")
    ap.add_argument("--qr", action="store_true", help="拉起并等待二维码出现")
    a = ap.parse_args()

    print("=" * 56)
    print("  NapCat 网关自检与自动配置")
    print("=" * 56)
    if a.check:
        d = napcat_setup.inspect()
        print(f"已安装      : {'是' if d['installed'] else '否'}")
        print(f"运行时目录  : {d['runtime_dir'] or '-'}")
        print(f"启动脚本    : {d['launcher'] or '-'}")
        print(f"WebUI 配置  : {d['webui_config'] or '-'} (host={d['webui_host']}, port={d['webui_port']})")
        print(f"OneBot 配置 : {', '.join(d['onebot_configs']) or '-'} (HTTP={d['onebot_http_enabled']}, port={d['onebot_port']})")
        print(f"二维码缓存  : {d['qrcode_cache'] or '-'}")
        print(f"端口状态    : 6099={'在线' if d['webui_online'] else '离线'} / 3000={'在线' if d['onebot_online'] else '离线'}")
        for i in d["issues"]:
            print("  [待修] " + i)
        for w in d["warnings"]:
            print("  [提醒] " + w)
        if not d["issues"] and not d["warnings"]:
            print("  全部正常 ✅")
        return 0

    d = napcat_setup.ensure(fix=True, start=False)
    print(f"已安装      : {'是' if d['installed'] else '否'}")
    print(f"运行时目录  : {d['runtime_dir']}")
    print(f"启动脚本    : {d['launcher'] or '（首次启动后生成）'}")
    print(f"端口状态    : 6099={'在线' if d['webui_online'] else '离线'} / 3000={'在线' if d['onebot_online'] else '离线'}")
    for f in d["fixed"]:
        print("  [已修复] " + f)
    for i in d["issues"]:
        print("  [待处理] " + i)
    for w in d["warnings"]:
        print("  [提醒] " + w)
    if d.get("needs_restart"):
        print("  配置已变更，NapCat 下次启动后生效（当前进程不受影响）。")
    if d.get("report"):
        print("自检报告    : " + d["report"])

    if not d["installed"]:
        print("")
        print("本机还没装 NapCat。两种安装方式：")
        print("  A. 在 WorkBuddy 里启用 OmniQQ 插件（自带 NapCat 运行时，推荐）")
        print("  B. 到 https://napneko.github.io/ 下载 Windows 一键包并运行一次 napcat.bat")
        print("  装好后重新运行本脚本，程序会自动完成配置。")
        return 2

    if a.start or a.qr:
        print("")
        print("正在拉起 NapCat …")
        r = napcat_launch.start(wait_qr=a.qr)
        print("  " + (r.get("msg") or r.get("error") or ""))
        if a.qr:
            print("  二维码就绪：" + ("是" if r.get("qr_ready") else "尚未生成，稍后在登录页点「刷新二维码」"))
        if not r.get("ok"):
            return 3

    print("")
    print("下一步：双击 start.bat，打开 http://127.0.0.1:8787 →「QQ 登录」直接扫码。")
    print("       不需要打开 NapCat 控制台，二维码和刷新都在登录页完成。")
    return 0 if d["ok"] else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        code = 1
    try:
        input("按回车退出…")
    except (EOFError, KeyboardInterrupt):
        pass
    sys.exit(code)

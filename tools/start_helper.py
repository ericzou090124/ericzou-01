# -*- coding: utf-8 -*-
"""资源管理 · 启动本地服务（中文提示放在 Python 里，避开 .bat 中文乱码）。

被仓库根目录的 start.bat 调用：定位 server.py、打开界面、前台运行服务。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

BASE = "http://127.0.0.1:8787"


def find_root() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.dirname(here)):
        for dirpath, _dirs, files in os.walk(base):
            if "server.py" in files:
                return dirpath
    return None


def main() -> None:
    root = find_root()
    if not root:
        print("[错误] 没有找到 server.py，请确认本文件与 server.py 在同一程序目录。")
        input("按回车退出…")
        sys.exit(1)

    os.chdir(root)
    py = sys.executable

    print("正在启动「资源管理」本地服务…")
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "资源管理")
    except Exception:
        desktop = "桌面/资源管理"
    print("统一资源库：" + desktop)
    print("界面地址： " + BASE)
    print("（关闭本窗口即停止服务；本服务仅监听本机 127.0.0.1）")
    print("")
    time.sleep(1)
    try:
        webbrowser.open(BASE)
    except Exception:
        pass
    try:
        subprocess.run([py, os.path.join(root, "server.py")], check=False)
    except KeyboardInterrupt:
        pass
    input("服务已停止，按回车退出…")


if __name__ == "__main__":
    main()

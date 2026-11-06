# -*- coding: utf-8 -*-
"""资源管理 · 一键安装与启动（中文提示全部放在 Python 里，避开 .bat 的中文乱码问题）。

被仓库根目录的 install.bat 调用：检查 Python、按需安装可选增强、启动本地服务并打开界面。
会自动定位 server.py（兼容解压后多一层文件夹的情况）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

BASE = "http://127.0.0.1:8787"


def find_root() -> str | None:
    """从本文件出发，递归查找包含 server.py 的目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.dirname(here)):
        for dirpath, _dirs, files in os.walk(base):
            if "server.py" in files:
                return dirpath
    return None


def main() -> None:
    root = find_root()
    if not root:
        print("")
        print("[错误] 没有找到 server.py。")
        print("请先把整个压缩包解压到一个文件夹，然后双击该文件夹里的 install.bat。")
        print("不要直接在压缩包（.zip）里双击运行本程序。")
        input("按回车退出…")
        sys.exit(1)

    os.chdir(root)
    py = sys.executable

    print("=" * 44)
    print("  资源管理 · 一键安装与启动")
    print("=" * 44)
    print("")

    print("[1/2] 依赖检查：核心功能只用 Python 标准库，无需安装任何包。")
    print("")
    ans = input("是否安装可选增强（PDF 正文抽取 / 本机渲染二维码）？建议装 [Y/n]：").strip().lower()
    if ans in ("", "y"):
        req = os.path.join(root, "requirements-optional.txt")
        if os.path.exists(req):
            print("正在安装可选增强（可能需要一两分钟，请耐心等待）…")
            rc = subprocess.run([py, "-m", "pip", "install", "-r", req], check=False)
            if rc.returncode != 0:
                print("[提示] 可选增强安装失败，程序仍可使用基础功能（PDF 只登记元数据）。")
        else:
            print("[提示] 未找到 requirements-optional.txt，跳过可选增强。")
    else:
        print("已跳过可选增强。程序可正常运行（PDF 只登记元数据，二维码用 NapCat 缓存图）。")

    print("")
    print("[2/2] 启动本地服务并打开界面…")
    print("界面地址： " + BASE)
    print("（关闭本窗口即停止服务；本服务仅监听本机 127.0.0.1）")
    print("")
    time.sleep(2)
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

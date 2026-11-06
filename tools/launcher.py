# -*- coding: utf-8 -*-
"""统一的本地服务启动逻辑（被 install_helper / start_helper 共用）。

关键点：服务以「独立控制台窗口」启动（Windows 下 CREATE_NEW_CONSOLE），
这样关闭「启动器」窗口不会把服务一起杀掉——这是修复「扫码登录后页面加载失败」
（ERR_CONNECTION_REFUSED）的根因。
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request

BASE = "http://127.0.0.1:8787"


def server_up(timeout: float = 2) -> bool:
    """探测本地服务是否已在响应 /api/health。"""
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            BASE + "/api/health", timeout=timeout).read()
        return True
    except Exception:
        return False


def port_listening(host: str = "127.0.0.1", port: int = 8787) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def launch_server(py: str, root: str) -> bool:
    """以独立窗口启动服务；返回是否成功拉起。

    启动器（install.bat / start.bat）退出后，服务窗口依旧存活。
    """
    serve = os.path.join(root, "server.py")
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    try:
        subprocess.Popen([py, serve], cwd=root, creationflags=flags)
    except Exception as e:  # 极少数系统不支持该标志，回退到普通子进程
        print("[warn] 独立窗口启动失败，改用普通方式启动：" + str(e))
        subprocess.Popen([py, serve], cwd=root)
    # 轮询健康接口，最多等约 20 秒
    for _ in range(40):
        if server_up(2):
            return True
        time.sleep(0.5)
    return False

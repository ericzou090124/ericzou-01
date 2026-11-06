"""一键登录入口：确保本地服务在跑，然后用默认浏览器打开 QQ 网页扫码登录页。

配合仓库根目录的「一键登录.bat」双击使用；不依赖第三方库。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8787"
LOGIN_URL = BASE + "/login"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def port_listening() -> bool:
    """端口已在监听就不要再启动一个服务实例，避免端口冲突。"""
    try:
        with socket.create_connection(("127.0.0.1", 8787), timeout=1):
            return True
    except OSError:
        return False


def alive(retries: int = 2) -> bool:
    for _ in range(retries):
        try:
            _OPENER.open(BASE + "/api/health", timeout=6).read()
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    if not alive():
        if port_listening():
            # 服务正忙（例如刚启动、或健康检查暂时慢），仍直接打开登录页
            print("服务已在监听，健康检查暂未响应，直接打开登录页…")
        else:
            print("本地服务未运行，正在启动…")
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                             cwd=str(ROOT), creationflags=flags)
            for _ in range(30):
                if alive(retries=1):
                    break
                time.sleep(0.6)
            if not port_listening():
                print("服务启动失败：请在项目目录手动运行 python server.py 后重试。")
                return
    print("已打开 QQ 网页扫码登录：" + LOGIN_URL)
    print("用手机 QQ 扫码 → 确认登录 → 页面会自动恢复在线来源并跳回资源管理器。")
    webbrowser.open(LOGIN_URL)


if __name__ == "__main__":
    main()

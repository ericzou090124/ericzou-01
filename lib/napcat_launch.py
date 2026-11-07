"""定位并拉起本机 NapCat（WebUI 与 OneBot 同一进程）。

v3.0.0：路径定位统一交给 napcat_setup（安装自检用的也是它，避免两份清单漂移）；
探活同时看 6099 / 3000 两个端口，任一就绪即视为网关已起；支持等二维码落盘。
启动只在「用户打开登录页 / 点刷新二维码 / 显式点启动」时触发。
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

from . import napcat_setup

_DETACHED = 0x00000008  # DETACHED_PROCESS：脱离父控制台，独立窗口运行


def find_runtime() -> str | None:
    p = napcat_setup.launcher_path()
    return str(p) if p else None


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def is_running(port: int | None = None) -> bool:
    """任一网关端口就绪即算运行；传 port 时只查指定端口。"""
    if port is not None:
        return _port_open(port)
    return _port_open(6099) or _port_open(3000)


def qrcode_path() -> str:
    p = napcat_setup.qrcode_cache()
    return str(p) if p else ""


def start(timeout: int = 40, wait_qr: bool = False) -> dict:
    """拉起 NapCat。已运行则直接返回；否则启动并等待网关端口就绪。

    wait_qr=True 时额外等 NapCat 把二维码写到 cache/qrcode.png（最多 15 秒）。
    """
    if is_running():
        return {"ok": True, "already": True,
                "msg": "NapCat 已在运行，二维码会直接显示在本页。",
                "webui_online": _port_open(6099), "onebot_online": _port_open(3000)}
    bat = find_runtime()
    if not bat:
        return {"ok": False, "error": "找不到 NapCat 启动脚本。请先双击 install.bat / tools/setup_napcat.bat 完成安装与配置。",
                "need_install": True}
    try:
        subprocess.Popen(
            ["cmd", "/c", bat], cwd=os.path.dirname(bat),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_DETACHED,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"启动失败：{e}"}

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_running():
            result = {"ok": True, "started": True, "launcher": bat,
                       "webui_online": _port_open(6099), "onebot_online": _port_open(3000),
                       "msg": "NapCat 已拉起，二维码正在生成，本页会自动显示。"}
            if wait_qr:
                q = time.time() + 15
                while time.time() < q:
                    if qrcode_path() or _port_open(6099):
                        result["qr_ready"] = True
                        break
                    time.sleep(0.8)
                result.setdefault("qr_ready", False)
            return result
        time.sleep(1.2)
    return {"ok": False, "launcher": bat,
            "error": f"已尝试启动，但 {timeout} 秒内网关端口仍未就绪。QQ 可能正在登录或启动较慢，"
                     "请稍后再点「刷新二维码」；也可以双击 tools/setup_napcat.bat 查看自检报告。"}


def webui_url() -> str:
    """仅内部诊断使用；产品界面已不再提供这个控制台入口。"""
    return f"http://127.0.0.1:{6099}/webui"

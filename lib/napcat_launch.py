"""定位并拉起本机 NapCat（WebUI 与 OneBot 同一进程）。

供登录页「启动 NapCat」按钮 / 主界面离线提示调用。
- 只在用户显式触发时启动；不读取、不输出任何令牌。
- 复用 NapCat 自身的 napcat.bat（OmniQQ-MCP 部署的运行时）。
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

_LOCAL = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
_CANDIDATES = [
    _LOCAL / "OmniQQ-MCP" / "napcat_runtime" / "shell_node" / "napcat.bat",
    _LOCAL / "napcat" / "napcat.bat",
    Path.home() / "napcat" / "napcat.bat",
    Path("C:/NapCatQQ/napcat.bat"),
    Path("D:/NapCatQQ/napcat.bat"),
]
_WEBUI_PORT = 6099
_DETACHED = 0x00000008  # DETACHED_PROCESS：脱离父控制台，独立窗口运行


def find_runtime() -> str | None:
    for p in _CANDIDATES:
        try:
            if p.is_file():
                return str(p)
        except Exception:
            pass
    # 兜底：在 LOCALAPPDATA 下递归找一个 napcat.bat
    try:
        for root, _dirs, files in os.walk(_LOCAL):
            if "napcat.bat" in files:
                return str(Path(root) / "napcat.bat")
    except Exception:
        pass
    return None


def is_running(port: int = _WEBUI_PORT) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.5)
        s.close()
        return True
    except Exception:
        return False


def start(timeout: int = 40) -> dict:
    """拉起 NapCat。已运行则直接返回；否则启动并最多等待 timeout 秒让 WebUI 端口就绪。"""
    if is_running():
        return {"ok": True, "already": True, "msg": "NapCat 已在运行，直接刷新即可。"}
    bat = find_runtime()
    if not bat:
        return {"ok": False, "error": "找不到 NapCat 启动脚本（napcat.bat）。请确认 NapCat 已安装；"
                                       "或手动打开控制台 http://127.0.0.1:6099/webui 登录。"}
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
            return {"ok": True, "started": True,
                    "msg": "已拉起 NapCat，正在初始化 WebUI，请稍候刷新页面即可看到二维码。"}
        time.sleep(1.5)
    return {"ok": False, "error": f"已尝试启动，但 {timeout} 秒内 6099 端口仍未就绪。"
                                   "NapCat 可能正在登录 QQ 或启动较慢，请稍后点「刷新二维码」重试；"
                                   "也可手动打开控制台 http://127.0.0.1:6099/webui。"}


def webui_url() -> str:
    return "http://127.0.0.1:6099/webui"

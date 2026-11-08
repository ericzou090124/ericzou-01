"""定位并拉起本机 NapCat（WebUI 与 OneBot 同一进程）。

v3.0.0：路径定位统一交给 napcat_setup（安装自检用的也是它，避免两份清单漂移）；
探活同时看 6099 / 3000 两个端口，任一就绪即视为网关已起；支持等二维码落盘。
启动只在「用户打开登录页 / 点刷新二维码 / 显式点启动」时触发。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

from . import napcat_setup, qq

# v3.6.0：NapCat 需要自己的控制台（会往控制台打印二维码 / 日志）。
# 旧版用 DETACHED_PROCESS 无控制台启动，cmd.exe 活着但 node 子进程立刻退出，
# 于是「已登录却一直卡在扫码页」。改成独立控制台 + 隐藏窗口。
_NEW_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE


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
    """任一网关端口就绪即算运行；传 port 时只查指定端口。

    注意：这是「进程/网关是否起来」的判据，**不等于群文件接口可用**。
    WebUI 6099 在线但 OneBot 3000 没起时，这里仍为 True —— 这正是
    v3.5.0 「已登录却一直卡在扫码页」的根因，必须另用 onebot_running()。
    """
    if port is not None:
        return _port_open(port)
    return _port_open(6099) or _port_open(3000)


def onebot_port() -> int:
    try:
        return int(str(qq.BASE).rsplit(":", 1)[-1].split("/")[0])
    except (ValueError, IndexError):
        return 3000


def onebot_running() -> bool:
    """群文件接口（OneBot HTTP）是否真正可用：既探端口，也验 /get_login_info。"""
    return qq.online()


def qrcode_path() -> str:
    p = napcat_setup.qrcode_cache()
    return str(p) if p else ""


def start(timeout: int = 40, wait_qr: bool = False, force: bool = False,
          require_onebot: bool = False, uin: str = "") -> dict:
    """拉起 NapCat。

    force=True 时忽略「已在运行」直接再启动一份（配合 restart() 先杀旧进程）。
    require_onebot=True 时必须等 OneBot 3000 也起来才算成功 —— 用户要的是
    群文件能用，而不是只把 WebUI 拉起来又卡在扫码页。
    """
    if not force and is_running() and (not require_onebot or onebot_running()):
        return {"ok": True, "already": True,
                "msg": "NapCat 已在运行，二维码会直接显示在本页。",
                "webui_online": _port_open(6099), "onebot_online": onebot_running()}
    bat = find_runtime()
    if not bat:
        return {"ok": False, "error": "找不到 NapCat 启动脚本。请先双击 install.bat / tools/setup_napcat.bat 完成安装与配置。",
                "need_install": True}
    uin = str(uin or "").strip()
    args = ["cmd", "/c", bat]
    if uin.isdigit() and 5 <= len(uin) <= 11:
        args += ["-q", uin]  # NapCat 原生免扫码快速登录，比 WebUI 接口可靠
    try:
        kw = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE：有控制台但不弹窗打扰用户
            kw = {"creationflags": _NEW_CONSOLE, "startupinfo": si}
        subprocess.Popen(
            args, cwd=os.path.dirname(bat),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"启动失败：{e}"}

    ready = (lambda: is_running() and (not require_onebot or onebot_running()))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ready():
            result = {"ok": True, "started": True, "launcher": bat,
                       "webui_online": _port_open(6099), "onebot_online": onebot_running(),
                       "msg": ("NapCat 已重启，群文件接口已就绪，二维码/登录态会直接显示在本页。"
                               if require_onebot else "NapCat 已拉起，二维码正在生成，本页会自动显示。")}
            if wait_qr:
                q = time.time() + 15
                while time.time() < q:
                    if qrcode_path() or _port_open(6099):
                        result["qr_ready"] = True
                        break
                    time.sleep(0.8)
                result.setdefault("qr_ready", False)
            return result
        time.sleep(1.0)
    return {"ok": False, "launcher": bat, "webui_online": _port_open(6099),
            "onebot_online": onebot_running(),
            "error": (f"已尝试启动，但 {timeout} 秒内群文件接口（OneBot {onebot_port()}）仍未就绪。"
                      if require_onebot else
                      f"已尝试启动，但 {timeout} 秒内网关端口仍未就绪。QQ 可能正在登录或启动较慢，"
                      "请稍后再点「刷新二维码」；也可以双击 tools/setup_napcat.bat 查看自检报告。")}


def _napcat_pids() -> list[int]:
    """只找 NapCat 运行时自己的 node/cmd 进程，绝不碰 QQ.exe 或其它 node 程序。"""
    if not os.name == "nt":
        return []
    ps = ("Get-CimInstance Win32_Process | Where-Object { "
          "$_.CommandLine -like '*napcat_runtime*shell_node*' -and "
          "($_.Name -eq 'node.exe' -or $_.Name -eq 'cmd.exe') -and "
          "($_.CommandLine -like '*napcat.mjs*' -or $_.CommandLine -like '*index.js*' "
          "-or $_.CommandLine -like '*napcat.bat*') } | "
          "Select-Object ProcessId | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=20)
        data = json.loads((r.stdout or "").strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        return [int(x["ProcessId"]) for x in data if isinstance(x, dict) and x.get("ProcessId")]
    except Exception:  # noqa: BLE001
        return []


def restart(uin: str = "", timeout: int = 45, require_onebot: bool = True,
            force: bool = False) -> dict:
    """强制重启本机 NapCat，并等到 OneBot 群文件接口真正可用。

    解决 v3.5.0 的真实故障：WebUI 6099 在线、QQ 已登录，但 OneBot 3000 没起来，
    旧的 start() 因「已在运行」直接返回，登录页永远卡在「等待扫码 / 无法重复登录」。
    """
    steps: list[str] = []
    if onebot_running() and not force:
        return {"ok": True, "already": True, "onebot_online": True,
                "steps": ["群文件接口本来就在线，无需重启"], "restarted": False}
    pids = _napcat_pids()
    if pids:
        steps.append(f"结束卡住的 NapCat 进程 {len(pids)} 个（只影响 NapCat，不动 QQ 客户端）")
        kill = ("$ids = @(" + ",".join(str(p) for p in pids) + "); "
                "foreach ($i in $ids) { Stop-Process -Id $i -Force -ErrorAction SilentlyContinue }")
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", kill],
                           capture_output=True, text=True, timeout=20)
        except Exception:  # noqa: BLE001
            pass
        # 等端口释放，否则新进程可能因端口占用立刻退出
        for _ in range(8):
            if not _port_open(6099):
                break
            time.sleep(0.6)
    else:
        steps.append("未发现卡住的 NapCat 进程，直接拉起")
    launched = start(timeout=timeout, force=True,
                     require_onebot=require_onebot, uin=uin)
    steps.append("重新拉起 NapCat，等待群文件接口就绪" if launched.get("ok")
                 else ("拉起失败：" + str(launched.get("error") or "")[:120]))
    return {"ok": bool(launched.get("ok")), "restarted": bool(pids),
            "killed": len(pids), "onebot_online": onebot_running(),
            "webui_online": _port_open(6099), "uin": str(uin or ""),
            "start": launched, "steps": steps,
            "error": "" if launched.get("ok") else str(launched.get("error") or "")}


def webui_url() -> str:
    """仅内部诊断使用；产品界面已不再提供这个控制台入口。"""
    return f"http://127.0.0.1:{6099}/webui"

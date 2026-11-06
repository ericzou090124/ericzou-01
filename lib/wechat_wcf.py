"""微信（群文件）可选数据源：基于 GitHub 成熟方案 WeChatFerry（PyPI: wcferry）的「监听式」适配器。

重要前提（与 QQ/NapCat 不同）：
- 微信没有「列出群文件全目录」的开放接口，也无法读取加密聊天数据库。
- WeChatFerry 通过本机注入「微信 3.9.x」进程暴露本地 RPC。本模块**只在**以下前提下工作：
  1) 用户在 config 显式开启 sources.wechat.wcf.enabled；
  2) 用户自行安装并运行 WeChatFerry 客户端 + 微信 3.9.x（且已登录）；
  3) 用户指定要监听的群（wxid 列表）。
- 本模块**绝不读取任何加密聊天数据库**，只通过 RPC 接收「文件/附件」消息，并把用户所选群内的
  附件下载/登记到统一资源目录。默认关闭；wcferry 未安装时 status 给出明确指引。
- 使用本功能需用户自行承担平台合规责任（本项目只做本地、授权、只读式采集）。

集成方式对齐 qq.py：暴露 available / status / start_capture / stop_capture，使 server 可像刷新 QQ 一样
启动「微信监听采集」，把捕获到的文件行 upsert 进 catalog。
"""
from __future__ import annotations

import json
import os
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config

# 微信消息类型（appmsg）中代表「文件/附件」的 type 值
_FILE_APPMSG_TYPES = {"6", "5", "8"}  # 6=文件 5=链接/名片(部分) 8=表情包外的附件；以 xml 中 <type> 为准


def available() -> bool:
    try:
        import wcferry  # noqa: F401
        return True
    except Exception:
        return False


def _wcf_client(cfg):
    from wcferry import Wcf
    wcf = (cfg.get("sources") or {}).get("wechat", {}).get("wcf", {}) or {}
    host = wcf.get("host", "127.0.0.1")
    port = int(wcf.get("port", 10086))
    try:
        return Wcf(host=host, port=port)
    except TypeError:
        # 旧版 wcferry 的 Wcf() 不接受参数
        return Wcf()


def _xml_text(xml: str, tag: str) -> str:
    try:
        root = ET.fromstring(xml)
    except Exception:
        return ""
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == tag and el.text:
            return el.text.strip()
    return ""


def _parse_size(s: str) -> int:
    try:
        return int(float(s))
    except Exception:
        return 0


def _fmt(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return ""
    for unit, base in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= base:
            return f"{n / base:.1f} {unit}"
    return f"{n} B"


def status(cfg: dict) -> dict:
    w = (cfg.get("sources") or {}).get("wechat", {}) or {}
    wcf = w.get("wcf", {}) or {}
    out = {
        "enabled": bool(wcf.get("enabled")),
        "available": available(),
        "connected": False, "login": False,
        "rooms": [], "reason": "", "mode": "wechatferry",
    }
    if not wcf.get("enabled"):
        out["reason"] = "未开启：在 config.json 的 sources.wechat.wcf.enabled 设为 true，并安装 wcferry、运行 WeChatFerry 客户端 + 微信 3.9.x 登录后可用"
        return out
    if not out["available"]:
        out["reason"] = "未安装 wcferry：pip install wcferry（另需 WeChatFerry 客户端 + 微信 3.9.x 并登录）"
        return out
    try:
        c = _wcf_client(cfg)
        out["connected"] = True
        try:
            out["login"] = bool(c.is_login())
        except Exception:
            out["login"] = False
        if out["login"]:
            try:
                rooms = [x for x in c.get_contacts()
                         if str((x or {}).get("wxid", "")).startswith("@chatroom")]
                out["rooms"] = [{"wxid": x.get("wxid"), "name": x.get("name")} for x in rooms]
            except Exception as e:
                out["reason"] = f"获取群列表失败：{e}"
    except Exception as e:
        out["connected"] = False
        out["reason"] = f"连接 WeChatFerry RPC 失败：{e}（确认 WeChatFerry 客户端已启动且微信 3.9.x 已登录）"
    return out


# ---- 监听群清单持久化：记住用户上次选择的群，重启后无需重选 ----
def _rooms_path() -> Path:
    return config.state("wechat_rooms.json")


def load_rooms() -> list[str]:
    try:
        return [str(x) for x in json.loads(_rooms_path().read_text(encoding="utf-8")) if x]
    except Exception:
        return []


def save_rooms(rooms: list[str]) -> None:
    try:
        _rooms_path().write_text(json.dumps([str(x) for x in (rooms or [])], ensure_ascii=False),
                                 encoding="utf-8")
    except Exception:
        pass


def get_rooms(cfg: dict) -> dict:
    """发现已登录微信下的群列表（仅 available + login 时可用）。"""
    st = status(cfg)
    return {"ok": bool(st.get("login")), "available": st.get("available"),
            "login": st.get("login"), "rooms": st.get("rooms", []), "reason": st.get("reason", "")}


def _room_names(wcf) -> dict:
    try:
        return {c.get("wxid"): c.get("name", "") for c in wcf.get_contacts()}
    except Exception:
        return {}


class _Capture:
    """监听指定群内的文件/附件消息，逐条回调 on_row（由 server 负责 upsert 进 catalog）。"""

    def __init__(self, wcf, rooms: list[str], on_row):
        self.wcf = wcf
        self.rooms = set(rooms or [])
        self.on_row = on_row
        self.names = _room_names(wcf)
        self._running = False

    def _is_file_msg(self, msg) -> bool:
        xml = getattr(msg, "xml", "") or ""
        if "appmsg" in xml:
            t = _xml_text(xml, "type")
            if t in _FILE_APPMSG_TYPES:
                return True
            # 有的文件消息 type 不在白名单但含 attach/file 关键字
            if "attach" in xml.lower() or "file" in xml.lower():
                return True
        return False

    def _to_row(self, msg) -> dict | None:
        xml = getattr(msg, "xml", "") or ""
        name = _xml_text(xml, "title") or (getattr(msg, "content", "") or "")[:60]
        if not name:
            return None
        size = _parse_size(_xml_text(xml, "totallen") or _xml_text(xml, "size") or
                           _xml_text(xml, "totalsize"))
        room = getattr(msg, "roomid", "") or ""
        return {
            "source": "微信(WeChatFerry)",
            "group": self.names.get(room, room),
            "group_id": room,
            "path": name,
            "name": name,
            "folder": "(群文件消息)",
            "ext": os.path.splitext(name)[1].lower(),
            "size_bytes": size,
            "size": _fmt(size),
            "uploader": getattr(msg, "sender", "") or "",
            "uploaded_at": "",
            "file_id": str(getattr(msg, "id", "")),
            "busid": 0,
            "local_path": "",
        }

    def _cb(self, msg) -> None:
        try:
            if not getattr(msg, "from_group", False):
                return
            if self.rooms and getattr(msg, "roomid", "") not in self.rooms:
                return
            if not self._is_file_msg(msg):
                return
            row = self._to_row(msg)
            if row:
                self.on_row(row)
        except Exception:
            pass

    def start(self) -> None:
        self._running = True
        self.wcf.enable_receiving_msg(callback=self._cb)

    def stop(self) -> None:
        self._running = False
        try:
            self.wcf.disable_receiving_msg()
        except Exception:
            pass

    def download(self, msg_id: str) -> str:
        """尽力下载附件到本地，返回路径；失败返回空串（GC 行为由 RPC 决定）。"""
        try:
            paths = self.wcf.download_attachments([msg_id])
            if paths:
                return str(paths[0])
        except Exception:
            pass
        return ""


_capture: "_Capture | None" = None
_capture_lock = threading.Lock()


def start_capture(cfg: dict, rooms: list[str] | None, on_row) -> dict:
    """启动微信监听采集。rooms 为空时回退到已持久化的监听清单；两者皆空则要求先选择群。

    监听范围严格限定为用户显式指定的群，绝不监听全部群，避免误采集无关群文件。
    """
    global _capture
    st = status(cfg)
    if not st.get("enabled"):
        return {"ok": False, "error": st.get("reason", "未开启微信采集")}
    if not st.get("available"):
        return {"ok": False, "error": "未安装 wcferry（pip install wcferry）"}
    if not st.get("login"):
        return {"ok": False, "error": "微信未登录或 WeChatFerry 未连接"}
    effective = list(rooms) if rooms else load_rooms()
    if not effective:
        return {"ok": False, "error": "未指定监听群：请在请求中传 rooms，或先 /api/wechat/wcf/rooms 发现群并保存监听清单"}
    save_rooms(effective)
    with _capture_lock:
        if _capture is not None:
            _capture.stop()
        c = _wcf_client(cfg)
        _capture = _Capture(c, effective, on_row)
        _capture.start()
    return {"ok": True, "rooms": len(effective), "captured": _captured_count()}


def stop_capture() -> dict:
    global _capture
    with _capture_lock:
        if _capture is not None:
            _capture.stop()
            _capture = None
    return {"ok": True, "running": False}


def is_capturing() -> bool:
    with _capture_lock:
        return _capture is not None and _capture._running


_counter = {"n": 0}
_counter_lock = threading.Lock()


def _captured_count() -> int:
    with _counter_lock:
        return _counter["n"]


def _note_captured() -> None:
    with _counter_lock:
        _counter["n"] += 1

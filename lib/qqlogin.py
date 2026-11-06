"""QQ 网页扫码登录（本机 NapCat WebUI 适配层）。

用途：登录态过期时，不再往桌面丢二维码图片，而是由本地网页展示实时二维码，
扫码确认后自动把资源管理器切回在线来源。

安全边界：
- 只访问 127.0.0.1 上的 NapCat WebUI（默认 6099），不访问任何外部二维码服务；
- WebUI token 从本机配置读取，会话凭证只存在本进程内存，绝不下发前端、不写日志；
- 二维码内容（QQ 登录链接）只在本机页面里渲染成图片，不上传、不外发。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import qq

_LOCAL = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
_NAPCAT = _LOCAL / "OmniQQ-MCP" / "napcat_runtime" / "shell_node" / "napcat"
_WEBUI_JSON = _NAPCAT / "config" / "webui.json"
_QR_PNG = _NAPCAT / "cache" / "qrcode.png"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_CRED = {"token": "", "ts": 0.0}
_QR = {"text": "", "image": "", "source": ""}

_PHASE_TEXT = {
    "waiting_qrcode": "等待手机 QQ 扫码",
    "qrcode_scanned": "已扫码，请在手机上确认登录",
    "waiting_confirm": "已扫码，请在手机上确认登录",
    "confirming": "正在确认登录",
    "logging_in": "正在登录，请稍候",
    "core_ready": "登录完成，正在启动群文件接口",
    "offline": "QQ 未登录",
}


def _cfg() -> tuple[str, int, str]:
    """返回 (host, port, token)。配置缺失时给可诊断的异常。"""
    if not _WEBUI_JSON.is_file():
        raise RuntimeError(f"找不到 NapCat WebUI 配置：{_WEBUI_JSON}")
    d = json.loads(_WEBUI_JSON.read_text(encoding="utf-8"))
    host = str(d.get("host") or "127.0.0.1")
    if host in ("::", "0.0.0.0", ""):
        host = "127.0.0.1"
    return host, int(d.get("port") or 6099), str(d.get("token") or "")


def webui_url() -> str:
    try:
        host, port, _ = _cfg()
        return f"http://{host}:{port}/webui"
    except Exception:
        return "http://127.0.0.1:6099/webui"


def _cfg_port() -> int:
    try:
        return _cfg()[1]
    except Exception:
        return 6099


def is_webui_running(host: str = "127.0.0.1", port: int | None = None) -> bool:
    """只做端口探活（不发任何业务请求），用于快速判断 NapCat 是否在线。"""
    import socket
    port = port or _cfg_port()
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        return True
    except Exception:
        return False


def _post(path: str, body: dict, bearer: str = "", timeout: float = 8) -> dict:
    host, port, _ = _cfg()
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(f"http://{host}:{port}{path}",
                                 data=json.dumps(body).encode("utf-8"), headers=headers)
    return json.loads(_OPENER.open(req, timeout=timeout).read().decode("utf-8", "replace"))


def _credential(force: bool = False) -> str:
    """WebUI 登录：SHA256(token + '.napcat') 换会话凭证，缓存 10 分钟。"""
    if not force and _CRED["token"] and time.time() - _CRED["ts"] < 600:
        return _CRED["token"]
    _, _, token = _cfg()
    if not token:
        raise RuntimeError("NapCat WebUI 未配置 token，无法自动登录")
    h = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
    r = _post("/api/auth/login", {"hash": h, "totpCode": ""})
    cred = str((r.get("data") or {}).get("Credential") or "")
    if r.get("code") != 0 or not cred:
        raise RuntimeError(f"WebUI 会话登录失败：{r.get('message') or r}")
    _CRED.update(token=cred, ts=time.time())
    return cred


def _api(path: str, body: dict | None = None, timeout: float = 8) -> dict:
    """带凭证调用 WebUI API；凭证失效自动重新换一次。"""
    body = body or {}
    r = _post(path, body, _credential(), timeout)
    if r.get("code") == -1 and str(r.get("message", "")).lower() == "unauthorized":
        r = _post(path, body, _credential(force=True), timeout)
    return r


def qr_image(text: str) -> tuple[str, str]:
    """把二维码内容渲染成 PNG data URL。优先本机 OpenCV，失败回落到 NapCat 自带图片。"""
    if not text:
        return "", ""
    if _QR["text"] == text and _QR["image"]:
        return _QR["image"], _QR["source"]
    image, source = "", ""
    try:
        import cv2

        raw = cv2.QRCodeEncoder_create().encode(text)
        if raw is None:
            raise RuntimeError("二维码编码失败")
        big = cv2.resize(raw, (raw.shape[1] * 10, raw.shape[0] * 10),
                         interpolation=cv2.INTER_NEAREST)
        big = cv2.copyMakeBorder(big, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
        ok, buf = cv2.imencode(".png", big)
        if not ok:
            raise RuntimeError("二维码 PNG 编码失败")
        image = "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
        source = "opencv"
    except Exception:
        # 没有 OpenCV 时，NapCat 自己也会把当前二维码写到 cache/qrcode.png
        try:
            if _QR_PNG.is_file():
                image = "data:image/png;base64," + base64.b64encode(_QR_PNG.read_bytes()).decode("ascii")
                source = "napcat_cache"
        except Exception:
            pass
    _QR.update(text=text, image=image, source=source)
    return image, source


def status() -> dict:
    """给登录页的一次性快照：二维码、扫码阶段、已保存账号、OneBot 是否恢复。"""
    out = {
        "ok": False, "webui_online": False, "webui_url": webui_url(),
        "need_start": False,
        "is_login": False, "phase": "", "phase_text": "正在连接 NapCat…",
        "qr_key": "", "qr_image": "", "qr_source": "",
        "qr_login_accepted": False, "login_error": "",
        "accounts": [], "onebot_online": False,
        "hint": "", "updated_at": datetime.now().strftime("%H:%M:%S"),
    }
    try:
        r = _api("/api/QQLogin/CheckLoginStatus")
        if r.get("code") != 0:
            raise RuntimeError(str(r.get("message") or r))
        d = r.get("data") or {}
        out["ok"] = True
        out["webui_online"] = True
        out["is_login"] = bool(d.get("isLogin"))
        out["phase"] = str(d.get("loginPhase") or "")
        out["phase_text"] = _PHASE_TEXT.get(out["phase"], out["phase"] or "等待扫码")
        out["qr_login_accepted"] = bool(d.get("qrLoginAccepted"))
        out["login_error"] = str(d.get("loginError") or "")
        # 只把「版本标识」发给前端，登录链接原文不下发页面，降低泄露面
        qr_text = str(d.get("qrcodeurl") or "")
        out["qr_key"] = hashlib.sha256(qr_text.encode("utf-8")).hexdigest()[:16] if qr_text else ""
        if out["is_login"]:
            out["phase_text"] = "登录成功"
            out["onebot_online"] = qq.online()
            if not out["onebot_online"]:
                out["hint"] = "QQ 已登录，群文件接口还在启动，稍等几秒即可自动恢复。"
        elif out["qr_login_accepted"]:
            out["phase_text"] = "已扫码，请在手机上确认登录"
        if qr_text:
            out["qr_image"], out["qr_source"] = qr_image(qr_text)
        try:
            acc = _api("/api/QQLogin/GetQuickLoginListNew").get("data") or []
            out["accounts"] = [{"uin": str(x.get("uin") or ""),
                                "nick": str(x.get("nickName") or ""),
                                "quick": bool(x.get("isQuickLogin"))}
                               for x in acc if isinstance(x, dict) and x.get("uin")]
        except Exception:
            pass
        if not out["qr_image"] and not out["is_login"]:
            out["hint"] = "暂时取不到二维码，请点「刷新二维码」重试；WebUI 控制台也可手动登录。"
    except Exception as e:  # noqa: BLE001
        # 这里是给用户看的提示，绝不能把原始 Python 异常（如 URLError/WinError 10061）
        # 直接暴露到页面上。按错误性质给可操作的指引。
        out["webui_online"] = False
        out["need_start"] = True
        etype = type(e).__name__
        es = str(e)
        if "10061" in es or etype in ("URLError", "ConnectionError", "TimeoutError",
                                       "ConnectionRefusedError", "OSError"):
            out["hint"] = (f"本机 NapCat 没有运行（WebUI 端口 {_cfg_port()} 无响应）。\n"
                           f"点本页「启动 NapCat」按钮即可自动拉起；若没反应也可在浏览器打开 "
                           f"{out['webui_url']} 手动登录。")
        else:
            out["hint"] = (f"无法连接 NapCat WebUI（{etype}）。\n"
                           f"请确认 NapCat 已安装并打开控制台 {out['webui_url']}；"
                           f"若已在运行仍报错，可能是令牌失效，请在控制台重新登录。")
    return out


def refresh_qrcode() -> dict:
    """强制让 QQ 重新生成二维码（过期时用）。"""
    try:
        _api("/api/QQLogin/RefreshQRcode", timeout=15)
        _QR.update(text="", image="", source="")
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True}


def quick_login(uin: str) -> dict:
    """尝试用 NapCat 已缓存凭证免扫码快速登录；凭证失效时仍会回到二维码流程。"""
    if not uin.isdigit() or not (5 <= len(uin) <= 11):
        return {"ok": False, "error": "QQ 号格式不正确"}
    try:
        r = _api("/api/QQLogin/SetQuickLogin", {"uin": uin}, timeout=20)
        return {"ok": r.get("code") == 0, "raw": str(r.get("message") or ""),
                "hint": "已提交快速登录，页面会自动检测登录结果；若凭证同样失效，请改用扫码。"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}

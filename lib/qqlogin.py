"""QQ 登录：本页直出二维码 + 多源冗余 + 自动刷新（v3.0.0 重写）。

用户反馈的两个真实故障：
1. 「打开 NapCat 控制台」入口指向 127.0.0.1:6099/webui，NapCat 未运行时必然
   ERR_CONNECTION_REFUSED —— 这个跑不通的入口已彻底从产品里移除；
2. 二维码只能通过 NapCat 控制台拿到，本页显示「暂时没有可用二维码」。

现在的链路（全部在资源管理器自己的页面里完成，不需要打开任何 NapCat 控制台）：
  - 二维码优先取 NapCat WebUI 的 CheckLoginStatus（6099 在线时）；
  - WebUI 不通时直接读 NapCat 自己写的 cache/qrcode.png；
  - 「刷新二维码」会自动拉起未运行的 NapCat，并等待新二维码出现；
  - 二维码陈旧时本页自动向 QQ 申请新的，不再需要去 NapCat 里刷新；
  - 登录成功以 OneBot /get_login_info 为权威判据，WebUI isLogin 仅作辅助。

安全边界不变：只访问 127.0.0.1，token 从本机配置读取，会话凭证只在进程内存，
二维码内容只在本机渲染成图片，不上传、不经过任何第三方二维码服务。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import napcat_launch, napcat_setup, qq

_NAPCAT_DIR_FALLBACK = (Path(__file__).resolve().parent.parent)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_CRED = {"token": "", "ts": 0.0}
_QR = {"text": "", "image": "", "source": "", "key": "", "ts": 0.0}
_LAST_REFRESH = {"ts": 0.0}
_LOGIN = {"ok": False, "ts": 0.0}
_ACCOUNTS = {"list": [], "ts": 0.0}
_RECOVER = {"ts": 0.0, "result": None}
_ALREADY_LOGGED_IN = re.compile(r"已登录|无法重复登录|already\s*logged|重复登录", re.I)

_PHASE_TEXT = {
    "waiting_qrcode": "等待手机 QQ 扫码",
    "qrcode_scanned": "已扫码，请在手机上确认登录",
    "waiting_confirm": "已扫码，请在手机上确认登录",
    "confirming": "正在确认登录",
    "logging_in": "正在登录，请稍候",
    "core_ready": "登录完成，正在启动群文件接口",
    "offline": "QQ 未登录",
}


# ---------------------------------------------------------------- 本机 WebUI 适配
def _cfg() -> tuple[str, int, str]:
    """(host, port, token)。始终强制本机 IPv4，避免 '::' 绑定导致 127.0.0.1 被拒。"""
    p = napcat_setup.webui_config()
    if not p:
        return "127.0.0.1", 6099, ""
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return "127.0.0.1", 6099, ""
    return "127.0.0.1", int(d.get("port") or 6099), str(d.get("token") or "")


def webui_url() -> str:
    """仅供内部诊断使用；产品界面不再对外暴露这个控制台地址。"""
    _, port, _ = _cfg()
    return f"http://127.0.0.1:{port}/webui"


def _webui_reachable() -> bool:
    import socket
    _, port, _ = _cfg()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def _post(path: str, body: dict, bearer: str = "", timeout: float = 4) -> dict:
    _, port, _ = _cfg()
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode("utf-8"), headers=headers)
    return json.loads(_OPENER.open(req, timeout=timeout).read().decode("utf-8", "replace"))


def _credential(force: bool = False) -> str:
    if not force and _CRED["token"] and time.time() - _CRED["ts"] < 600:
        return _CRED["token"]
    _, _, token = _cfg()
    if not token:
        raise RuntimeError("NapCat WebUI 未配置 token")
    h = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
    r = _post("/api/auth/login", {"hash": h, "totpCode": ""})
    cred = str((r.get("data") or {}).get("Credential") or "")
    if r.get("code") != 0 or not cred:
        raise RuntimeError(f"WebUI 会话登录失败：{r.get('message') or r}")
    _CRED.update(token=cred, ts=time.time())
    return cred


def _api(path: str, body: dict | None = None, timeout: float = 4) -> dict:
    body = body or {}
    r = _post(path, body, _credential(), timeout)
    if r.get("code") == -1 and str(r.get("message", "")).lower() == "unauthorized":
        r = _post(path, body, _credential(force=True), timeout)
    return r


# ---------------------------------------------------------------- 二维码渲染
def _render_text(text: str) -> str:
    """把二维码内容渲染成 PNG data URL：cv2 → qrcode 库 → 空（回落到 NapCat 缓存图）。"""
    if not text:
        return ""
    try:
        import cv2
        raw = cv2.QRCodeEncoder_create().encode(text)
        if raw is not None:
            big = cv2.resize(raw, (raw.shape[1] * 10, raw.shape[0] * 10),
                             interpolation=cv2.INTER_NEAREST)
            big = cv2.copyMakeBorder(big, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
            ok, buf = cv2.imencode(".png", big)
            if ok:
                return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception:
        pass
    try:
        import qrcode
        from io import BytesIO
        im = qrcode.make(text)
        bio = BytesIO()
        im.save(bio, format="PNG")
        return "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode("ascii")
    except Exception:
        return ""


def _cache_qr() -> tuple[str, str, int]:
    """直接读 NapCat 写下的二维码图片。key 用 mtime+size，图片一变就能被前端识别。"""
    p = napcat_setup.qrcode_cache()
    if not p:
        return "", "", 0
    try:
        raw = p.read_bytes()
        if len(raw) < 200 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return "", "", 0
        st = p.stat()
        age = max(0, int(time.time() - st.st_mtime))
        key = f"cache-{st.st_mtime_ns}-{st.st_size}"
        return ("data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                key, age)
    except OSError:
        return "", "", 0


def _qr_pick(webui: dict | None) -> tuple[str, str, str, int]:
    """返回 (image, key, source, age_s)。WebUI 渲染优先，缓存图兜底。"""
    text = str((webui or {}).get("qrcodeurl") or "")
    if text:
        img = _render_text(text)
        if img:
            return img, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "本机渲染", 0
    img, key, age = _cache_qr()
    if img:
        return img, key, "NapCat 二维码", age
    return "", "", "", 0


# ---------------------------------------------------------------- 登录态
def _onebot_login() -> bool:
    """OneBot /get_login_info 是登录成功的权威判据；1.5s 内复用结果避免轮询拖慢页面。"""
    if time.time() - _LOGIN["ts"] < 1.5:
        return _LOGIN["ok"]
    try:
        ok = qq.online()
    except Exception:
        ok = False
    _LOGIN.update(ok=ok, ts=time.time())
    return ok


# ---------------------------------------------------------------- 对外：状态快照
def status() -> dict:
    setup = napcat_setup.status()
    # 直接探一次 WebUI，不依赖端口快照，避免刚启动/探测抖动时误判成"未运行"
    webui_ok = _webui_reachable()
    setup["webui_online"] = bool(setup["webui_online"] or webui_ok)
    setup["running"] = bool(setup["running"] or webui_ok)
    webui = None
    webui_err = ""
    if webui_ok:
        try:
            r = _api("/api/QQLogin/CheckLoginStatus")
            if r.get("code") == 0:
                webui = r.get("data") or {}
            else:
                webui_err = str(r.get("message") or "")[:120]
        except Exception as e:  # noqa: BLE001
            webui_err = type(e).__name__

    login_error = str((webui or {}).get("loginError") or "")
    # v3.6.0：QQ 核心其实已登录时 NapCat 会回「当前账号已登录,无法重复登录」，
    # 但 WebUI isLogin 仍是 false、OneBot 3000 也没起 —— 旧版会一直展示一张
    # 扫了也必然失败的二维码，用户手机点了确认也永远「登录不成功」。
    already_logged_in = bool(_ALREADY_LOGGED_IN.search(login_error))
    webui_is_login = bool((webui or {}).get("isLogin"))
    onebot_online = setup["onebot_online"] or _onebot_login()
    is_login = onebot_online or webui_is_login
    image, key, source, age = ("", "", "", 0) if is_login else _qr_pick(webui)
    if already_logged_in and not onebot_online:
        # 这张码扫了只会得到「无法重复登录」，不要给用户看
        image, key, source = "", "", ""
    # 缓存图超过 3 分钟基本已过期，绝不展示给用户扫（否则会一直提示"二维码失效"）。
    # v3.6.0 更重要的一条：NapCat / WebUI 根本没在线时，本机缓存里那张码是**死码** ——
    # 没有进程在等扫码确认，用户手机点同意也不会有任何反应。旧版在 NapCat 退出后
    # 仍把缓存图渲染成「等待扫码」，正是「明明同意了却一直没登录」的另一半原因。
    qr_offline_discarded = False
    if image and source == "NapCat 二维码" and not webui_ok:
        qr_offline_discarded = True
    qr_stale = False
    if image and source == "NapCat 二维码" and (age > 180 or qr_offline_discarded):
        image, key, source, qr_stale = "", "", "", True

    # 二维码陈旧时自动向 QQ 申请新的（节流：60s 内最多一次），不需要用户去 NapCat 里刷新
    auto_refreshed = False
    if not is_login and not already_logged_in and setup["running"] and (not image or age > 100):
        if time.time() - _LAST_REFRESH["ts"] > 60 and _webui_reachable():
            _LAST_REFRESH["ts"] = time.time()
            try:
                _api("/api/QQLogin/RefreshQRcode", timeout=6)
                auto_refreshed = True
            except Exception:
                pass

    # 快速登录清单 30s 内复用，避免每 1.5s 轮询都打两次 WebUI 接口拖慢页面
    if time.time() - _ACCOUNTS["ts"] > 30 and webui is not None:
        try:
            acc = _api("/api/QQLogin/GetQuickLoginListNew", timeout=3).get("data") or []
            _ACCOUNTS["list"] = [{"uin": str(x.get("uin") or ""), "nick": str(x.get("nickName") or ""),
                                  "quick": bool(x.get("isQuickLogin"))}
                                 for x in acc if isinstance(x, dict) and x.get("uin")]
            _ACCOUNTS["ts"] = time.time()
        except Exception:
            pass
    accounts = list(_ACCOUNTS["list"])
    quick_uin = next((a["uin"] for a in accounts if a.get("quick") and a["uin"].isdigit()), "")
    if not quick_uin:
        quick_uin = (local_quick_uins() or [""])[0]  # 网关没起来时也能给出免扫码入口
    # 「当前账号已登录,无法重复登录」+ 根本没有二维码 = 电脑上 QQ 客户端已占用该账号，
    # 这时反复自动恢复只会一直撞同一堵墙，应引导用户换号 / 退出电脑 QQ。
    account_conflict = already_logged_in and not str((webui or {}).get("qrcodeurl") or "")
    # 自动恢复只在「确实卡住且还有救」时触发；有保存凭证但 QQ 尚未登录时只给手动按钮。
    need_recover = (not onebot_online) and (already_logged_in or webui_is_login) and not account_conflict
    can_recover = (not onebot_online) and (already_logged_in or webui_is_login or bool(quick_uin))

    phase = str((webui or {}).get("loginPhase") or "")
    qr_accepted = bool((webui or {}).get("qrLoginAccepted"))
    if is_login:
        phase_text = "登录成功"
    elif qr_accepted:
        phase_text = "已扫码，请在手机上确认登录"
    else:
        phase_text = _PHASE_TEXT.get(phase, "等待扫码" if image else "等待二维码")

    hint = ""
    recover_hint = ""
    if account_conflict:
        hint = ("当前 QQ 已经在**电脑上的 QQ 客户端**登录，NapCat 不能重复登录同一个账号，"
                "所以手机点了确认也不会成功、页面还会一直显示未登录。"
                "请点上方「退出登录 / 换 QQ 扫码」用另一个 QQ 扫码；"
                "或者先退出电脑 QQ 客户端，再点「一键恢复登录」。")
        recover_hint = "已退出电脑 QQ，重新恢复登录"
    elif need_recover:
        hint = ("QQ 其实已经登录了，但群文件接口（OneBot 3000）没启动，所以电脑上一直显示未登录。"
                "不要再扫这张码（会提示「无法重复登录」）；点下方「一键恢复登录」即可，"
                "程序会自动用已保存的凭证恢复，必要时重启 NapCat。")
        recover_hint = "一键恢复登录（自动用已保存凭证 / 重启 NapCat，约 10~30 秒）"
    elif not setup["installed"]:
        hint = "本机还没检测到 NapCat。请先双击 install.bat（或 tools/setup_napcat.bat）完成安装与配置。"
    elif is_login and not onebot_online:
        hint = "QQ 已登录，群文件接口仍在启动，稍等几秒即可自动恢复。"
    elif not setup["running"]:
        hint = ("NapCat 未运行，页面会自动拉起并生成全新二维码；若没反应，点「刷新二维码」。"
                + ("已丢弃本机缓存的旧二维码（没有进程在等确认，扫了也不会有反应）。"
                   if qr_offline_discarded else ""))
    elif not image:
        hint = ("旧二维码已过期，正在向 QQ 申请新码…" if (qr_stale or auto_refreshed)
                else "暂时没有可用二维码，点「刷新二维码」让 QQ 重新生成一张。")
    elif not setup["webui_online"]:
        hint = "已通过 NapCat 本机二维码缓存直出，扫码与刷新都在本页完成。"

    return {
        "ok": True,
        "napcat_installed": setup["installed"],
        "napcat_running": setup["running"],
        "need_start": not setup["running"],
        "webui_online": setup["webui_online"],          # 兼容旧字段，仅表示网关端口
        "onebot_online": setup["onebot_online"],
        "is_login": is_login,
        "phase": phase, "phase_text": phase_text,
        "qr_image": image, "qr_key": key, "qr_source": source, "qr_age_s": age,
        "qr_stale": qr_stale, "qr_auto_refreshed": auto_refreshed,
        "qr_offline_discarded": qr_offline_discarded,
        "qr_login_accepted": qr_accepted,
        "login_error": login_error,
        "already_logged_in": already_logged_in,
        "account_conflict": account_conflict,
        "need_recover": need_recover,
        "can_recover": can_recover,
        "quick_uin": quick_uin,
        "recover_hint": recover_hint,
        "accounts": accounts,
        "local_uins": local_quick_uins(),
        "hint": hint,
        "setup": setup,
        "webui_error": webui_err,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
    }


# ---------------------------------------------------------------- 对外：刷新 / 拉起
def refresh_qrcode(auto_start: bool = True) -> dict:
    """刷新二维码：NapCat 没跑就自动拉起，跑着就向 QQ 申请新码，然后等待新码出现。

    这是「二维码可以直接刷新」的唯一入口，全程不要求用户打开 NapCat 控制台。
    """
    global _QR
    setup = napcat_setup.status()
    webui_ok = _webui_reachable()
    started = False
    if not (setup["running"] or webui_ok):
        if not auto_start:
            return {"ok": False, "error": "NapCat 未运行"}
        if not setup["installed"]:
            return {"ok": False, "error": "未检测到 NapCat 运行时，请先双击 install.bat 完成安装",
                    "need_install": True}
        from . import napcat_launch
        r = napcat_launch.start(timeout=40)
        if not r.get("ok"):
            return {"ok": False, "error": str(r.get("error") or "启动 NapCat 失败")[:200],
                    "need_install": False}
        started = bool(r.get("started"))

    # 尽力让 QQ 重新出码；WebUI 不通也没关系，NapCat 自己会刷新缓存图
    requested = False
    if _webui_reachable():
        try:
            _api("/api/QQLogin/RefreshQRcode", timeout=8)
            requested = True
        except Exception:
            pass
    _QR.update(text="", image="", source="", key="", ts=0.0)
    _LAST_REFRESH["ts"] = time.time()
    _CRED.update(token="", ts=0.0)

    # 等最多 12 秒让「新」二维码落盘：必须比调用前的缓存图更新，避免把过期旧图当成新码
    before = _cache_qr()[1]
    deadline = time.time() + 12
    found = False
    while time.time() < deadline:
        if _webui_reachable():
            try:
                d = (_api("/api/QQLogin/CheckLoginStatus", timeout=3).get("data") or {})
                if d.get("qrcodeurl") or d.get("isLogin"):
                    found = True
                    break
            except Exception:
                pass
        _img, key, age = _cache_qr()
        if _img and age < 90 and (not before or key != before):
            found = True
            break
        time.sleep(0.8)

    msg = ("已自动启动 NapCat 并取得新二维码，请用手机 QQ 扫码。" if started
           else "已向 QQ 申请新二维码，本页会自动换成最新的。")
    if not found:
        msg = "已提交刷新请求，二维码正在生成；本页会持续自动检测，请稍候几秒。"
    return {"ok": True, "started": started, "requested": requested, "qr_ready": found, "msg": msg}


def local_quick_uins() -> list[str]:
    """NapCat 网关没起来时，也能从 QQNT 本机账号目录读出可快速登录的 QQ 号。

    形如 ~/Documents/Tencent Files/<QQ号>/，只取纯数字 5~11 位目录名，
    不读任何聊天数据、不碰加密数据库。
    """
    # 本工具自己的 OneBot 配置是按账号命名的，优先用它，避免登错号
    import glob
    preferred: list[str] = []
    for f in glob.glob(qq.CONFIG_GLOB):
        name = Path(f).stem.replace("onebot11_", "")
        if name.isdigit() and 5 <= len(name) <= 11:
            preferred.append(name)
    found: list[tuple[float, str]] = []
    for base in (Path.home() / "Documents" / "Tencent Files",
                 Path.home() / "文档" / "Tencent Files"):
        if not base.is_dir():
            continue
        try:
            for d in base.iterdir():
                if d.is_dir() and d.name.isdigit() and 5 <= len(d.name) <= 11:
                    found.append((d.stat().st_mtime, d.name))
        except OSError:
            continue
    rest = [name for _ts, name in sorted(found, reverse=True)
            if name not in preferred]
    return list(dict.fromkeys(preferred + rest))


def _restart_via_webui() -> bool:
    """优先用 NapCat 自带的 RestartNapCat 接口重启，比杀进程干净得多。

    该请求会在重启过程中被断开，因此连接异常也视为「已提交」，由调用方轮询恢复。
    """
    if not _webui_reachable():
        return False
    try:
        _api("/api/QQLogin/RestartNapCat", timeout=5)
    except Exception:  # noqa: BLE001 - 重启时连接被主动断开属预期
        pass
    _CRED.update(token="", ts=0.0)
    return True


def switch_account(uin: str = "") -> dict:
    """退出当前 QQ / 换号重新扫码：清自动登录 → 干净重启 NapCat → 全新二维码。

    不能走 WebUI 的 RestartNapCat：它会**继承旧的 `-q <旧QQ号>` 启动参数**，
    重启后依旧尝试登录旧账号并再次报「无法重复登录」。这里只结束 NapCat
    自己的进程树再重新拉起，不传 -q（或传用户选的 uin），才能真正回到扫码态。
    全程不删除任何 QQ 账号数据、不动 QQ 客户端。
    """
    from . import napcat_launch
    steps: list[str] = []
    uin = str(uin or "").strip()
    if _webui_reachable():
        try:
            _api("/api/QQLogin/SetQuickLoginQQ", {"uin": ""}, timeout=5)
            steps.append("已关闭「自动登录旧账号」，重启后不会自动登回原来的 QQ")
        except Exception:  # noqa: BLE001
            steps.append("自动登录开关未响应，继续强制重启")
    rr = napcat_launch.restart(uin=uin, timeout=20, require_onebot=False, force=True)
    steps += rr.get("steps") or []
    steps.append("已用" + (f"账号 {uin} " if uin.isdigit() else "「全新扫码」")
                 + "模式重新启动 NapCat（不继承旧账号参数）")

    back = False
    for _ in range(15):
        if _webui_reachable():
            back = True
            break
        time.sleep(1.0)
    if back and not uin.isdigit():
        try:
            _api("/api/QQLogin/RefreshQRcode", timeout=6)
            steps.append("已向 QQ 申请全新二维码，用新账号扫码即可")
        except Exception:  # noqa: BLE001
            steps.append("新二维码正在生成，登录页会自动显示")
    elif not back:
        steps.append("WebUI 还在启动，登录页会持续自动检测")
    _CRED.update(token="", ts=0.0)
    _ACCOUNTS.update(list=[], ts=0.0)
    _LOGIN.update(ok=False, ts=0.0)
    _QR.update(text="", image="", source="", key="", ts=0.0)
    _LAST_REFRESH["ts"] = time.time()
    _RECOVER.update(ts=0.0, result=None)
    return {"ok": True, "need_scan": True, "webui_online": _webui_reachable(),
            "onebot_online": qq.online(), "login_url": "/login", "steps": steps,
            "msg": "已退出当前 QQ 的登录态，请用另一个 QQ 扫码登录。"}


def recover(uin: str = "") -> dict:
    """v3.6.0：把「手机已同意、电脑却一直没登录成功」的状态真正恢复过来。

    症状：NapCat WebUI 6099 在线、QQ 核心已登录（loginError=当前账号已登录,
    无法重复登录），但 OneBot 3000 没起，/get_login_info 永远失败；旧版登录页
    只会继续展示一张扫了必然失败的二维码，并每 2.5 秒空转轮询。

    恢复顺序（都只操作本机，不动 QQ 账号数据）：
      1) 已在线 → 直接成功；
      2) 用本机已保存凭证 SetQuickLogin（免扫码），等最多 6 秒；
      3) 仍不在线 → 只结束 NapCat 自己的进程树并重新拉起，等 OneBot 真正可用。
    失败结果 25 秒内复用，避免前端轮询把 NapCat 反复重启。
    """
    now = time.time()
    prev = _RECOVER.get("result")
    if isinstance(prev, dict) and not prev.get("ok") and now - _RECOVER["ts"] < 25:
        return dict(prev, throttled=True)

    if qq.online():
        return {"ok": True, "already": True, "onebot_online": True,
                "steps": ["群文件接口本来就在线，无需恢复"], "restarted": False}
    steps: list[str] = []
    uin = str(uin or "").strip()
    if not uin.isdigit():
        uin = next((a["uin"] for a in _ACCOUNTS["list"]
                    if a.get("quick") and str(a.get("uin") or "").isdigit()), "")
    if not uin.isdigit() and _webui_reachable():
        # 进程刚启动时内存缓存为空，直接问一次 WebUI，别把「有凭证」误判成「没凭证」
        try:
            acc = _api("/api/QQLogin/GetQuickLoginListNew", timeout=3).get("data") or []
            uin = next((str(x.get("uin") or "") for x in acc
                        if isinstance(x, dict) and x.get("isQuickLogin")
                        and str(x.get("uin") or "").isdigit()), "")
        except Exception:
            pass
    if not uin.isdigit():
        uin = (local_quick_uins() or [""])[0]

    if uin and _webui_reachable():
        try:
            _api("/api/QQLogin/SetQuickLogin", {"uin": uin}, timeout=6)
            steps.append(f"已用本机保存的凭证快速登录 {uin}（免扫码）")
        except Exception as e:  # noqa: BLE001
            steps.append(f"快速登录无响应（{type(e).__name__}），改用重启 NapCat")
        for _ in range(6):
            if qq.online():
                break
            time.sleep(1.0)
    restarted = killed = 0
    if not qq.online() and _restart_via_webui():
        steps.append("已通过 NapCat 自带接口重启（不结束 QQ 客户端）")
        restarted = 1
        for _ in range(20):
            if qq.online():
                break
            time.sleep(1.0)
    if not qq.online():
        rr = napcat_launch.restart(uin=uin, timeout=35)
        steps += rr.get("steps") or []
        restarted = max(restarted, 1 if rr.get("restarted") else 0)
        killed = int(rr.get("killed") or 0)
    ok = qq.online()
    if ok:
        result = {"ok": True, "already": False, "onebot_online": True,
                  "webui_online": _webui_reachable(), "uin": uin,
                  "restarted": bool(restarted), "killed": killed,
                  "steps": steps or ["群文件接口已恢复"], "error": ""}
    else:
        result = {"ok": False, "already": False, "onebot_online": False,
                  "webui_online": _webui_reachable(), "uin": uin,
                  "restarted": bool(restarted), "killed": killed,
                  "steps": steps,
                  "error": "群文件接口仍未就绪：请确认 QQ 已登录，或点「退出登录 / 换 QQ 扫码」重新登录一次"}
    _RECOVER.update(ts=now, result=result)
    _ACCOUNTS["ts"] = 0.0
    _LOGIN["ts"] = 0.0
    return result


def quick_login(uin: str) -> dict:
    """用 NapCat 已缓存凭证免扫码快速登录；凭证失效会自动回到二维码流程。"""
    if not uin.isdigit() or not (5 <= len(uin) <= 11):
        return {"ok": False, "error": "QQ 号格式不正确"}
    if not _webui_reachable():
        return {"ok": False, "error": "NapCat 未运行，请先点「刷新二维码」自动拉起"}
    try:
        r = _api("/api/QQLogin/SetQuickLogin", {"uin": uin}, timeout=20)
        return {"ok": r.get("code") == 0, "raw": str(r.get("message") or ""),
                "hint": "已提交快速登录，页面会自动检测登录结果；若凭证失效，请改用扫码。"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}

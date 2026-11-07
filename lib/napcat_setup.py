"""NapCat 网关：安装自检 + 自动配置 + 可回滚备份（v3.0.0）。

背景（用户实测反馈）：
- install 之前只装 Python 依赖 + 启动服务，并没有真正确认 NapCat 已装好、接口已配好；
- webui.json 里 host 为 "::"，部分 Windows/Node 组合下浏览器访问 127.0.0.1:6099 会被拒绝；
- onebot11_*.json 若没启用 HTTP 服务或 token 为空，群文件接口（3000）也不可用。

本模块把「装没装 / 能不能用 / 怎么修」做成一次可执行的自检与修复：
- 只读写本机 NapCat 自己的配置文件，绝不触碰 QQ 账号数据、聊天库；
- 任何写入前先生成 `.rmbak` 备份，可随时人工回滚；
- `ensure(fix=False)` 是纯只读体检，自测可安全反复调用；
- 报告落到 state/napcat_setup.json（state/ 已被 gitignore，绝不进仓库）。

所有路径都从环境变量推导，不硬编码任何用户名。
"""
from __future__ import annotations

import json
import os
import secrets
import socket
from datetime import datetime
from pathlib import Path

_LOCAL = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
ROOT = Path(__file__).resolve().parent.parent
_WEBUI_PORT_DEFAULT = 6099
_ONEBOT_PORT_DEFAULT = 3000


# ---------------------------------------------------------------- 路径定位
def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        try:
            if p.is_file():
                return p
        except OSError:
            pass
    return None


def runtime_dir() -> Path | None:
    """NapCat 运行时根目录（包含 node.exe / index.js 的那一层）。"""
    c = [
        _LOCAL / "OmniQQ-MCP" / "napcat_runtime" / "shell_node",
        _LOCAL / "OmniQQ-MCP" / "napcat_runtime",
        _LOCAL / "napcat",
        Path.home() / "napcat",
        Path("C:/NapCatQQ"),
        Path("D:/NapCatQQ"),
    ]
    for p in c:
        try:
            if p.is_dir() and ((p / "napcat" / "napcat.mjs").is_file()
                               or (p / "napcat.mjs").is_file()
                               or (p / "napcat.bat").is_file()):
                return p
        except OSError:
            pass
    return None


def napcat_dir() -> Path | None:
    r = runtime_dir()
    if not r:
        return None
    for p in (r / "napcat", r):
        try:
            if (p / "napcat.mjs").is_file():
                return p
        except OSError:
            pass
    return None


def config_dir() -> Path | None:
    n = napcat_dir()
    if not n:
        return None
    p = n / "config"
    return p if p.is_dir() else None


def launcher_path() -> Path | None:
    """返回可直接 `cmd /c` 拉起的启动脚本；优先选择已验证存在的那一个。"""
    r = runtime_dir()
    if not r:
        return None
    return _first_existing([
        r / "napcat.bat",
        r / "launcher-user.bat",
        napcat_dir() / "launcher-user.bat" if napcat_dir() else Path("__none__"),
        r / "launcher.bat",
        napcat_dir() / "launcher.bat" if napcat_dir() else Path("__none__"),
        r / "quickLoginExample.bat",
    ])


def qrcode_cache() -> Path | None:
    n = napcat_dir()
    if not n:
        return None
    p = n / "cache" / "qrcode.png"
    return p if p.is_file() else None


def webui_config() -> Path | None:
    c = config_dir()
    if not c:
        return None
    return c / "webui.json" if (c / "webui.json").is_file() else None


def onebot_configs() -> list[Path]:
    c = config_dir()
    if not c:
        return []
    try:
        return sorted(c.glob("onebot11_*.json"))
    except OSError:
        return []


# ---------------------------------------------------------------- 低层读写
def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _write_with_backup(path: Path, data: dict) -> None:
    """原子写 + 一次性备份（.rmbak 只生成一次，保留用户原始配置）。"""
    bak = path.with_suffix(path.suffix + ".rmbak")
    try:
        if not bak.is_file() and path.is_file():
            bak.write_bytes(path.read_bytes())
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_ports() -> dict:
    return {
        6099: _port_open(6099),
        3000: _port_open(3000),
    }


# ---------------------------------------------------------------- 体检
def inspect() -> dict:
    """纯只读体检。返回结构化事实 + 问题清单，不做任何修改。"""
    out = {
        "installed": False, "runtime_dir": "", "launcher": "",
        "webui_config": "", "onebot_configs": [], "qrcode_cache": "",
        "webui_host": "", "webui_port": _WEBUI_PORT_DEFAULT, "webui_disabled": False,
        "onebot_port": _ONEBOT_PORT_DEFAULT, "onebot_http_enabled": False,
        "onebot_token": False, "webui_token": False,
        "running": False, "webui_online": False, "onebot_online": False,
        "issues": [], "warnings": [],
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    r = runtime_dir()
    if not r:
        out["issues"].append("未检测到 NapCat 运行时：请先安装 NapCat（或安装 WorkBuddy 的 OmniQQ 插件，其自带 NapCat 运行时）")
        return out
    out["installed"] = True
    out["runtime_dir"] = str(r)
    lp = launcher_path()
    out["launcher"] = str(lp) if lp else ""
    if not lp:
        out["issues"].append("找到运行时但找不到启动脚本（napcat.bat / launcher-user.bat）")

    wc = webui_config()
    if wc:
        out["webui_config"] = str(wc)
        d = _read(wc)
        out["webui_host"] = str(d.get("host") or "")
        out["webui_port"] = int(d.get("port") or _WEBUI_PORT_DEFAULT)
        out["webui_disabled"] = bool(d.get("disableWebUI"))
        out["webui_token"] = bool(d.get("token"))
        if out["webui_disabled"]:
            out["issues"].append("NapCat WebUI 被禁用（disableWebUI=true），二维码与登录接口不可用")
        h = out["webui_host"]
        if h in ("::", "0.0.0.0", "::1", ""):
            out["issues"].append(f"WebUI 绑定 host={h or '(空)'}，浏览器访问 127.0.0.1 可能被拒绝；应固定为 127.0.0.1")
        if not out["webui_token"]:
            out["warnings"].append("WebUI 未配置 token，自动登录接口可能不可用")
    else:
        out["issues"].append("缺少 webui.json：NapCat 首次启动后才会生成，请先启动一次 NapCat")

    cfgs = onebot_configs()
    out["onebot_configs"] = [str(p) for p in cfgs]
    ok = False
    for p in cfgs:
        d = _read(p)
        for s in (d.get("network") or {}).get("httpServers", []) or []:
            if not isinstance(s, dict):
                continue
            if s.get("enable"):
                ok = True
                out["onebot_port"] = int(s.get("port") or _ONEBOT_PORT_DEFAULT)
                out["onebot_token"] = bool(s.get("token"))
                if not out["onebot_token"]:
                    out["warnings"].append(f"{p.name} 的 HTTP 服务未设置 token，本程序无法鉴权访问")
            elif not ok:
                out["onebot_port"] = int(s.get("port") or _ONEBOT_PORT_DEFAULT)
    out["onebot_http_enabled"] = ok
    if not cfgs:
        out["warnings"].append("未找到 onebot11_*.json：NapCat 登录一次后会自动生成")
    elif not ok:
        out["issues"].append("OneBot 11 HTTP 服务未启用（httpServers[].enable=false），群文件接口 3000 不可用")

    qc = qrcode_cache()
    out["qrcode_cache"] = str(qc) if qc else ""
    ports = _probe_ports()
    out["webui_online"] = ports[6099]
    out["onebot_online"] = ports[3000]
    out["running"] = out["webui_online"] or out["onebot_online"]
    if not out["running"]:
        out["warnings"].append("NapCat 当前未运行；登录页点「刷新二维码」会自动拉起")
    return out


# ---------------------------------------------------------------- 修复
def ensure(fix: bool = True, start: bool = False, dry_run: bool = False) -> dict:
    """体检并修复配置。返回可展示给用户的完整结果。

    fix=False 或 dry_run=True 时纯只读；start=True 时顺带拉起 NapCat。
    """
    d = inspect()
    fixed: list[str] = []
    if fix and not dry_run and d["installed"]:
        # 1) WebUI：固定本机 IPv4、开启、补 token
        wc = webui_config()
        if wc:
            w = _read(wc)
            changed = False
            if str(w.get("host") or "") != "127.0.0.1":
                w["host"] = "127.0.0.1"
                changed = True
                fixed.append("webui.json: host 固定为 127.0.0.1（修复 6099 拒绝连接）")
            if w.get("disableWebUI"):
                w["disableWebUI"] = False
                changed = True
                fixed.append("webui.json: 重新启用 WebUI")
            if not w.get("token"):
                w["token"] = secrets.token_hex(6)
                changed = True
                fixed.append("webui.json: 生成随机 token")
            if int(w.get("port") or 0) != _WEBUI_PORT_DEFAULT:
                w["port"] = _WEBUI_PORT_DEFAULT
                changed = True
                fixed.append("webui.json: 端口统一为 6099")
            if changed:
                _write_with_backup(wc, w)
        # 2) OneBot：确保至少一个 HTTP 服务开启 + 有 token + 固定 3000
        for p in onebot_configs():
            o = _read(p)
            net = o.setdefault("network", {})
            srvs = net.setdefault("httpServers", [])
            changed = False
            if not srvs:
                srvs.append({"name": "httpServer", "enable": True, "host": "127.0.0.1",
                              "port": _ONEBOT_PORT_DEFAULT, "token": secrets.token_urlsafe(24),
                              "enableCors": True, "enableWebsocket": False})
                changed = True
                fixed.append(f"{p.name}: 新建本机 HTTP 服务（3000）")
            else:
                s = srvs[0]
                if not s.get("enable"):
                    s["enable"] = True
                    changed = True
                    fixed.append(f"{p.name}: 启用 HTTP 服务")
                if int(s.get("port") or 0) != _ONEBOT_PORT_DEFAULT:
                    s["port"] = _ONEBOT_PORT_DEFAULT
                    changed = True
                    fixed.append(f"{p.name}: 端口统一为 3000")
                if str(s.get("host") or "") != "127.0.0.1":
                    s["host"] = "127.0.0.1"
                    changed = True
                    fixed.append(f"{p.name}: host 固定为 127.0.0.1")
                if not s.get("token"):
                    s["token"] = secrets.token_urlsafe(24)
                    changed = True
                    fixed.append(f"{p.name}: 生成随机 token")
            if changed:
                _write_with_backup(p, o)

    after = inspect() if (fix and not dry_run and fixed) else d
    result = {
        "ok": after["installed"] and not after["issues"],
        "installed": after["installed"],
        "running": after["running"],
        "webui_online": after["webui_online"],
        "onebot_online": after["onebot_online"],
        "launcher": after["launcher"],
        "runtime_dir": after["runtime_dir"],
        "qrcode_cache": after["qrcode_cache"],
        "fixed": fixed,
        "issues": after["issues"],
        "warnings": after["warnings"],
        "needs_restart": bool(fixed) and after["running"],
        "checked_at": after["checked_at"],
    }
    if start and after["installed"] and not after["running"] and not dry_run:
        from . import napcat_launch
        r = napcat_launch.start()
        result["start"] = r
        result["running"] = bool(r.get("ok")) or _probe_ports()[6099] or _probe_ports()[3000]
        if not r.get("ok"):
            result["issues"].append("自动拉起 NapCat 失败：" + str(r.get("error") or "")[:160])
            result["ok"] = False
    # 报告只保存在本机 state/，不进仓库
    try:
        report = ROOT / "state" / "napcat_setup.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report"] = str(report)
    except OSError:
        pass
    return result


def status() -> dict:
    """给 HTTP API / 诊断面板的轻量快照（纯只读，不写盘）。"""
    d = inspect()
    return {
        "ok": d["installed"] and not d["issues"],
        "installed": d["installed"], "running": d["running"],
        "webui_online": d["webui_online"], "onebot_online": d["onebot_online"],
        "launcher": d["launcher"], "qrcode_cache": bool(d["qrcode_cache"]),
        "issues": d["issues"], "warnings": d["warnings"],
        "webui_port": d["webui_port"], "onebot_port": d["onebot_port"],
    }

"""资源管理 · 本地可视化服务（仅监听 127.0.0.1）。

零第三方依赖：标准库 http.server + sqlite3 FTS5 + 原生前端。
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ai, catalog, config, download, index, llm, qq, qqlogin, vault, wechat  # noqa: E402

CAT = None
SOURCE_STATUS = {"mode": "init", "online": False, "updated_at": "", "groups": {}, "errors": []}


def snapshot_path() -> Path:
    return config.state("qq_manifest.json")


def load_snapshot() -> list[dict]:
    return (config.read_json(snapshot_path(), {}) or {}).get("items", [])


def refresh(force_snapshot: bool = False) -> dict:
    """只读刷新来源元数据。接口不可用自动回落到离线快照，不下载任何文件内容。"""
    global CAT, SOURCE_STATUS
    cfg = config.CFG
    groups = (cfg["sources"]["qq"] or {}).get("groups", {})
    rows: list[dict] = []
    gs, errors, mode = {}, [], ""
    live = (not force_snapshot) and qq.online()
    if live:
        for key, g in groups.items():
            try:
                r, nfold = qq.walk(int(g["qq_group"]))
                rows += [dict(source="QQ群", group=g["display"], group_id=int(g["qq_group"]), **z) for z in r]
                gs[g["display"]] = {"files": len(r), "folders": nfold, "live": True}
            except Exception as e:
                errors.append(f"{g['display']}: {str(e)[:120]}")
                gs[g["display"]] = {"files": 0, "live": False}
        if not errors and rows:
            mode = "live"
            config.write_json(snapshot_path(), {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "items": rows})
    if mode != "live":
        rows = load_snapshot()
        mode = "snapshot" if rows else "empty"
        if rows:
            gs = {g["display"]: {"files": sum(1 for r in rows if r.get("group") == g["display"]),
                                  "live": False} for g in groups.values()}
            errors = errors or ["QQ 接口不可用，已使用离线元数据快照；下载已锁定，点「刷新来源」可恢复在线"]
    if not rows:
        return {"ok": False, "error": "QQ 接口不可用且没有离线快照，请先运行 tools/bootstrap.py"}
    CAT = catalog.load()
    n = catalog.upsert_manifest(CAT, rows, cfg)
    catalog.save(CAT)
    idx = index.rebuild(CAT)
    outlines = vault.build_outlines(CAT)
    SOURCE_STATUS = {"mode": mode, "online": live, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "groups": gs, "errors": errors, "qq_online": qq.online()}
    return {"ok": True, "mode": mode, "items": n, "indexed": idx, "outlines": outlines,
            "errors": errors, "counts": catalog.counts(CAT)}


def ensure() -> dict:
    global CAT
    if CAT is None:
        CAT = catalog.load()
        if not CAT.get("items"):
            refresh()
    return CAT


class Handler(BaseHTTPRequestHandler):
    server_version = "ResourceManager/1.0"

    def log_message(self, fmt, *args):
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    def _send(self, obj, code: int = 200, ctype: str = "application/json; charset=utf-8"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _sync_source(self):
        """QQ 服务可能在运行中途掉线：实时探活并立刻收紧为离线快照，避免界面谎报在线。

        恢复在线不自动放开，必须用户显式点「刷新来源」，防止用失效 file_id 下载。
        """
        global SOURCE_STATUS
        if SOURCE_STATUS.get("mode") != "live":
            SOURCE_STATUS["qq_online"] = False
            return
        on = qq.online()
        SOURCE_STATUS["qq_online"] = on
        if not on:
            SOURCE_STATUS = dict(SOURCE_STATUS, online=False, qq_online=False, mode="snapshot",
                                 errors=["QQ 服务在运行中掉线，已自动切为离线快照；点「刷新来源」可恢复在线"])
            print("QQ 服务掉线，已自动切为离线快照（下载已锁定）")

    def do_GET(self):
        self._sync_source()
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        try:
            if p in ("/", "/index.html"):
                return self._file("index.html")
            if p == "/login":
                return self._file("login.html")
            if p in ("/app.js", "/style.css"):
                return self._file(p.lstrip("/"))
            if p == "/api/qqlogin/status":
                return self._send(qqlogin.status())
            if p == "/api/health":
                # _sync_source() 已在请求开头实时探活；这里用状态缓存，
                # 避免 QQ 离线时每次健康检查都白等一次 OneBot 超时。
                return self._send({"ok": True, "docs": index.count(), "mode": SOURCE_STATUS.get("mode"),
                                   "qq_online": bool(SOURCE_STATUS.get("qq_online", False)),
                                   "vault": str(config.vault())})
            if p == "/api/state":
                cat = ensure()
                return self._send({"ok": True, "source": SOURCE_STATUS, "counts": catalog.counts(cat),
                                   "wechat": wechat.status(config.CFG),
                                   "settings": config.public_settings(),
                                   "download_cap": config.CFG.get("max_download_per_batch", 30)})
            if p == "/api/tree":
                node = json.loads(q.get("node", ["[]"])[0])
                return self._send({"ok": True, "children": catalog.tree(ensure(), q.get("dim", ["classify"])[0], node)})
            if p == "/api/files":
                node = json.loads(q.get("node", ["[]"])[0])
                xs, total = catalog.query(ensure(), q.get("dim", ["classify"])[0], node,
                                         q.get("q", [""])[0], int(q.get("limit", ["200"])[0]),
                                         with_total=True)
                return self._send({"ok": True, "items": xs, "total": total,
                                   "shown": len(xs), "truncated": total > len(xs)})
            if p == "/api/file":
                x = catalog.by_id(ensure(), q.get("id", [""])[0])
                if not x:
                    return self._send({"ok": False, "error": "文件不存在"}, 404)
                out = catalog.public(x)
                bp = index.body_path(x["id"])
                out["body_excerpt"] = bp.read_text(encoding="utf-8", errors="replace")[:2000] if bp.is_file() else ""
                out["asset_abs"] = str(config.vault() / x["asset"]) if x.get("asset") else ""
                out["note_abs"] = str(config.vault() / x["note"]) if x.get("note") else ""
                return self._send({"ok": True, "item": out})
            if p == "/api/ask":
                r = ai.answer(q.get("q", [""])[0], ensure(), fast=q.get("fast", ["0"])[0] in ("1", "true"))
                r["ok"] = True
                return self._send(r)
            if p == "/api/settings":
                return self._send({"ok": True, "settings": config.public_settings()})
            if p == "/api/outline":
                return self._send({"ok": True, "outlines": vault.build_outlines(ensure())})
            return self._send({"ok": False, "error": "未知端点"}, 404)
        except Exception as e:
            return self._send({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    def _file(self, name: str):
        f = config.WEB / name
        if not f.is_file():
            return self._send({"ok": False, "error": "missing"}, 404)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if name.endswith((".js", ".css", ".html")):
            ctype += "; charset=utf-8"
        return self._send(f.read_bytes(), ctype=ctype)

    def do_POST(self):
        self._sync_source()
        u = urllib.parse.urlparse(self.path)
        p, body = u.path, self._body()
        try:
            if p == "/api/refresh":
                return self._send(refresh(bool(body.get("snapshot"))))
            if p == "/api/qqlogin/refresh":
                return self._send(qqlogin.refresh_qrcode())
            if p == "/api/qqlogin/quick":
                return self._send(qqlogin.quick_login(str(body.get("uin") or "")))
            if p == "/api/qqlogin/restore":
                # 扫码确认后 OneBot 3000 通常要几秒才起来，等就绪再刷新来源，
                # 这样用户不必回到主界面手动点「刷新来源」。
                for _ in range(14):
                    if qq.online():
                        break
                    time.sleep(1.5)
                if not qq.online():
                    return self._send({"ok": False,
                                       "error": "扫码登录尚未完成或群文件接口（OneBot 3000）还没起来："
                                                "请先在页面上用手机 QQ 扫码并确认；已确认的话稍等几秒，"
                                                "或回主界面点「刷新来源」"})
                r = refresh()
                return self._send({"ok": bool(r.get("ok")), "mode": r.get("mode"),
                                   "items": r.get("items"), "error": r.get("error") or ""})
            if p == "/api/download":
                cat = ensure()
                if SOURCE_STATUS.get("mode") == "snapshot":
                    return self._send({"ok": False, "results": [],
                                      "error": "当前为离线快照，只能预览元数据，不能下载。请先「刷新来源」切回在线状态。"})
                chk = download.precheck(cat, body.get("ids") or [], body.get("scope", "selection"),
                                        bool(body.get("confirm")), body.get("confirmText", ""),
                                        body.get("nodeName", ""))
                if not chk["ok"] and body.get("dryRun"):
                    return self._send({"ok": False, "error": chk["error"]})
                r = download.run(cat, body.get("ids") or [], body.get("scope", "selection"),
                                 bool(body.get("confirm")), body.get("confirmText", ""), body.get("nodeName", ""))
                r["counts"] = catalog.counts(cat)
                return self._send(r)
            if p == "/api/ask":
                r = ai.answer(body.get("q", ""), ensure(), fast=bool(body.get("fast")))
                r["ok"] = True
                return self._send(r)
            if p == "/api/settings":
                patch = {}
                for k in ("provider", "base_url", "model", "api_key", "timeout"):
                    if k in body:
                        patch[k] = body[k]
                if "disable_thinking" in body or "local_base_url" in body or "local_model" in body:
                    loc = dict((config.settings().get("local") or {}))
                    if "disable_thinking" in body:
                        loc["disable_thinking"] = bool(body["disable_thinking"])
                    if "local_base_url" in body:
                        loc["base_url"] = body["local_base_url"]
                    if "local_model" in body:
                        loc["model"] = body["local_model"]
                    patch["local"] = loc
                config.save_settings(patch)
                return self._send({"ok": True, "settings": config.public_settings()})
            if p == "/api/settings/test":
                return self._send(llm.test())
            if p == "/api/reindex":
                cat = ensure()
                return self._send({"ok": True, "docs": index.rebuild(cat),
                                   "outlines": vault.build_outlines(cat)})
            if p == "/api/init":
                return self._send({"ok": True, "created": vault.init(),
                                   "outlines": vault.build_outlines(ensure())})
            return self._send({"ok": False, "error": "未知端点"}, 404)
        except Exception as e:
            return self._send({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)


def main():
    vault.init()
    print("初始化资源库…")
    r = refresh()
    print("来源刷新：", r.get("mode"), r.get("items"), "条；索引", r.get("indexed"), "篇")
    if r.get("errors"):
        print("警告：", "; ".join(r["errors"][:3]))
    host = config.CFG.get("host", "127.0.0.1")
    port = int(config.CFG.get("port", 8787))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"资源管理界面： http://{host}:{port}")
    print(f"Obsidian 库： {config.vault()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()

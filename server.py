"""资源管理 · 本地可视化服务（仅监听 127.0.0.1）。

零第三方依赖：标准库 http.server + sqlite3 FTS5 + 原生前端。
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (ai, catalog, config, config_validate, download, index, llm, localimport,  # noqa: E402
                 napcat_launch, napcat_setup, qq, qqlogin, vault, vocab)

CAT = None
SOURCE_STATUS = {"mode": "init", "online": False, "updated_at": "", "groups": {}, "errors": []}


def snapshot_path() -> Path:
    return config.state("qq_manifest.json")


def load_snapshot() -> list[dict]:
    return (config.read_json(snapshot_path(), {}) or {}).get("items", [])


def setup_status() -> dict:
    """给新手配置向导的快照：是否已配置完、当前群、NapCat 控制台地址。"""
    cfg = (config.CFG.get("sources", {}).get("qq", {}) or {}).get("groups", {}) or {}
    demo = set(cfg.keys()) <= {"pxb6", "nzf4", "xfq12"}
    return {"ok": True, "done": config.setup_done(), "demo": demo,
            "groups": [{"key": k, **v} for k, v in cfg.items()],
            "napcat": napcat_setup.status()}


def after_import(cat: dict, r: dict, body: dict, source: str = "QQ 群文件") -> dict:
    """v3.5.0 导入收尾：让成效**立刻可见**。

    1. 记录本次新增 id，重建大纲（🆕 标记落在原有分类里）；
    2. 重新部署最新版 AI 插件；
    3. 生成/刷新「00-本次导入.md」报告；
    4. 用 obsidian:// 自动打开本库并定位到报告（可在弹窗里取消）。
    """
    results = r.get("results") or []
    changed = [str(x.get("id")) for x in results if x.get("ok")]
    breakdown: dict[str, int] = {}
    for iid in changed:
        x = catalog.by_id(cat, iid)
        if x:
            key = str(x.get("subject") or "综合")
            breakdown[key] = breakdown.get(key, 0) + 1
    r["imported"] = len(changed)
    r["breakdown"] = breakdown
    vault.deploy_plugin()
    r["notes_refreshed"] = vault.refresh_notes(cat)  # 全部已导入笔记补齐完整正文
    if changed:
        vault.mark_recent(changed)
    r["outlines"] = vault.build_outlines(cat)
    r["report"] = vault.write_import_report(cat, results, {"source": source})
    r["vault"] = vault.status(cat)
    r["counts"] = catalog.counts(cat)
    cfg_open = (config.CFG.get("obsidian") or {}).get("open_after_import", True)
    want = bool(body.get("open_after", True)) and cfg_open and bool(changed)
    r["open"] = (vault.open_in_obsidian(r["report"]) if want else
                 {"ok": True, "opened": False, "method": "skipped", "path": str(vault.v())})
    r["opened"] = bool(r["open"].get("opened"))
    return r


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
                # 单次遍历上限 10s：在线但未登录等异常态下不会长时间阻塞刷新
                r, nfold = qq.walk(int(g["qq_group"]), timeout=10)
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
    # 只有 QQ 全量清单才允许按来源裁剪；其它来源一律纯增量并入，绝不删条目
    n = catalog.upsert_manifest(CAT, rows, cfg, prune_source="QQ群" if mode == "live" else None)
    catalog.save(CAT)
    # 增量同步：刷新来源后只重算变化的条目（首次运行 idx_meta 为空时等效全量重建）
    idx = index.sync(CAT)
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
            if p == "/setup":
                return self._file("setup.html")
            if p == "/api/setup":
                return self._send(setup_status())
            if p == "/api/qq/groups":
                gs, err = qq.list_groups()
                return self._send({"ok": True, "groups": gs, "error": err})
            if p == "/api/groups":
                # v3.5.0 群聊框选：在线读取本 QQ 的**全部**群；离线也能从本机目录
                # 元数据（含真实群号）列出已有群，保证任何账号、任何网络状态都可框选。
                groups_cfg = (config.CFG.get("sources", {}).get("qq", {}) or {}).get("groups", {})
                st_groups = (SOURCE_STATUS.get("groups") or {})
                configured = [{"code": c, "display": g.get("display", ""), "qq_group": g.get("qq_group", ""),
                               "files": (st_groups.get(g.get("display", ""), {}) or {}).get("files")}
                              for c, g in groups_cfg.items()]
                on = qq.online()
                live, err = qq.list_groups() if on else ([], "QQ 未在线，以下为本机已缓存的群清单")
                cfg_gids = {str(v.get("qq_group", "")) for v in groups_cfg.values()}
                merged: dict[str, dict] = {}
                for g in live:
                    merged[g["group_id"]] = {
                        "group_id": g["group_id"], "name": g.get("name", ""),
                        "member_count": g.get("member_count", 0), "files": 0,
                        "configured": g["group_id"] in cfg_gids, "from": "qq", "checked": g["group_id"] in cfg_gids,
                    }
                for x in catalog.items(ensure()):
                    name = str(x.get("group", "") or "").strip()
                    gid = str(x.get("group_id", "") or "").strip()
                    if not name or not gid.isdigit():
                        continue
                    e = merged.setdefault(gid, {
                        "group_id": gid, "name": name, "member_count": 0, "files": 0,
                        "configured": gid in cfg_gids, "from": "catalog", "checked": gid in cfg_gids,
                    })
                    e["files"] += 1
                for c, g in groups_cfg.items():
                    gid = str(g.get("qq_group", "")).strip()
                    if gid and gid not in merged:
                        merged[gid] = {"group_id": gid, "name": g.get("display", "") or f"群{gid}",
                                       "member_count": 0, "files": 0, "configured": True,
                                       "from": "config", "checked": True}
                available = sorted(merged.values(), key=lambda d: (-d["checked"], -d["files"], d["name"]))
                return self._send({"ok": True, "online": on, "error": err,
                                   "configured": configured, "available": available,
                                   "total_groups": len(available),
                                   "mode": SOURCE_STATUS.get("mode")})
            if p in ("/app.js", "/style.css"):
                return self._file(p.lstrip("/"))
            if p == "/api/qqlogin/status":
                return self._send(qqlogin.status())
            if p == "/api/napcat/status":
                return self._send({"ok": True, **napcat_setup.status(),
                                   "running": napcat_launch.is_running()})
            if p == "/api/napcat/setup":
                # ok 表示请求成功；自检结论放在 status 里，避免两个 ok 语义混淆
                return self._send({"ok": True, "status": napcat_setup.status()})
            if p == "/api/napcat/start":
                return self._send(napcat_launch.start())
            if p == "/api/diagnose":
                d = config_validate.validate()
                d["mode"] = SOURCE_STATUS.get("mode")
                d["qq_online"] = bool(SOURCE_STATUS.get("qq_online", False))
                d["index_docs"] = index.count()
                d["vault"] = str(config.vault())
                d["napcat"] = napcat_setup.status()
                return self._send({"ok": True, **d})
            if p == "/api/health":
                # _sync_source() 已在请求开头实时探活；这里用状态缓存，
                # 避免 QQ 离线时每次健康检查都白等一次 OneBot 超时。
                return self._send({"ok": True, "docs": index.count(), "mode": SOURCE_STATUS.get("mode"),
                                   "qq_online": bool(SOURCE_STATUS.get("qq_online", False)),
                                   "vault": str(config.vault())})
            if p == "/api/state":
                cat = ensure()
                return self._send({"ok": True, "source": SOURCE_STATUS, "counts": catalog.counts(cat),
                                   "integrity": catalog.verify_integrity(cat),
                                   "settings": config.public_settings(),
                                   "download_cap": config.CFG.get("max_download_per_batch", 30)})
            if p == "/api/tree":
                node = json.loads(q.get("node", ["[]"])[0])
                return self._send({"ok": True, "children": catalog.tree(ensure(), q.get("dim", ["classify"])[0], node,
                                                                        group=q.get("group", [""])[0])})
            if p == "/api/files":
                node = json.loads(q.get("node", ["[]"])[0])
                xs, total = catalog.query(ensure(), q.get("dim", ["classify"])[0], node,
                                         q.get("q", [""])[0], int(q.get("limit", ["200"])[0]),
                                         with_total=True, kind=q.get("kind", [""])[0],
                                         cfg=config.CFG, group=q.get("group", [""])[0])
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
                try:
                    scope = json.loads(q.get("scope", ["[]"])[0])
                except Exception:
                    scope = []
                r = ai.answer(q.get("q", [""])[0], ensure(),
                              fast=q.get("fast", ["0"])[0] in ("1", "true"), scope=scope,
                              group=q.get("group", [""])[0], dim=q.get("dim", ["subject"])[0])
                r["ok"] = True
                return self._send(r)
            if p == "/api/vault/status":
                return self._send(vault.status(ensure()))
            if p == "/api/vault/targets":
                return self._send({"ok": True, "current": str(vault.v()),
                                   "vaults": vault.discover_vaults(),
                                   "vault": vault.status(ensure())})
            if p == "/api/vault/content":
                return self._send(vault.content(q.get("id", [""])[0], ensure()))
            if p == "/api/vault/search":
                return self._send(vault.search(q.get("q", [""])[0], ensure(),
                                               group=q.get("group", [""])[0],
                                               limit=int(q.get("limit", ["20"])[0]),
                                               scope=q.get("scope", ["vault"])[0]))
            if p == "/api/local/scan":
                # 只读盘点：本机已另存的 QQ 群文件中有多少能与目录元数据精确对上
                return self._send(localimport.scan(ensure()))
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
            if p == "/api/groups/add":
                try:
                    groups = config.add_qq_group(str(body.get("code") or ""), str(body.get("display") or ""),
                                                str(body.get("qq_group") or ""))
                except ValueError as e:
                    return self._send({"ok": False, "error": str(e)}, 400)
                return self._send({"ok": True, "groups": groups})
            if p == "/api/groups/remove":
                groups = config.remove_qq_group(str(body.get("code") or ""))
                return self._send({"ok": True, "groups": groups})
            if p == "/api/groups/set":
                # 群聊框选：一次保存用户勾选的全部群（任意 QQ 账号通用）
                groups = config.set_qq_groups(body.get("groups") or [])
                vocab.invalidate()
                refreshed = None
                if bool(body.get("refresh")) and qq.online():
                    refreshed = refresh()
                return self._send({"ok": True, "groups": groups, "saved": len(groups),
                                   "refreshed": bool(refreshed and refreshed.get("ok")),
                                   "refresh": refreshed or {},
                                   "vault": vault.status(ensure())})
            if p == "/api/qqlogin/refresh":
                return self._send(qqlogin.refresh_qrcode())
            if p == "/api/qqlogin/quick":
                return self._send(qqlogin.quick_login(str(body.get("uin") or "")))
            if p == "/api/napcat/start":
                return self._send(napcat_launch.start())
            if p == "/api/napcat/setup":
                # 安装自检 + 自动修复本机 NapCat 配置（只改配置，不改 QQ 账号数据）
                return self._send(napcat_setup.ensure(fix=True, start=False))
            if p == "/api/qqlogin/restore":
                # 先快速判断 NapCat/OneBot 是否可达：完全没运行时立即给出可操作提示，
                # 避免轮询 20+ 秒让页面像卡死（这是 v1.2.3 自测发现的真实卡顿）。
                if not qq.reachable() and not qq.online():
                    return self._send({"ok": False, "need_start": True,
                                       "error": "NapCat 未运行：请点本页「刷新二维码」，"
                                                "程序会自动拉起 NapCat 并生成二维码。"})
                # 已扫码但 OneBot 3000 一般要几秒才起来：最多等约 8 秒，失败再提示手动刷新
                for _ in range(6):
                    if qq.online():
                        break
                    time.sleep(1.2)
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
                if r.get("ok"):
                    r = after_import(cat, r, body, "QQ 群文件在线下载")
                else:
                    r["counts"] = catalog.counts(cat)
                return self._send(r)
            if p == "/api/ask":
                r = ai.answer(body.get("q", ""), ensure(), fast=bool(body.get("fast")),
                              scope=body.get("scope") or [], group=body.get("group") or "",
                              dim=body.get("dim") or "subject")
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
            if p == "/api/reclassify":
                # 词库升级后原地重算分类：只改分类字段，绝不增删任何条目
                cat = ensure()
                before = len(catalog.items(cat))
                n = catalog.reclassify(cat, config.CFG)
                catalog.save(cat)
                index.sync(cat)
                v = catalog.verify_integrity(cat)
                if len(catalog.items(cat)) != before or not v["ok"]:
                    return self._send({"ok": False, "error": "重算后完整性校验失败，请检查目录",
                                       "integrity": v}, 500)
                return self._send({"ok": True, "items": n, "counts": catalog.counts(cat),
                                   "integrity": v, "outlines": vault.build_outlines(cat)})
            if p == "/api/maintain":
                return self._send(index.optimize())
            if p == "/api/init":
                return self._send({"ok": True, "created": vault.init(),
                                   "outlines": vault.build_outlines(ensure()),
                                   "vault": vault.status(ensure())})
            if p == "/api/vault/init":
                created = vault.init()
                cat = ensure()
                notes = vault.refresh_notes(cat)  # 旧版笔记也补齐完整正文
                return self._send({"ok": True, "created": created, "notes_refreshed": notes,
                                   "outlines": vault.build_outlines(cat),
                                   "vault": vault.status(cat)})
            if p == "/api/vault/open":
                # 在本机文件管理器里打开新库文件夹；失败只回传路径，不报错
                opened, err = False, ""
                try:
                    import os
                    os.startfile(str(vault.v()))  # noqa: S606 - 仅 Windows 本机、用户显式点击
                    opened = True
                except Exception as e:
                    err = str(e)[:120]
                return self._send({"ok": True, "opened": opened, "error": err,
                                   "path": str(vault.v()), "vault": vault.status(ensure())})
            if p == "/api/vault/open-obsidian":
                return self._send(vault.open_in_obsidian(str(body.get("file") or "")))
            if p == "/api/vault/target":
                r = vault.set_vault(body.get("target") or {})
                if r.get("ok") and bool(body.get("open", True)):
                    r["open"] = vault.open_in_obsidian("00-使用说明.md")
                return self._send(r)
            if p == "/api/vault/import":
                # 一键批量导入：显式确认 + 当前范围（或指定 ids），复用 download 的全部闸门。
                # 离线 / QQNT 内核异常时自动改走「本机已另存文件」通道，链路不中断。
                cat = ensure()
                ids = [str(i) for i in (body.get("ids") or []) if i]
                if not ids:
                    try:
                        node = json.loads(body.get("node", "[]") or "[]")
                    except Exception:
                        node = []
                    cap = int(config.CFG.get("max_download_per_batch", 30))
                    xs, _t = catalog.query(cat, body.get("dim") or "subject", node,
                                           body.get("q") or "", 100000, with_total=True,
                                           kind=body.get("kind") or "", cfg=config.CFG,
                                           group=body.get("group") or "")
                    ids = [x["id"] for x in xs if not x.get("downloaded")][:cap]
                if SOURCE_STATUS.get("mode") == "snapshot" or not qq.online():
                    pairs = localimport.pick(cat, ids)
                    if not pairs:
                        return self._send({"ok": False,
                                           "error": "QQ 在线下载不可用，且所选范围内没有本机已另存的对应文件。"
                                                    "可点「刷新来源」恢复在线，或把 QQ 群文件另存到"
                                                    " config.json 的 local_import_dirs 目录后再试。",
                                           "vault": vault.status(cat)})
                    r = localimport.run(cat, pairs, bool(body.get("confirm")))
                    r["source"] = "local_saved_file"
                else:
                    r = download.run(cat, ids, "selection", bool(body.get("confirm")), "", "")
                    # 在线但直链内核异常时，同样用本地已另存文件兜底，不让链路断在这一步
                    if not r.get("ok"):
                        pairs = localimport.pick(cat, ids)
                        if pairs:
                            local_r = localimport.run(cat, pairs, bool(body.get("confirm")))
                            if local_r.get("ok"):
                                local_r["source"] = "local_saved_file_fallback"
                                local_r["online_error"] = r.get("error") or ""
                                r = local_r
                if r.get("ok"):
                    src = ("本机已另存群文件" if str(r.get("source", "")).startswith("local")
                           else "QQ 群文件在线下载")
                    r = after_import(cat, r, body, src)
                else:
                    r["vault"] = vault.status(cat)
                    r["counts"] = catalog.counts(cat)
                return self._send(r)
            if p == "/api/vault/import-local":
                # 显式离线导入：按界面给出的 (id, path) 清单导入本机已另存的 QQ 群文件
                cat = ensure()
                r = localimport.run(cat, body.get("pairs") or [], bool(body.get("confirm")))
                r["counts"] = catalog.counts(cat)
                if r.get("ok"):
                    r = after_import(cat, r, body, "本机已另存群文件")
                return self._send(r)
            if p == "/api/setup/config":
                saved = config.save_qq_groups(body.get("groups") or [])
                return self._send({"ok": True, "saved": len(saved)})
            if p == "/api/setup/done":
                config.mark_setup_done()
                return self._send({"ok": True})
            return self._send({"ok": False, "error": "未知端点"}, 404)
        except Exception as e:
            return self._send({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)


def main():
    # 启动期配置自检：把配置问题集中暴露成可读清单，而不是在请求中才崩溃
    _d = config_validate.validate()
    if _d["errors"]:
        print("配置错误：")
        for e in _d["errors"]:
            print("  ✗", e)
    if _d["warnings"]:
        print("配置提醒：")
        for w in _d["warnings"]:
            print("  !", w)
    if _d["ok"] and not _d["warnings"]:
        print("配置自检通过。")

    vault.init()
    host = config.CFG.get("host", "127.0.0.1")
    port = int(config.CFG.get("port", 8787))
    srv = ThreadingHTTPServer((host, port), Handler)
    # 关键健壮性修复：先起 HTTP 服务，再在后台刷新来源。
    # 否则当 NapCat/OneBot 在线但登录态异常时，refresh() 的群文件遍历会长时间阻塞，
    # 导致进程迟迟不接受连接、浏览器「进不去」。后台刷新不影响界面立即可用，
    # 且 ensure() 会优先复用已落盘的 catalog.json，首屏即有数据。
    threading.Thread(target=refresh, daemon=True).start()
    print(f"资源管理界面： http://{host}:{port}")
    print(f"Obsidian 库： {config.vault()}")
    print("正在后台刷新来源（首次可能需联网；离线时自动使用本地快照）…")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()

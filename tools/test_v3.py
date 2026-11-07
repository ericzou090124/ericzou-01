# -*- coding: utf-8 -*-
"""v3.0.0 端到端自测：起真实 HTTP 服务，逐个打接口并做完整性断言。

覆盖用户反馈的四类问题：
  A. QQ 登录链路（无控制台外链、二维码本页直出、刷新自动拉起）
  B. install 的 NapCat 安装自检与配置修复
  C. 分类不漏项（高等代数召回、多归属标签、微信来源并入不删条目）
  D. 微信登录与群文件采集的可视化入口与端点
  F. v3.1.0 泛化分类回归（体裁 / 动态主题 / 模态 / 词表 CRUD / 新页面）

不调用 server.main()，避免刷新来源时产生网络请求 / 写盘副作用；
真实 catalog.json 只读，任何会写盘的操作都用 mock 或显式恢复。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from lib import catalog, config, napcat_setup, qqlogin  # noqa: E402

PORT = int(os.environ.get("RM_TEST_PORT", "8799"))
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, detail: str = ""):
    ok = bool(cond)
    RESULTS.append((name, ok, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


def get(path: str, timeout: float = 15):
    with OPENER.open(BASE + path, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "")
    return raw, ctype, json.loads(raw.decode("utf-8")) if "json" in ctype else None


def post(path: str, body: dict | None = None, timeout: float = 30):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(body or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print("=" * 60)
    print("  v3.0.0 端到端自测（真实 HTTP 服务 @ %s）" % BASE)
    print("=" * 60)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # ---------- A. 静态页面 / 登录 ----------
        print("\n[A] 页面与静态资源")
        for p in ("/", "/login", "/setup", "/wechat", "/app.js", "/style.css"):
            try:
                raw, ct, _ = get(p)
                check("GET " + p, len(raw) > 100, f"{len(raw)} B / {ct.split(';')[0]}")
            except Exception as e:
                check("GET " + p, False, str(e))
        login_html = (config.WEB / "login.html").read_text(encoding="utf-8")
        setup_html = (config.WEB / "setup.html").read_text(encoding="utf-8")
        import re
        def no_console_entry(html: str) -> bool:
            # 只判断「可点击的入口 / 外链」，说明文字里提到该名词不算入口
            return ("btn-webui" not in html and "webui_url" not in html
                    and "6099/webui" not in html
                    and not re.search(r'<a\b[^>]*href=[^>]*webui', html, re.I)
                    and not re.search(r'<a\b[^>]*id=["\']webui', html, re.I))
        check("登录页已删除 NapCat 控制台入口", no_console_entry(login_html))
        check("配置向导已删除 NapCat 控制台入口", no_console_entry(setup_html))
        check("登录页含「刷新二维码」与自动拉起", "btn-qr" in login_html and "autoStart" in login_html)

        st = get("/api/qqlogin/status")[2]
        check("登录状态字段完整",
              all(k in st for k in ("napcat_installed", "napcat_running", "qr_image", "qr_key",
                                    "qr_source", "is_login", "onebot_online", "setup", "hint")),
              f"installed={st['napcat_installed']} running={st['napcat_running']} qr={st['qr_source'] or 'none'}")
        check("登录状态不再对外暴露 webui_url / 控制台地址",
              "webui_url" not in st and "6099/webui" not in json.dumps(st, ensure_ascii=False))

        # ---------- B. NapCat 安装自检 ----------
        print("\n[B] NapCat 安装自检与配置修复")
        s0 = get("/api/napcat/setup")[2]
        check("GET /api/napcat/setup 可用", s0.get("ok") is True and "status" in s0,
              f"installed={s0.get('status', {}).get('installed')} running={s0.get('status', {}).get('running')}")
        s1 = post("/api/napcat/setup")
        check("POST /api/napcat/setup 返回自检结果", "fixed" in s1 and "issues" in s1,
              f"fixed={len(s1.get('fixed', []))} issues={len(s1.get('issues', []))}")
        insp = napcat_setup.inspect()
        check("WebUI host 已固定为 127.0.0.1（修复拒绝连接）",
              insp["webui_host"] == "127.0.0.1", f"host={insp['webui_host']}")
        check("OneBot HTTP 服务已启用且端口 3000",
              insp["onebot_http_enabled"] and insp["onebot_port"] == 3000)
        check("自检报告已写入 state/",
              (config.state("napcat_setup.json")).is_file())
        cfg_paths = [p for p in [insp["webui_config"]] + insp["onebot_configs"] if p]
        check("已生成 .rmbak 可回滚备份",
              any(Path(p).with_suffix(Path(p).suffix + ".rmbak").is_file() for p in cfg_paths),
              f"{len(cfg_paths)} 个配置文件")
        print("  修复明细：" + ("；".join(s1["fixed"]) or "（配置本来就是正确的）"))

        # ---------- C. 分类不漏项 ----------
        print("\n[C] 分类完整性 / 召回 / 多归属")
        state = get("/api/state")[2]
        c = state["counts"]
        check("目录条目总数仍是 1625（分类升级未丢文件）", c["total"] == 1625, f"total={c['total']}")
        check("完整性校验通过", state["integrity"]["ok"] is True,
              f"unique={state['integrity']['unique_ids']} tagged={state['integrity']['tagged']}")
        check("主题标签已生成", c.get("tags", 0) >= 40 and c.get("tagged") == c["total"],
              f"tags={c.get('tags')} tagged={c.get('tagged')}")

        q = urllib.parse.quote("高等代数")
        hits = get(f"/api/files?dim=classify&node=%5B%5D&q={q}&limit=500")[2]
        check("搜索「高等代数」不再是 1 条", hits["total"] >= 100, f"total={hits['total']}（旧版为 1）")

        tagnode = urllib.parse.quote(json.dumps(["高等代数"], ensure_ascii=False))
        taghits = get(f"/api/files?dim=tag&node={tagnode}&limit=500")[2]
        check("「按主题标签 › 高等代数」可下钻且不留空", taghits["total"] >= 100,
              f"total={taghits['total']}")

        tree = get("/api/tree?dim=tag&node=%5B%5D")[2]
        names = {x["name"] for x in tree["children"]}
        check("标签树含相关主题节点", "高等代数" in names and len(names) >= 40,
              f"{len(names)} 个标签节点")
        sum_counts = sum(x["count"] for x in tree["children"])
        check("多归属生效：标签节点计数之和 > 文件总数",
              sum_counts > c["total"], f"{sum_counts} > {c['total']}")

        # 微信来源只并入、绝不删 QQ 条目（mock save，内存验证）
        cat = server.CAT or catalog.load()
        before = len(catalog.items(cat))
        old_save = catalog.save
        catalog.save = lambda _c: None
        try:
            n = catalog.upsert_manifest(cat, [{
                "source": "微信(WeChatFerry)", "group": "自测群", "path": "t.pdf",
                "name": "线性代数讲义.pdf", "folder": "(群文件消息)"}], config.CFG)
        finally:
            catalog.save = old_save
        after = len(catalog.items(cat))
        check("微信文件并入不删 QQ 群条目", n == 1 and after == before + 1,
              f"{before} → {after}")
        v = catalog.verify_integrity(cat)
        check("并入后完整性仍通过", v["ok"] is True, f"total={v['total']}")

        # ---------- D. 微信入口 ----------
        print("\n[D] 微信登录与群文件采集")
        ws = get("/api/wechat/wcf/status")[2]
        check("微信状态字段完整",
              all(k in ws for k in ("enabled", "available", "login", "capturing",
                                    "captured", "saved_rooms", "login_hint")),
              f"enabled={ws['enabled']} login={ws['login']} capturing={ws['capturing']}")
        lg = post("/api/wechat/wcf/login")
        check("微信登录检测端点可用且有可操作指引",
              "ok" in lg and (lg.get("hint") or lg.get("msg") or lg.get("error")),
              f"ok={lg.get('ok')} error={(lg.get('error') or '')[:60]}")
        rs = get("/api/wechat/wcf/rooms")[2]
        check("群清单端点可用（未登录时给出明确原因）", "ok" in rs and "reason" in rs,
              f"ok={rs.get('ok')} reason={(rs.get('reason') or '')[:60]}")

        # 一键启用 / 关闭：测完必须恢复原状
        orig = bool(config.CFG["sources"]["wechat"]["wcf"].get("enabled"))
        en = post("/api/wechat/wcf/enable", {"enabled": True})
        en_state = get("/api/wechat/wcf/status")[2]
        off = post("/api/wechat/wcf/enable", {"enabled": orig})
        check("一键启用 / 关闭可用且状态可回退",
              en.get("ok") is True and en_state.get("enabled") is True and off.get("ok") is True,
              f"enabled→True→{orig}")
        check("配置回退到原值",
              bool(config.CFG["sources"]["wechat"]["wcf"].get("enabled")) == orig)

        diag = get("/api/diagnose")[2]
        check("系统诊断含 NapCat 与微信检查项", "napcat" in diag and "wechat" in diag)

        # ---------- 回归：老端点 ----------
        print("\n[E] 老端点回归")
        for p in ("/api/health", "/api/tree?dim=classify&node=%5B%5D",
                  "/api/files?dim=classify&node=%5B%5D&limit=5", "/api/settings", "/api/outline"):
            try:
                d = get(p)[2]
                check("GET " + p.split("?")[0], d.get("ok") is not False, "")
            except Exception as e:
                check("GET " + p.split("?")[0], False, str(e))

        # ---------- F. v3.1.0 泛化分类 ----------
        print("\n[F] v3.1.0 泛化分类回归")
        raw, ct, _ = get("/taxonomy")
        check("GET /taxonomy 分类体系页面可用", len(raw) > 3000 and "html" in ct, f"{len(raw)} B")
        check("页面顶部有分类体系入口", 'id="btn-taxonomy"' in
              (config.WEB / "index.html").read_text(encoding="utf-8"))
        snap = get("/api/taxonomy")[2]
        check("GET /api/taxonomy 快照字段完整",
              all(k in snap for k in ("genre_count", "alias_count", "genres",
                                      "genre_distribution", "modality_distribution", "profile")),
              f"{snap.get('genre_count')} 体裁 / {snap.get('alias_count')} 同义词")
        check("快照声明不采用 im-mcp（隐私边界）",
              any("im-mcp" in s for s in snap.get("not_adopted", [])))
        for dim in ("genre", "topic", "modality"):
            d = get(f"/api/tree?dim={dim}&node=%5B%5D")[2]
            check(f"/api/tree?dim={dim} 有节点", d.get("ok") is True and len(d["children"]) > 0,
                  f"{len(d.get('children', []))} 个")
        stt = get("/api/state")[2]
        check("/api/state 含 taxonomy 与 genre/topics/modalities 计数",
              "genre_count" in (stt.get("taxonomy") or {})
              and all(k in stt["counts"] for k in ("genres", "topics", "modalities")))
        pv = post("/api/taxonomy/preview", {"rows": [
            {"folder": "财务/报销", "name": "11月差旅费报销单.xlsx", "ext": ".xlsx"},
            {"folder": "例会", "name": "周会会议纪要.docx", "ext": ".docx"}]})
        check("dry-run 预览不写盘且给出具体体裁",
              pv.get("dry_run") is True and all(
                  x["genre"] in ("财务与票据", "会议与纪要") for x in pv["items"]),
              "、".join(x["genre"] for x in pv.get("items", [])))
        check("目录完整性（含新维度）仍通过", stt["integrity"]["ok"] is True,
              f"missing_genre={stt['integrity'].get('missing_genre')}")

    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=3)

    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"  结果：{passed}/{len(RESULTS)} 通过")
    for n, ok, d in RESULTS:
        if not ok:
            print("   FAIL:", n, d)
    print("=" * 60)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""v3.2.0 端到端自测：起真实 HTTP 服务，逐个打接口并做完整性断言。

覆盖用户反馈的核心问题：
  A. 静态页面 / QQ 登录页（无微信、无分类体系入口、无控制台外链）
  B. NapCat 安装自检与配置修复
  C. 单值分类一致性（subject/kind/source 三个维度：树节点和 == 文件总数，绝不空分类 / 计数对不上）
  D. 分类完整性 + 搜索多归属召回（高等代数）+ 不错分回归
  E. 老端点回归（health / tree / files / settings / outline）
  F. 群聊管理（增减群 + 群筛选）
  G. v3.4.0：主页 Obsidian 完整链路、库状态 / 库内检索、离线导入闸门、四六级与 CET 精准召回

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

# 预载真实目录到 server，避免首请求触发阻塞式 refresh（确保集成测试首屏即稳定）
server.CAT = catalog.load()

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
    print("  v3.2.0 端到端自测（真实 HTTP 服务 @ %s）" % BASE)
    print("=" * 60)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # ---------- A. 静态页面 / 登录 ----------
        print("\n[A] 页面与静态资源")
        for p in ("/", "/login", "/setup", "/app.js", "/style.css"):
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
        check("主页与登录页不再含微信入口（应已删除）",
              "微信" not in (config.WEB / "index.html").read_text(encoding="utf-8")
              and "wechat" not in login_html.lower())

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

        # ---------- C. 单值分类一致性（直接守护用户反馈的计数 bug）----------
        print("\n[C] 单值分类一致性（subject / kind / source）")
        state = get("/api/state")[2]
        c = state["counts"]
        total = c["total"]
        check("目录条目总数 > 0 且完整性校验通过（分类升级未丢文件）",
              total > 0 and state["integrity"]["ok"] is True,
              f"total={total} unique={state['integrity']['unique_ids']} tagged={state['integrity']['tagged']}")
        for dim in ("subject", "kind", "source"):
            tree = get(f"/api/tree?dim={dim}&node=%5B%5D")[2]
            files = get(f"/api/files?dim={dim}&node=%5B%5D&limit=5")[2]
            sum_counts = sum(x["count"] for x in tree["children"])
            check(f"维度 {dim}：树节点计数之和 == 文件总数（无空分类/计数对不上）",
                  tree.get("ok") and files.get("ok") and sum_counts == files["total"] == total,
                  f"树和={sum_counts} 文件数={files['total']} 节点数={len(tree['children'])}")
            # 逐层下钻：每个非末级节点，其「文件列表 total」必须等于树里该节点的 count
            # 抽查首个可下钻节点
            if tree["children"]:
                first = tree["children"][0]["name"]
                node = urllib.parse.quote(json.dumps([first], ensure_ascii=False))
                sub = get(f"/api/tree?dim={dim}&node={node}")[2]
                subf = get(f"/api/files?dim={dim}&node={node}&limit=5")[2]
                if sub.get("ok") and sub.get("children"):
                    sub_sum = sum(x["count"] for x in sub["children"])
                    check(f"维度 {dim} › {first}：下钻后仍一致",
                          sub_sum == subf["total"],
                          f"子树和={sub_sum} 文件数={subf['total']}")

        # ---------- D. 分类完整性 + 搜索多归属召回 + 不错分 ----------
        print("\n[D] 完整性 / 召回 / 不错分")
        check("标签覆盖全部条目（单值分类下每条都带标签）",
              c.get("tagged") == c["total"] and c.get("tags", 0) >= 40,
              f"tags={c.get('tags')} tagged={c.get('tagged')}")

        q = urllib.parse.quote("高等代数")
        hits = get(f"/api/files?dim=subject&node=%5B%5D&q={q}&limit=500")[2]
        check("搜索「高等代数」不是 1 条（多归属别名召回）", hits["total"] >= 100, f"total={hits['total']}（旧版为 1）")

        # 不错分：.pptx 销售报表不应归为课件资源；工作资料归位；流体力学→大学物理/试卷
        from lib import classify as _clf
        _, _, k_rpt = _clf.classify({"folder": "", "name": "2024年Q3销售业绩报表.pptx"}, config.CFG)
        check("销售报表 .pptx 不再错判为课件资源", k_rpt != "课件资源", f"kind={k_rpt}")
        _, _, k_mt = _clf.classify({"folder": "例会", "name": "周会会议纪要.docx", "ext": ".docx"}, config.CFG)
        check("周会会议纪要归为会议纪要", k_mt == "会议纪要", f"kind={k_mt}")
        d_f, s_f, k_f = _clf.classify({"folder": "", "name": "流体力学I期末试题.pdf"}, config.CFG)
        check("流体力学I期末试题 → 大学物理/试卷与解析", s_f == "大学物理" and k_f == "试卷与解析", f"{s_f}/{k_f}")

        # ---------- E. 老端点回归 ----------
        print("\n[E] 老端点回归")
        for p in ("/api/health", "/api/tree?dim=subject&node=%5B%5D",
                  "/api/files?dim=subject&node=%5B%5D&limit=5", "/api/settings", "/api/outline"):
            try:
                d = get(p)[2]
                check("GET " + p.split("?")[0], d.get("ok") is not False, "")
            except Exception as e:
                check("GET " + p.split("?")[0], False, str(e))

        # 旧多值维度必须已失效：dim=classify 回落到 subject，不得产生 genre 类节点
        legacy = get("/api/tree?dim=classify&node=%5B%5D")[2]
        if legacy.get("ok"):
            check("dim=classify 未暴露旧体裁节点（已迁移到单值）",
                  not any("体裁" in (x.get("name") or "") for x in legacy.get("children", [])),
                  f"{len(legacy.get('children', []))} 个节点")

        diag = get("/api/diagnose")[2]
        check("系统诊断仍可用（含 NapCat 检查，但不再含微信）", "napcat" in diag)

        print("\n[F] 群聊管理（增减群 + 群筛选）")
        grp = get("/api/groups")[2]
        check("/api/groups 返回 ok 且含 configured/available",
              grp.get("ok") and "configured" in grp and "available" in grp,
              f"configured={len(grp.get('configured', []))}")
        groups_all = sorted({x.get("group", "") for x in server.CAT["items"]})
        g0 = groups_all[0]
        cnt_g0 = sum(1 for x in server.CAT["items"] if x.get("group") == g0)
        gf = get("/api/files?dim=subject&node=%5B%5D&group=" + urllib.parse.quote(g0) + "&limit=5")[2]
        check("群筛选 /api/files?group 只返回该群",
              gf.get("ok") and gf.get("total") == cnt_g0, f"total={gf.get('total')} expect={cnt_g0}")
        gt = get("/api/tree?dim=subject&node=%5B%5D&group=" + urllib.parse.quote(g0))[2]
        check("群筛选 /api/tree?group 只返回该群",
              gt.get("ok") and gt.get("ok") and sum(c["count"] for c in gt.get("children", [])) == cnt_g0, "")
        import copy as _copy
        _snap = _copy.deepcopy(config.CFG)
        try:
            a = config.add_qq_group("g_t3_tmp", "T群", "888888888")
            check("add_qq_group 写入新群且不重排代号",
                  "g_t3_tmp" in a and all(k in a for k in _snap.get("sources", {}).get("qq", {}).get("groups", {})))
            try:
                config.add_qq_group("g_bad", "坏", "xyz"); check("非法群号被拒绝", False, "")
            except ValueError:
                check("非法群号被拒绝", True, "")
            r = config.remove_qq_group("g_t3_tmp")
            check("remove_qq_group 移除临时群", "g_t3_tmp" not in r)
        finally:
            config.CFG.clear(); config.CFG.update(_snap)
            config.write_json(config.CONFIG_PATH, _snap)

        print("\n[G] v3.4.0 Obsidian 完整链路 / AI 智能 / 离线导入闸门")
        # 主页必须能看见完整的四步链路
        home_raw, _, _ = get("/")
        home = home_raw.decode("utf-8", "replace")
        for token in ("Obsidian 知识库", "一键批量导入", "库内 AI 检索", "自动分类入库", "vault-strip"):
            check("主页链路含「" + token + "」", token in home, "")

        vs = get("/api/vault/status")[2]
        check("/api/vault/status 返回新库完整状态",
              vs.get("ok") and vs.get("name") == config.vault_name()
              and all(k in vs for k in ("downloaded", "notes", "assets", "outlines", "structure", "by_kind")),
              f"name={vs.get('name')} downloaded={vs.get('downloaded')}")

        vq = get("/api/vault/search?q=" + urllib.parse.quote("四六级真题") + "&limit=5")[2]
        check("/api/vault/search 结构正确（只搜库内笔记）",
              vq.get("ok") and isinstance(vq.get("items"), list) and "answer" in vq,
              f"found={vq.get('found')} pool={vq.get('total')}")
        if vs.get("downloaded") and vs.get("notes"):
            check("库内已有笔记时能检索到资料", bool(vq.get("items")), f"matched={vq.get('matched')}")

        ls = get("/api/local/scan")[2]
        check("/api/local/scan 只读盘点可用",
              ls.get("ok") and isinstance(ls.get("files"), list) and isinstance(ls.get("dirs"), list),
              f"matched={ls.get('matched')} dirs={len(ls.get('dirs', []))}")

        pair = ({"id": ls["files"][0]["id"], "path": ls["files"][0]["path"]}
                if ls.get("files") else {"id": "none", "path": "none"})
        before_dl = vs.get("downloaded")
        gate = post("/api/vault/import-local", {"confirm": False, "pairs": [pair]})
        check("离线导入未确认时拒绝（confirm 闸门）", gate.get("ok") is False)
        gate2 = post("/api/vault/import-local", {"confirm": True,
                                                 "pairs": [{"id": "none", "path": "C:\\Windows\\win.ini"}]})
        check("离线导入拒绝白名单之外的路径", gate2.get("ok") is False)
        check("闸门测试不改动库状态", get("/api/vault/status")[2].get("downloaded") == before_dl, "")

        ask = post("/api/ask", {"q": "给我找一套四六级真题", "scope": ["英语"],
                                "dim": "subject", "fast": True})
        srcs = [s.get("name", "") if isinstance(s, dict) else str(s) for s in ask.get("sources", [])]
        check("AI 修复：subject=英语 下问四六级真题不再答「没有」",
              ask.get("found") is True and any("CET" in n.upper() for n in srcs),
              f"found={ask.get('found')} sources={len(srcs)}")
        cet6 = get("/api/ask?q=" + urllib.parse.quote("CET6真题有哪些") + "&dim=subject&fast=1")[2]
        n6 = [s.get("name", "") if isinstance(s, dict) else str(s) for s in cet6.get("sources", [])]
        check("AI 精准召回 CET6 不混入 CET4",
              cet6.get("found") is True and n6 and all("CET6" in n.upper() for n in n6[:5]),
              f"{n6[:3]}")

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

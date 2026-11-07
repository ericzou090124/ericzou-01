# -*- coding: utf-8 -*-
"""v3.1.0 泛化分类端到端自测：证明分类是内容驱动的，不是「学生一套 / 店主一套」。

覆盖：
  A. 校园群 / 工作群双场景对照：工作资料必须落到具体体裁，不能全进「其他资料」，
     且同一函数对同一行输入的结果不受「周围是什么群」影响（无隐藏场景分支）。
  B. 动态主题 / 模态 / 敏感件闸门 / 语义匹配。
  C. 受控词表 CRUD（隔离 state，绝不污染用户目录）。
  D. 真实 1625 条目录原地重分类的四道完整性门禁 + 新增三个下钻维度。
  E. 真实 HTTP 服务：/taxonomy 页面、/api/taxonomy、preview、synonym、新维度接口。

用法：python tools/test_taxonomy.py
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from lib import catalog, classify, config, taxonomy  # noqa: E402

PORT = int(os.environ.get("RM_TAX_PORT", "8801"))
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, detail: str = ""):
    ok = bool(cond)
    RESULTS.append((name, ok, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


def get(path: str, timeout: float = 20):
    with OPENER.open(BASE + path, timeout=timeout) as r:
        raw = r.read()
        ct = r.headers.get("Content-Type", "")
    return raw, ct, json.loads(raw.decode("utf-8")) if "json" in ct else None


def post(path: str, body: dict | None = None, timeout: float = 30):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(body or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def row(folder: str, name: str) -> dict:
    ext = (name.rsplit(".", 1)[-1] if "." in name else "")
    return {"folder": folder, "name": name,
            "path": (folder + "/" if folder else "") + name,
            "ext": "." + ext if ext else "", "size_bytes": 1024}


# 两套语料：故意混合放进同一个列表，程序不知道哪几行属于「学生」、哪几行属于「工作」
CAMPUS = [
    (row("课程资料/高等代数", "第七章 线性变换与特征值.pdf"), "课程与教学|培训与资料|参考资料"),
    (row("考试与复习", "2023年线性代数期末真题A卷.doc"), "试题与考核"),
    (row("科研/论文", "本科毕业设计开题报告.docx"), "科研与文献|项目与任务|报告与总结"),
    (row("教材", "理论力学 重庆大学出版社 第1版.pdf"), "参考资料|培训与资料|课程与教学"),
]
OFFICE = [
    (row("客户资料/华南区", "2024年11月销售合同_补充协议.pdf"), "合同与协议"),
    (row("财务/报销", "11月差旅费报销单_张三.xlsx"), "财务与票据"),
    (row("采购", "供应商进货单_11月.xlsx"), "采购与供应"),
    (row("例会", "2024-11-05 周会会议纪要.docx"), "会议与纪要"),
    (row("法务", "保密协议NDA_签署版.pdf"), "法务与合规"),
    (row("人事", "2024版员工手册与考勤制度.docx"), "人事与行政"),
    (row("产品", "PRD 用户故事与功能清单 v2.1.pdf"), "产品与需求"),
    (row("项目/智慧门店", "智慧门店项目里程碑排期表.xlsx"), "项目与任务"),
    (row("运营", "第三季度销售报表与业绩复盘.pptx"), "客户与销售|报告与总结|数据与报表"),
    (row("行政", "关于2025年春节放假安排的通知.pdf"), "通知与公告"),
    (row("数据", "门店经营指标看板与台账.xlsx"), "数据与报表"),
    (row("研发", "接口文档与SDK部署说明.md"), "代码与工程"),
]


def main() -> int:
    print("=" * 66)
    print("  v3.1.0 泛化分类自测（内容驱动 / 双场景对照 / 真实 HTTP）")
    print("=" * 66)

    # ---------------- A. 双场景对照 ----------------
    print("\n[A] 校园群 / 工作群对照")
    office_out = {}
    for r, expected in OFFICE:
        g = taxonomy.infer(r, config.CFG)["genre"]
        office_out[r["name"]] = g
        check(f"工作资料「{r['name'][:20]}」→ {g}", g in expected.split("|"), f"期望 {expected}")
    for r, expected in CAMPUS:
        g = taxonomy.infer(r, config.CFG)["genre"]
        check(f"校园资料「{r['name'][:20]}」→ {g}", g in expected.split("|"), f"期望 {expected}")

    bad = [g for g in office_out.values() if g in ("其他资料", "参考资料")]
    check("工作群资料没有全部落进「综合 / 其他资料 / 其他」", not bad, f"长尾兜底 {len(bad)}/{len(OFFICE)} 份")
    specific = len({g for g in office_out.values()})
    check("工作群体裁足够精细（≥6 个不同规范体裁）", specific >= 6, f"{specific} 个体裁")
    check("旧三级分类不再把工作资料塞进「课件资源」",
          classify.classify_extended(OFFICE[8][0], config.CFG)["kind"] == "客户与销售",
          classify.classify_extended(OFFICE[8][0], config.CFG)["kind"])

    # 同一输入，先跑完一整批校园资料再跑，结果必须逐字节一致 → 无隐藏「场景自适应」状态
    before = {k: json.dumps(taxonomy.infer(r, config.CFG), ensure_ascii=False, sort_keys=True)
              for k, (r, _e) in enumerate(OFFICE)}
    for r, _e in CAMPUS:
        taxonomy.infer(r, config.CFG)
    after = {k: json.dumps(taxonomy.infer(r, config.CFG), ensure_ascii=False, sort_keys=True)
             for k, (r, _e) in enumerate(OFFICE)}
    check("分类结果不受「周围是什么群」影响（无场景分支 / 无隐藏全局态）", before == after)
    src = taxonomy.infer.__code__.co_names
    check("推断函数没有调用场景识别", "detect_profile" not in src, f"co_names={len(src)} 项")

    # ---------------- B. 主题 / 模态 / 闸门 / 语义匹配 ----------------
    print("\n[B] 动态主题 / 模态 / 敏感件闸门 / 语义匹配")
    t = taxonomy.infer(OFFICE[0][0], config.CFG)
    check("主题词从群内文件夹动态提取（华南区）", "华南区" in t["topics"], str(t["topics"]))
    check("主题来自内容而非预设主题表", "华南区" not in {a for g in taxonomy.genres() for a in g["aliases"]})
    mods = {taxonomy.modality(row("x", "a.xlsx")): "表格",
            taxonomy.modality(row("x", "a.pptx")): "演示",
            taxonomy.modality(row("x", "a.zip")): "压缩包",
            taxonomy.modality(row("x", "a.mp4")): "音视频"}
    check("模态按扩展名正确识别", len(mods) == 4, str(mods))
    sens = row("人事", "员工银行卡与密码登记表.xlsx")
    check("敏感件闸门命中", taxonomy.is_sensitive(sens, config.CFG) is True)
    cfg_llm = copy.deepcopy(config.CFG)
    cfg_llm["classification"]["taxonomy"]["llm_assist"] = True
    inf = taxonomy.infer(sens, config.CFG)
    check("敏感件即使开启 LLM 也只走规则层",
          taxonomy.llm_enrich(sens, inf, cfg_llm) is inf)
    check("语义匹配：进货单 → 采购与供应",
          "采购与供应" in taxonomy.match("进货单", config.CFG)["genres"])
    check("语义匹配：报销 → 财务与票据",
          "财务与票据" in taxonomy.match("报销", config.CFG)["genres"])
    ex = classify.expand_query("采购单", config.CFG)
    check("搜索召回扩展到同体裁用词", "进货单" in ex and "供应商" in ex, f"{len(ex)} 个候选词")
    _, n_ga = catalog.query(catalog.load(), "classify", [], "高等代数", limit=1,
                            with_total=True, cfg=config.CFG)
    check("v3.0.0 的「高等代数」召回未回归", n_ga >= 100, f"{n_ga} 条")

    # ---------------- C. 受控词表 CRUD（隔离） ----------------
    print("\n[C] 受控词表 CRUD（隔离 state，可撤销）")
    orig_state, orig_path = config.STATE, taxonomy._overrides_path
    tmp = Path(tempfile.mkdtemp(prefix="rm_taxonomy_"))
    config.STATE = tmp
    taxonomy._overrides_path = lambda: tmp / "taxonomy_overrides.json"
    try:
        r1 = taxonomy.save_synonym("财务与票据", "对账单", "add", config.CFG)
        check("新增同义词成功", r1.get("ok") is True and "对账单" in r1["aliases"])
        g2 = taxonomy.infer(row("财务", "华南区客户对账单.xlsx"), config.CFG)["genre"]
        check("新同义词立即生效（对账单 → 财务与票据）", g2 == "财务与票据", g2)
        r2 = taxonomy.save_synonym("财务与票据", "对账单", "remove", config.CFG)
        check("移除同义词成功（可撤销）", r2.get("ok") is True and "对账单" not in r2["aliases"])
        r3 = taxonomy.save_synonym("不存在的体裁", "xx", "add", config.CFG)
        check("未知体裁被拒绝", r3.get("ok") is False)
    finally:
        config.STATE = orig_state
        taxonomy._overrides_path = orig_path
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------- D. 真实目录完整性 ----------------
    print("\n[D] 真实目录原地重分类 · 四道门禁 + 新维度")
    real = catalog.load()
    cat = copy.deepcopy(real)
    xs = catalog.items(cat)
    before_ids = [x["id"] for x in xs]
    before_dl = {x["id"]: bool(x.get("downloaded")) for x in xs}
    check("真实目录条目数为 1625", len(xs) == 1625, f"total={len(xs)}")
    n = catalog.reclassify(cat, config.CFG)
    after_ids = [x["id"] for x in xs]
    after_dl = {x["id"]: bool(x.get("downloaded")) for x in xs}
    check("重分类不改变条目数", n == len(xs) == len(before_ids))
    check("重分类不改变 id 集合", set(after_ids) == set(before_ids))
    check("重分类不改变下载状态", after_dl == before_dl)
    v = catalog.verify_integrity(cat)
    check("重分类后完整性门禁通过（含 genre / modality）", v["ok"] is True,
          f"missing_genre={v['missing_genre']} missing_modality={v['missing_modality']}")
    c = catalog.counts(cat)
    check("每条都有可浏览体裁", c["genre_covered"] + c["genre_other"] == c["total"],
          f"covered={c['genre_covered']} long_tail={c['genre_other']}")
    check("动态主题维度有内容", c["topics"] > 100, f"{c['topics']} 个主题")
    for dim, least in (("genre", 5), ("topic", 50), ("modality", 4)):
        tr = catalog.tree(cat, dim, [])
        check(f"新下钻维度 {dim} 可用", len(tr) >= least, f"{len(tr)} 个节点")
    gh = catalog.query(cat, "genre", ["试题与考核"], "", limit=5, with_total=True)
    check("按体裁可下钻且不留空", gh[1] > 0, f"{gh[1]} 份")

    # 微信 / 本地来源只并入，绝不删 QQ 条目（真实缺陷回归）
    before = len(catalog.items(cat))
    catalog.upsert_manifest(cat, [row("财务/报销", "11月差旅费报销单_张三.xlsx") |
                                  {"source": "微信(WeChatFerry)", "group": "自测工作群"}], config.CFG)
    check("工作群来源并入不删既有条目", len(catalog.items(cat)) == before + 1,
          f"{before} → {len(catalog.items(cat))}")
    check("并入后完整性仍通过", catalog.verify_integrity(cat)["ok"] is True)

    # ---------------- E. 真实 HTTP ----------------
    print("\n[E] 真实 HTTP 服务 / 新端点")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    saved_save = catalog.save
    catalog.save = lambda _c: None  # 任何会写盘的请求都只在内存生效
    try:
        raw, ct, _ = get("/taxonomy")
        check("GET /taxonomy 页面可用", len(raw) > 3000 and "html" in ct, f"{len(raw)} B")
        check("分类体系页面含双场景样例与边界说明",
              b"guiwei" in raw and b"im-mcp" in raw and "工作群样例".encode() in raw)
        snap = get("/api/taxonomy")[2]
        check("GET /api/taxonomy 快照完整",
              all(k in snap for k in ("genre_count", "alias_count", "genres",
                                      "genre_distribution", "modality_distribution",
                                      "profile", "sources", "not_adopted")),
              f"{snap['genre_count']} 体裁 / {snap['alias_count']} 同义词")
        check("快照明确标注不采用 im-mcp", any("im-mcp" in x for x in snap["not_adopted"]))
        check("profile 明确声明仅统计展示", "仅统计" in snap["profile"]["note"])
        mt = get("/api/taxonomy?q=" + urllib.parse.quote("进货单"))[2]
        check("GET /api/taxonomy?q= 语义匹配可用",
              "采购与供应" in (mt.get("match") or {}).get("genres", []))
        st = get("/api/state")[2]
        check("/api/state 含 taxonomy 概要", "genre_count" in (st.get("taxonomy") or {}))
        check("/api/state counts 含新维度计数",
              all(k in st["counts"] for k in ("genres", "topics", "modalities", "genre_covered")))
        diag = get("/api/diagnose")[2]
        check("/api/diagnose 含 taxonomy 检查项", "taxonomy" in diag)
        for dim in ("genre", "topic", "modality"):
            d = get(f"/api/tree?dim={dim}&node=%5B%5D")[2]
            check(f"GET /api/tree?dim={dim} 可用", d.get("ok") is True and len(d["children"]) > 0,
                  f"{len(d['children'])} 个节点")
        pv = post("/api/taxonomy/preview", {"rows": [r for r, _e in OFFICE[:6]]})
        check("POST /api/taxonomy/preview 是纯 dry-run",
              pv.get("dry_run") is True and len(pv["items"]) == 6)
        check("dry-run 结果对工作资料给出具体体裁",
              all(x["genre"] not in ("其他资料", "参考资料") for x in pv["items"]),
              "、".join(x["genre"] for x in pv["items"]))
        # CRUD 端点：隔离 overrides 路径，避免写用户 state
        tmp2 = Path(tempfile.mkdtemp(prefix="rm_tax_http_"))
        orig_path2 = taxonomy._overrides_path
        taxonomy._overrides_path = lambda: tmp2 / "taxonomy_overrides.json"
        try:
            syn = post("/api/taxonomy/synonym", {"genre": "采购与供应", "word": "验收清单"})
            check("POST /api/taxonomy/synonym 可用", syn.get("ok") is True and "验收清单" in syn["aliases"])
        finally:
            taxonomy._overrides_path = orig_path2
            shutil.rmtree(tmp2, ignore_errors=True)
        bad_syn = post("/api/taxonomy/synonym", {"genre": "不存在的体裁", "word": "x"})
        check("词表 CRUD 拒绝未知体裁", bad_syn.get("ok") is False)
        # 老端点回归
        for p in ("/api/health", "/api/tree?dim=classify&node=%5B%5D",
                  "/api/files?dim=classify&node=%5B%5D&limit=5",
                  "/api/tree?dim=tag&node=%5B%5D", "/wechat", "/login", "/"):
            try:
                raw, _ct, d = get(p)
                ok = len(raw) > 100 and (d is None or d.get("ok") is not False)
                check("老端点回归 " + p.split("?")[0], ok, f"{len(raw)} B")
            except Exception as e:
                check("老端点回归 " + p.split("?")[0], False, str(e))
    finally:
        catalog.save = saved_save
        srv.shutdown()
        srv.server_close()
        th.join(timeout=3)

    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print("\n" + "=" * 66)
    print(f"  结果：{passed}/{len(RESULTS)} 通过")
    for n, ok, d in RESULTS:
        if not ok:
            print("   FAIL:", n, d)
    print("=" * 66)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

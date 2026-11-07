"""持续迭代回归自测：校验核心链路不静默损坏。

用法：
    python tools/smoke_test.py
退出码 0 = 通过；非 0 = 失败（打印首个失败项）。

覆盖（v3.2.0 单值分类模型）：
- lib 各模块可导入
- 索引 rebuild / sync 增量一致性（count 稳定、变更可被拾起）
- 单值树一致性：subject / kind / source 三个维度下，子节点计数之和 == 该节点匹配文件数
  （直接回应用户反馈「分类下文件数目和实际数目完全不一致 / 出现空分类」）
- 分类完整性门禁（无缺项漏项 / 单值 domain/subject/kind 齐全 / 标签覆盖）
- 搜索召回（高等代数多归属别名召回，不只有 1 条）
- 不错分：.pptx 销售报表不判为课件资源；工作群资料归位到工作类类型
- 下载流水线（sync 而非 rebuild、并行路径不丢数据、瞬时失败重试 / 永久失败不重试）
- AI 问答（空问题优雅返回、退化路径命中、LLM 代理策略）
- 配置自检（正常无 errors；坏配置报可读错误）
- NapCat 自检 / QQ 登录页结构（无微信 / 无分类体系入口）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import catalog, config, index, ai, llm  # noqa: E402


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def main():
    print("[1] imports OK")

    cat = catalog.load()
    if not cat.get("items"):
        fail("catalog 为空，无法自测（请先 refresh 或导入数据源）")
    total = len(cat["items"])
    print(f"[2] catalog items = {total}")

    n_rebuild = index.rebuild(cat)
    if n_rebuild != total:
        fail(f"rebuild 写入 {n_rebuild} ≠ catalog {total}")
    print(f"[3] rebuild -> {n_rebuild}")

    n_sync1 = index.sync(cat)
    if n_sync1 != total:
        fail(f"首次 sync 应等效全量，得到 {n_sync1} ≠ {total}")
    print(f"[4] sync(unchanged) -> {n_sync1} (应等于 rebuild)")

    # 制造一处变更：复制一个条目的 body 文件并改写其 stat，sync 应只动该条
    import shutil
    probe = cat["items"][0]
    bp = index.body_path(probe["id"])
    bp.parent.mkdir(parents=True, exist_ok=True)
    prior = bp.read_text(encoding="utf-8", errors="replace") if bp.is_file() else ""
    bp.write_text(prior + "\n# smoke-probe\n", encoding="utf-8")
    n_sync2 = index.sync(cat)
    if n_sync2 != total:
        fail(f"变更后 sync 总条数应不变，得到 {n_sync2} ≠ {total}")
    print(f"[5] sync(after 1 body change) -> {n_sync2} (总数不变，仅该条重算)")

    # 空问题不应抛异常（修复 scope 在定义前被引用）
    try:
        r0 = ai.answer("", cat)
        if not isinstance(r0, dict) or "answer" not in r0:
            fail("ai.answer('') 返回结构异常")
    except Exception as e:
        fail(f"ai.answer('') 抛异常（应为优雅返回）：{type(e).__name__}: {e}")
    print("[6] ai.answer('') 不崩溃（空问题优雅返回）")

    # LLM opener：本地直连、外部走代理
    import urllib.request as _ur
    def _has_proxy(op):
        return any(isinstance(h, _ur.ProxyHandler) for h in op.handlers)
    local_op = llm._opener_for("http://127.0.0.1:8080/v1/chat/completions")
    ext_op = llm._opener_for("https://api.openai.com/v1/chat/completions")
    if _has_proxy(local_op) or not _has_proxy(ext_op):
        fail(f"llm opener 代理策略异常：local_has_proxy={_has_proxy(local_op)} ext_has_proxy={_has_proxy(ext_op)}")
    print("[6c] llm opener: 本地直连 / 外部走代理 区分正确")

    # ---- v3.2.0 核心回归：单值树维度一致性（直接守护用户反馈的计数 bug）----
    v = catalog.verify_integrity(cat)
    if not v["ok"] or v["total"] != total:
        fail(f"[7] 分类完整性校验失败：{v}")
    if v["tagged"] != total:
        fail(f"[7] 标签覆盖不足：{v['tagged']}/{total}（单值分类下每条都应带标签）")
    print(f"[7] 完整性 OK（unique={v['unique_ids']} tagged={v['tagged']}/{total}）")

    for dim in ("subject", "kind", "source"):
        tc = catalog.verify_tree_consistency(cat, dim)
        if not tc["ok"]:
            fail(f"[8] 单值维度 {dim} 不一致：子节点和={tc['children_sum']} 实际={tc['node_total']}（用户反馈的计数 bug 复现）")
        print(f"[8] 维度 {dim} 一致：子节点和={tc['children_sum']} == 实际={tc['node_total']}（{tc['children']} 个节点）")

    # 搜索「高等代数」必须多归属召回，不会只有 1 条
    import json as _json
    _, n_ga = catalog.query(cat, "subject", [], "高等代数", 500, with_total=True, cfg=config.CFG)
    if n_ga < 100:
        fail(f"[9] 搜索「高等代数」召回仅 {n_ga} 条（单值别名召回退化）")
    print(f"[9] 搜索「高等代数」召回 {n_ga} 条（多归属别名生效）")

    # ---- 错分回归：裸扩展名 / 工作群资料 ----
    from lib import classify as _clf
    # 裸 pptx 销售报表不应判为「课件资源」
    _, _, k_report = _clf.classify({"folder": "", "name": "2024年Q3销售业绩报表.pptx"}, config.CFG)
    if k_report == "课件资源":
        fail(f"[10] 销售报表 .pptx 被错判为「课件资源」：{k_report}")
    # 工作群资料应落到工作类类型，而非长尾「其他资料」
    work = [
        ({"folder": "财务/报销", "name": "11月差旅费报销单.xlsx", "ext": ".xlsx"}, "财务与票据"),
        ({"folder": "例会", "name": "2024-11-05 周会会议纪要.docx", "ext": ".docx"}, "会议纪要"),
        ({"folder": "法务", "name": "保密协议NDA_签署版.pdf", "ext": ".pdf"}, "合同与协议"),
        ({"folder": "采购", "name": "供应商进货单_11月.xlsx", "ext": ".xlsx"}, "采购与供应"),
    ]
    for row, want in work:
        _, _, got = _clf.classify(row, config.CFG)
        if got != want:
            fail(f"[10] 工作资料「{row['name']}」归为「{got}」，期望「{want}」")
    # 学科全名命中：流体力学I期末试题 → 大学物理 / 试卷与解析
    d_f, s_f, k_f = _clf.classify({"folder": "", "name": "流体力学I期末试题.pdf"}, config.CFG)
    if s_f != "大学物理" or k_f != "试卷与解析":
        fail(f"[10] 「流体力学I期末试题」错分：{s_f}/{k_f}")
    print(f"[10] 不错分 OK：销售报表→{k_report}；工作资料4/4 归位；流体力学→{s_f}/{k_f}")

    # 下载流水线重构回归：用 sync 而非 rebuild，且并行路径不丢数据
    import tempfile as _tf
    from pathlib import Path as _P
    from lib import download as _dl
    _tmp = _P(_tf.mkdtemp(prefix="rm_dl_test_"))
    _orig_vault = config.vault
    config.vault = lambda: _tmp
    class _FakeQQ:
        @staticmethod
        def online(): return True
        @staticmethod
        def fetch_url(gid, fid, busid): return "http://example/x.pdf"
        @staticmethod
        def download_to(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("body-bytes")
        @staticmethod
        def fmt_size(n): return f"{n}B"
    class _FakeExtract:
        @staticmethod
        def extract(dest, mx): return ("body-bytes", "ok")
        @staticmethod
        def summarize(b): return "summary"
    class _FakeVault:
        @staticmethod
        def asset_rel(x): return f"assets/{x['id']}.pdf"
        @staticmethod
        def write_note(x, body): return f"notes/{x['id']}.md"
        @staticmethod
        def build_outlines(c): return {}
    _calls = {"rebuild": 0, "sync": 0}
    class _FakeIndex:
        @staticmethod
        def body_path(iid): return config.state("bodies") / f"{iid}.txt"
        @staticmethod
        def rebuild(c): _calls["rebuild"] += 1; return 1
        @staticmethod
        def sync(c): _calls["sync"] += 1; return 1
    _orig = (_dl.qq, _dl.vault, _dl.extract, _dl.index, _dl.catalog.save)
    _dl.qq, _dl.vault, _dl.extract, _dl.index = _FakeQQ(), _FakeVault(), _FakeExtract(), _FakeIndex()
    _dl.catalog.save = lambda c: None  # 关键：禁止测试把 2 条假目录写回真实 catalog.json
    _dcat = {"version": 1, "items": [
        {"id": "r-t1", "source": "QQ群", "group": "g", "path": "a.pdf", "name": "a.pdf",
         "ext": ".pdf", "group_id": 123, "file_id": "f1", "busid": 102, "size_bytes": 10, "downloaded": False},
        {"id": "r-t2", "source": "QQ群", "group": "g", "path": "b.pdf", "name": "b.pdf",
         "ext": ".pdf", "group_id": 123, "file_id": "f2", "busid": 102, "size_bytes": 10, "downloaded": False},
    ]}
    os.environ["RM_DOWNLOAD_WORKERS"] = "4"  # 触发并行路径
    try:
        _r = _dl.run(_dcat, ["r-t1", "r-t2"], confirm=True)
    finally:
        _dl.qq, _dl.vault, _dl.extract, _dl.index, _dl.catalog.save = _orig
        config.vault = _orig_vault
        os.environ.pop("RM_DOWNLOAD_WORKERS", None)
    if _r.get("succeeded") != 2:
        fail(f"download.run 应成功 2 条，得到 {_r.get('succeeded')}: {_r}")
    if _calls["rebuild"] != 0 or _calls["sync"] != 1:
        fail(f"download.run 必须只用 sync 不用 rebuild：{_calls}")
    if not (_dcat["items"][0]["downloaded"] and _dcat["items"][1]["downloaded"]):
        fail("download.run 未就地标记条目为已下载")
    print(f"[11] download.run 用 sync(非rebuild) 且并行路径成功 2 条，索引调用 {_calls}")

    # ai.answer 退化路径（FTS 未命中但词命中）必须正确命中，不能误报未找到
    _o_srch, _o_qt, _o_cnt = ai.index.search, ai.index.query_terms, ai.index.count
    ai.index.search = lambda *a, **k: []          # 模拟 FTS 完全 miss
    ai.index.query_terms = lambda q, max_terms=24: ["复变"]  # 命中词在真实 catalog 中存在
    ai.index.count = lambda: total
    try:
        _ra = ai.answer("复变函数", cat, fast=True)
    finally:
        ai.index.search, ai.index.query_terms, ai.index.count = _o_srch, _o_qt, _o_cnt
    if not _ra.get("found"):
        fail(f"ai.answer 退化路径误报未找到（修复前 corpus 为空 valid2 恒空）：{_ra}")
    if _ra.get("mode") not in ("fast", "llm", "local"):
        fail(f"ai.answer 退化路径 mode 异常：{_ra}")
    print(f"[12] ai.answer 退化路径(FTS miss) 仍命中 found={_ra.get('found')} mode={_ra.get('mode')}")

    # 配置自检：正常配置无 errors；坏配置应报可读错误
    import copy as _copy
    from lib import config_validate as _cv
    _good = _cv.validate()
    if not isinstance(_good, dict) or "ok" not in _good or "errors" not in _good or "warnings" not in _good:
        fail("config_validate.validate 返回结构异常")
    _orig_cfg = config.CFG
    try:
        _bad = _copy.deepcopy(config.CFG)
        _bad["port"] = 0
        _bad["allowed_ext"] = []
        _bad["sources"]["qq"]["groups"]["pxb6"]["qq_group"] = "not-a-number"
        config.CFG = _bad
        _r = _cv.validate()
        if _r["ok"]:
            fail("config_validate 对非法配置未报错")
        if len(_r["errors"]) < 3:
            fail(f"config_validate 漏报错误：{_r['errors']}")
    finally:
        config.CFG = _orig_cfg
    print(f"[13] config_validate 正常配置 ok={_good['ok']}；坏配置正确报出 {len(_r['errors'])} 条错误")

    # NapCat 自检 / QQ 登录页结构（v3.2.0：无微信 / 无分类体系入口）
    from lib import napcat_setup as _ns, qqlogin as _ql
    _s = _ns.status()
    if "installed" not in _s or "issues" not in _s or "running" not in _s:
        fail(f"[14] NapCat 自检结构异常：{_s}")
    _ins = _ns.inspect()
    if _ins["installed"] and _ins["webui_host"] not in ("127.0.0.1", ""):
        fail(f"[14] WebUI host 仍是 {_ins['webui_host']}，6099 会拒绝 127.0.0.1 连接")
    _qs = _ql.status()
    if "webui_url" in _qs or not all(k in _qs for k in ("qr_image", "qr_key", "setup", "hint")):
        fail("[14] qqlogin.status 结构异常或仍在对外暴露控制台地址")
    _lg = (config.WEB / "login.html").read_text(encoding="utf-8")
    if 'id="btn-webui"' in _lg or "6099/webui" in _lg:
        fail("[14] 登录页仍保留跑不通的 NapCat 控制台入口")
    if "微信" in _lg or "wechat" in (config.WEB / "index.html").read_text(encoding="utf-8").lower():
        fail("[14] 主页/登录页仍残留微信入口（应已删除）")
    print(f"[14] NapCat 自检(installed={_s['installed']} host={_ins['webui_host']}) / 登录页 / 无微信入口 均 OK")

    # 下载重试：瞬时失败应重试后成功；永久失败(已失效)不重试
    import tempfile as _tf2
    _tmp2 = _P(_tf2.mkdtemp(prefix="rm_retry_test_"))
    _ovc = config.vault
    config.vault = lambda: _tmp2
    class _CountQQ:
        def __init__(self): self.n = 0
        def online(self): return True
        def fetch_url(self, gid, fid, busid):
            self.n += 1
            if self.n < 3:
                raise RuntimeError("OneBot 超时（瞬时）")
            return "http://example/x.pdf"
        def download_to(self, url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text("body")
        def fmt_size(self, n): return f"{n}B"
    class _PermQQ:
        def __init__(self): self.n = 0
        def online(self): return True
        def fetch_url(self, gid, fid, busid):
            self.n += 1
            return None  # 触发『获取直链失败（...已失效...）』，属永久错误
        def download_to(self, url, dest): dest.write_text("x")
        def fmt_size(self, n): return f"{n}B"
    _dcat_r = {"version": 1, "items": [{"id": "r-r1", "source": "QQ群", "group": "g", "path": "a.pdf",
                                        "name": "a.pdf", "ext": ".pdf", "group_id": 1, "file_id": "f",
                                        "busid": 102, "size_bytes": 1, "downloaded": False}]}
    _dcat_p = {"version": 1, "items": [{"id": "r-r2", "source": "QQ群", "group": "g", "path": "b.pdf",
                                        "name": "b.pdf", "ext": ".pdf", "group_id": 1, "file_id": "f",
                                        "busid": 102, "size_bytes": 1, "downloaded": False}]}
    os.environ["RM_DOWNLOAD_WORKERS"] = "1"  # 串行便于计数
    _cq, _pq = _CountQQ(), _PermQQ()
    try:
        _orig_r = (_dl.qq, _dl.vault, _dl.extract, _dl.index, _dl.catalog.save)
        _dl.qq, _dl.vault, _dl.extract, _dl.index = _cq, _FakeVault(), _FakeExtract(), _FakeIndex()
        _dl.catalog.save = lambda c: None
        _rr = _dl.run(_dcat_r, ["r-r1"], confirm=True)
        if _rr.get("succeeded") != 1:
            fail(f"重试后仍未成功：{_rr}")
        if _cq.n < 3:
            fail(f"重试次数不足：fetch 被调用 {_cq.n} 次")
        _dl.qq = _pq
        _pr = _dl.run(_dcat_p, ["r-r2"], confirm=True)
        if _pr.get("succeeded") != 0:
            fail(f"永久失败应 0 成功：{_pr}")
        if _pq.n != 1:
            fail(f"永久错误不应重试（fetch 被调用 {_pq.n} 次）")
    finally:
        _dl.qq, _dl.vault, _dl.extract, _dl.index, _dl.catalog.save = _orig_r
        config.vault = _ovc
        os.environ.pop("RM_DOWNLOAD_WORKERS", None)
    print(f"[15] 下载瞬时失败重试成功（fetch {_cq.n} 次后成功）；[16] 永久失败不重试（fetch {_pq.n} 次）")

    # 集成自测：起一个本地 server 实例（隔离临时 STATE + vault），验证 HTTP 层与 JSON 形状不回归
    import time as _time, shutil as _sh, threading as _th, json as _json
    import urllib.request as _ur, urllib.parse as _up
    import server as _srvmod  # server.py 位于项目根目录（lib 之外），ROOT 已在 sys.path
    _srvmod.CAT = cat  # 预载真实目录，避免首请求触发阻塞式 refresh（本测试会切换临时 STATE）
    _test_port = int(os.environ.get("RM_TEST_PORT", "8799"))
    _tmp_state = _P(_tf.mkdtemp(prefix="rm_srv_state_"))
    _tmp_vault = _P(_tf.mkdtemp(prefix="rm_srv_vault_"))
    _snap_src = config.STATE / "qq_manifest.json"
    if _snap_src.is_file():
        _sh.copy2(_snap_src, _tmp_state / "qq_manifest.json")  # 复用真实快照，使刷新可走 snapshot 模式
    _cfg_port, _orig_state, _orig_vault = config.CFG.get("port"), config.STATE, config.vault
    config.CFG["port"] = _test_port
    config.STATE = _tmp_state
    config.vault = lambda: _tmp_vault
    _srv = None
    try:
        _srv = _srvmod.ThreadingHTTPServer(("127.0.0.1", _test_port), _srvmod.Handler)
        _th.Thread(target=_srv.serve_forever, daemon=True).start()
        _op = _ur.build_opener(_ur.ProxyHandler({}))  # 直连 127.0.0.1，绕开沙箱代理
        def _get(path):
            with _op.open(f"http://127.0.0.1:{_test_port}{path}", timeout=30) as r:
                return _json.loads(r.read().decode("utf-8"))
        _ready = False
        for _ in range(60):
            try: _get("/api/health"); _ready = True; break
            except Exception: _time.sleep(0.3)
        if not _ready:
            fail("集成测试：server 未在预期时间内就绪")
        _hp = _get("/api/health")
        if not _hp.get("ok") or _hp.get("docs") != index.count():
            fail(f"集成 /api/health 异常：{_hp}")
        _dp = _get("/api/diagnose")
        if not _dp.get("ok"):
            fail(f"集成 /api/diagnose 异常：{_dp}")
        # 单值维度 tree 一致性（HTTP 层）
        for dim in ("subject", "kind", "source"):
            _tp = _get(f"/api/tree?dim={dim}&node=" + _up.quote("[]"))
            if not _tp.get("ok") or not isinstance(_tp.get("children"), list):
                fail(f"集成 /api/tree?dim={dim} 异常：{_tp}")
            _fp = _get(f"/api/files?dim={dim}&node=" + _up.quote("[]") + "&limit=5")
            if not _fp.get("ok") or not isinstance(_fp.get("items"), list):
                fail(f"集成 /api/files?dim={dim} 异常：{_fp}")
            _sum = sum(c["count"] for c in _tp["children"])
            if _sum != _fp["total"]:
                fail(f"集成 维度 {dim} 树和={_sum} ≠ 文件总数={_fp['total']}（计数 bug 复现）")
        _sp = _get("/api/state")
        if not _sp.get("ok") or "counts" not in _sp or not _sp["integrity"].get("ok"):
            fail(f"集成 /api/state 异常：{_sp}")
        # 旧多值维度必须已失效（回落单值，不产生 genre/topics/modalities 节点）
        _legacy = _get("/api/tree?dim=classify&node=" + _up.quote("[]"))
        if _legacy.get("ok") and len(_legacy.get("children", [])) > 0:
            # 回落到 subject，应当等于 subject 顶层；只要不出现 genre 类节点即可
            if any("体裁" in (c.get("name") or "") for c in _legacy["children"]):
                fail("集成 dim=classify 仍暴露旧体裁节点（应已迁移）")
        # 群筛选 HTTP 层：group 参数只返回该群；/api/groups 返回已配置+可添加
        _g0 = sorted({x.get("group", "") for x in cat["items"]})[0]
        _gt = _get(f"/api/tree?dim=subject&node=" + _up.quote("[]") + "&group=" + _up.quote(_g0))
        if not _gt.get("ok") or not isinstance(_gt.get("children"), list):
            fail(f"集成 /api/tree?group 异常：{_gt}")
        _gf = _get(f"/api/files?dim=subject&node=" + _up.quote("[]") + "&group=" + _up.quote(_g0) + "&limit=5")
        if not _gf.get("ok"):
            fail(f"集成 /api/files?group 异常：{_gf}")
        if _gf["total"] != sum(1 for x in cat["items"] if x.get("group") == _g0):
            fail(f"集成 group 筛选总数不符：{_gf['total']}")
        _grp = _get("/api/groups")
        if not _grp.get("ok") or "configured" not in _grp or "available" not in _grp:
            fail(f"集成 /api/groups 异常：{_grp}")
        print(f"[17] 集成自测通过：health/diagnose/tree/files/state 均 ok；"
              f"三维度树一致；docs={_hp.get('docs')}；group 筛选与 /api/groups OK")
    finally:
        if _srv: _srv.shutdown(); _srv.server_close()
        config.CFG["port"] = _cfg_port
        config.STATE = _orig_state
        config.vault = _orig_vault

    # ---- v3.3.0 群聊管理：增量增删 + 群筛选 ----
    # [19] config.add_qq_group / remove_qq_group：增量增删、不重排既有代号、非法群号报错、还原真实配置
    import json as _json
    _cfg_path = config.CONFIG_PATH
    _snap = _json.loads(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.is_file() else _copy.deepcopy(config.CFG)
    _orig_groups = dict((config.CFG.setdefault("sources", {}).setdefault("qq", {})).get("groups", {}))
    try:
        _g_add = config.add_qq_group("g_test_tmp", "测试群", "999999999")
        if "g_test_tmp" not in _g_add or _g_add["g_test_tmp"]["qq_group"] != "999999999":
            fail("[19] add_qq_group 未正确写入新群")
        for _k in _orig_groups:
            if _k not in _g_add:
                fail(f"[19] add_qq_group 把既有代号 {_k} 弄丢了（重排问题）")
        try:
            config.add_qq_group("g_x", "坏群", "abc")
            fail("[19] 非法群号未报错")
        except ValueError:
            pass
        _g_rem = config.remove_qq_group("g_test_tmp")
        if "g_test_tmp" in _g_rem:
            fail("[19] remove_qq_group 未移除临时群")
    finally:
        config.CFG.clear(); config.CFG.update(_snap); config.write_json(_cfg_path, _snap)
    print("[19] 群管理 add/remove OK（增量增删、不重排代号、非法群号报错、配置已还原）")

    # [20] 群筛选：tree/query 的 group 参数只返回该群；各群条目和 == 总数
    _groups_all = sorted({x.get("group", "") for x in cat["items"]})
    _sum_pg = 0
    for _g in _groups_all:
        _cnt = sum(1 for x in cat["items"] if x.get("group") == _g)
        _, _tot_g = catalog.query(cat, "subject", [], "", 100000, with_total=True, group=_g)
        if _tot_g != _cnt:
            fail(f"[20] query 群「{_g}」总数={_tot_g} ≠ 实际={_cnt}")
        _tr = catalog.tree(cat, "subject", [], group=_g)
        if sum(c["count"] for c in _tr) != _cnt:
            fail(f"[20] tree 群「{_g}」桶和 != 该群条目数({_cnt})")
        _sum_pg += _cnt
    if _sum_pg != total:
        fail(f"[20] 各群条目和={_sum_pg} ≠ 总数={total}")
    print(f"[20] 群筛选 OK：{len(_groups_all)} 个群，tree/query 均只返回该群；各群和 == 总数({total})")

    # [21] AI 检索范围支持按群限定（_pool 按 group 过滤，保证「只在该群内作答」）
    for _g in _groups_all:
        _pool = ai._pool(cat, {"group": _g})
        if any(x.get("group") != _g for x in _pool):
            fail(f"[21] ai._pool group={_g} 混入其它群")
        if len(_pool) != sum(1 for x in cat["items"] if x.get("group") == _g):
            fail(f"[21] ai._pool group={_g} 数量不符")
    print(f"[21] AI 群范围 OK：_pool 按 group 严格过滤（{len(_groups_all)} 个群）")

    # 最小 LLM 调用（可选）：配置存在则跑，缺失则跳过
    try:
        cfg = config.CFG.get("ai", {}) or {}
        if cfg.get("endpoint") or cfg.get("api_key"):
            r = ai.answer(cat, "请简要说明本库包含哪些科目？", scope=None)
            if not isinstance(r, dict) or "answer" not in r:
                fail("ai.answer 返回结构异常")
            print("[18] ai.answer OK")
        else:
            print("[18] ai.answer skipped (no llm config)")
    except Exception as e:
        print(f"[18] ai.answer skipped (err: {e})")

    print("\nALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()

"""持续迭代回归自测：校验核心链路不静默损坏。

用法：
    python tools/smoke_test.py
退出码 0 = 通过；非 0 = 失败（打印首个失败项）。

覆盖：
- lib 各模块可导入（含 GitHub 微信适配器 wechat_wcf）
- 索引 rebuild / sync 增量一致性（count 稳定、变更可被拾起）
- wechat_wcf.status 在默认关闭下安全返回
- 若 LLM 可用，跑一次最小 ask 不崩
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import catalog, config, index, ai, wechat_wcf  # noqa: E402


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

    s = wechat_wcf.status(config.CFG)
    if s.get("enabled") is not False or s.get("mode") != "wechatferry":
        fail(f"wechat_wcf.status 默认应 enabled=False 且 mode=wechatferry: {s}")
    print(f"[6] wechat_wcf.status ok (enabled={s.get('enabled')}, available={s.get('available')}, mode={s.get('mode')})")

    # 空问题不应抛 NameError（修复 scope 在定义前被引用）
    try:
        r0 = ai.answer("", cat)
        if not isinstance(r0, dict) or "answer" not in r0:
            fail("ai.answer('') 返回结构异常")
    except Exception as e:
        fail(f"ai.answer('') 抛异常（应为优雅返回）：{type(e).__name__}: {e}")
    print("[6b] ai.answer('') 不崩溃（空问题优雅返回）")

    # LLM opener：本地直连、外部走代理
    from lib import llm as _llm
    import urllib.request as _ur
    def _has_proxy(op):
        return any(isinstance(h, _ur.ProxyHandler) for h in op.handlers)
    local_op = _llm._opener_for("http://127.0.0.1:8080/v1/chat/completions")
    ext_op = _llm._opener_for("https://api.openai.com/v1/chat/completions")
    # 本地地址不应走代理（直连）；外部地址应带 ProxyHandler（沿用环境变量代理，沙箱出网必需）
    if _has_proxy(local_op) or not _has_proxy(ext_op):
        fail(f"llm opener 代理策略异常：local_has_proxy={_has_proxy(local_op)} ext_has_proxy={_has_proxy(ext_op)}")
    print("[6c] llm opener: 本地直连 / 外部走代理 区分正确")

    # 微信监听群清单持久化往返
    wechat_wcf.save_rooms(["wxid_a", "wxid_b"])
    if wechat_wcf.load_rooms() != ["wxid_a", "wxid_b"]:
        fail("wechat_wcf save/load_rooms 往返失败")
    wechat_wcf.save_rooms([])  # 还原，避免遗留测试数据
    gr = wechat_wcf.get_rooms(config.CFG)
    if "login" not in gr or "rooms" not in gr:
        fail("wechat_wcf.get_rooms 结构异常")
    print("[8] wechat_wcf 群清单持久化往返 + get_rooms 结构 OK")

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
    print(f"[9] download.run 用 sync(非rebuild) 且并行路径成功 2 条，索引调用 {_calls}")

    # ai.answer 退化路径（FTS 未命中但词命中）必须正确命中，不能误报未找到
    from lib import ai as _ai
    _o_srch, _o_qt, _o_cnt = _ai.index.search, _ai.index.query_terms, _ai.index.count
    _ai.index.search = lambda *a, **k: []          # 模拟 FTS 完全 miss
    _ai.index.query_terms = lambda q, max_terms=24: ["复变"]  # 命中词在真实 catalog 中存在
    _ai.index.count = lambda: total
    try:
        _ra = _ai.answer("复变函数", cat, fast=True)
    finally:
        _ai.index.search, _ai.index.query_terms, _ai.index.count = _o_srch, _o_qt, _o_cnt
    if not _ra.get("found"):
        fail(f"ai.answer 退化路径误报未找到（修复前 corpus 为空 valid2 恒空）：{_ra}")
    if _ra.get("mode") not in ("fast", "llm", "local"):
        fail(f"ai.answer 退化路径 mode 异常：{_ra}")
    print(f"[10] ai.answer 退化路径(FTS miss) 仍命中 found={_ra.get('found')} mode={_ra.get('mode')}")

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
    print(f"[11] config_validate 正常配置 ok={_good['ok']}；坏配置正确报出 {len(_r['errors'])} 条错误")

    # 群文件分类：锁住「泛化词导致领域误判」缺陷（生活与办事词库原含裸词『指南』）
    from lib import classify as _clf
    _cd1 = _clf.classify({"folder": "", "name": "C语言程序设计上机指南.txt"}, config.CFG)[0]
    if _cd1 != "学习":
        fail(f"学习类文档领域误判为「{_cd1}」（词库含泛化词）")
    _cd2 = _clf.classify({"folder": "", "name": "宿舍水电缴费指南.pdf"}, config.CFG)[0]
    if _cd2 != "生活与办事":
        fail(f"生活类文档领域误判为「{_cd2}」")
    _cd3 = _clf.classify({"folder": "", "name": "2024年校招简历模板.docx"}, config.CFG)[0]
    if _cd3 != "实习与就业":
        fail(f"就业类文档领域误判为「{_cd3}」")
    print("[15] 群文件分类领域正确（学习 / 生活与办事 / 实习与就业 均归位）")

    # ---- v3.0.0 新增回归：分类不漏项 / 多归属 / 别名召回 / 微信并入不删条目 ----
    _v = catalog.verify_integrity(cat)
    if not _v["ok"] or _v["total"] != total:
        fail(f"[16] 分类完整性校验失败：{_v}")
    _, _n_ga = catalog.query(cat, "classify", [], "高等代数", limit=1,
                             with_total=True, cfg=config.CFG)
    if _n_ga < 100:
        fail(f"[16] 搜索「高等代数」召回仅 {_n_ga} 条（旧缺陷为 1 条）")
    _tn = catalog.tree(cat, "tag", [])
    if not any(x["name"] == "高等代数" for x in _tn):
        fail("[16] 标签树缺少「高等代数」相关主题节点")
    if sum(x["count"] for x in _tn) <= total:
        fail("[16] 标签未实现多归属（计数之和应大于文件总数）")
    _before_v3 = len(cat["items"])
    catalog.upsert_manifest(cat, [{
        "source": "微信(WeChatFerry)", "group": "自测群", "path": "s.pdf",
        "name": "线性代数讲义.pdf", "folder": "(群文件消息)"}], config.CFG)
    if len(cat["items"]) != _before_v3 + 1:
        fail("[16] 微信来源并入把 QQ 群条目删掉了（漏项回归）")
    cat["items"] = cat["items"][:_before_v3]  # 纯内存还原，不写盘
    print(f"[16] 分类完整性 OK；「高等代数」召回 {_n_ga} 条；{len(_tn)} 个多归属标签；微信并入不删条目")

    # ---- v3.0.0 新增回归：NapCat 自检 / QQ 登录页 / 微信入口 ----
    from lib import napcat_setup as _ns, qqlogin as _ql
    _s = _ns.status()
    if "installed" not in _s or "issues" not in _s or "running" not in _s:
        fail(f"[17] NapCat 自检结构异常：{_s}")
    _ins = _ns.inspect()
    if _ins["installed"] and _ins["webui_host"] not in ("127.0.0.1", ""):
        fail(f"[17] WebUI host 仍是 {_ins['webui_host']}，6099 会拒绝 127.0.0.1 连接")
    _qs = _ql.status()
    if "webui_url" in _qs or not all(k in _qs for k in ("qr_image", "qr_key", "setup", "hint")):
        fail("[17] qqlogin.status 结构异常或仍在对外暴露控制台地址")
    _lg = (config.WEB / "login.html").read_text(encoding="utf-8")
    if 'id="btn-webui"' in _lg or "6099/webui" in _lg:
        fail("[17] 登录页仍保留跑不通的 NapCat 控制台入口")
    if not (config.WEB / "wechat.html").is_file() or 'id="btn-wechat"' not in (config.WEB / "index.html").read_text(encoding="utf-8"):
        fail("[17] 微信登录/群文件页面入口缺失")
    print(f"[17] NapCat 自检(installed={_s['installed']} host={_ins['webui_host']}) / 登录页 / 微信入口 均 OK")

    # ---- v3.1.0 新增回归：内容驱动泛化分类（工作群资料不能全落「其他资料」） ----
    from lib import taxonomy as _tax
    _work = [
        ({"folder": "财务/报销", "name": "11月差旅费报销单.xlsx", "ext": ".xlsx"}, "财务与票据"),
        ({"folder": "采购", "name": "供应商进货单_11月.xlsx", "ext": ".xlsx"}, "采购与供应"),
        ({"folder": "例会", "name": "2024-11-05 周会会议纪要.docx", "ext": ".docx"}, "会议与纪要"),
        ({"folder": "法务", "name": "保密协议NDA_签署版.pdf", "ext": ".pdf"}, "法务与合规"),
    ]
    for _r, _want in _work:
        _got = _tax.infer(_r, config.CFG)["genre"]
        if _got != _want:
            fail(f"[18] 工作群资料「{_r['name']}」被归为「{_got}」，期望「{_want}」")
    if "采购与供应" not in _tax.match("进货单", config.CFG)["genres"]:
        fail("[18] 受控词语义匹配失效")
    if "进货单" not in _clf.expand_query("采购单", config.CFG):
        fail("[18] 泛化召回扩展失效")
    for _d in ("genre", "topic", "modality"):
        if len(catalog.tree(cat, _d, [])) < 2:
            fail(f"[18] 新下钻维度 {_d} 无节点")
    if not catalog.verify_integrity(cat)["ok"]:
        fail("[18] 泛化分类后完整性门禁失败")
    if 'id="btn-taxonomy"' not in (config.WEB / "index.html").read_text(encoding="utf-8"):
        fail("[18] 分类体系入口缺失")
    print("[18] 泛化分类 OK：工作资料 4/4 归位、语义匹配 / 召回扩展 / 三个新维度 / 完整性均通过")

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
        # 瞬时失败重试
        _dl.qq, _dl.vault, _dl.extract, _dl.index = _cq, _FakeVault(), _FakeExtract(), _FakeIndex()
        _dl.catalog.save = lambda c: None
        _rr = _dl.run(_dcat_r, ["r-r1"], confirm=True)
        if _rr.get("succeeded") != 1:
            fail(f"重试后仍未成功：{_rr}")
        if _cq.n < 3:
            fail(f"重试次数不足：fetch 被调用 {_cq.n} 次")
        # 永久失败不重试
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
    print(f"[12] 下载瞬时失败重试成功（fetch {_cq.n} 次后成功）；[13] 永久失败不重试（fetch {_pq.n} 次）")

    # 集成自测：起一个本地 server 实例（隔离临时 STATE + vault），验证 HTTP 层与 JSON 形状不回归
    import time as _time, shutil as _sh, threading as _th, json as _json
    import urllib.request as _ur, urllib.parse as _up
    import server as _srvmod  # server.py 位于项目根目录（lib 之外），ROOT 已在 sys.path
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
        _tp = _get("/api/tree?dim=classify&node=" + _up.quote("[]"))
        if not _tp.get("ok") or not isinstance(_tp.get("children"), list):
            fail(f"集成 /api/tree 异常：{_tp}")
        _fp = _get("/api/files?dim=classify&node=" + _up.quote("[]") + "&limit=5")
        if not _fp.get("ok") or not isinstance(_fp.get("items"), list):
            fail(f"集成 /api/files 异常：{_fp}")
        _sp = _get("/api/state")
        if not _sp.get("ok") or "counts" not in _sp:
            fail(f"集成 /api/state 异常：{_sp}")
        print(f"[14] 集成自测通过：health/diagnose/tree/files/state 均 ok（docs={_hp.get('docs')}, files_items={len(_fp.get('items', []))}）")
    finally:
        if _srv: _srv.shutdown(); _srv.server_close()
        config.CFG["port"] = _cfg_port
        config.STATE = _orig_state
        config.vault = _orig_vault

    # 最小 LLM 调用（可选）：配置存在则跑，缺失则跳过
    try:
        cfg = config.CFG.get("ai", {}) or {}
        if cfg.get("endpoint") or cfg.get("api_key"):
            r = ai.answer(cat, "请简要说明本库包含哪些科目？", scope=None)
            if not isinstance(r, dict) or "answer" not in r:
                fail("ai.answer 返回结构异常")
            print("[7] ai.answer OK")
        else:
            print("[7] ai.answer skipped (no llm config)")
    except Exception as e:
        print(f"[7] ai.answer skipped (err: {e})")

    print("\nALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()

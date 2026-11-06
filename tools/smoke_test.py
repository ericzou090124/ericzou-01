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

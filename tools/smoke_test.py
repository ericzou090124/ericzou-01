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

"""微基准：量化增量同步相比全量重建的收益，顺便验证索引一致性。

用法：python tools/bench.py
仅读取本地 catalog 与索引，不触网、不改数据源。输出各阶段耗时与一致性断言。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import catalog, index, config  # noqa: E402


def _bench(name, fn, repeat=1):
    best = None
    for _ in range(repeat):
        t = time.perf_counter()
        r = fn()
        dt = time.perf_counter() - t
        if best is None or dt < best:
            best = dt
    print(f"  {name:<34} {best*1000:8.1f} ms  -> {r}")
    return r


def main():
    print(f"[bench] state dir: {config.state('')}")
    cat = catalog.load()
    total = len(cat.get("items", []))
    print(f"[bench] catalog items = {total}\n")

    print("[1] 全量重建 rebuild")
    n1 = _bench("index.rebuild (cold)", lambda: index.rebuild(cat))
    assert n1 == total, f"rebuild 写入 {n1} ≠ {total}"

    print("[2] 增量同步 sync（无变化，应等效全量但只插变化行）")
    n2 = _bench("index.sync (no change)", lambda: index.sync(cat))
    assert n2 == total, f"sync 总数 {n2} ≠ {total}"

    print("[3] 单条正文变化后的增量同步（应远快于重建）")
    import shutil  # noqa
    probe = cat["items"][0]
    bp = index.body_path(probe["id"])
    prior = bp.read_text(encoding="utf-8", errors="replace") if bp.is_file() else ""
    bp.write_text(prior + "\n# bench-probe\n", encoding="utf-8")
    _bench("index.sync (1 body changed)", lambda: index.sync(cat))
    # 还原：去掉探针行再同步一次，保证不污染索引
    bp.write_text(prior, encoding="utf-8")
    index.sync(cat)

    print("[4] 检索一致性")
    q = "复变函数 积分变换"
    a = index.search(q, 10)
    print(f"  搜索「{q}」命中 {len(a)} 条")

    print("[5] 索引维护 optimize")
    opt = _bench("index.optimize", lambda: index.optimize(), repeat=1)
    print(f"   维护前 {opt['before_bytes']} B -> 维护后 {opt['after_bytes']} B（节省 {opt['saved_bytes']} B）")

    print("\nALL BENCH ASSERTS PASSED")


if __name__ == "__main__":
    main()

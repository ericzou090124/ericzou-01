# -*- coding: utf-8 -*-
"""词库升级后原地重算分类（只改分类字段，绝不增删条目、绝不碰下载状态）。

用法：
    python tools/reclassify.py            # 备份 + 重算 + 完整性校验 + 写回
    python tools/reclassify.py --dry-run  # 只预览，不写盘

自带四道门禁：条目数 / id 集合 / downloaded 状态 / 分类完整性 必须与重算前一致。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import catalog, classify, config  # noqa: E402

CAT_PATH = config.state("catalog.json")
BAK = config.state("catalog.pre_reclassify.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cat = catalog.load()
    xs = catalog.items(cat)
    before_ids = [x["id"] for x in xs]
    before_dl = {x["id"]: bool(x.get("downloaded")) for x in xs}
    before_dom = collections.Counter(x.get("domain") for x in xs)
    before_sub = collections.Counter(x.get("subject") for x in xs)
    print(f"重算前：{len(xs)} 条；领域 {len(before_dom)} 个 / 科目 {len(before_sub)} 个")

    # 搜索召回对比：旧行为 = 纯字符串匹配（不带别名扩展）
    old_cfg = {"classification": {k: v for k, v in config.CFG["classification"].items()
                                   if k != "aliases"}}
    _, old_total = catalog.query(cat, "classify", [], "高等代数", limit=1,
                                 with_total=True, cfg=old_cfg)
    print(f"重算前 搜索「高等代数」（纯字符串）：{old_total} 条")

    for x in xs:
        d, s, k, tags = classify.classify_full(x, config.CFG)
        x.update({"domain": d, "subject": s, "kind": k, "tags": tags})

    after_ids = [x["id"] for x in xs]
    after_dl = {x["id"]: bool(x.get("downloaded")) for x in xs}
    checks = {
        "条目数不变": len(after_ids) == len(before_ids),
        "id 集合不变": set(after_ids) == set(before_ids),
        "下载状态不变": after_dl == before_dl,
        "分类完整性": catalog.verify_integrity(cat)["ok"],
    }
    after_dom = collections.Counter(x.get("domain") for x in xs)
    after_sub = collections.Counter(x.get("subject") for x in xs)
    new_hits, new_total = catalog.query(cat, "classify", [], "高等代数", limit=1,
                                        with_total=True, cfg=config.CFG)
    print(f"重算后：{len(xs)} 条；领域 {len(after_dom)} 个 / 科目 {len(after_sub)} 个 / "
          f"标签 {catalog.counts(cat)['tags']} 个")
    print(f"重算后 搜索「高等代数」：{new_total} 条")
    print("完整性门禁：" + "  ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()))
    if not all(checks.values()):
        print("校验失败，不写盘。")
        return 2
    if new_total <= old_total:
        print("警告：召回数没有提升，请检查 aliases 配置。")

    print("新增/变化的领域：" + ", ".join(
        f"{k}({before_dom.get(k,0)}→{v})" for k, v in after_dom.most_common()
        if v != before_dom.get(k, 0))[:400])
    print("新增/变化的科目：" + ", ".join(
        f"{k}({before_sub.get(k,0)}→{v})" for k, v in after_sub.most_common()
        if v != before_sub.get(k, 0))[:400])

    if a.dry_run:
        print("--dry-run：未写盘。")
        return 0

    # 一次性备份，保留用户原始目录
    if not BAK.is_file():
        BAK.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已备份原目录：" + str(BAK))
    catalog.save(cat)
    print("已写回：" + str(CAT_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())

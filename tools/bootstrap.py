"""离线引导：把已有的 QQ 群文件清单快照导入本程序。

用途：NapCat 未启动 / 502 时，仍可用「已授权可见的元数据」跑通预览、大纲与 AI 元数据问答。
快照只有文件名、路径、体积、file_id 等元数据，**不包含任何文件内容**。
离线快照状态下禁止下载（server 会拒绝）。

用法：
  python tools/bootstrap.py                       # 自动找 ../qq2obsidian/state
  python tools/bootstrap.py --from <目录>         # 指定含 */qqfiles.json 的目录
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import config, vault  # noqa: E402
import server  # noqa: E402


def find_cache() -> Path:
    for c in (ROOT.parent / "qq2obsidian" / "state",
              Path.home() / "WorkBuddy" / "2026-11-06-15-42-58" / "qq2obsidian" / "state"):
        if c.is_dir() and list(c.glob("*/qqfiles.json")):
            return c
    return ROOT.parent / "qq2obsidian" / "state"


def build(src: Path) -> int:
    groups = (config.CFG["sources"]["qq"] or {}).get("groups", {})
    rows = []
    for f in sorted(src.glob("*/qqfiles.json")):
        key = f.parent.name
        g = groups.get(key)
        if not g:
            continue
        d = config.read_json(f, {}) or {}
        for r in d.get("files", []):
            rows.append(dict(source="QQ群", group=g["display"], group_id=int(g["qq_group"]), **r))
    if not rows:
        raise RuntimeError(f"在 {src} 没有找到可导入的群文件清单")
    config.write_json(config.state("qq_manifest.json"), {
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "items": rows,
    })
    print(f"快照已写入：{len(rows)} 条元数据（来自 {src}）")
    vault.init()
    r = server.refresh(force_snapshot=True)
    print("离线引导结果：", r.get("mode"), r.get("items"), "条 / 索引", r.get("indexed"), "篇 / 大纲",
          (r.get("outlines") or {}).get("pages"), "页")
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default="")
    a = ap.parse_args()
    build(Path(a.src) if a.src else find_cache())

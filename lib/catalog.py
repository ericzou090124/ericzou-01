"""统一资源目录 catalog.json：全系统唯一事实源。

条目无论是否下载都存在；downloaded 只表示「原文件已落地且正文已入库」。

v3.0.0 两个关键修复：
- 旧版 upsert_manifest 会用「本次 rows」反向裁剪整个目录，导致微信采集 / 本地目录
  并入时把 1625 条 QQ 群文件删光（真正的漏项）。现在默认只并入不裁剪，
  只有 refresh() 拿到 QQ 全量清单时才显式按同来源 prune。
- 新增多归属 tags 与「按主题标签」维度，同一份文件可出现在多个节点下，
  不再因为单选分类而被"藏"起来。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import classify, config, qq

DIMS = {
    "classify": ["domain", "subject", "kind"],
    "source": ["source", "group", "folder"],
    "tag": ["tags"],  # 维度名叫 tag，实际字段是复数 tags（多值）
}

# 参与搜索的字段；tags 为多值列表，_hay() 会自动展开
_SEARCH_FIELDS = ("name", "path", "folder", "group", "domain", "subject", "kind", "summary", "tags")

_CACHE: dict[str, tuple] = {}  # path -> (mtime_ns, size, data)


def make_id(source: str, group: str, path: str) -> str:
    return "r-" + hashlib.sha1(f"{source}|{group}|{path}".encode("utf-8")).hexdigest()[:16]


def load() -> dict:
    p = config.state("catalog.json")
    try:
        st = p.stat()
        key = (st.st_mtime_ns, st.st_size)
        cached = _CACHE.get(str(p))
        if cached and cached[0] == key:
            return cached[1]
    except OSError:
        pass
    data = config.read_json(p, {"version": 2, "updated_at": "", "items": []})
    try:
        st = p.stat()
        _CACHE[str(p)] = ((st.st_mtime_ns, st.st_size), data)
    except OSError:
        pass
    return data


def save(cat: dict) -> None:
    cat["version"] = 2
    cat["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config.write_json(config.state("catalog.json"), cat)
    _CACHE.pop(str(config.state("catalog.json")), None)


def items(cat: dict) -> list[dict]:
    return cat.setdefault("items", [])


def by_id(cat: dict, rid: str) -> dict | None:
    return next((x for x in items(cat) if x["id"] == rid), None)


def upsert_manifest(cat: dict, rows: list[dict], cfg: dict,
                     prune_source: str | None = None) -> int:
    """把来源元数据并入目录，保留已有的 downloaded / note / asset / summary。

    prune_source=None（默认）：纯增量并入，绝不删除任何既有条目 —— 微信采集、
    本地授权目录等「部分来源」必须用这个模式，否则会把 QQ 群文件删光。
    prune_source="QQ群"：只在拿到该来源的**全量**清单时，清理该来源已消失的条目。
    """
    index = {x["id"]: x for x in items(cat)}
    seen = set()
    for r in rows:
        source = r.get("source") or "QQ群"
        group = r.get("group") or "未知群"
        rid = r.get("id") or make_id(source, group, r["path"])
        seen.add(rid)
        dom, subj, kind, tags = classify.classify_full(r, cfg)
        old = index.get(rid) or {}
        rec = {
            "id": rid, "source": source, "group": group,
            "group_id": r.get("group_id", ""), "path": r["path"], "name": r["name"],
            "folder": r.get("folder", ""), "ext": r.get("ext", ""),
            "size_bytes": r.get("size_bytes", 0), "size": r.get("size") or qq.fmt_size(r.get("size_bytes", 0)),
            "uploader": r.get("uploader", ""), "uploaded_at": r.get("uploaded_at", ""),
            "file_id": r.get("file_id", ""), "busid": r.get("busid", 102),
            "domain": dom, "subject": subj, "kind": kind, "tags": tags,
            "downloaded": bool(old.get("downloaded")),
            "asset": old.get("asset", ""), "note": old.get("note", ""),
            "summary": old.get("summary", ""), "extract_status": old.get("extract_status", ""),
            "body_chars": old.get("body_chars", 0), "local_path": r.get("local_path", ""),
        }
        if old.get("asset") and not Path(config.vault() / old["asset"]).exists():
            rec.update({"downloaded": False, "asset": "", "note": "", "summary": "", "body_chars": 0})
        index[rid] = rec
    if prune_source:
        cat["items"] = [v for k, v in index.items()
                       if k in seen or str(v.get("source", "")) != prune_source]
    else:
        cat["items"] = list(index.values())
    return len(rows)


def reclassify(cat: dict, cfg: dict) -> int:
    """只重算分类字段，绝不动条目集合 / 下载状态。用于词库升级后的原地迁移。"""
    n = 0
    for x in items(cat):
        d, s, k, tags = classify.classify_full(x, cfg)
        x.update({"domain": d, "subject": s, "kind": k, "tags": tags})
        n += 1
    return n


def public(x: dict) -> dict:
    """前端可见字段：绝不下发 file_id / 令牌 / 本地缓存绝对路径。"""
    keys = ("id", "source", "group", "path", "name", "folder", "ext", "size", "size_bytes",
            "uploader", "uploaded_at", "domain", "subject", "kind", "tags", "downloaded",
            "asset", "note", "summary", "extract_status", "body_chars")
    out = {k: x.get(k, "") for k in keys}
    if not isinstance(out.get("tags"), list):
        out["tags"] = []
    return out


def _hay(x: dict) -> str:
    parts = []
    for k in _SEARCH_FIELDS:
        v = x.get(k, "")
        parts.append(" ".join(str(t) for t in v) if isinstance(v, (list, tuple)) else str(v or ""))
    return " ".join(parts).lower()


def _matches(x: dict, dim: str, node: list[str]) -> bool:
    levels = DIMS.get(dim, DIMS["classify"])
    for i in range(min(len(node), len(levels))):
        v = x.get(levels[i], "")
        if isinstance(v, (list, tuple)):
            if node[i] not in [str(t) for t in v]:
                return False
        elif str(v or "") != node[i]:
            return False
    return True


def _labels(x: dict, key: str) -> list[str]:
    v = x.get(key, "")
    if isinstance(v, (list, tuple)):
        return [str(t) for t in v if t] or ["未分类"]
    return [str(v or "") or "未分类"]


def tree(cat: dict, dim: str, node: list[str]) -> list[dict]:
    levels = DIMS.get(dim, DIMS["classify"])
    if len(node) >= len(levels):
        return []
    key = levels[len(node)]
    bucket: dict[str, dict] = {}
    for x in items(cat):
        if not _matches(x, dim, node):
            continue
        # 多值字段（tags）会让同一条目落进多个桶，这正是「不漏项」的关键
        for label in _labels(x, key):
            b = bucket.setdefault(label, {"name": label, "count": 0, "downloaded": 0, "size_bytes": 0})
            b["count"] += 1
            b["downloaded"] += int(bool(x.get("downloaded")))
            b["size_bytes"] += int(x.get("size_bytes") or 0)
    out = list(bucket.values())
    for b in out:
        b["size"] = qq.fmt_size(b["size_bytes"])
    return sorted(out, key=lambda b: (-b["count"], b["name"]))


def query(cat: dict, dim: str, node: list[str], q: str = "", limit: int = 200,
          with_total: bool = False, kind: str = "", cfg: dict | None = None):
    """按节点 + 查询词过滤。查询词会做同义/相关主题扩展，避免「搜高等代数只有 1 条」。"""
    q = (q or "").strip().lower()
    kind = (kind or "").strip()
    terms = classify.expand_query(q, cfg or config.CFG) if q else []
    out = []
    for x in items(cat):
        if not _matches(x, dim, node):
            continue
        if kind and str(x.get("kind", "")) != kind:
            continue
        if terms and not any(t in _hay(x) for t in terms):
            continue
        out.append(public(x))
    out.sort(key=lambda x: (not x["downloaded"], x["domain"], x["subject"], x["name"]))
    total = len(out)
    page = out[:limit]
    # total 必须是该节点匹配到的全部条数，而不是 limit 截断后的长度
    return (page, total) if with_total else page


def counts(cat: dict) -> dict:
    xs = items(cat)
    tagset = {t for x in xs for t in (x.get("tags") or []) if t}
    return {
        "total": len(xs),
        "downloaded": sum(1 for x in xs if x.get("downloaded")),
        "metadata_only": sum(1 for x in xs if not x.get("downloaded")),
        "size_bytes": sum(int(x.get("size_bytes") or 0) for x in xs),
        "domains": len({x.get("domain") for x in xs}),
        "subjects": len({x.get("subject") for x in xs}),
        "tags": len(tagset),
        "tagged": sum(1 for x in xs if x.get("tags")),
    }


def verify_integrity(cat: dict) -> dict:
    """完整性门禁：条目数、id 唯一、每条都有主分类与标签。用于自测与刷新后校验。"""
    xs = items(cat)
    ids = [x.get("id") for x in xs]
    missing_class = [x["id"] for x in xs
                     if not all(str(x.get(k, "") or "") for k in ("domain", "subject", "kind"))]
    missing_tags = [x["id"] for x in xs if not x.get("tags")]
    return {
        "ok": len(ids) == len(set(ids)) and not missing_class and not missing_tags,
        "total": len(xs), "unique_ids": len(ids) == len(set(ids)),
        "missing_class": len(missing_class), "missing_tags": len(missing_tags),
        "tagged": sum(1 for x in xs if x.get("tags")),
    }

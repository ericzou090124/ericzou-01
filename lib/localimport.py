"""离线导入通道：把本机已另存的 QQ 群文件真实导入独立 Obsidian 库。

用途：QQNT / NapCat 群文件内核异常（get_group_file_url 拿不到直链）时，
「分类整理 → 批量导入 → 自动分类入库 → 库内 AI 检索」这条链路仍然能跑通。
只处理文件名能与目录元数据精确对上的真实文件，绝不扫描或复制任意路径。

安全闸门（与 download.precheck 同等级）：
- confirm 必须显式为 true；
- 每个来源文件必须位于 config.local_import_dirs 展开后的白名单目录内（含子目录）；
- 文件名必须与目录条目的 name 完全一致，扩展名必须在 allowed_ext 白名单；
- 单批上限同样取 max_download_per_batch；
- 只复制、不移动、不删除用户原文件。

导入后的处理与网络下载完全一致：抽取正文 → 写 body → 更新元数据 → 生成预览笔记
→ catalog.save → index.sync → 重建多级大纲。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import catalog, config, extract, index, qq, vault

# 占位符：让 config.json 里可以写可移植路径，而不是写死某台机器的绝对路径
_PLACEHOLDERS = {
    "{home}": lambda: Path.home(),
    "{root}": lambda: config.ROOT,
    "{workspace}": lambda: config.ROOT.parent,
    "{desktop}": lambda: Path.home() / "Desktop",
}


def _expand(raw: str) -> Path:
    s = str(raw or "").strip()
    for key, fn in _PLACEHOLDERS.items():
        if s.startswith(key):
            s = str(fn()) + s[len(key):]
            break
    return Path(s).expanduser()


def dirs() -> list[Path]:
    """可用的本地另存目录（只返回真实存在的目录）。"""
    raw = list(config.CFG.get("local_import_dirs") or [])
    # 默认候选：项目 inbox、桌面「QQ资料自动入库」、工作区 qq2obsidian/inbox
    raw += ["{root}/inbox", "{desktop}/QQ资料自动入库", "{workspace}/qq2obsidian/inbox"]
    out: list[Path] = []
    for r in raw:
        try:
            p = _expand(r).resolve()
            if p.is_dir() and p not in out:
                out.append(p)
        except (OSError, ValueError):
            continue
    return out


def _allowed(p: Path, roots: list[Path]) -> bool:
    try:
        rp = p.resolve()
        return any(rp == root or root in rp.parents for root in roots)
    except (OSError, ValueError):
        return False


def _allowed_ext(p: Path) -> bool:
    return p.suffix.lower() in {str(e).lower() for e in config.CFG.get("allowed_ext", [])}


def scan(cat: dict | None = None) -> dict:
    """扫描白名单目录，返回能与目录元数据精确对上的真实文件清单（只读，不复制任何东西）。"""
    cat = cat or catalog.load()
    roots = dirs()
    by_name: dict[str, list[dict]] = {}
    for x in catalog.items(cat):
        by_name.setdefault(x["name"], []).append(x)

    found, unmatched, seen_ids = [], 0, set()
    for root in roots:
        try:
            candidates = sorted(p for p in root.rglob("*") if p.is_file())
        except OSError:
            continue
        for p in candidates:
            if p.name.startswith("_") or p.name.startswith("."):
                continue
            if not _allowed_ext(p):
                continue
            items = by_name.get(p.name)
            if not items:
                unmatched += 1
                continue
            # 同名条目优先选「群内路径能对上」的，其次选未下载的
            parent = str(p.parent).replace("\\", "/").lower()
            items = sorted(items, key=lambda x: (
                0 if x.get("folder") and str(x["folder"]).lower() in parent else 1,
                bool(x.get("downloaded")), x["id"]))
            x = items[0]
            # 同一份文件可能在两个另存目录里各存一份：目录条目只认一次，避免重复导入
            if x["id"] in seen_ids:
                continue
            seen_ids.add(x["id"])
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            found.append({
                "id": x["id"], "name": x["name"], "path": str(p),
                "dir": str(root), "size_bytes": size, "size": qq.fmt_size(size),
                "ext": p.suffix.lower(), "downloaded": bool(x.get("downloaded")),
                "group": x.get("group", ""), "domain": x.get("domain", ""),
                "subject": x.get("subject", ""), "kind": x.get("kind", ""),
                "chain": " › ".join(vault._chain(x)),
            })
    by_kind: dict[str, int] = {}
    for f in found:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    return {"ok": True, "dirs": [str(d) for d in roots], "files": found,
            "matched": len(found), "unmatched": unmatched,
            "pending": sum(1 for f in found if not f["downloaded"]),
            "by_kind": by_kind, "vault": str(vault.v())}


def _one(x: dict, src: Path) -> tuple[dict, bool]:
    """复制单个真实文件并走完与网络下载相同的入库动作。"""
    try:
        dest_rel = vault.asset_rel(x)
        dest = config.vault() / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
            tmp = dest.with_name(dest.name + ".part")
            shutil.copy2(src, tmp)
            tmp.replace(dest)
        body, status = extract.extract(dest, int(config.CFG.get("max_chars_per_file", 60000)))
        index.body_path(x["id"]).write_text(body, encoding="utf-8")
        x.update({
            "downloaded": True, "asset": dest_rel,
            "summary": extract.summarize(body), "extract_status": status,
            "body_chars": len(body), "size_bytes": dest.stat().st_size,
            "size": qq.fmt_size(dest.stat().st_size),
            "import_mode": "local_saved_file",
        })
        x["note"] = vault.write_note(x, body)
        return ({"id": x["id"], "name": x["name"], "ok": True, "asset": dest_rel,
                 "note": x["note"], "status": status, "mode": "local"}, True)
    except Exception as e:
        return ({"id": x.get("id"), "name": x.get("name"), "ok": False,
                 "error": f"{type(e).__name__}: {str(e)[:160]}"}, False)


def run(cat: dict, pairs: list[dict], confirm: bool = False) -> dict:
    """按 (id, path) 显式清单导入。pairs 为空时拒绝执行，绝不隐式全量导入。"""
    if not confirm:
        return {"ok": False, "error": "导入必须经过显式确认（confirm=true）", "results": []}
    if not pairs:
        return {"ok": False, "error": "未指定任何文件（pairs 为空）", "results": []}
    roots = dirs()
    idx = {x["id"]: x for x in catalog.items(cat)}
    cap = int(config.CFG.get("max_download_per_batch", 30))
    todo, rejected = [], []
    for pair in pairs[:cap]:
        iid, raw = str(pair.get("id") or ""), str(pair.get("path") or "")
        x, src = idx.get(iid), Path(raw)
        if not x:
            rejected.append({"id": iid, "error": "目录中没有该文件 id"})
            continue
        if not raw or not src.is_file():
            rejected.append({"id": iid, "error": "本地文件不存在"})
            continue
        if not _allowed(src, roots):
            rejected.append({"id": iid, "error": "文件不在允许的本地另存目录内"})
            continue
        if src.name != x["name"]:
            rejected.append({"id": iid, "error": "文件名与目录元数据不一致"})
            continue
        if not _allowed_ext(src):
            rejected.append({"id": iid, "error": "扩展名不在下载白名单内"})
            continue
        if x.get("downloaded"):
            rejected.append({"id": iid, "error": "已入库，无需重复导入"})
            continue
        todo.append((x, src))
    if not todo:
        return {"ok": False, "error": "没有可导入的文件（所选文件均已入库或未通过校验）",
                "results": rejected}

    results, changed = list(rejected), []
    for x, src in todo:
        r, ok = _one(x, src)
        results.append(r)
        if ok:
            changed.append(x)
    if changed:
        catalog.save(cat)
        index.sync(cat)
        outlines = vault.build_outlines(cat)
    else:
        outlines = {}
    return {
        "ok": bool(changed), "mode": "local", "requested": len(pairs),
        "attempted": len(todo), "succeeded": len(changed),
        "skipped_over_cap": max(0, len(pairs) - cap), "results": results,
        "outlines": outlines, "vault": vault.status(cat),
        "note": "只处理了本批上限内的文件；如需继续请再次确认剩余条目。" if len(pairs) > cap else "",
    }


def pick(cat: dict, ids: list[str], limit: int = 0) -> list[dict]:
    """把「当前筛选范围」的 id 列表与本地可导入文件求交集，返回 (id, path) 清单。"""
    cap = limit or int(config.CFG.get("max_download_per_batch", 30))
    want = set(str(i) for i in ids)
    out = []
    for f in scan(cat)["files"]:
        if f["downloaded"] or f["id"] not in want:
            continue
        out.append({"id": f["id"], "path": f["path"]})
        if len(out) >= cap:
            break
    return out

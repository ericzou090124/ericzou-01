"""下载确认闸门 + 入库流水线。

所有下载（单个 / 多选 / 整类）都走这里，服务端重复校验：
- confirm 必须为 true，且 ids 必须显式给出；
- 整类下载额外要求 confirmText 等于节点名；
- 离线快照状态拒绝下载；
- 单批上限由 config.max_download_per_batch 控制，绝不隐式扩到全量。

入库后只做「增量同步」`index.sync()`，不再每次全量重建 FTS（rebuild 是 O(n)，
仅刷新等需要整体重算的场景才用；下载每批只动少数文件，sync 只重算变化的条目）。
下载与抽取是 I/O 密集型，单批内用有界线程池并发拉取（失败自动降级为串行），
不改动「下载前必须经确认」的任何闸门。
"""
from __future__ import annotations

import concurrent.futures as _cf
import os
from pathlib import Path

from . import catalog, config, download as _self, extract, index, qq, vault


def precheck(cat: dict, ids: list[str], scope: str, confirm: bool,
             confirm_text: str, node_name: str) -> dict:
    if not confirm:
        return {"ok": False, "error": "下载必须经过显式确认（confirm=true）"}
    if not ids:
        return {"ok": False, "error": "未指定任何文件（ids 为空）"}
    if scope == "category" and (confirm_text or "").strip() != (node_name or "").strip():
        return {"ok": False, "error": "整类下载需要二次确认：请原样输入节点名称"}
    # 一次构建 id->item 映射，避免逐个 by_id 的 O(n) 线性扫描（批越大收益越明显）
    idx = {x["id"]: x for x in catalog.items(cat)}
    found = [idx.get(i) for i in ids]
    found = [x for x in found if x]
    if not found:
        return {"ok": False, "error": "没有找到任何有效的文件 id"}
    todo = [x for x in found if not x.get("downloaded")]
    if not todo:
        return {"ok": False, "error": "所选文件均已下载，无需重复下载"}
    cap = int(config.CFG.get("max_download_per_batch", 30))
    skipped = len(todo) - cap if len(todo) > cap else 0
    return {"ok": True, "items": todo[:cap], "skipped": skipped,
            "total_bytes": sum(int(x.get("size_bytes") or 0) for x in todo[:cap])}


def _process_one(x: dict) -> tuple:
    """处理单条下载入库；原地修改 x（仅本条目，不影响其它线程），返回 (result, changed, x)。

    仅在这里做实际的网络拉取 / 抽取 / 写盘；线程安全由「每条只改自己的 x 且写独立文件」保证。
    """
    try:
        if not x.get("file_id"):
            raise RuntimeError("缺少 file_id，请重新刷新来源")
        if x.get("ext") and x["ext"] not in config.CFG.get("allowed_ext", []):
            raise RuntimeError("扩展名不在下载白名单内")
        asset_rel = vault.asset_rel(x)
        dest = config.vault() / asset_rel
        if not dest.is_file():
            url = qq.fetch_url(int(x.get("group_id") or 0), x["file_id"], int(x.get("busid") or 102))
            if not url:
                raise RuntimeError("获取直链失败（file_id 可能已失效，请重新刷新来源）")
            qq.download_to(url, dest)
            if not dest.is_file() or dest.stat().st_size == 0:
                raise RuntimeError("下载结果为空")
        body, status = extract.extract(dest, int(config.CFG.get("max_chars_per_file", 60000)))
        index.body_path(x["id"]).write_text(body, encoding="utf-8")
        x.update({
            "downloaded": True, "asset": asset_rel,
            "summary": extract.summarize(body), "extract_status": status,
            "body_chars": len(body),
            "size_bytes": dest.stat().st_size,
            "size": qq.fmt_size(dest.stat().st_size),
        })
        x["note"] = vault.write_note(x, body)
        return ({"id": x["id"], "name": x["name"], "ok": True,
                 "asset": asset_rel, "note": x["note"], "status": status}, True, x)
    except Exception as e:
        return ({"id": x.get("id"), "name": x.get("name"), "ok": False,
                 "error": f"{type(e).__name__}: {str(e)[:160]}"}, False, x)


def run(cat: dict, ids: list[str], scope: str = "selection", confirm: bool = False,
        confirm_text: str = "", node_name: str = "") -> dict:
    chk = precheck(cat, ids, scope, confirm, confirm_text, node_name)
    if not chk["ok"]:
        return {"ok": False, "error": chk["error"], "results": []}
    todo = chk["items"]
    if not qq.online():
        return {"ok": False,
                "error": "QQ 接口当前离线（离线快照只能预览元数据，不能下载）。请先刷新来源或启动 NapCat。",
                "results": []}

    results, changed = [], []
    workers = int(os.environ.get("RM_DOWNLOAD_WORKERS", "4"))
    use_parallel = len(todo) > 1 and workers > 1
    try:
        if use_parallel:
            with _cf.ThreadPoolExecutor(max_workers=min(workers, len(todo))) as ex:
                futs = {ex.submit(_process_one, x): x for x in todo}
                for fut in _cf.as_completed(futs):
                    res, ok, x = fut.result()
                    results.append(res)
                    if ok:
                        changed.append(x)
        else:
            for x in todo:
                res, ok, _ = _process_one(x)
                results.append(res)
                if ok:
                    changed.append(x)
    except Exception:
        # 并行路径异常（如线程池调度失败）整体降级为串行，保证不丢数据、不半途而废
        results, changed = [], []
        for x in todo:
            res, ok, _ = _process_one(x)
            results.append(res)
            if ok:
                changed.append(x)

    if changed:
        catalog.save(cat)
        # 仅增量同步：只重算本批变化的条目，避免每次下载都全量重建索引
        index.sync(cat)
        outlines = vault.build_outlines(cat)
    else:
        outlines = {}
    return {
        "ok": any(r["ok"] for r in results),
        "requested": len(ids), "attempted": len(todo), "succeeded": len(changed),
        "skipped_over_cap": chk["skipped"], "results": results, "outlines": outlines,
        "note": "只处理了本批上限内的文件；如需继续请再次确认剩余条目。" if chk["skipped"] else "",
    }

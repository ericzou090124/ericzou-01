"""grounded 问答：命中判定与源文件索引一律由本地检索给出，模型只负责中文概括。

- 未命中 → 直接如实回答，不调用模型；
- 「有哪些 / 多少 / 未下载」类问题走目录确定性统计，绝不臆造正文；
- 未下载条目在上下文和回答里必须标注「仅元数据、无正文摘要」；
- 所有问题都先做 科目 / 领域 / 类型 识别（含前端传入的当前浏览范围），把检索严格限定在范围内，
  避免跨科目串味（例如问「高等代数」却答「复变函数」）。
"""
from __future__ import annotations

import re
import time

from . import catalog, config, index, llm

NOT_FOUND = "授权可见的资料中没有检索到相关信息"
LIST_INTENT = re.compile(r"有哪些|哪几|多少|清单|列一下|都有什么|没下载|未下载|还没下载|存在哪些|包含哪些")
SYSTEM = (
    "你是本地知识库助手。只能依据下面给出的【资料片段】回答，不能补充外部知识、不能推测、不能编造。\n"
    "片段分两类：【已下载·含正文】可以概括正文；【仅元数据·未下载·无正文】只有文件名和路径，"
    "回答这类条目时必须明确写「仅元数据，未下载，无正文摘要」，不得描述文件内容。\n"
    "回答控制在 2-4 句、简短直接。不要判断资料「有没有」——命中判定已由检索系统完成。\n"
    "若片段只是题目、选项、目录或清单，没有明确的答案/结论，必须明确回答「资料只给出题目与选项，未给答案」，"
    "严禁用常识或从选项里推断答案，也不要把选项罗列成结论。\n"
    "如果片段不足，就只复述片段里确实存在的信息并说明依据不足。\n"
    "严格只依据给定范围内的资料；若范围内没有相关资料，就如实说明，不要借用范围外的知识作答。"
)


def _hay(x: dict, body: str = "") -> str:
    return " ".join(str(x.get(k, "") or "") for k in
                    ("name", "path", "folder", "group", "source", "domain", "subject", "kind", "summary")) + " " + body


def _source(x: dict, n: int, score: float = 0.0) -> dict:
    return {
        "n": n, "id": x["id"], "name": x.get("name", ""), "path": x.get("path", ""),
        "group": x.get("group", ""), "source": x.get("source", ""),
        "domain": x.get("domain", ""), "subject": x.get("subject", ""), "kind": x.get("kind", ""),
        "size": x.get("size", ""), "downloaded": bool(x.get("downloaded")),
        "note": x.get("note", ""), "asset": x.get("asset", ""),
        "summary": x.get("summary", ""), "score": round(score, 3),
    }


def _filters(q: str, cfg: dict) -> dict:
    """从问题文本识别 科目 / 领域 / 类型 范围。"""
    c = cfg.get("classification") or {}
    f = {}
    subs = c.get("subjects") or {}
    for label in subs:
        if label == "综合":
            continue
        kws = subs[label] or []
        if label in q or any(k and k in q for k in kws):
            f["subject"] = label
            break
    for d in (c.get("domains") or []):
        if d["name"] in q:
            f["domain"] = d["name"]
            break
    generic = {"资料", "其他", "文件", "内容"}
    for rule in c.get("kinds") or []:
        label = rule["name"]
        if label == "其他资料":
            continue
        if label in q or any(k and k not in generic and k in q for k in rule.get("keywords", [])):
            f["kind"] = label
            break
    return f


_LABELS = {"domain": "领域", "subject": "科目", "kind": "类型"}


def _scope_from_path(path) -> dict:
    """把前端浏览路径 [领域] / [领域,科目] / [领域,科目,类型] 转成检索过滤器。"""
    f = {}
    for i, val in enumerate((path or [])[:3]):
        if val and str(val) not in ("全部", ""):
            f[("domain", "subject", "kind")[i]] = str(val)
    return f


def _merge_filter(scope: dict, qfilter: dict) -> dict:
    """范围（浏览路径）打底，问题识别出的范围覆盖之；二者取并集。"""
    f = dict(scope or {})
    f.update(qfilter or {})
    return f


def _where(f: dict) -> str:
    return "、".join(f"{_LABELS[k]}「{v}」" for k, v in f.items()) or "全部可见资料"


def _pool(cat: dict, f: dict) -> list[dict]:
    xs = catalog.items(cat)
    if not f:
        return xs
    return [x for x in xs if all(str(x.get(k, "")) == v for k, v in f.items())]


def _list_answer(q: str, cat: dict, cfg: dict, t0: float, pool: list[dict], f: dict) -> dict:
    if not f and not index.query_terms(q):
        return {"answer": NOT_FOUND + "。已检索授权可见目录，未找到可回答该问题的条目。",
                "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": int((time.time() - t0) * 1000)}
    sel = pool
    if not f:
        # 无范围时退回检索词命中过滤
        terms = index.query_terms(q)
        sel = [x for x in pool if any(t in _hay(x).lower() for t in terms if len(t) >= 2)]
    if not sel:
        return {"answer": NOT_FOUND + f"。已检索授权可见目录，未找到「{_where(f)}」范围内可回答该问题的条目。",
                "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": int((time.time() - t0) * 1000)}
    only_meta = "未下载" in q or "没下载" in q or "还没下载" in q
    pl = [x for x in sel if not x.get("downloaded")] if only_meta else sel
    if not pl:
        pl = sel
    pl.sort(key=lambda x: (-int(bool(x.get("downloaded"))), x.get("name", "")))
    dl = sum(1 for x in sel if x.get("downloaded"))
    where = _where(f)
    size = sum(int(x.get("size_bytes") or 0) for x in sel)
    label = "未下载（仅元数据）" if only_meta else "授权可见"
    answer = (f"{where}共 {len(sel)} 份{label}资料，其中已下载 {dl} 份、仅元数据 {len(sel)-dl} 份，"
              f"合计约 {size/1024/1024:.1f} MB。代表文件：" +
              "、".join(x["name"] for x in pl[:4]) + "。")
    if only_meta:
        answer += "这些条目仅元数据，未下载，无正文摘要；需要内容请先下载。"
    elif dl < len(sel):
        answer += "其中未下载条目仅元数据，无正文摘要。"
    return {"answer": answer, "found": True, "sources": [_source(x, i + 1) for i, x in enumerate(pl[:5])],
            "mode": "catalog", "scanned": len(catalog.items(cat)), "took_ms": int((time.time() - t0) * 1000)}


def _snippet(body: str, terms: list[str], width: int) -> str:
    """按命中词定位正文窗口，避免答案落在被截断的前几百字之外。"""
    clean = re.sub(r"\s+", " ", body or "").strip()
    if not clean:
        return "（正文为空或不可抽取）"
    low = clean.lower()
    positions = [low.find(t.lower()) for t in terms if len(t) >= 2 and t.lower() in low]
    pos = min(positions) if positions else -1
    start = 0 if pos < 0 else max(0, pos - width // 4)
    return clean[start:start + width]


def _local_answer(q: str, hits: list[tuple[float, dict, str]]) -> str:
    parts = []
    for _, x, body in hits[:3]:
        if x.get("downloaded") and body.strip():
            clean = re.sub(r"\s+", " ", body).strip()
            segs = [s for s in re.split(r"(?<=[。！？；])", clean[:900]) if len(s.strip()) >= 10]
            if segs:
                parts.append("".join(segs[:2])[:220])
        else:
            parts.append(f"{x['name']}（仅元数据，未下载，无正文摘要）")
    return ("根据已入库资料：" + " ".join(parts)) if parts else "已检索到相关资料，请点开下方源文件索引查看。"


def answer(q: str, cat: dict | None = None, fast: bool = False, scope: list | None = None) -> dict:
    t0 = time.time()
    q = (q or "").strip()
    if not q:
        return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
    cfg = config.CFG
    cat = cat or catalog.load()
    f = _merge_filter(_scope_from_path(scope), _filters(q, cfg))
    where = _where(f)

    if LIST_INTENT.search(q):
        return _list_answer(q, cat, cfg, t0, _pool(cat, f), f)

    terms = index.query_terms(q)
    valid = [t for t in terms if len(t) >= 2]
    if not valid:
        return {"answer": NOT_FOUND + f"（问题过短或无有效检索词；范围：{where}）。",
                "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": int((time.time() - t0) * 1000)}

    pool = _pool(cat, f)
    haymap = {x["id"]: _hay(x).lower() for x in pool}  # 预计算一次，避免对每个候选重复拼接 9 字段
    if not pool:
        return {"answer": NOT_FOUND + f"。「{where}」范围内暂无授权可见资料，无法作答。",
                "found": False, "sources": [], "mode": "none", "scope": f, "scanned": index.count(),
                "took_ms": int((time.time() - t0) * 1000)}

    # 在 pool 内检索：先走 FTS，再退回词命中打分，确保不跨范围串味
    raw = index.search(q, 24)
    pool_ids = {x["id"]: x for x in pool}
    hits_pool = [h for h in raw if h["item_id"] in pool_ids]
    if not hits_pool:
        scored = []
        for x in pool:
            hay = haymap.get(x["id"], _hay(x).lower())
            sc = sum(1 for t in valid if t.lower() in hay) / max(1, len(valid))
            if sc > 0:
                scored.append((sc, x, ""))
        scored.sort(key=lambda t: -t[0])
        hits_pool = [{"item_id": x["id"], "body": ""} for _, x, _ in scored[:24]]

    by_id = {h["item_id"]: h for h in hits_pool}
    corpus = " ".join((h.get("title", "") + " " + h.get("meta", "") + " " + h.get("body", ""))
                      for h in hits_pool).lower()
    valid2 = [t for t in valid if t.lower() in corpus]
    if not valid2:
        return {"answer": NOT_FOUND + f"。已在「{where}」范围内检索授权可见目录与已入库正文，未找到能回答这个问题的内容。",
                "found": False, "sources": [], "mode": "none", "scope": f, "scanned": index.count(),
                "took_ms": int((time.time() - t0) * 1000)}

    s = config.settings()
    top_k = int(s.get("top_k", 5))
    threshold = float(s.get("min_relevance", 0.22))
    scored = []
    for h in hits_pool:
        x = pool_ids.get(h["item_id"])
        if not x:
            continue
        body = h.get("body", "") or ""
        hay = (haymap.get(x["id"], "") + " " + body).lower()
        sc = sum(1 for t in valid2 if t.lower() in hay) / max(1, len(valid2))
        scored.append((sc, x, body))
    scored.sort(key=lambda t: -t[0])
    kept = [t for t in scored[:top_k * 2] if t[0] >= max(0.15, threshold * 0.6)][:top_k]
    best = scored[0][0] if scored else 0
    if best < threshold or not kept:
        return {"answer": NOT_FOUND + f"。已在「{where}」范围内检索授权可见目录与已入库正文，未找到能回答这个问题的内容。",
                "found": False, "sources": [], "mode": "none", "scope": f, "best_score": round(best, 3),
                "scanned": index.count(), "took_ms": int((time.time() - t0) * 1000)}

    per = max(600, int(int(s.get("max_context_chars", 4200)) / max(1, len(kept))))
    ctx = []
    for i, (_, x, body) in enumerate(kept, 1):
        tag = "【已下载·含正文】" if x.get("downloaded") else "【仅元数据·未下载·无正文】"
        if x.get("downloaded"):
            detail = ("摘要：" + (x.get("summary") or "无") + "\n正文命中片段：" + _snippet(body, valid2, per))[:per]
        else:
            detail = "（无正文，只有文件名与路径；不要据此推测文件内容）"
        ctx.append(f"{i}. {tag} {x['name']}｜来源：{x['source']}/{x['group']}｜"
                   f"分类：{x['domain']}/{x['subject']}/{x['kind']}｜路径：{x['path']}\n{detail}")
    scope_head = f"【检索范围：{where}】只依据该范围内的资料片段回答，不得借用范围外知识。\n"
    context = scope_head + "\n".join(ctx)[:int(s.get("max_context_chars", 4200))]
    result = {"found": True, "scope": f, "sources": [_source(x, i + 1, sc) for i, (sc, x, _) in enumerate(kept)],
              "scanned": index.count(), "best_score": round(best, 3)}

    if fast:
        result.update({"answer": _local_answer(q, kept), "mode": "fast"})
    else:
        text, err = llm.chat(SYSTEM, f"资料片段：\n{context}\n\n问题：{q}", s)
        if text and NOT_FOUND in text:
            result.update({"answer": _local_answer(q, kept), "mode": "local", "note": "模型误判未命中，已改用原文摘录"})
        elif text:
            result.update({"answer": text, "mode": "llm"})
        else:
            result.update({"answer": _local_answer(q, kept), "mode": "local", "note": f"{err}，已本地降级"})
    result["took_ms"] = int((time.time() - t0) * 1000)
    return result

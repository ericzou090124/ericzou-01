"""grounded 问答：命中判定与源文件索引一律由本地检索给出，模型只负责中文概括。

- 未命中 → 直接如实回答，不调用模型；
- 「有哪些 / 多少 / 未下载」类问题走目录确定性统计，绝不臆造正文；
- 未下载条目在上下文和回答里必须标注「仅元数据、无正文摘要」。
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
    "如果片段不足，就只复述片段里确实存在的信息并说明依据不足。"
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
    c = cfg.get("classification") or {}
    f = {}
    for label in (c.get("subjects") or {}):
        if label != "综合" and (label in q or any(k in q for k in (c["subjects"][label] or [])[:2])):
            f["subject"] = label
            break
    for label in [d["name"] for d in (c.get("domains") or [])]:
        if label in q:
            f["domain"] = label
            break
    generic = {"资料", "其他", "文件", "内容"}
    for rule in c.get("kinds") or []:
        label = rule["name"]
        if label == "其他资料":
            continue
        aliases = [label, label[:2], label[2:]] + [x for x in rule.get("keywords", []) if x not in generic]
        if any(a and a not in generic and a in q for a in aliases):
            f["kind"] = label
            break
    return f


_LABELS = {"subject": "科目", "domain": "领域", "kind": "类型"}


def _where(f: dict) -> str:
    return "、".join(f"{_LABELS[k]}「{v}」" for k, v in f.items()) or "当前范围"


def _list_answer(q: str, cat: dict, cfg: dict, t0: float) -> dict:
    xs = catalog.items(cat)
    f = _filters(q, cfg)
    sel = [x for x in xs if all(str(x.get(k, "")) == v for k, v in f.items())]
    if not sel:
        # 退回按检索词命中过滤，避免「有哪些」无筛选项时把全库都列出来
        terms = index.query_terms(q)
        sel = [x for x in xs if any(t in _hay(x).lower() for t in terms if len(t) >= 2)]
    if not sel:
        return {"answer": NOT_FOUND + "。已检索授权可见目录，未找到可回答该问题的条目。",
                "found": False, "sources": [], "mode": "none", "took_ms": int((time.time()-t0)*1000)}
    only_meta = "未下载" in q or "没下载" in q or "还没下载" in q
    pool = [x for x in sel if not x.get("downloaded")] if only_meta else sel
    if not pool:
        pool = sel
    pool.sort(key=lambda x: (-int(bool(x.get("downloaded"))), x.get("name", "")))
    dl = sum(1 for x in sel if x.get("downloaded"))
    where = _where(f)
    size = sum(int(x.get("size_bytes") or 0) for x in sel)
    label = "未下载（仅元数据）" if only_meta else "授权可见"
    answer = (f"{where}共 {len(sel)} 份{label}资料，其中已下载 {dl} 份、仅元数据 {len(sel)-dl} 份，"
             f"合计约 {size/1024/1024:.1f} MB。代表文件：" +
             "、".join(x["name"] for x in pool[:4]) + "。")
    if only_meta:
        answer += "这些条目仅元数据，未下载，无正文摘要；需要内容请先下载。"
    elif dl < len(sel):
        answer += "其中未下载条目仅元数据，无正文摘要。"
    return {"answer": answer, "found": True, "sources": [_source(x, i+1) for i, x in enumerate(pool[:5])],
            "mode": "catalog", "scanned": len(xs), "took_ms": int((time.time()-t0)*1000)}


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


def answer(q: str, cat: dict | None = None, fast: bool = False) -> dict:
    t0 = time.time()
    q = (q or "").strip()
    if not q:
        return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "took_ms": 0}
    cfg = config.CFG
    cat = cat or catalog.load()
    s = config.settings()
    if LIST_INTENT.search(q):
        return _list_answer(q, cat, cfg, t0)

    raw = index.search(q, 24)
    by_id = {x["id"]: x for x in catalog.items(cat)}
    terms = index.query_terms(q)
    corpus = " ".join((h.get("title", "") + " " + h.get("meta", "") + " " + h.get("body", "")) for h in raw).lower()
    valid = [t for t in terms if len(t) >= 2 and t.lower() in corpus]
    top_k = int(s.get("top_k", 5))
    threshold = float(s.get("min_relevance", 0.22))
    short_and_full = len(terms) <= 3 and len(valid) == len(terms) >= 2
    if len(valid) < 2 and not short_and_full:
        return {"answer": NOT_FOUND + "。已检索授权可见目录与已入库正文，未找到能回答这个问题的内容。",
                "found": False, "sources": [], "mode": "none", "scanned": index.count(),
                "took_ms": int((time.time()-t0)*1000)}

    scored = []
    for h in raw:
        x = by_id.get(h["item_id"])
        if not x:
            continue
        body = h.get("body", "") or ""
        hay = _hay(x, body).lower()
        sc = sum(1 for t in valid if t.lower() in hay) / max(1, len(valid))
        scored.append((sc, x, body))
    scored.sort(key=lambda t: -t[0])
    kept = [t for t in scored[:top_k * 2] if t[0] >= max(0.15, threshold * 0.6)][:top_k]
    best = scored[0][0] if scored else 0
    if best < threshold or not kept:
        return {"answer": NOT_FOUND + "。已检索授权可见目录与已入库正文，未找到能回答这个问题的内容。",
                "found": False, "sources": [], "mode": "none", "best_score": round(best, 3),
                "scanned": index.count(), "took_ms": int((time.time()-t0)*1000)}

    per = max(600, int(int(s.get("max_context_chars", 4200)) / max(1, len(kept))))
    ctx = []
    for i, (_, x, body) in enumerate(kept, 1):
        tag = "【已下载·含正文】" if x.get("downloaded") else "【仅元数据·未下载·无正文】"
        if x.get("downloaded"):
            detail = ("摘要：" + (x.get("summary") or "无") + "\n正文命中片段：" + _snippet(body, valid, per))[:per]
        else:
            detail = "（无正文，只有文件名与路径；不要据此推测文件内容）"
        ctx.append(f"{i}. {tag} {x['name']}｜来源：{x['source']}/{x['group']}｜"
                   f"分类：{x['domain']}/{x['subject']}/{x['kind']}｜路径：{x['path']}\n{detail}")
    context = "\n".join(ctx)[:int(s.get("max_context_chars", 4200))]
    result = {"found": True, "sources": [_source(x, i+1, sc) for i, (sc, x, _) in enumerate(kept)],
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

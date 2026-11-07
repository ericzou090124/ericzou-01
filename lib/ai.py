"""grounded 问答：命中判定与源文件索引一律由本地检索给出，模型只负责中文概括。

v3.4.0 智能化改造（直接回应用户「明明有四六级真题，AI 却说没有」）：
- **范围按维度映射**：前端按「学科 / 类型 / 来源」浏览时，浏览路径必须映射到对应字段。
  旧版把 path[0] 一律当 domain，导致在「按学科 › 英语」下提问被错筛成
  domain=英语 → 空池 → 谎报「没有」。现在按 catalog.DIMS[dim] 映射。
- **口语 / 别名扩展**：「四六级真题」→ CET / CET4 / CET6 / 四级 / 六级 / 真题 / 试卷 /
  题+解 等，解决「文件名是 CET6题+解，用户说的是四六级真题」的词面不一致。
- **过滤器分级放宽**：问题里识别出的 类型 / 科目 / 领域 只是「线索」不是硬约束；
  严格范围搜不到就逐级放宽，并在回答里如实标注放宽了什么。群聊范围始终保留。
- **找资料意图**：「给我找一套 / 有没有 / 找一份」走确定性目录清单，直接列出真实文件 +
  可点击源索引，不让模型去编「无法提供真题内容」。
- 未下载条目仍一律标注「仅元数据、无正文摘要」；绝不臆造正文。
"""
from __future__ import annotations

import re
import time

from . import catalog, config, index, llm

NOT_FOUND = "授权可见的资料中没有检索到相关信息"
LIST_INTENT = re.compile(r"有哪些|哪几|多少|清单|列一下|都有什么|没下载|未下载|还没下载|存在哪些|包含哪些")
META_INTENT = re.compile(r"未下载|没下载|还没下载")
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

_LABELS = {"domain": "领域", "subject": "科目", "kind": "类型",
           "group": "群聊", "source": "来源", "folder": "文件夹"}


def _hay(x: dict, body: str = "") -> str:
    parts = []
    for k in ("name", "path", "folder", "group", "source", "domain", "subject", "kind",
              "summary", "tags"):
        v = x.get(k, "")
        parts.append(" ".join(str(t) for t in v) if isinstance(v, (list, tuple)) else str(v or ""))
    return (" ".join(parts) + " " + (body or "")).lower()


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
    """从问题文本识别 科目 / 领域 / 类型「线索」。注意：这只是线索，不是硬约束。"""
    c = cfg.get("classification") or {}
    f = {}
    for label in (c.get("subjects") or {}):
        if label == "综合":
            continue
        kws = c["subjects"][label] or []
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


def _dim_levels(dim: str) -> list[str]:
    """浏览维度 → 路径各层对应的字段名。"""
    if dim in catalog.DIMS:
        return catalog.DIMS[dim]
    return ["domain", "subject", "kind"]  # 兼容旧 classify 维度


def _scope_from_path(path, dim: str = "subject") -> dict:
    """把前端浏览路径按「当前维度」转成检索过滤器。

    subject:  ['英语']              → {'subject':'英语'}
    kind:     ['试卷与解析']         → {'kind':'试卷与解析'}
    source:   ['QQ群','彭小帮6.0']   → {'source':'QQ群','group':'彭小帮6.0'}
    """
    levels = _dim_levels(dim or "subject")
    f = {}
    for i, val in enumerate((path or [])[:len(levels)]):
        v = str(val or "").strip()
        if v and v not in ("全部",):
            f[levels[i]] = v
    return f


def _merge_filter(scope: dict, qfilter: dict) -> dict:
    f = dict(scope or {})
    f.update(qfilter or {})
    return f


def _where(f: dict) -> str:
    return "、".join(f"{_LABELS.get(k, k)}「{v}」" for k, v in f.items()) or "全部可见资料"


def _pool(cat: dict, f: dict) -> list[dict]:
    xs = catalog.items(cat)
    if not f:
        return xs
    return [x for x in xs if all(str(x.get(k, "")) == v for k, v in f.items())]


def _is_find_intent(q: str, cfg: dict) -> bool:
    if LIST_INTENT.search(q):
        return True
    words = ((cfg.get("search") or {}).get("find_intent") or [])
    return any(str(w) in q for w in words)


def _recall_terms(q: str, cfg: dict) -> tuple[list[str], set[str]]:
    """把口语问题扩展成「真正能命中文件名」的检索词集合。

    返回 (全部候选词, 用户原始词)。别名表只在「标签或长词确实出现在问题里」时整组展开，
    避免把整库泛词都塞进来导致召回噪声。
    """
    low = (q or "").strip().lower()
    base = [str(t).strip().lower() for t in index.query_terms(q)]
    extra: list[str] = []
    for key, words in (((cfg.get("search") or {}).get("phrase_expansions") or {})).items():
        k = str(key).lower()
        if k and k in low:
            extra.append(k)
            extra += [str(w).lower() for w in (words or []) if w]
    aliases = ((cfg.get("classification") or {}).get("aliases") or {})
    for label, words in aliases.items():
        lab = str(label).lower()
        ws = [str(w).lower() for w in (words or []) if w]
        if lab in low or any(len(w) >= 3 and w in low for w in ws):
            extra.append(lab)
            extra += ws
    terms, seen = [], set()
    for t in base + extra:
        t = (t or "").strip().lower()
        if len(t) >= 2 and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms, {t for t in base if len(t) >= 2}


def _rank(q: str, pool: list[dict], cfg: dict, top_k: int) -> tuple[list[dict], list[str], float]:
    """在候选池内做「词面 + FTS 正文」混合召回与相关度打分。

    每个条目记录命中的具体词；相关度 = 命中词数 / 全池实际出现过的词数，
    天然抑制「一个泛词命中一半目录」的假相关。
    """
    terms, core = _recall_terms(q, cfg)
    if not terms:
        return [], [], 0.0
    bodies: dict[str, str] = {}
    try:
        for h in index.search(q, max(24, top_k * 4)):
            if h.get("body"):
                bodies[h["item_id"]] = h["body"]
    except Exception:
        bodies = {}
    rows = []
    for x in pool:
        body = bodies.get(x["id"], "")
        hay = _hay(x, body)
        name = str(x.get("name") or "").lower()
        hit = {t for t in terms if t in hay}
        if not hit:
            continue
        s = 0.0
        core_hit = 0
        latin_hit = 0
        for t in hit:
            s += 1.0
            if t in name:
                s += 1.1
            if t in core:
                s += 0.9
                core_hit += 1
                # 具体英文/数字混合词（CET6 / CET4 / python…）出现在文件名里 = 强证据
                if re.fullmatch(r"[a-z0-9_.+#-]{3,}", t) and (t in name or t in str(x.get("path", "")).lower()):
                    latin_hit += 1
                    s += 2.0
            if body and t in body.lower():
                s += 0.5
        if body:
            s += 0.8
        rows.append({"x": x, "body": body, "hit": hit, "s": s,
                     "core_hit": core_hit, "latin_hit": latin_hit})
    if not rows:
        return [], terms, 0.0
    valid: set[str] = set()
    for r in rows:
        valid |= r["hit"]
    for r in rows:
        r["rel"] = len(r["hit"] & valid) / max(1, len(valid))
        r["score"] = r["s"] + 3.0 * r["rel"]
    rows.sort(key=lambda r: (-r["score"], str(r["x"].get("name", ""))))
    return rows, terms, rows[0]["rel"]


def _catalog_answer(q: str, rows: list[dict], f: dict, cat: dict, t0: float,
                    relaxed: str, only_meta: bool) -> dict:
    """找资料意图：确定性目录清单，列出真实文件 + 可点击源索引，绝不编造正文。"""
    sel = [r for r in rows if (not r["x"].get("downloaded"))] if only_meta else rows
    if not sel:
        sel = rows
    top = sel[:8]
    dl = sum(1 for r in sel if r["x"].get("downloaded"))
    where = _where(f)
    lines = [f"{i}. {r['x']['name']}（{r['x'].get('subject') or '综合'} / {r['x'].get('kind') or '其他资料'}"
             f" · {'已下载' if r['x'].get('downloaded') else '仅元数据·未下载'}）"
             for i, r in enumerate(top, 1)]
    head = f"在「{where}」范围内找到 {len(sel)} 份与「{q}」相关的资料"
    if relaxed:
        head += f"（{relaxed}）"
    head += f"，其中已下载 {dl} 份、仅元数据 {len(sel) - dl} 份。前 {len(top)} 份：\n"
    tail = ("\n未下载条目只有文件名与分类等元数据，无正文摘要；勾选后点「批量导入到 Obsidian」"
            "即可下载、抽取正文并自动分类入库。" if len(sel) > dl else
            "\n已下载条目含正文，可在下方源文件索引点开预览或打开 Obsidian 笔记。")
    return {"answer": head + "\n".join(lines) + tail, "found": True, "mode": "catalog",
            "scope": f, "relaxed": relaxed, "total_matched": len(sel),
            "sources": [_source(r["x"], i + 1, r["score"]) for i, r in enumerate(top)],
            "scanned": len(catalog.items(cat)), "best_score": round(rows[0]["rel"], 3),
            "took_ms": int((time.time() - t0) * 1000)}


def _snippet(body: str, terms: list[str], width: int) -> str:
    clean = re.sub(r"\s+", " ", body or "").strip()
    if not clean:
        return "（正文为空或不可抽取）"
    low = clean.lower()
    positions = [low.find(t.lower()) for t in terms if len(t) >= 2 and t.lower() in low]
    pos = min(positions) if positions else -1
    start = 0 if pos < 0 else max(0, pos - width // 4)
    return clean[start:start + width]


def _local_answer(rows: list[dict]) -> str:
    parts = []
    for r in rows[:3]:
        x, body = r["x"], r["body"]
        if x.get("downloaded") and body.strip():
            clean = re.sub(r"\s+", " ", body).strip()
            segs = [s for s in re.split(r"(?<=[。！？；])", clean[:900]) if len(s.strip()) >= 10]
            if segs:
                parts.append("".join(segs[:2])[:220])
        else:
            parts.append(f"{x['name']}（仅元数据，未下载，无正文摘要）")
    return ("根据已入库资料：" + " ".join(parts)) if parts else "已检索到相关资料，请点开下方源文件索引查看。"


def _ladder(f: dict, hard: dict, qf: dict) -> list[tuple[dict, str]]:
    """构造「严格 → 逐级放宽」的过滤器阶梯。群聊范围（用户显式选择）永不丢弃。"""
    out = [(f, "")]
    qf2 = {k: v for k, v in qf.items() if k != "kind"}
    if qf2 != qf:
        out.append((_merge_filter(hard, qf2), "已自动放宽问题里的「类型」线索"))
    if qf:
        out.append((dict(hard), "已自动放宽问题里的分类线索"))
    cur = dict(hard)
    for k in ("folder", "subject", "domain", "kind", "source"):
        if k in cur:
            cur = {a: b for a, b in cur.items() if a != k}
            out.append((dict(cur), f"已自动放宽浏览范围（{_LABELS.get(k, k)}）"))
    if hard:
        out.append(({}, "已自动放宽到全部授权可见资料"))
    # 去重（保留首次出现，说明文字取更宽松的那条）
    seen, uniq = set(), []
    for cand, note in out:
        key = tuple(sorted(cand.items()))
        if key not in seen:
            seen.add(key)
            uniq.append((cand, note))
    return uniq


def answer(q: str, cat: dict | None = None, fast: bool = False, scope: list | None = None,
          group: str = "", dim: str = "subject") -> dict:
    t0 = time.time()
    q = (q or "").strip()
    cfg = config.CFG
    if not q:
        return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none",
                "scope": _scope_from_path(scope, dim), "took_ms": 0}
    cat = cat or catalog.load()

    # 浏览范围（按维度正确映射）+ 群聊范围 = 用户显式约束，始终保留
    hard = _scope_from_path(scope, dim)
    gf = str(group or "").strip()
    if gf:
        hard["group"] = gf
    # 问题里识别出的分类字段 = 线索，可被放宽
    qf = _filters(q, cfg)
    f = _merge_filter(hard, qf)

    s = config.settings()
    top_k = int(s.get("top_k", 5))
    threshold = float(s.get("min_relevance", 0.22))
    gate = max(0.12, threshold * 0.5)

    rows, terms, best, used_f, relaxed = [], [], 0.0, f, ""
    fallback = None
    for cand_f, note in _ladder(f, hard, qf):
        pool = _pool(cat, cand_f)
        if not pool:
            continue
        r, t, br = _rank(q, pool, cfg, top_k)
        if not r:
            continue
        if br >= gate:
            rows, terms, best, used_f, relaxed = r, t, br, cand_f, note
            break
        if fallback is None or br > fallback[2]:
            fallback = (r, t, br, cand_f, note)
    if not rows and fallback:
        rows, terms, best, used_f, relaxed = fallback
    if not rows or best < gate:
        return {"answer": NOT_FOUND + f"。已在「{_where(f)}」及其放宽范围内检索授权可见目录与已入库正文，"
                          "未找到能回答该问题的资料。",
                "found": False, "sources": [], "mode": "none", "scope": f,
                "best_score": round(best, 3), "scanned": index.count(),
                "took_ms": int((time.time() - t0) * 1000)}

    where = _where(used_f)
    if _is_find_intent(q, cfg):
        # 「找资料」要精准：至少命中一个用户原词，且相关度接近最佳命中，
        # 避免宽泛范围里把整个分类的几百份都列进来（如问 CET6 却返回 402 份试卷）。
        precise = [r for r in rows if r.get("core_hit", 0) > 0 and r["score"] >= rows[0]["score"] * 0.55]
        # 若问题里有明确英文/编号词（CET6），只保留文件名真的含该词的，避免 CET4 混进来
        latin = [r for r in (precise or rows) if r.get("latin_hit", 0) > 0]
        if latin:
            precise = latin
        return _catalog_answer(q, precise or rows, used_f, cat, t0, relaxed,
                               bool(META_INTENT.search(q)))

    kept = [r for r in rows[:top_k * 2] if r["rel"] >= gate][:top_k] or rows[:top_k]
    per = max(600, int(int(s.get("max_context_chars", 4200)) / max(1, len(kept))))
    valid = sorted({t for r in kept for t in r["hit"]}, key=lambda t: (-len(t), t))
    ctx = []
    for i, r in enumerate(kept, 1):
        x, body = r["x"], r["body"]
        tag = "【已下载·含正文】" if x.get("downloaded") else "【仅元数据·未下载·无正文】"
        if x.get("downloaded"):
            detail = ("摘要：" + (x.get("summary") or "无") + "\n正文命中片段：" + _snippet(body, valid, per))[:per]
        else:
            detail = "（无正文，只有文件名与路径；不要据此推测文件内容）"
        ctx.append(f"{i}. {tag} {x['name']}｜来源：{x['source']}/{x['group']}｜"
                   f"分类：{x['domain']}/{x['subject']}/{x['kind']}｜路径：{x['path']}\n{detail}")
    scope_head = f"【检索范围：{where}】只依据该范围内的资料片段回答，不得借用范围外知识。\n"
    if relaxed:
        scope_head += f"【说明】{relaxed}，回答时不要声称范围内没有资料。\n"
    context = scope_head + "\n".join(ctx)[:int(s.get("max_context_chars", 4200))]
    result = {"found": True, "scope": used_f, "relaxed": relaxed,
              "sources": [_source(r["x"], i + 1, r["score"]) for i, r in enumerate(kept)],
              "scanned": index.count(), "best_score": round(best, 3)}

    if fast:
        result.update({"answer": _local_answer(kept), "mode": "fast"})
    else:
        text, err = llm.chat(SYSTEM, f"资料片段：\n{context}\n\n问题：{q}", s)
        if text and NOT_FOUND in text:
            result.update({"answer": _local_answer(kept), "mode": "local", "note": "模型误判未命中，已改用原文摘录"})
        elif text:
            result.update({"answer": text, "mode": "llm"})
        else:
            result.update({"answer": _local_answer(kept), "mode": "local", "note": f"{err}，已本地降级"})
    result["took_ms"] = int((time.time() - t0) * 1000)
    return result

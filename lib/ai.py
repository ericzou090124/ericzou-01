"""grounded 问答：命中判定与源文件索引一律由本地检索给出，模型只负责中文概括。

v3.5.0 泛化改造（回应用户「AI 能搜出来的资料很少，只有四六级又快又准」）：
- **根因**：旧版靠 jieba 通用词典切词 + 一份手工写的「四六级」别名词表，
  专业术语（罗尔/柯西/马原/线代）被切碎；问题里识别出的分类词被当成**硬过滤**，
  「机器学习」被错筛成 domain=学习、「罗尔…中值定理」被错筛成 复变函数与积分变换；
  再叠加为 CET6 精准度加的 0.55 分数闸门，普通问题往往只剩 5 条甚至误报「没有」。
- **现在**：lib/vocab.py 从当前目录的真实文件名/分类里自动学词（df 词典、
  最长匹配切词、共现别名、简称跳字、错字近似），**不硬编码任何学科词表**。
  换任何一个 QQ 群、任何一门课都自动获得同等的召回能力。
  四六级的 phrase_expansions 降级为可选增强，删掉它也能通过共现学到 CET6。
- 问题里的分类线索只做**相关性加权**，不再当硬过滤；硬约束只有用户显式选的
  浏览路径与群聊范围。严格范围无结果时仍逐级放宽并如实标注。
- 命中即返回，不再用 min_relevance 把真实命中判成「没找到」；top_k 提高到 8，
  回答给出「共命中 N 份」并列出更多可点击源索引。
- 未下载条目仍一律标注「仅元数据、无正文摘要」；绝不臆造正文。
"""
from __future__ import annotations

import re
import time

from . import catalog, config, index, llm, vocab

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
# 口语虚词：不作为「用户实义词」，避免「有哪些资料」把全库都召回
_QUERY_STOP = {
    "资料", "文件", "内容", "相关", "关于", "一下", "这个", "那个", "哪些", "哪个",
    "多少", "有没有", "请问", "帮我", "看看", "给我", "我想", "需要", "推荐", "一套",
    "一份", "什么", "怎么", "怎么样", "咋样", "所有", "全部", "其它", "其他", "可以",
    "总结", "列一下", "找一套", "找一份", "找找", "想找", "来一套", "要一套",
}


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


def _hints(q: str, cfg: dict) -> dict:
    """问题里的 科目/领域/类型 线索 —— **只用于加权，绝不用于过滤**。"""
    c = cfg.get("classification") or {}
    f = {}
    for label in (c.get("subjects") or {}):
        if label == "综合":
            continue
        kws = c["subjects"][label] or []
        if label in q or any(k and len(k) >= 2 and k in q for k in kws):
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
        if label in q or any(k and len(k) >= 2 and k not in generic and k in q
                             for k in rule.get("keywords", [])):
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


def _recall_terms(q: str, cfg: dict, cat: dict) -> tuple[list[str], set[str], set[str]]:
    """通用召回词：(全部候选词, 用户实义词, 自动扩展词)。

    核心来自 vocab（从当前目录自动学出），手工词表只是可选增强；
    即使把 config.search.phrase_expansions 全部删空，泛化能力也不受影响。
    """
    low = (q or "").strip().lower()
    try:
        v = vocab.get(cat)
        core_v, extra_v = v.expand(q)
        # 区分度过滤：覆盖超过 18% 目录的词（「学习」「pdf」「其他资料」「通选」…）
        # 没有检索价值，留着会让任意问题命中半库。
        informative = lambda t: v.informative(t)
    except Exception:
        v, core_v, extra_v = None, [], []
        informative = lambda t: True
    # jieba / trigram 词同样算用户实义词（兼容 FTS 与历史打桩测试）
    try:
        base = [str(t).strip().lower() for t in index.query_terms(q, 32)]
    except TypeError:
        base = [str(t).strip().lower() for t in index.query_terms(q)]
    raw_core = {t for t in (core_v + base) if len(t) >= 2 and t not in _QUERY_STOP}
    core = {t for t in raw_core if informative(t)}
    if not core and v is not None:
        # 只在「词完全没在库里出现」时保留兜底；绝不把「学习」这类覆盖半库的超泛词放回来
        unknown = [t for t in raw_core if v.coverage(t) == 0]
        core = set(sorted(unknown, key=len, reverse=True)[:1])
    extra: set[str] = {str(w).lower() for w in extra_v if len(str(w)) >= 2}
    # 可选增强：手工短语表 / 分类别名（不再必需）
    for key, words in ((cfg.get("search") or {}).get("phrase_expansions") or {}).items():
        k = str(key).lower()
        if k and k in low:
            extra.add(k)
            extra |= {str(w).lower() for w in (words or []) if w}
    for label, words in ((cfg.get("classification") or {}).get("aliases") or {}).items():
        lab = str(label).lower()
        ws = [str(w).lower() for w in (words or []) if w]
        if lab in low or any(len(w) >= 3 and w in low for w in ws):
            extra.add(lab)
            extra |= set(ws)
    extra = {t for t in extra if informative(t)} - core
    # 长词优先，减少「截断子串」噪声
    terms = sorted(core, key=lambda t: (-len(t), t)) + sorted(extra, key=lambda t: (-len(t), t))
    return terms[:96], core, extra


def _rank(q: str, pool: list[dict], cfg: dict, cat: dict, top_k: int,
          hints: dict | None = None) -> tuple[list[dict], list[str], float]:
    """词面 + FTS 正文混合召回。用户实义词权重高，自动扩展词只做低权补充。"""
    terms, core, extra = _recall_terms(q, cfg, cat)
    if not terms:
        return [], [], 0.0
    bodies: dict[str, str] = {}
    try:
        for h in index.search(q, max(32, top_k * 4), extra=sorted(extra)):
            if h.get("body"):
                bodies[h["item_id"]] = h["body"]
    except TypeError:  # 兼容旧签名/打桩
        try:
            for h in index.search(q, max(32, top_k * 4)):
                if h.get("body"):
                    bodies[h["item_id"]] = h["body"]
        except Exception:
            bodies = {}
    except Exception:
        bodies = {}
    try:
        similar: dict[str, list[str]] = {
            t: vocab.get(cat).similar(t, 2) for t in list(core)[:8]
        }
    except Exception:
        similar = {}
    latin_core = {t for t in core if re.fullmatch(r"[a-z0-9_.+#-]{3,}", t)}
    # 扩展词单独构成召回时要更严：至少命中 2 个高区分度词，或 1 个极具体词。
    # 既保留「四六级 → CET6 真题」这类跨词面召回，又挡住「大二 / 高等数学」这类噪声。
    try:
        vv = vocab.get(cat)
        strong = {t for t in extra if vv.coverage(t) <= max(8, vv.n * 0.05)}
        very_strong = {t for t in extra if 0 < vv.coverage(t) <= 12}
    except Exception:
        strong, very_strong = set(extra), set()
    rows = []
    for x in pool:
        body = bodies.get(x["id"], "")
        hay = _hay(x, body)
        name = str(x.get("name") or "").lower()
        path = str(x.get("path") or "").lower()
        core_hit = {t for t in core if t in hay}
        strong_hit = {t for t in strong if t in hay}
        extra_hit = {t for t in extra if t in hay}
        soft = {t for t, ws in similar.items() for w in ws if w in hay}
        if not core_hit and not (len(strong_hit) >= 2 or (strong_hit & very_strong)):
            continue
        s = 0.0
        latin_hit = 0
        for t in core_hit:
            s += 2.0
            if t in name:
                s += 1.6
            if body and t in body.lower():
                s += 0.8
            if t in latin_core and (t in name or t in path):
                latin_hit += 1
                s += 3.0
        for t in extra_hit:
            s += 0.35
            if t in name:
                s += 0.2
        s += 0.4 * len(soft)
        if body:
            s += 0.8
        for k, v in (hints or {}).items():
            if str(x.get(k, "")) == v:
                s += 1.2  # 分类线索只加权，不排除其它条目
        rows.append({"x": x, "body": body, "hit": core_hit | extra_hit,
                     "core_hit": len(core_hit), "latin_hit": latin_hit,
                     "s": s, "score": s, "rel": min(1.0, len(core_hit) / max(1, len(core)) + 0.35)})
    if not rows:
        return [], terms, 0.0
    rows.sort(key=lambda r: (-r["score"], str(r["x"].get("name", ""))))
    # 有真实命中即算找到，不再用相关度阈值误杀泛化查询
    return rows, terms, 1.0


def _catalog_answer(q: str, rows: list[dict], f: dict, cat: dict, t0: float,
                    relaxed: str, only_meta: bool) -> dict:
    """找资料意图：确定性目录清单，列出真实文件 + 可点击源索引，绝不编造正文。"""
    sel = [r for r in rows if (not r["x"].get("downloaded"))] if only_meta else rows
    if not sel:
        sel = rows
    top = sel[:12]
    dl = sum(1 for r in sel if r["x"].get("downloaded"))
    where = _where(f)
    lines = [f"{i}. {r['x']['name']}（{r['x'].get('subject') or '综合'} / {r['x'].get('kind') or '其他资料'}"
             f" · {'已下载' if r['x'].get('downloaded') else '仅元数据·未下载'}）"
             for i, r in enumerate(top, 1)]
    head = f"在「{where}」范围内共找到 {len(sel)} 份与「{q}」相关的资料"
    if relaxed:
        head += f"（{relaxed}）"
    head += f"，其中已下载 {dl} 份、仅元数据 {len(sel) - dl} 份。相关度最高的 {len(top)} 份：\n"
    tail = ("\n未下载条目只有文件名与分类等元数据，无正文摘要；勾选后点「批量导入到 Obsidian」"
            "即可下载、抽取正文并自动分类入库。" if len(sel) > dl else
            "\n已下载条目含正文，可在下方源文件索引点开预览或打开 Obsidian 笔记。")
    if len(sel) > len(top):
        tail += f"\n（还有 {len(sel)-len(top)} 份同类资料，可在左侧分类树或搜索框继续查看。）"
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
    """构造「严格 → 逐级放宽」的过滤器阶梯。群聊范围（用户显式选择）永不丢弃。

    v3.5.0：问题里的分类线索不再是硬过滤，因此阶梯只放宽用户浏览路径。
    """
    out = [(f, "")]
    cur = dict(hard)
    for k in ("folder", "subject", "domain", "kind", "source"):
        if k in cur:
            cur = {a: b for a, b in cur.items() if a != k}
            out.append((dict(cur), f"已自动放宽浏览范围（{_LABELS.get(k, k)}）"))
    if hard:
        out.append(({}, "已自动放宽到全部授权可见资料"))
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

    # 硬约束只有用户显式选择：浏览路径（按维度映射）+ 群聊范围
    hard = _scope_from_path(scope, dim)
    gf = str(group or "").strip()
    if gf:
        hard["group"] = gf
    f = dict(hard)
    hints = _hints(q, cfg)  # 只加权，不过滤

    s = config.settings()
    top_k = int(s.get("top_k", 8))
    threshold = float(s.get("min_relevance", 0.22))
    gate = max(0.12, threshold * 0.5)

    rows, terms, best, used_f, relaxed = [], [], 0.0, f, ""
    fallback = None
    for cand_f, note in _ladder(f, hard, {}):
        pool = _pool(cat, cand_f)
        if not pool:
            continue
        r, t, br = _rank(q, pool, cfg, cat, top_k, hints)
        if not r:
            continue
        if br >= gate:
            rows, terms, best, used_f, relaxed = r, t, br, cand_f, note
            break
        if fallback is None or br > fallback[2]:
            fallback = (r, t, br, cand_f, note)
    if not rows and fallback:
        rows, terms, best, used_f, relaxed = fallback
    if not rows:
        return {"answer": NOT_FOUND + f"。已在「{_where(f)}」及其放宽范围内检索授权可见目录与已入库正文，"
                          "未找到能回答该问题的资料。",
                "found": False, "sources": [], "mode": "none", "scope": f,
                "total_matched": 0, "best_score": 0,
                "scanned": index.count(), "took_ms": int((time.time() - t0) * 1000)}

    where = _where(used_f)
    if _is_find_intent(q, cfg):
        # 命中过用户原词的排前面；问题里有具体英文/编号（CET6）时只保留文件名真含该词的，
        # 避免 CET4 混进 CET6 的结果。一般问题不再用 0.55 分数闸门砍掉真实命中。
        precise = [r for r in rows if r.get("core_hit", 0) > 0]
        if latin_tokens := {t for t in terms if re.fullmatch(r"[a-z0-9_.+#-]{3,}", t)
                            and t in q.lower()}:
            latin = [r for r in (precise or rows) if r.get("latin_hit", 0) > 0]
            if latin:
                precise = latin
        return _catalog_answer(q, precise or rows, used_f, cat, t0, relaxed,
                               bool(META_INTENT.search(q)))

    kept = rows[:top_k]
    per = max(600, int(int(s.get("max_context_chars", 12000)) / max(1, len(kept))))
    valid = sorted({t for r in kept for t in r["hit"]}, key=lambda t: (-len(t), t))[:24]
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
    context = scope_head + "\n".join(ctx)[:int(s.get("max_context_chars", 12000))]
    result = {"found": True, "scope": used_f, "relaxed": relaxed,
              "sources": [_source(r["x"], i + 1, r["score"]) for i, r in enumerate(kept)],
              "total_matched": len(rows), "scanned": index.count(),
              "best_score": round(best, 3)}

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

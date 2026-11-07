"""分类：单值三级（领域 / 学科 / 类型）+ 多归属主题标签（仅用于搜索召回）。

设计原则（直接回应用户反馈的三大 bug）：
1. **计数严格一致**：每个文件在「学科 / 类型 / 来源」每个维度上只有「一个值」，
   因此任意层级节点计数之和 == 文件总数，绝不会出现「节点数加起来对不上」或「空分类」。
2. **不漏项**：多归属 `tags` 只用于搜索召回扩展，不作为树维度；树维度一律单值。
3. **不错分**：关键词按长度加权，科目全名命中额外加权；裸扩展名（如 ppt）已从词库剔除，
   不会再因文件名里包含 ".pptx" 就把工作报表错判成「课件资源」。

2026-11-07 重做：移除了 v3.1.0 的 genre/topic/modality 多值树维度——
那些维度正是「分类计数对不上、出现空分类、错分」的根因。现在分类结果只有
domain / subject / kind / tags，界面树也只用这三个单值维度。
"""
from __future__ import annotations


def _kw_weight(k: str) -> int:
    """长关键词更可信：『高等代数』比『代数』更有判别力。"""
    n = len((k or "").strip())
    if n >= 6:
        return 4
    if n >= 4:
        return 3
    if n >= 2:
        return 2
    return 1


def _score(text: str, keywords) -> int:
    t = (text or "").lower()
    total = 0
    for k in keywords or []:
        if k and str(k).lower() in t:
            total += _kw_weight(str(k))
    return total


def _best(scores: dict, default: str) -> str:
    if not scores:
        return default
    # 同分时优先更具体的（名字更长）标签，避免泛类目抢位
    return max(scores, key=lambda k: (scores[k], len(k)))


def classify_full(row: dict, cfg: dict) -> tuple[str, str, str, list[str]]:
    """返回 (domain, subject, kind, tags)。tags 为多归属标签，仅用于搜索召回。"""
    c = cfg.get("classification") or {}
    folder = str(row.get("folder", "") or "")
    name = str(row.get("name", "") or "")
    hay = (folder + " " + name).lower()

    # ---- 学科：命中多个就都记下来，主学科取分数最高者 ----
    sub_scores: dict[str, int] = {}
    for label, kws in (c.get("subjects") or {}).items():
        if not kws:
            continue
        s = 3 * _score(folder, kws) + 2 * _score(name, kws)
        if label and str(label).lower() in hay:
            s += 12  # 学科全名直接出现 = 强证据
        if s > 0:
            sub_scores[str(label)] = s
    subject = _best(sub_scores, "综合")

    # ---- 资源类型（单值，按分数取最高）----
    kind_scores: dict[str, int] = {}
    for rule in c.get("kinds") or []:
        n = str(rule.get("name") or "")
        s = 2 * _score(folder, rule.get("keywords", [])) + _score(name, rule.get("keywords", []))
        if s > 0:
            kind_scores[n] = s
    kind = _best(kind_scores, "其他资料")

    # ---- 领域 ----
    dom_scores: dict[str, int] = {}
    for rule in c.get("domains") or []:
        n = str(rule.get("name") or "")
        s = 2 * _score(folder, rule.get("keywords", [])) + _score(name, rule.get("keywords", []))
        if s > 0:
            dom_scores[n] = s
    domain = _best(dom_scores, "其他")
    if domain == "其他":
        if subject != "综合" or kind in ("课件资源", "习题作业", "上课笔记", "试卷与解析"):
            domain = "学习"

    # ---- 多归属标签：主学科 + 命中领域 + 类型 + 相关主题别名（仅搜索召回用）----
    tags: set[str] = set()
    for label in sub_scores:
        if label != "综合":
            tags.add(label)
    if domain != "其他":
        tags.add(domain)
    if kind != "其他资料":
        tags.add(kind)
    for label, words in (c.get("aliases") or {}).items():
        if any(str(w).lower() in hay for w in (words or []) if w):
            tags.add(str(label))
    if not tags:
        tags = {"综合", kind}

    # 固定顺序 + 上限，保证 catalog 稳定、不会因 dict 顺序抖动
    ordered = sorted(tags, key=lambda t: (-len(t), t))[:12]
    return domain, subject, kind, ordered


def classify(row: dict, cfg: dict) -> tuple[str, str, str]:
    """兼容旧接口：只返回三级主分类。"""
    d, s, k, _t = classify_full(row, cfg)
    return d, s, k


def classify_extended(row: dict, cfg: dict) -> dict:
    """目录写入所需的全部分类字段。单值 domain/subject/kind/tags，外加兼容字段。

    不引入任何多值树维度，从根本上杜绝「计数对不上 / 空分类 / 错分」。
    genre / topics / modality 仅作为占位兼容字段（恒为空），不在任何界面树中使用。
    """
    domain, subject, kind, tags = classify_full(row, cfg)
    return {
        "domain": domain, "subject": subject, "kind": kind, "tags": tags,
        "genre": "", "topics": [], "modality": "",
        "confidence": 1.0, "reason": {"matched": sorted(tags)[:8]}, "engine": "rules",
    }


def expand_query(q: str, cfg: dict) -> list[str]:
    """把查询词扩展为「同义 / 相关主题」候选词，用于搜索召回，避免漏项。

    例：搜「高等代数」→ 高等代数、高代、线性代数、线代、矩阵、行列式…
    """
    q = (q or "").strip().lower()
    if not q:
        return []
    if len(q) < 2:
        return [q]  # 单字查询不做相关词扩展，否则会召回整库
    aliases = (cfg.get("classification") or {}).get("aliases") or {}
    terms: set[str] = {q}
    for label, words in aliases.items():
        lab = str(label).lower()
        ws = [str(w).lower() for w in (words or []) if w]
        if q == lab or q in lab or lab in q or any(q in w or w in q for w in ws):
            terms.add(lab)
            terms.update(ws)
    # 长词优先，短泛词不单独作为唯一依据展示（匹配阶段仍全部参与）
    return sorted((t for t in terms if t), key=lambda t: (-len(t), t))

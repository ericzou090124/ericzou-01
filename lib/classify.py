"""分类 v3.1.0：三级主分类（单选） + 多归属主题标签 + 别名召回 + 泛化体裁/主题/模态。

v3.1.0 新增 `classify_extended()`：在 v3.0.0 原有三元组之上叠加一层**内容驱动**的
中性受控词表推断（lib/taxonomy.py）。它不区分「学生群 / 工作群」，同一套体裁词表
服务所有场景：工作群的合同、进货单、报销单、会议纪要、法务文件不会再全落进
「综合 / 其他资料 / 其他」。原有 `classify_full()` / `classify()` 行为完全保留。

旧版的两个真实问题：
1. 「赢家通吃」+ 泛词：高等代数词库里放了「多项式」，于是
   「第七章勒让德多项式.doc」被判成高等代数，而全库真正的高等代数资料是 0 份，
   搜索「高等代数」只出现这 1 条，看起来像严重漏项；
2. 每个文件只能属于一个科目，一份「线性代数期末真题」在「学习 › 线性代数」
   和「考试与复习」里二选一，用户从另一条路径就找不到它。

现在：
- 关键词按长度加权，科目全名命中额外加权，泛词不再能单独决定分类；
- 每个文件同时带多个「主题标签」（命中的科目 / 领域 / 类型 / 相关主题别名），
  在「按主题标签」视图里同一份文件会出现在多个节点下 —— 不藏文件；
- 搜索时对查询词做同义/相关词扩展，搜「高等代数」能召回线性代数、矩阵、
  行列式、多项式等全部相关资料，而不是只剩 1 条。

主分类仍返回三元组，保持老版本 / 审计脚本的兼容性。
"""
from __future__ import annotations

from . import taxonomy


def _kw_weight(k: str) -> int:
    """长关键词更可信：『高等代数』比『代数』『多项式』更有判别力。"""
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
    """返回 (domain, subject, kind, tags)。tags 为去重后的多归属标签。"""
    c = cfg.get("classification") or {}
    folder = str(row.get("folder", "") or "")
    name = str(row.get("name", "") or "")
    hay = (folder + " " + name).lower()

    # ---- 科目：命中多个就都记下来，主科目取分数最高者 ----
    sub_scores: dict[str, int] = {}
    for label, kws in (c.get("subjects") or {}).items():
        if not kws:
            continue
        s = 3 * _score(folder, kws) + 2 * _score(name, kws)
        if label and str(label).lower() in hay:
            s += 12  # 科目全名直接出现 = 强证据
        if s > 0:
            sub_scores[str(label)] = s
    subject = _best(sub_scores, "综合")

    # ---- 资源类型 ----
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
        if subject != "综合" or kind in ("课件资源", "习题作业", "上课笔记"):
            domain = "学习"

    # ---- 多归属标签：主分类 + 所有命中科目 + 相关主题别名 ----
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
    """v3.1.0 融合结果：原有三级分类 + 泛化体裁 / 动态主题 / 模态 / 依据。

    返回 dict 覆盖 catalog 写入所需的全部分类字段；不改动条目集合与下载状态。
    词表默认规则层（零依赖、离线、可解释），llm_assist 显式开启且非敏感件才调模型，
    模型失败静默回退规则层 —— 保证任何环境都能完成分类。
    """
    domain, subject, kind, tags = classify_full(row, cfg)
    tcfg = (cfg.get("classification") or {}).get("taxonomy") or {}
    inf = taxonomy.infer(row, cfg) if tcfg.get("enabled", True) else {
        "genre": "其他资料", "topics": [], "modality": taxonomy.modality(row),
        "confidence": 0.3, "reason": {"matched": [], "genre_scores": {}}, "engine": "off"}
    if tcfg.get("llm_assist"):
        inf = taxonomy.llm_enrich(row, inf, cfg)

    # 旧三级词库是围绕校园课程归纳的：当它拿不到任何科目证据（subject == "综合"）时，
    # 「其他资料 / 课件资源」这类兜底类目会吞噬工作群资料——实测销售合同、报销单、
    # 会议纪要全落进「其他 / 综合 / 其他资料」；带 .pptx 的销售报表甚至被判成
    # 「学习 / 课件资源」，只因为扩展名里含 "ppt"。
    # 中性规则（不判断是学生还是职场，与场景无关）：
    #   没有科目证据 + 内容驱动层给出明确体裁 ⇒ 用该体裁作为资源类型，领域归「综合」。
    # 有科目证据的校园文件完全保持 v3.0.0 结果不变。
    genre = inf["genre"]
    long_tail = genre in ("其他资料", taxonomy.FALLBACK_GENRE)
    if subject == "综合" and not long_tail:
        kind = genre
        if domain in ("学习", "其他"):
            domain = "综合"

    merged = set(tags)
    if not long_tail:
        merged.add(genre)
    # 动态主题入多归属标签，但限制数量与长度，避免把噪音词变成一堆空类目
    for tp in inf["topics"][:2]:
        if len(tp) >= 3:
            merged.add(tp)
    if inf["modality"] != "其他":
        merged.add(inf["modality"])
    ordered = sorted(merged, key=lambda t: (-len(t), t))[:18]

    return {
        "domain": domain, "subject": subject, "kind": kind, "tags": ordered,
        "genre": genre, "topics": inf["topics"], "modality": inf["modality"],
        "confidence": inf["confidence"], "reason": inf["reason"], "engine": inf["engine"],
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
        # 双向命中：查标签名，或查该组里的任一别名
        if q == lab or q in lab or lab in q or any(q in w or w in q for w in ws):
            terms.add(lab)
            terms.update(ws)
    # v3.1.0：受控词表语义匹配。搜「采购单」→ 同时召回「进货单 / 供应商 / 报价单」
    # 等同一体裁的规范词，工作群资料不会因为用词不同就搜不到。
    tm = taxonomy.match(q, cfg)
    if tm["canonical"]:
        terms.update(tm["canonical"])
        terms.update(tm["terms"][:30])
    # 长词优先，短泛词不单独作为唯一依据展示（匹配阶段仍全部参与）
    return sorted((t for t in terms if t), key=lambda t: (-len(t), t))

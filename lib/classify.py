"""分类 v3.0.0：三级主分类（单选） + 多归属主题标签 + 别名召回。

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
    # 长词优先，短泛词不单独作为唯一依据展示（匹配阶段仍全部参与）
    return sorted((t for t in terms if t), key=lambda t: (-len(t), t))

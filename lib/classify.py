"""三级分类：领域 → 科目/主题 → 资源类型。

匹配优先级：群内文件夹名 > 文件名 > 兜底。规则全部在 config.json，可改。
"""
from __future__ import annotations


def _hits(text: str, keywords: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for k in keywords if k and k.lower() in t)


def classify(row: dict, cfg: dict) -> tuple[str, str, str]:
    c = cfg.get("classification") or {}
    folder, name = row.get("folder", ""), row.get("name", "")
    hay = folder + " " + name

    subject, best = "综合", 0
    for label, kws in (c.get("subjects") or {}).items():
        if not kws:
            continue
        score = 3 * _hits(folder, kws) + 2 * _hits(name, kws)
        if score > best:
            subject, best = label, score

    kind, best = "其他资料", 0
    for rule in c.get("kinds") or []:
        score = 2 * _hits(folder, rule.get("keywords", [])) + _hits(name, rule.get("keywords", []))
        if score > best:
            kind, best = rule["name"], score

    domain, best = "其他", 0
    for rule in c.get("domains") or []:
        score = 2 * _hits(folder, rule.get("keywords", [])) + _hits(name, rule.get("keywords", []))
        if score > best:
            domain, best = rule["name"], score
    if domain == "其他":
        if subject != "综合" or kind in ("课件教材", "习题作业", "笔记总结"):
            domain = "学习"

    return domain, subject, kind

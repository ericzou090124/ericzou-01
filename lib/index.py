"""SQLite FTS5 全文索引：元数据 + 已下载正文。

未下载条目也进索引（只有 title / meta），因此 AI 能基于授权可见的元数据回答，
但永远不会把「文件名」误当作「文件内容」。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import config

CJK = re.compile(r"[\u4e00-\u9fff]+")
LATIN = re.compile(r"[A-Za-z0-9_.+#-]{2,}")
STOP = re.compile(
    r"(有什么|什么|怎么|怎么样|咋样|咋说|哪些|哪个|哪份|多少|请问|帮我|看看|有没有|"
    r"讲一下|说一下|那块儿|这个|那个|里面|资料|文件|相关|关于|一下|的吗|呢|啊|吧|吗|"
    r"老用错|咋办|咋弄|分别|顺便|同时|以及)", re.I
)


def connect() -> sqlite3.Connection:
    db = config.state("index.db")
    con = sqlite3.connect(str(db))
    cols = ("title, body, meta, item_id UNINDEXED, downloaded UNINDEXED, "
            "note UNINDEXED, asset UNINDEXED")
    try:
        con.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5({cols}, tokenize='trigram')")
    except sqlite3.OperationalError:
        con.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5({cols})")
    return con


def query_terms(q: str, max_terms: int = 24) -> list[str]:
    cleaned = STOP.sub(" ", q or "")
    terms = []
    for seg in CJK.findall(cleaned):
        if len(seg) >= 3:
            terms.extend(seg[i:i + 3] for i in range(len(seg) - 2))
        elif len(seg) >= 2:
            terms.append(seg)
    terms += [w.lower() for w in LATIN.findall(q or "")]
    if not terms:
        for seg in CJK.findall(q or ""):
            terms.extend(seg[i:i + 3] for i in range(max(1, len(seg) - 2)))
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:max_terms]


def _match_expr(terms: list[str]) -> str:
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms if len(t) >= 2)


def body_path(item_id: str) -> Path:
    p = config.state("bodies") / f"{item_id}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def rebuild(cat: dict) -> int:
    con = connect()
    try:
        con.execute("DELETE FROM fts")
        n = 0
        for x in cat.get("items", []):
            bp = body_path(x["id"])
            body = ""
            if bp.is_file():
                try:
                    body = bp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            meta = " ".join(str(x.get(k, "")) for k in
                            ("name", "path", "folder", "group", "source", "domain", "subject", "kind", "summary"))
            con.execute(
                "INSERT INTO fts(title, body, meta, item_id, downloaded, note, asset) VALUES (?,?,?,?,?,?,?)",
                (x.get("name", ""), body[:60000], meta, x["id"], int(bool(x.get("downloaded"))),
                 x.get("note", ""), x.get("asset", "")),
            )
            n += 1
        con.commit()
        return n
    finally:
        con.close()


def search(q: str, limit: int = 20) -> list[dict]:
    terms = query_terms(q)
    expr = _match_expr(terms)
    con = connect()
    try:
        rows = []
        if expr:
            try:
                rows = con.execute(
                    "SELECT item_id, title, body, meta, downloaded, note, asset, bm25(fts, 8.0, 1.0, 4.0) AS s "
                    "FROM fts WHERE fts MATCH ? ORDER BY s LIMIT ?", (expr, limit * 3)
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if not rows:  # 短词 / 口语补充召回
            keys = [t for t in terms if len(t) >= 2][:8]
            if keys:
                where = " OR ".join("(title LIKE ? OR body LIKE ? OR meta LIKE ?)" for _ in keys)
                args = []
                for k in keys:
                    args += [f"%{k}%"] * 3
                rows = con.execute(
                    "SELECT item_id, title, body, meta, downloaded, note, asset, 0.0 "
                    f"FROM fts WHERE {where} LIMIT ?", (*args, limit * 3)
                ).fetchall()
        cols = ("item_id", "title", "body", "meta", "downloaded", "note", "asset", "score")
        return [dict(zip(cols, r)) for r in rows]
    finally:
        con.close()


def count() -> int:
    con = connect()
    try:
        return con.execute("SELECT count(*) FROM fts").fetchone()[0]
    finally:
        con.close()

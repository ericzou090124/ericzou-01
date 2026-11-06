"""SQLite FTS5 全文索引：元数据 + 已下载正文。

未下载条目也进索引（只有 title / meta），因此 AI 能基于授权可见的元数据回答，
但永远不会把「文件名」误当作「文件内容」。
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from pathlib import Path

from . import config

CJK = re.compile(r"[\u4e00-\u9fff]+")
LATIN = re.compile(r"[A-Za-z0-9_.+#-]{2,}")
STOP = re.compile(
    r"(有什么|什么|怎么|怎么样|咋样|咋说|哪些|哪个|哪份|多少|请问|帮我|看看|有没有|"
    r"讲一下|说一下|那块儿|这个|那个|里面|资料|文件|相关|关于|一下|的吗|呢|啊|吧|吗|"
    r"老用错|咋办|咋弄|分别|顺便|同时|以及)", re.I
)

# 线程级只读连接缓存：避免每次检索都新建/关闭 SQLite 连接（FTS 只读连接可按线程安全复用）。
# 写操作（rebuild）使用 _new_connection() 独立连接并在末尾关闭，不污染读缓存。
_CONN_LOCAL = threading.local()
_COUNT_CACHE = {"value": None}

_COLS = ("title, body, meta, item_id UNINDEXED, downloaded UNINDEXED, "
         "note UNINDEXED, asset UNINDEXED")


def _new_connection() -> sqlite3.Connection:
    db = config.state("index.db")
    con = sqlite3.connect(str(db))
    try:
        con.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5({_COLS}, tokenize='trigram')")
    except sqlite3.OperationalError:
        con.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5({_COLS})")
    con.execute("CREATE TABLE IF NOT EXISTS idx_meta(item_id TEXT PRIMARY KEY, csig TEXT, bstat TEXT)")
    # 旧单列 schema 兼容：若实际只有 sig 列，重建为新结构（rebuild/sync 都依赖 csig/bstat）
    try:
        con.execute("SELECT csig FROM idx_meta LIMIT 1")
    except sqlite3.OperationalError:
        con.execute("DROP TABLE IF EXISTS idx_meta")
        con.execute("CREATE TABLE idx_meta(item_id TEXT PRIMARY KEY, csig TEXT, bstat TEXT)")
    return con


def _meta_str(x: dict) -> str:
    return " ".join(str(x.get(k, "")) for k in
                    ("name", "path", "folder", "group", "source", "domain", "subject", "kind", "summary"))


def _body_clip(x: dict) -> str:
    bp = body_path(x["id"])
    if bp.is_file():
        try:
            return bp.read_text(encoding="utf-8", errors="replace")[:60000]
        except OSError:
            pass
    return ""


def _bstat(x: dict) -> str:
    """正文文件 stat（size:mtime_ns）；文件不存在则 0:0。不读正文内容。"""
    bp = body_path(x["id"])
    try:
        st = bp.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return "0:0"


def _cat_sig(x: dict) -> str:
    """仅元数据（不含正文内容）的廉价指纹：用于快速判断是否「元数据层面未变」。"""
    raw = f"{x.get('name', '')}|{_meta_str(x)}|{int(bool(x.get('downloaded')))}|{x.get('note', '')}|{x.get('asset', '')}"
    return hashlib.md5(raw.encode("utf-8", "replace")).hexdigest()


def _insert(con: sqlite3.Connection, x: dict) -> None:
    con.execute(
        "INSERT INTO fts(title, body, meta, item_id, downloaded, note, asset) VALUES (?,?,?,?,?,?,?)",
        (x.get("name", ""), _body_clip(x), _meta_str(x), x["id"], int(bool(x.get("downloaded"))),
         x.get("note", ""), x.get("asset", "")),
    )
    con.execute("INSERT OR REPLACE INTO idx_meta(item_id, csig, bstat) VALUES (?, ?, ?)",
                (x["id"], _cat_sig(x), _bstat(x)))


def connect() -> sqlite3.Connection:
    con = getattr(_CONN_LOCAL, "con", None)
    if con is None:
        con = _new_connection()
        _CONN_LOCAL.con = con
    return con


# 可选中文分词（jieba）：显著提升检索词精度（"高等代数考试内容" → 高等代数/考试/内容，
# 而非滑动 3-gram 的噪声）。未安装时回退到 trigram 逻辑，核心功能不受影响。
_JIEBA = None


def _jieba():
    global _JIEBA
    if _JIEBA is None:
        if os.environ.get("RM_NO_JIEBA"):
            _JIEBA = False
        else:
            try:
                import jieba
                try:
                    jieba.setLogLevel(20)
                except Exception:
                    pass
                _JIEBA = jieba
            except Exception:
                _JIEBA = False
    return _JIEBA


def query_terms(q: str, max_terms: int = 24) -> list[str]:
    cleaned = STOP.sub(" ", q or "")
    if _jieba():
        # 分词模式：用 jieba 切出有意义的词，过滤停用词与单字，再补 Latin 词
        toks = _jieba().lcut(cleaned)
        terms = [t for t in toks if t and len(t) >= 2 and not STOP.fullmatch(t)]
        terms += [w.lower() for w in LATIN.findall(q or "")]
    else:
        # 回退模式：滑动 3-gram（保证 FTS5 trigram 能命中）
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
    """全量重建：清空 fts 与 idx_meta 后逐条写入。用于「刷新」等需要整体重算的场景。"""
    _COUNT_CACHE["value"] = None
    con = _new_connection()
    try:
        con.execute("DELETE FROM fts")
        con.execute("DELETE FROM idx_meta")
        n = 0
        for x in cat.get("items", []):
            _insert(con, x)
            n += 1
        con.commit()
        _COUNT_CACHE["value"] = n
        return n
    finally:
        con.close()


def sync(cat: dict) -> int:
    """增量同步：仅对新增 / 删除 / 变更的条目做增删改，避免每次捕获落库都全量重建（REVIEW 瓶颈#4）。

    用两部分指纹判断：
    - csig：仅元数据（不含正文内容）的指纹，O(1) 字符串哈希、无需磁盘 I/O；
    - bstat：正文文件 stat（size:mtime_ns）。
    常见场景（捕获落库后元数据与正文都不变）下，绝大多数条目 csig 命中即整条跳过——
    既不 stat 也不读正文，sync 成本从「全量重建」降到「遍历比对 + 仅变更项重算」。
    """
    _COUNT_CACHE["value"] = None
    con = _new_connection()
    try:
        # 旧表结构兼容迁移（早期版本 idx_meta 只有 sig 单列）
        try:
            existing = {r[0]: (r[1], r[2]) for r in
                        con.execute("SELECT item_id, csig, bstat FROM idx_meta").fetchall()}
        except sqlite3.OperationalError:
            con.execute("DROP TABLE IF EXISTS idx_meta")
            con.execute("CREATE TABLE idx_meta(item_id TEXT PRIMARY KEY, csig TEXT, bstat TEXT)")
            existing = {}
        desired = {x["id"]: _cat_sig(x) for x in cat.get("items", [])}
        # 删除：存在于索引但已不在目录中的条目
        for iid in (i for i in existing if i not in desired):
            con.execute("DELETE FROM fts WHERE item_id=?", (iid,))
            con.execute("DELETE FROM idx_meta WHERE item_id=?", (iid,))
        for x in cat.get("items", []):
            iid = x["id"]
            csig = desired[iid]
            if iid in existing:
                ec, eb = existing[iid]
                if ec == csig:
                    # 元数据未变：比对正文 stat，相同则整条跳过（不 stat 不读正文）
                    if _bstat(x) == eb:
                        continue
                    con.execute("DELETE FROM fts WHERE item_id=?", (iid,))  # 仅正文变化
                else:
                    con.execute("DELETE FROM fts WHERE item_id=?", (iid,))  # 元数据变化
                _insert(con, x)
            else:
                _insert(con, x)  # 新增
        con.commit()
        _COUNT_CACHE["value"] = len(cat.get("items", []))
        return _COUNT_CACHE["value"]
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
    if _COUNT_CACHE["value"] is not None:
        return _COUNT_CACHE["value"]
    con = connect()
    try:
        v = con.execute("SELECT count(*) FROM fts").fetchone()[0]
    finally:
        pass
    _COUNT_CACHE["value"] = v
    return v


def db_size() -> int:
    p = config.state("index.db")
    return p.stat().st_size if p.is_file() else 0


def optimize() -> dict:
    """SQLite 维护：ANALYZE 更新统计让查询规划更优，VACUUM 回收 sync/rebuild 产生的空闲页。

    可在大量捕获/刷新后调用（如 /api/maintain）。对只读检索无影响，仅优化文件体积与规划。
    """
    _COUNT_CACHE["value"] = None
    before = db_size()
    con = _new_connection()
    try:
        con.execute("ANALYZE")
        con.execute("VACUUM")
        con.commit()
    finally:
        con.close()
    after = db_size()
    return {"ok": True, "before_bytes": before, "after_bytes": after,
            "saved_bytes": max(0, before - after)}

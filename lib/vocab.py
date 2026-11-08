"""语料自适应检索词典 —— AI 搜索的泛化底座。

v3.5.0：旧版只靠 jieba 通用词典 + 一份手工写的「四六级」别名词表。
结果就是：四六级又快又准，换个学科（罗尔/柯西/马原/有限元）立刻召回稀少甚至误判「没有」。
本模块**不硬编码任何主题词**，而是直接从当前目录的真实文件名/路径/分类里学词：

1. df 词典：所有 CJK 2~8 字连续子串 + Latin token，按文档频次筛选；
2. 最长匹配切词：把用户口语问题切成「这个库里真实存在的词」，专业术语不再被切碎；
3. 共现扩展：同一份资料里一起出现的词自动互为关联词（「四六级」↔「CET6」是学出来的，
   不是写死的；换任何一个群的术语都同样成立）；
4. 缩写/跳字扩展：「高数」→「高等数学」、「线代」→「线性代数」这类简称自动对齐；
5. 错字近似：共享字符 bigram 的近似词做软召回。

目录变化时按签名自动重建；纯标准库，无第三方依赖。
"""
from __future__ import annotations

import re
from collections import Counter

from . import catalog

CJK = re.compile(r"[\u4e00-\u9fff]+")
LATIN = re.compile(r"[A-Za-z0-9_.+#-]{2,}")
# 只用于「词首/词尾」的虚字过滤：词中间出现这些字是合法的（有机化学、有界…）
BAD_EDGE = set("的了吗呢吧啊哦把被和与或是有在为我你他这那哪个什么多少请问帮我看看相关关于一下及其之乎者也很更最就都也还")
STOP_WORDS = {
    "资料", "文件", "内容", "相关", "关于", "一下", "这个", "那个", "哪些", "哪个", "多少",
    "有没有", "请问", "帮我", "看看", "给我", "我想", "需要", "推荐", "找一套", "找一份",
    "是什么", "怎么办", "怎么样", "总结", "其它", "其他", "可以", "哪些", "所有", "全部",
}
MAX_WORDS = 60000
_CACHE: dict = {"sig": None, "vocab": None}


def _tokens(text: str) -> set[str]:
    """一份资料的候选子串集合（df 按文档计数，不按出现次数）。"""
    out: set[str] = set()
    for seg in CJK.findall(text or ""):
        n = len(seg)
        for size in range(2, min(8, n) + 1):
            for i in range(n - size + 1):
                w = seg[i:i + size]
                if w[0] in BAD_EDGE or w[-1] in BAD_EDGE or w in STOP_WORDS:
                    continue
                out.add(w)
    for w in LATIN.findall(text or ""):
        w = w.lower().strip("._-+#")
        if len(w) >= 2:
            out.add(w)
    return out


class Vocab:
    def __init__(self, xs: list[dict]):
        df: Counter = Counter()
        docs: list[set[str]] = []
        for x in xs:
            text = " ".join(str(x.get(k, "") or "") for k in
                            ("name", "path", "folder", "subject", "kind", "domain", "group"))
            tags = x.get("tags") or []
            if isinstance(tags, (list, tuple)):
                text += " " + " ".join(str(t) for t in tags)
            ws = _tokens(text)
            docs.append(ws)
            df.update(ws)
        n = max(1, len(xs))
        self.n = n
        # 保留：出现 >=2 份资料的词，或长度 >=4 的专业长词（哪怕只出现 1 次）；
        # 丢弃覆盖近一半目录的超泛词（它们对区分度没有贡献）。
        kept = [(w, c) for w, c in df.items()
                if (c >= 2 or len(w) >= 4) and c <= n * 0.45 and w not in STOP_WORDS]
        kept.sort(key=lambda t: (-(len(t[0]) * min(t[1], 20)), t[0]))
        kept = kept[:MAX_WORDS]
        self.df: dict[str, int] = dict(kept)
        self.words: set[str] = set(self.df)
        # 全字段覆盖度：比 df 更严格（df 只看文件名/分类的子串建立时的集合），
        # 这里按「任意检索词在整条资料里是否出现」实测，能把 domain/kind/扩展名
        # 这类「df=0 但几乎每条都命中」的超泛词挡掉。
        self.hay: list[str] = [" ".join(
            [str(x.get(k, "") or "") for k in
             ("name", "path", "folder", "group", "source", "domain", "subject", "kind", "summary")]
            + [str(t) for t in (x.get("tags") or []) if t]
        ).lower() for x in xs]
        self._cov: dict[str, int] = {}
        self.by_len: dict[int, set[str]] = {}
        for w in self.words:
            self.by_len.setdefault(len(w), set()).add(w)
        # 共现：用「最长匹配」把每份资料切成词，再两两累加；同时把单值分类字段作虚拟词，
        # 让「同科目但文件名用词不同」的资料也能互相扩展（四六级 ↔ CET6 即由此学出）。
        self.co: dict[str, Counter] = {}
        for x, _ws in zip(xs, docs):
            text = str(x.get("name", "") or "") + " " + str(x.get("path", "") or "")
            ws = set(self.cut(text))
            for k in ("subject", "kind", "domain"):
                v = str(x.get(k, "") or "").strip()
                if v and v != "综合":
                    ws.add(v)
            ws = {w for w in ws if w not in STOP_WORDS and len(w) >= 2}
            for w in list(ws)[:24]:
                c = self.co.setdefault(w, Counter())
                for other in ws:
                    if other != w:
                        c[other] += 1
        # bigram 倒排，用于错字近似（只索引关联不多的 bigram，避免超泛词拖慢）
        self.bg: dict[str, set[str]] = {}
        for w in self.words:
            if len(w) < 2 or len(w) > 8:
                continue
            for i in range(len(w) - 1):
                b = w[i:i + 2]
                bucket = self.bg.setdefault(b, set())
                if len(bucket) < 240:
                    bucket.add(w)

    def coverage(self, term: str) -> int:
        """该词实际命中多少份资料（含分类字段、路径、扩展名）。带缓存。"""
        t = str(term or "").lower()
        if t not in self._cov:
            self._cov[t] = sum(1 for h in self.hay if t in h) if len(t) >= 2 else 0
        return self._cov[t]

    def informative(self, term: str, ratio: float = 0.18) -> bool:
        """是否有区分度：命中面不超过全库的 18%，且至少真的命中过。"""
        c = self.coverage(term)
        return 0 < c <= max(30, self.n * ratio)

    def cut(self, q: str) -> list[str]:
        """把问题按「本库真实存在的词」最长优先切开，返回用户实义词。"""
        out: list[str] = []
        seen: set[str] = set()

        def add(w: str) -> None:
            if len(w) >= 2 and w not in STOP_WORDS and w not in seen:
                seen.add(w)
                out.append(w)

        for seg in CJK.findall(q or ""):
            i, n = 0, len(seg)
            while i < n:
                hit = ""
                for size in range(min(8, n - i), 1, -1):
                    cand = seg[i:i + size]
                    if cand in self.words:
                        hit = cand
                        break
                if hit:
                    add(hit)
                    i += len(hit)
                else:
                    i += 1
        for w in LATIN.findall(q or ""):
            add(w.lower().strip("._-+#"))
        return out

    def related(self, term: str, k: int = 4, min_co: int = 2) -> list[str]:
        """共现关联词：同一份资料里经常一起出现的词，天然构成「同义/别名」。"""
        c = self.co.get(term)
        if not c:
            return []
        out = []
        for w, n in c.most_common(60):
            if n < min_co or w == term or w in STOP_WORDS or len(w) < 2:
                continue
            if self.df.get(w, 0) > self.n * 0.30 and n < 4:
                continue  # 泛词只有在强共现时才用
            out.append(w)
            if len(out) >= k:
                break
        return out

    def abbrev(self, term: str, k: int = 4) -> list[str]:
        """简称/跳字：'高数' → '高等数学'，'线代' → '线性代数'。"""
        if not CJK.fullmatch(term or "") or len(term) < 2 or len(term) > 3:
            return []
        out = []
        for w, c in self.df.items():
            if not CJK.fullmatch(w) or len(w) <= len(term) or len(w) > 9:
                continue
            pos, ok = -1, True
            for ch in term:
                pos = w.find(ch, pos + 1)
                if pos < 0:
                    ok = False
                    break
            if ok:
                out.append((w, c))
        out.sort(key=lambda t: (len(t[0]), -t[1]))
        return [w for w, _ in out[:k]]

    def similar(self, term: str, k: int = 3) -> list[str]:
        """共享 bigram 的近似词（错字、异体写法）；只用于软加分。"""
        if len(term) < 2:
            return []
        grams = {term[i:i + 2] for i in range(len(term) - 1)}
        if not grams:
            return []
        score: Counter = Counter()
        for g in grams:
            for w in self.bg.get(g, ()):
                if w != term:
                    score[w] += 1
        need = max(1, int(len(grams) * 0.6))
        return [w for w, n in score.most_common(k * 3) if n >= need][:k]

    def expand(self, q: str) -> tuple[list[str], list[str]]:
        """返回 (核心用户词, 自动扩展词)。全部来自当前语料，无需任何主题词表。"""
        core = self.cut(q)
        extra: list[str] = []
        for t in core[:12]:
            extra += self.related(t, 3)
            extra += self.abbrev(t, 3)
        seen, uniq = set(core), []
        for w in extra:
            if w not in seen and len(w) >= 2:
                seen.add(w)
                uniq.append(w)
        return core, uniq


def signature(xs: list[dict]) -> tuple:
    """目录指纹：条目数 + 前/后 id + 已下载数，变化时自动重建词典。"""
    ids = [str(x.get("id", "")) for x in xs]
    return (len(xs), ids[0] if ids else "", ids[-1] if ids else "",
            sum(1 for x in xs if x.get("downloaded")))


def get(cat: dict | None = None) -> Vocab:
    cat = cat or catalog.load()
    xs = catalog.items(cat)
    sig = signature(xs)
    if _CACHE["sig"] != sig or _CACHE["vocab"] is None:
        _CACHE["vocab"] = Vocab(xs)
        _CACHE["sig"] = sig
    return _CACHE["vocab"]


def invalidate() -> None:
    _CACHE["sig"] = None
    _CACHE["vocab"] = None

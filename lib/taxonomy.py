"""受控词表 + 内容驱动的泛化分类层（v3.1.0）。

借鉴 GitHub 上已验证的成熟项目的**设计思想**，但不引入它们的运行时依赖：

- [guiwei](https://github.com/xntj-ai/guiwei)（MIT）：不预设固定目录树、按「模态 + 文档体裁」
  归类、``vocab`` 别名归一表防止标签裂变、dry-run 默认 + 全程可撤销、敏感件闸门；
- [RAG-In-A-Box](https://github.com/DevNexsler/RAG-In-A-Box)：Taxonomy 受控词表 +
  语义匹配 + 可 CRUD 管理，让 AI 检索对齐同一套规范标签；
- [FolderFox](https://github.com/ChenAI-TGF/FolderFox)：整理前先看方案、可撤销；
- [WeChatBridge](https://github.com/freestylefly/WeChatBridge)：不读数据库、不注入的
  本地归档通道（本项目已有的「授权本地目录」适配器与之同构）。

**不采用** [im-mcp](https://github.com/stkoecn/im-mcp)：它从微信进程内存提取密钥并解密
SQLite 聊天库，与本仓库「绝不读取加密聊天数据库、不解密、不注入」的隐私边界冲突。

关键约束（与用户要求一致）：**分类是内容/体裁驱动的，不硬编码「学生用 A 目录 / 店主用 B 目录」**。
本模块只有一套中性的受控词表（合同 / 财务 / 会议 / 方案 / 人事 / 客户 / 产品 / 法务…），
任何领域的文件都映射到同一套规范体裁；主题词从文件名、群内文件夹路径、已下载正文摘要
**动态提取**，不预设主题表。场景识别只做统计展示，绝不决定目录。

零第三方硬依赖：全部规则用标准库；jieba / LLM 均为可选增强，缺失或失败静默回退。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from . import config

# ---------------------------------------------------------------- 中性受控词表
# 规范体裁（genre）不绑定任何行业；aliases 是同义/相关词，用于归一与召回。
# 同一套词表同时服务「学生课程群」和「工作资料群」，不做任何场景分支。
DEFAULT_GENRES: list[dict] = [
    {"name": "合同与协议", "aliases": ["合同", "协议", "合约", "补充协议", "框架协议", "签约",
                                "协议书", "意向书", "订单合同", "采购合同", "服务合同",
                                "租赁合同", "contract", "agreement"]},
    {"name": "财务与票据", "aliases": ["发票", "报销", "报销单", "收据", "账单", "对账单",
                                "结算", "付款", "回款", "预算", "决算", "成本", "费用",
                                "税", "报税", "纳税", "工资表", "财务报表", "流水",
                                "凭证", "记账", "差旅费", "invoice"]},
    {"name": "采购与供应", "aliases": ["进货单", "进货", "采购单", "采购", "供应商", "报价单",
                                "询价", "招标", "投标", "标书", "入库单", "出库单",
                                "库存", "物流单", "到货", "比价", "订货"]},
    {"name": "会议与纪要", "aliases": ["会议纪要", "周会", "例会", "纪要", "会议记录", "会议材料",
                                "议程", "晨会", "评审会", "复盘会", "会议", "minutes"]},
    {"name": "方案与规划", "aliases": ["方案", "规划", "计划书", "策划", "提案", "建设方案",
                                "实施方案", "解决方案", "技术方案", "路线图", "roadmap",
                                "proposal", "策划案"]},
    {"name": "报告与总结", "aliases": ["报告", "总结", "复盘", "周报", "月报", "季报", "年报",
                                "述职", "分析报告", "调研报告", "汇报", "report"]},
    {"name": "通知与公告", "aliases": ["通知", "公告", "公示", "通报", "放假", "安排", "日程",
                                "提醒", "函", "通告"]},
    {"name": "人事与行政", "aliases": ["员工手册", "人事", "招聘", "入职", "离职", "考勤", "绩效",
                                "考核表", "组织架构", "任命", "培训计划", "规章制度",
                                "请假", "简历", "劳动合同", "社保", "公积金", "员工名单"]},
    {"name": "客户与销售", "aliases": ["客户", "销售", "商机", "线索", "回访", "渠道", "签单",
                                "业绩", "客户名单", "crm", "订单", "销售报表"]},
    {"name": "产品与需求", "aliases": ["需求文档", "需求", "prd", "产品说明", "原型", "用户故事",
                                "功能清单", "竞品", "产品规格", "设计稿", "产品规划"]},
    {"name": "法务与合规", "aliases": ["法务", "合规", "保密协议", "nda", "授权书", "营业执照",
                                "资质", "条款", "法律风险", "知识产权", "商标", "审计",
                                "诉讼", "律师函"]},
    {"name": "培训与资料", "aliases": ["培训", "课件", "教材", "讲义", "教程", "学习笔记",
                                "手册", "指南", "入门", "课程", "授课", "参考资料"]},
    {"name": "数据与报表", "aliases": ["数据表", "报表", "统计表", "数据", "看板", "dashboard",
                                "指标", "台账", "明细表", "汇总表", "数据导出"]},
    {"name": "课程与教学", "aliases": ["课件", "课本", "教案", "章节", "知识点", "上机",
                                "课后题", "讲义", "授课", "教学大纲", "课程表"]},
    {"name": "试题与考核", "aliases": ["真题", "试卷", "期末", "期中", "试题", "考题", "模拟题",
                                "答案", "解析", "习题", "作业", "考试", "a卷", "b卷"]},
    {"name": "科研与文献", "aliases": ["论文", "文献", "综述", "开题", "实验报告", "数据集",
                                "参考文献", "专利", "科研"]},
    {"name": "项目与任务", "aliases": ["项目", "任务", "里程碑", "排期", "进度", "todo", "看板",
                                "迭代", "sprint", "立项", "工单", "验收单", "交付"]},
    {"name": "素材与媒体", "aliases": ["图片", "截图", "海报", "logo", "视频", "音频", "素材",
                                "配图", "照片", "banner"]},
    {"name": "代码与工程", "aliases": ["源码", "代码", "脚本", "工程", "接口文档", "api", "sdk",
                                "部署", "配置", "readme", "编译", "代码仓库"]},
    {"name": "生活与事务", "aliases": ["宿舍", "水电", "缴费", "食堂", "医保", "户籍", "社团",
                                "迎新", "报到", "奖助", "生活"]},
    # 长尾兜底（guiwei 的「归入文档兜底」）：没有任何体裁词时不做行业猜测，
    # 细粒度交给动态主题（课程名 / 项目名 / 客户名）与模态。
    {"name": "参考资料", "aliases": ["参考资料", "参考材料", "资料汇编", "题库", "提纲",
                                "lecture", "chapter", "readme"]},
]
FALLBACK_GENRE = "参考资料"

# 模态（guiwei 的「顶层按模态分桶」思想，只用扩展名判断，不读文件内容）
MODALITY_BY_EXT = {
    "文档": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".wps"},
    "表格": {".xlsx", ".xls", ".csv", ".tsv"},
    "演示": {".pptx", ".ppt", ".key"},
    "图片": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"},
    "音视频": {".mp3", ".mp4", ".wav", ".m4a", ".avi", ".mkv", ".mov"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "代码": {".py", ".ipynb", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".json", ".yaml", ".yml"},
}

# 主题词提取用的通用噪音（不是分类词表，只用于剔除无意义片段）
_NOISE = {
    "文件", "资料", "文档", "附件", "最终", "最终版", "定稿", "草稿", "副本", "新建", "备份",
    "版本", "修改", "更新", "打印", "扫描件", "复印件", "合集", "汇总", "全部", "其他", "综合",
    "第一", "第二", "第三", "第四", "第五", "上册", "下册", "完整版", "高清", "无水印",
    "请查收", "已确认", "待确认", "内部", "公开", "临时", "正式", "最新", "旧版", "新版",
    "群文件", "聊天记录", "未命名", "未分类", "杂项",
    "copy", "final", "draft", "new", "old", "v1", "v2", "v3", "test", "temp", "file", "doc",
}
_DATE_PAT = re.compile(r"^(?:20\d{2}[-_./年]?)?(?:\d{1,2}[-_./月日]?){0,3}$")
_SPLIT_RE = re.compile(r"[\\/_\-\s（）()\[\]【】〔〕,，。.、；;：:！!？?~～+&|#＃]+")
_EXT_RE = re.compile(r"\.[a-z0-9]{1,6}$", re.I)
_LEAD_NUM_RE = re.compile(r"^(?:[vV]?\d+(?:\.\d+)*[)）]?[-_ ]?|第[一二三四五六七八九十百\d]+[章节讲]?)")
_LEAD_DATE_RE = re.compile(r"^20\d{2}[-_./年]?\d{0,2}[-_./月日]?[-_ ]?")


def _cfg_taxonomy(cfg: dict) -> dict:
    return ((cfg or {}).get("classification") or {}).get("taxonomy") or {}


def genres(cfg: dict | None = None) -> list[dict]:
    """受控词表：config.json 覆盖优先，合并用户自定义同义词。

    词表是**中性**的，不因场景切换；用户新增/删除同义词写 state/taxonomy_overrides.json，
    不进仓库、随时可撤（guiwei 的 vocab 归一 + FolderFox 的可撤销思路）。
    """
    cfg = cfg or config.CFG
    t = _cfg_taxonomy(cfg)
    base = [dict(g) for g in (t.get("genres") or DEFAULT_GENRES)]
    ov = _load_overrides()
    for g in base:
        extra = ov.get("add", {}).get(g["name"], [])
        removed = {str(r).lower() for r in ov.get("remove", {}).get(g["name"], [])}
        g["aliases"] = [a for a in dict.fromkeys(list(g.get("aliases") or []) + list(extra))
                        if a and str(a).lower() not in removed]
    for name, words in ov.get("add", {}).items():
        if not any(g["name"] == name for g in base):
            base.append({"name": name, "aliases": list(words)})
    return base


def modality(row: dict) -> str:
    ext = str(row.get("ext") or "").lower()
    if not ext:
        m = _EXT_RE.search(str(row.get("name") or "").lower())
        ext = m.group(0) if m else ""
    for label, exts in MODALITY_BY_EXT.items():
        if ext in exts:
            return label
    return "其他"


# ---------------------------------------------------------------- 动态主题词
def _segments(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT_RE.split(str(text or "")) if p.strip()]


def _clean_topic(seg: str, noise_lc: set[str], sorted_terms: list[tuple[str, str]]) -> str:
    """把一个片段洗成主题词：去扩展名/编号/日期 → 剔噪音 → 剥离体裁词。"""
    s = _EXT_RE.sub("", str(seg or "")).strip()
    s = _LEAD_DATE_RE.sub("", s)
    s = _LEAD_NUM_RE.sub("", s).strip(" -_（）()[]【】,，。.、")
    if not s or _DATE_PAT.match(s) or s.isdigit():
        return ""
    low = s.lower()
    if low in noise_lc or len(low) < 2 or len(low) > 20:
        return ""
    # 剥离命中的体裁词，剩下的才是「主题」（项目名 / 客户名 / 课程名 / 学科名）
    for term_lc, _orig in sorted_terms:
        if term_lc in low:
            low = low.replace(term_lc, "").strip(" -_（）()[]【】,，。.、")
    low = low.strip(" -_（）()[]【】,，。.、")
    # 剥离体裁词后常留下悬空连接词或单字前缀（「考试与复习」→「与复习」、
    # 「2024版员工手册与考勤制度」→「版与制度」）：按连接词切段，保留最长的有意义段。
    if any(c in low for c in "与和及&、"):
        parts = [p.strip(" -_（）()[]【】,，。.、版第") for p in re.split(r"[与和及&、]+", low)]
        parts = [p for p in parts if len(p) >= 2 and p not in noise_lc]
        low = max(parts, key=len) if parts else ""
    low = re.sub(r"[表图稿]$", "", low) if len(low) > 3 else low
    low = low.strip(" -_（）()[]【】,，。.、")
    if not low or low in noise_lc or len(low) < 2 or len(low) > 16 or _DATE_PAT.match(low):
        return ""
    return low


def extract_topics(row: dict, vocab_terms: set[str], limit: int = 4) -> list[str]:
    """从群内文件夹路径 / 文件名 / 已下载摘要动态提取主题，不预设主题表。

    群内目录名（项目名、客户名、课程名）权重最高；文件名片段次之；
    正文摘要只在已下载时参与，绝不读取未下载文件的云端内容。
    """
    noise_lc = {w.lower() for w in _NOISE}
    noise_lc |= {v.lower() for v in vocab_terms}
    sorted_terms = sorted(((str(v).lower(), str(v)) for v in vocab_terms if len(str(v)) >= 2),
                         key=lambda p: -len(p[0]))
    scored: dict[str, int] = {}
    display: dict[str, str] = {}

    def add(seg: str, w: int):
        c = _clean_topic(seg, noise_lc, sorted_terms)
        if not c:
            return
        key = c.lower()
        if key not in scored or scored[key] < w:
            scored[key] = w
            display[key] = c  # 保留原始大小写用于展示（英文/缩写）

    for seg in _segments(row.get("folder", "")):
        add(seg, 5)  # 群文件夹 = 项目 / 客户 / 课程，最可信
    name = str(row.get("name") or "")
    for seg in _segments(_EXT_RE.sub("", name)):
        add(seg, 3)
    for m in re.findall(r"[（(【\[]([^）)】\]]{2,16})[）)】\]]", name):
        add(m, 4)  # 括号里的项目/客户代号
    summary = str(row.get("summary") or "")
    if summary:
        for seg in _segments(summary[:120])[:6]:
            add(seg, 1)
    # 可选 jieba：把长中文串切成词，补足纯中文长文件名
    if not scored:
        try:
            import jieba  # type: ignore
            for w in jieba.lcut(_EXT_RE.sub("", name)):
                if 2 <= len(w) <= 8:
                    add(w, 2)
        except Exception:
            pass
    keys = sorted(scored, key=lambda k: (-scored[k], -len(k), k))
    return [display[k] for k in keys[:limit]]


# ---------------------------------------------------------------- 体裁推断
def infer(row: dict, cfg: dict | None = None) -> dict:
    """内容/体裁驱动的单文件推断，返回规范标签 + 动态主题 + 依据 + 置信度。

    不预设「学生 / 店主」两套目录：所有领域共用同一套中性受控词表。
    """
    cfg = cfg or config.CFG
    t = _cfg_taxonomy(cfg)
    gs = genres(cfg)
    vocab_terms = {str(a) for g in gs for a in g["aliases"] if a}
    hay = " ".join(str(row.get(k) or "") for k in ("folder", "path", "name", "summary")).lower()
    folder_lc = str(row.get("folder") or "").lower()

    scores: dict[str, int] = {}
    hits: dict[str, list[str]] = {}
    for g in gs:
        s, hh = 0, []
        for a in g["aliases"]:
            a_lc = str(a).lower()
            if not a_lc or a_lc not in hay:
                continue
            # 长别名更可信；文件夹命中额外加权（群里常按用途建目录）
            w = 4 if len(a_lc) >= 5 else (3 if len(a_lc) >= 3 else 2)
            if a_lc in folder_lc:
                w += 2
            if a_lc == str(g["name"]).lower():
                w += 3
            s += w
            hh.append(str(a))
        if s:
            scores[g["name"]] = s
            hits[g["name"]] = hh

    # 同分时优先更具体（名字更长）的体裁，避免泛类目抢位
    genre = max(scores, key=lambda k: (scores[k], len(k))) if scores else FALLBACK_GENRE
    all_hits = sorted({h for v in hits.values() for h in v}, key=len, reverse=True)
    max_topics = int(t.get("max_topics", 4))
    topics = extract_topics(row, vocab_terms, max_topics)
    if not topics:
        topics = ([genre] if genre not in ("其他资料", FALLBACK_GENRE)
                  else [str(row.get("folder") or "未命名主题")[:12]])

    total = sum(scores.values()) or 1
    confidence = round(min(0.98, 0.35 + 0.5 * (scores.get(genre, 0) / total)
                           + 0.1 * min(3, len(all_hits)) / 3), 2) if scores else 0.3
    return {
        "genre": genre,
        "topics": topics[:max_topics],
        "modality": modality(row),
        "confidence": confidence,
        "reason": {"matched": all_hits[:8], "genre_scores": dict(sorted(
            scores.items(), key=lambda kv: -kv[1])[:5])},
        "engine": "rules",
    }


def is_sensitive(row: dict, cfg: dict | None = None) -> bool:
    """敏感件闸门：命中隐私词的文件不送 LLM，只按文件名做规则归类（借鉴 guiwei）。"""
    t = _cfg_taxonomy(cfg or config.CFG)
    words = t.get("sensitive_keywords") or ["密码", "密钥", "身份证", "银行卡", "私钥", "口令", "凭据"]
    hay = (str(row.get("name") or "") + " " + str(row.get("folder") or "")).lower()
    return any(str(w).lower() in hay for w in words)


def llm_enrich(row: dict, inferred: dict, cfg: dict | None = None) -> dict:
    """可选 LLM 增强：只在显式开启且模型可用时调用；失败/敏感件静默回退规则层。

    只把文件名、群内路径和**已下载**正文摘要送模型；未下载文件绝无正文可送。
    """
    cfg = cfg or config.CFG
    t = _cfg_taxonomy(cfg)
    if not t.get("llm_assist") or is_sensitive(row, cfg):
        return inferred
    try:
        from . import llm
        allowed = [g["name"] for g in genres(cfg)]
        prompt = (
            "你是文件归档助手。只根据给定信息，从下面的规范体裁列表中选一个最合适的，"
            "并提取不超过 4 个主题词。只返回 JSON，格式：{\"genre\":\"...\",\"topics\":[\"...\"]}。\n"
            "规范体裁：" + "、".join(allowed) + "\n"
            + "文件名：" + str(row.get("name") or "")[:120] + "\n"
            + "群内路径：" + str(row.get("path") or "")[:160] + "\n"
            + "已下载摘要：" + str(row.get("summary") or "")[:300] + "\n"
            + "规则层建议：" + inferred["genre"]
        )
        raw = llm.chat([{"role": "user", "content": prompt}], max_tokens=160, timeout=20)
        m = re.search(r"\{[\s\S]*?\}", raw or "")
        if not m:
            return inferred
        d = json.loads(m.group(0))
        g = str(d.get("genre") or "")
        if g not in allowed:
            return inferred
        tp = [str(x)[:16] for x in (d.get("topics") or []) if x][:4]
        out = dict(inferred)
        out.update(genre=g, topics=list(dict.fromkeys(tp + inferred["topics"]))[:6],
                   engine="llm+rules", confidence=max(inferred["confidence"], 0.8))
        return out
    except Exception:
        return inferred


def preview(rows: list[dict], cfg: dict | None = None) -> dict:
    """FolderFox 式「先看方案再执行」：纯只读预览，绝不写 catalog / 不移动文件。"""
    cfg = cfg or config.CFG
    out = []
    for r in (rows or [])[:12]:
        x = infer(r, cfg)
        out.append({"name": str(r.get("name") or ""), "folder": str(r.get("folder") or ""),
                    "genre": x["genre"], "topics": x["topics"], "modality": x["modality"],
                    "confidence": x["confidence"], "matched": x["reason"]["matched"][:5],
                    "sensitive": is_sensitive(r, cfg), "engine": x["engine"]})
    return {"ok": True, "dry_run": True, "items": out,
            "note": "仅预览推断结果，未写入目录、未移动或改名任何文件；确认后可用「重新归类」应用词表变更。"}


# ---------------------------------------------------------------- 词表管理与语义匹配
def _overrides_path() -> Path:
    return config.state("taxonomy_overrides.json")


def _load_overrides() -> dict:
    try:
        d = json.loads(_overrides_path().read_text(encoding="utf-8"))
        return {"add": d.get("add") or {}, "remove": d.get("remove") or {}}
    except Exception:
        return {"add": {}, "remove": {}}


def save_synonym(genre_name: str, word: str, action: str = "add",
                 cfg: dict | None = None) -> dict:
    """受控词表 CRUD：同义词写 state/（不进仓库），可随时回退。"""
    gs = genres(cfg)
    if not any(g["name"] == genre_name for g in gs):
        return {"ok": False, "error": f"未知体裁：{genre_name}"}
    word = str(word or "").strip()
    if not (1 <= len(word) <= 24):
        return {"ok": False, "error": "同义词长度应为 1–24 个字符"}
    ov = _load_overrides()
    if action == "remove":
        ov["remove"].setdefault(genre_name, [])
        if word not in ov["remove"][genre_name]:
            ov["remove"][genre_name].append(word)
        ov["add"][genre_name] = [w for w in ov["add"].get(genre_name, []) if w != word]
    else:
        ov["add"].setdefault(genre_name, [])
        if word not in ov["add"][genre_name]:
            ov["add"][genre_name].append(word)
        ov["remove"][genre_name] = [w for w in ov["remove"].get(genre_name, []) if w != word]
    config.write_json(_overrides_path(), ov)
    return {"ok": True, "genre": genre_name, "word": word, "action": action,
            "aliases": next(g["aliases"] for g in genres(cfg) if g["name"] == genre_name)}


def match(q: str, cfg: dict | None = None) -> dict:
    """语义匹配的受控词表：把口语查询映射到规范体裁 + 同义词集合（用于召回扩展）。

    不是「第一个命中就停」：按别名长度打分，允许多个体裁同时命中，
    这样「销售合同」「项目周报」这类复合词不会只剩一个标签。
    """
    q = (q or "").strip().lower()
    out: dict = {"query": q, "canonical": [], "terms": [], "genres": []}
    if len(q) < 2:
        return out
    gs = genres(cfg)
    scored = []
    for g in gs:
        s, hh = 0, []
        for a in g["aliases"]:
            a_lc = str(a).lower()
            if not a_lc:
                continue
            if q == a_lc or q == g["name"].lower():
                s += 6 + len(a_lc)
            elif a_lc in q:
                s += 3 + len(a_lc)
            elif q in a_lc or q in g["name"].lower():
                s += 1 + len(q)
            else:
                continue
            hh.append(str(a))
        if s:
            scored.append((s, g["name"], hh))
    if not scored:
        return out
    scored.sort(key=lambda z: (-z[0], -len(z[1])))
    top = scored[0][0]
    for s, name, hh in scored:
        if s < max(3, top * 0.55):
            continue
        g = next(x for x in gs if x["name"] == name)
        out["genres"].append(name)
        out["canonical"].append(name)
        out["terms"].extend([name] + [str(a) for a in g["aliases"]])
    out["terms"] = list(dict.fromkeys(out["terms"]))
    return out


def detect_profile(rows: list[dict], cfg: dict | None = None) -> dict:
    """只做统计展示，不改变任何分类结果（避免硬编码两套目录）。"""
    campus = {"课程与教学", "试题与考核", "科研与文献", "生活与事务"}
    office = {"合同与协议", "财务与票据", "采购与供应", "会议与纪要", "人事与行政",
              "客户与销售", "产品与需求", "法务与合规", "项目与任务"}
    c = {"校园": 0, "职场": 0, "通用": 0}
    for x in rows:
        g = str(x.get("genre") or "")
        if g in campus:
            c["校园"] += 1
        elif g in office:
            c["职场"] += 1
        else:
            c["通用"] += 1
    n = max(1, len(rows))
    label = max(c, key=c.get)
    return {"profile": label if c[label] / n > 0.4 else "通用",
            "distribution": c, "total": len(rows),
            "note": "仅统计展示，分类不使用「学生/职场」预设目录"}


def snapshot(cat_rows: list[dict], cfg: dict | None = None) -> dict:
    """给 /api/taxonomy 的只读快照：词表规模、体裁分布、模态分布、场景统计。"""
    cfg = cfg or config.CFG
    gs = genres(cfg)
    return {
        "ok": True,
        "version": "3.1.0",
        "genre_count": len(gs),
        "alias_count": sum(len(g["aliases"]) for g in gs),
        "genres": [{"name": g["name"], "alias_count": len(g["aliases"])} for g in gs],
        "genre_distribution": dict(Counter(str(x.get("genre") or "其他资料") for x in cat_rows).most_common()),
        "modality_distribution": dict(Counter(str(x.get("modality") or "其他") for x in cat_rows).most_common()),
        "profile": detect_profile(cat_rows, cfg),
        "llm_assist": bool(_cfg_taxonomy(cfg).get("llm_assist")),
        "overrides": _load_overrides(),
        "sources": ["guiwei (MIT)", "RAG-In-A-Box Taxonomy", "FolderFox", "WeChatBridge"],
        "not_adopted": ["im-mcp（需解密微信聊天数据库，与本项目隐私边界冲突）"],
    }

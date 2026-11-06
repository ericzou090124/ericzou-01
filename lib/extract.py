"""零额外依赖正文抽取 + 抽取式摘要。PDF 可选 PyMuPDF，图片不 OCR。"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".ipynb", ".html", ".htm", ".xml", ".yaml", ".yml"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
OOXML_EXT = {".docx", ".pptx", ".xlsx"}


def _xml_text(data: bytes, tags: tuple[str, ...]) -> str:
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(data)
    except Exception:
        return ""
    parts = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in tags and el.text:
            parts.append(el.text)
        elif tag in ("p", "row") and parts:
            parts.append("\n")
    return " ".join(parts) if len(parts) < 5 else "\n".join(
        s for s in " ".join(parts).split("\n") if s.strip()
    )


def _ooxml(path: Path, ext: str) -> str:
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if ext == ".docx":
                targets = [n for n in names if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)]
                tags = ("t",)
            elif ext == ".pptx":
                targets = sorted([n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)])
                tags = ("t",)
            else:
                targets = [n for n in names if n == "xl/sharedStrings.xml"] + sorted(
                    [n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)])
                tags = ("t", "v")
            for n in targets:
                try:
                    t = _xml_text(z.read(n), tags)
                except Exception:
                    continue
                if t.strip():
                    out.append(f"[{n}]\n{t}")
    except (zipfile.BadZipFile, OSError):
        return ""
    return "\n\n".join(out)


def _pdf(path: Path, limit: int) -> str:
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz  # type: ignore
        doc = fitz.open(path)
        chunks, total = [], 0
        for i, page in enumerate(doc):
            t = page.get_text("text")
            if t and t.strip():
                chunks.append(f"--- 第 {i+1} 页 ---\n{t}")
                total += len(t)
            if total >= limit:
                break
        doc.close()
        return "\n".join(chunks)
    except Exception:
        return ""


def extract(path: Path, max_chars: int) -> tuple[str, str]:
    """返回 (正文, 状态)。永不抛异常，失败降级为仅元数据可检索。"""
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXT:
            text = path.read_text(encoding="utf-8", errors="replace")
            if ext == ".ipynb":
                try:
                    nb = json.loads(text)
                    text = "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []))
                except Exception:
                    pass
            status = "全文"
        elif ext in OOXML_EXT:
            text = _ooxml(path, ext)
            status = "全文" if text.strip() else "仅文件名（无可提取文字或扫描件）"
        elif ext == ".pdf":
            text = _pdf(path, max_chars)
            status = "全文" if text.strip() else "仅文件名（扫描件需 OCR）"
        elif ext in IMAGE_EXT:
            text, status = "", "仅文件名（图片未做 OCR）"
        else:
            text, status = "", "未解析正文，仅登记元数据"
    except Exception as e:
        text, status = "", f"抽取失败（{type(e).__name__}），仅元数据可检索"
    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars], status


def summarize(text: str, limit: int = 220) -> str:
    """抽取式摘要：取开头信息密度最高的几句，不臆造内容。"""
    clean = re.sub(r"\[.*?\]|--- 第 \d+ 页 ---", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return ""
    segs = [s.strip() for s in re.split(r"(?<=[。！？；.!?])", clean) if len(s.strip()) >= 12]
    out, total = [], 0
    for s in segs[:6]:
        if total + len(s) > limit:
            break
        out.append(s)
        total += len(s)
        if len(out) >= 3:
            break
    return "".join(out) if out else clean[:limit]

"""同步 GitHub 仓库元信息与全部 Releases（幂等）。

做什么
------
1. 更新仓库 `description` / `homepage` / `topics`（让仓库更容易被搜到、被看懂）。
2. 为每个 git tag 创建或更新一个 GitHub Release；正文取自 `docs/CHANGELOG.md` 对应版本段落，
   并追加安装方式、文档索引与该版本的可用性审计结论。已存在的 Release 只更新正文，**保留附件**。
3. 对历史补丁标签 `vX.Y.Z-p1` 生成专门的修复说明；对有已知缺陷的原 tag 在正文中醒目提示可用的补丁标签。

Token 来源（不落盘、不回显）
---------------------------
优先环境变量 `GITHUB_TOKEN` / `GH_TOKEN`；否则调用 `git credential fill` 从系统凭据管理器获取。

用法
----
    python tools/sync_github_releases.py --dry-run   # 只打印计划，不写远端
    python tools/sync_github_releases.py --apply      # 实际创建/更新
    python tools/sync_github_releases.py --apply --skip-existing  # 只补缺失的
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER, REPO = "ericzou090124", "ericzou-01"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
WEB = f"https://github.com/{OWNER}/{REPO}"

DESCRIPTION = (
    "QQ / 微信群文件 → 本地 Obsidian 知识库：三级自动分类、微信监听采集、"
    "SQLite FTS5 全文检索、AI 防臆造问答。Python 标准库实现，零第三方硬依赖，数据全在本机。"
)
TOPICS = [
    "obsidian", "qq", "wechat", "knowledge-base", "group-files",
    "full-text-search", "sqlite-fts5", "python", "local-first",
    "ai-search", "wechatferry", "napcat", "note-taking",
]
KNOWN_FIX = {f"v1.{n}.0": f"v1.{n}.0-p1" for n in (3, 4, 5, 6)}

FOOTER = """
---

### 安装与使用

```bash
git clone https://github.com/ericzou090124/ericzou-01.git
cd ericzou-01
python server.py            # 浏览器打开 http://127.0.0.1:8787
python tools/smoke_test.py  # 回归自测
```

也可直接双击仓库根目录的 `resource-manager-installer.bat` 自解压安装器。

### 文档

- [项目主页（README）]({web}#readme)
- [新增功能详解：微信监听采集 / 群文件分类]({web}/blob/main/docs/FEATURES.md)
- [全版本可用性审计报告]({web}/blob/main/docs/VERSION_AUDIT.md)
- [更新日志]({web}/blob/main/docs/CHANGELOG.md) · [开发者日志]({web}/blob/main/docs/DEVLOG.md)
- [存档说明与验收清单]({web}/blob/main/docs/RELEASE.md)
""".format(web=WEB)


def token() -> str:
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k].strip()
    r = subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, cwd=ROOT)
    m = re.search(r"^password=(.*)$", r.stdout, re.M)
    if not m:
        raise RuntimeError("无法获取 GitHub 凭据：请设置 GITHUB_TOKEN 或配置 git credential helper")
    return m.group(1).strip()


def request(method: str, url: str, tok: str, payload: dict | None = None,
           accept: str = "application/vnd.github+json"):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + tok, "Accept": accept,
        "Content-Type": "application/json", "User-Agent": "resource-manager-release-sync",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:500]}
    except Exception as e:
        return -1, {"error": f"{type(e).__name__}: {e}"}


def changelog_sections() -> dict[str, str]:
    text = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    out = {}
    for chunk in re.split(r"(?=^## \[v[^\]]+\])", text, flags=re.M):
        m = re.match(r"^## \[(v[^\]]+)\]", chunk)
        if m:
            out[m.group(1)] = chunk.strip()
    return out


def short_subject(section: str, fallback: str) -> str:
    lines = [l.strip() for l in section.splitlines()[1:] if l.strip()]
    for l in lines:
        if l.startswith(("#", "|", "-", ">")):
            continue
        return l[:46].rstrip("。 ·")
    return fallback


def build_body(tag: str, sections: dict[str, str]) -> str:
    if tag.endswith("-p1"):
        base = tag[:-3]
        return (f"# {tag} · 历史版本补丁\n\n"
                f"基于 `{base}` 的**最小修复版本**，只修复 `ai.answer(\"\")` 在变量 `f` 定义前引用 "
                f"`scope=f` 导致的 `NameError`（空查询即崩溃）。该缺陷在主线 **v1.7.0** 已修复。\n\n"
                f"- **原 `{base}` 标签保持不变**，以便完整回溯历史。\n"
                f"- 本补丁标签已通过 `tools/version_audit.py` 的全部检测项。\n"
                f"- 需要回退到该系列版本时，请检出本标签而非原标签。\n\n"
                f"生成方式：`python tools/fix_legacy_tag.py --apply`\n" + FOOTER)
    section = sections.get(tag, "")
    head = ""
    if tag in KNOWN_FIX:
        head = (f"> ⚠️ **已知历史缺陷**：本版本的 `ai.answer(\"\")` 会抛 `NameError`（空查询崩溃）。"
                f"请使用已通过全部检测的补丁标签 [`{KNOWN_FIX[tag]}`]"
                f"({WEB}/releases/tag/{KNOWN_FIX[tag]})；本标签保留原貌仅供历史回溯。\n\n")
    body = (section + "\n\n" if section else f"# {tag}\n\n") + FOOTER
    return head + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    if not a.apply and not a.dry_run:
        ap.print_help()
        return 0

    try:
        tok = token()
    except Exception as e:
        print("ERROR:", e)
        return 1

    sections = changelog_sections()
    tags = subprocess.run(["git", "tag", "--list", "--sort=v:refname"],
                         cwd=ROOT, capture_output=True, text=True).stdout.split()
    st, existing = request("GET", API + "/releases?per_page=100", tok)
    if st != 200:
        print("ERROR: 无法读取远端 Releases:", existing)
        return 1
    by_tag = {r["tag_name"]: r for r in existing}
    latest = "v2.8.0" if "v2.8.0" in tags else tags[-1]

    print(f"本地 tags={len(tags)}  远端 releases={len(existing)}  latest={latest}")
    if a.dry_run:
        for t in tags:
            print(("  UPDATE " if t in by_tag else "  CREATE ") + t)
        print("  METADATA description + topics")
        return 0

    # 1) 仓库元信息
    s1, r1 = request("PATCH", API, tok, {
        "description": DESCRIPTION, "homepage": WEB + "#readme", "has_issues": True})
    print(f"[metadata] description/homepage -> {s1}" + ("" if s1 == 200 else f" {r1}"))
    req = urllib.request.Request(API + "/topics", method="PUT",
                                 data=json.dumps({"names": TOPICS}).encode(), headers={
                                     "Authorization": "Bearer " + tok,
                                     "Accept": "application/vnd.github+json",
                                     "Content-Type": "application/json",
                                     "User-Agent": "resource-manager-release-sync"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            print(f"[metadata] topics -> {r.status} ({len(TOPICS)} 个)")
    except Exception as e:
        print(f"[metadata] topics 失败: {e}")

    # 2) Releases
    created = updated = failed = 0
    for t in tags:
        body = build_body(t, sections)
        if t in by_tag:
            if a.skip_existing:
                continue
            rel = by_tag[t]
            s, r = request("PATCH", API + "/releases/" + str(rel["id"]), tok, {
                "body": body, "make_latest": "true" if t == latest else "false"})
            if s == 200:
                updated += 1
                print(f"[update] {t}")
            else:
                failed += 1
                print(f"[FAIL-update] {t} -> {s} {r}")
            continue
        sha = subprocess.run(["git", "rev-list", "-n", "1", t], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        payload = {
            "tag_name": t, "target_commitish": sha,
            "name": f"{t} · {short_subject(sections.get(t, ''), '历史补丁' if t.endswith('-p1') else '版本更新')}",
            "body": body, "draft": False, "prerelease": False,
            "make_latest": "true" if t == latest else "false",
        }
        s, r = request("POST", API + "/releases", tok, payload)
        if s == 201:
            created += 1
            print(f"[create] {t}")
        else:
            failed += 1
            print(f"[FAIL-create] {t} -> {s} {r}")

    print(f"\n完成：新建 {created} / 更新 {updated} / 失败 {failed}")
    print(f"Releases 页面： {WEB}/releases")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""同步 GitHub 仓库元信息与全部 Releases（幂等）。

做什么
------
1. 更新仓库 `description` / `homepage` / `topics`（让仓库更容易被搜到、被看懂）。
2. 为每个 git tag 创建或更新一个 GitHub Release；正文取自 `docs/CHANGELOG.md` 对应版本段落，
   并追加**统一下载入口 + 3 步速通 + 完整使用闭环 + 文档索引**。最新版额外附带展开版教程。
   已存在的 Release 只更新正文，**保留附件**。
3. 对历史补丁标签 `vX.Y.Z-p1` 生成专门的修复说明；对有已知缺陷的原 tag 在正文中醒目提示可用的补丁标签。
4. 可选 `--assets-dir dist`：把 `tools/build_release_assets.py` 产出的资产幂等上传到最新版 Release
   （同名资产先删后传），让 Releases 页面本身就能闭环下载 → 安装 → 使用。

Token 来源（不落盘、不回显）
---------------------------
优先环境变量 `GITHUB_TOKEN` / `GH_TOKEN`；否则调用 `git credential fill` 从系统凭据管理器获取。

用法
----
    python tools/build_release_assets.py              # 先生成 dist/ 资产
    python tools/sync_github_releases.py --dry-run   # 只打印计划，不写远端
    python tools/sync_github_releases.py --apply      # 实际创建/更新
    python tools/sync_github_releases.py --apply --assets-dir dist  # 同步正文并上传资产
    python tools/sync_github_releases.py --apply --skip-existing     # 只补缺失的
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
    "QQ 群文件 → 本地 Obsidian 知识库：全量群聊框选、单值自动分类、"
    "语料自适应 AI 泛化检索、导入后自动打开 Obsidian 并读取全文、库内 AI 助手。"
    "Python 标准库实现，零第三方硬依赖，数据全在本机。"
)
TOPICS = [
    "obsidian", "qq", "knowledge-base", "group-files", "auto-classification",
    "full-text-search", "sqlite-fts5", "python", "local-first",
    "ai-search", "napcat", "note-taking", "obsidian-plugin",
]
KNOWN_FIX = {f"v1.{n}.0": f"v1.{n}.0-p1" for n in (3, 4, 5, 6)}

FOOTER = """
---

### 📥 下载与安装（3 分钟闭环）

| 下载 | 适合谁 | 怎么用 |
| --- | --- | --- |
| ⭐ [resource-manager-installer.bat]({web}/releases/latest/download/resource-manager-installer.bat) | **小白首选** | 下载后**直接双击**，自动解压 + 启动服务 + 打开浏览器，无需先解压 |
| [resource-manager-full.zip]({web}/releases/latest/download/resource-manager-full.zip) | 想拿到**仓库全部内容** / 离线保存 / 改代码 | 先解压整个 zip，再双击里面的 `start.bat` |
| [SHA256SUMS.txt]({web}/releases/latest/download/SHA256SUMS.txt) | 想核对文件完整性 | 见 [教程「校验」一节]({web}/blob/main/docs/INSTALL.md#-校验文件完整性可选) |

> 上面三条直链**永远指向最新版**。要拿本页面这个历史版本，请点本页下方的 `Source code (zip)`，或 `git checkout <tag>`。

**三步速通**：① 装 Python 3.10+（Windows 安装时勾选 `Add python.exe to PATH`）→ ② 双击安装器 → ③ 浏览器打开 `http://127.0.0.1:8787`，点顶栏「群聊」读取并框选本 QQ 的全部群。

**完整使用闭环**：读取并框选群聊 → 顶栏「刷新来源」只读盘点 → 左栏按「学科 / 类型 / 来源」逐级浏览（计数严格一致）→ 勾选并**显式确认下载**，或主页「Obsidian 知识库」一键批量导入（可选已有库 / 新建库）→ **自动打开 Obsidian 并显示本次导入报告**，新文件在原有分类大纲里带 🆕 标记 → 右侧「AI 问答」或库内 AI 助手检索全部资料、读取已导入文件全文。

📖 **零基础图文教程（含常见问题、启动/停止/更新/卸载、macOS / Linux）**：[{web}/blob/main/docs/INSTALL.md]({web}/blob/main/docs/INSTALL.md)

### 文档

- [项目主页（README）]({web}#readme) · [零基础安装教程]({web}/blob/main/docs/INSTALL.md)
- [分类与检索实现细节（历史资料，微信能力已移除）]({web}/blob/main/docs/FEATURES.md) · [架构说明]({web}/blob/main/docs/ARCHITECTURE.md)
- [全版本可用性审计报告]({web}/blob/main/docs/VERSION_AUDIT.md)
- [更新日志]({web}/blob/main/docs/CHANGELOG.md) · [开发者日志]({web}/blob/main/docs/DEVLOG.md)
- [存档说明与验收清单]({web}/blob/main/docs/RELEASE.md)
""".format(web=WEB)

# 仅最新版 Release 追加：把教程的「骨架」直接放进 Release 页面，做到不跳链接也能闭环
LATEST_GUIDE = """
---

## 🧭 最新版使用指南（展开版）

<details>
<summary><b>① 准备工作（一次性）</b></summary>

- 装 [Python 3.10+](https://www.python.org/downloads/)，Windows 安装时**务必勾选 `Add python.exe to PATH`**。
- QQ 群文件需要本机 [NapCat](https://napneko.github.io/)（OneBot 11）扫码登录；没装也能先以「离线快照」浏览本机已缓存的群目录。
- Obsidian 与本地大模型都是**可选增强**：装了 Obsidian 才能体验「导入后自动打开」；模型没开时 AI 自动降级为纯本地检索，仍不编造答案。

</details>

<details>
<summary><b>② 安装并启动</b></summary>

双击 `resource-manager-installer.bat`：自动解压、启动仅监听 `127.0.0.1:8787` 的本地服务并打开浏览器。
若浏览器没自动打开，手动访问 `http://127.0.0.1:8787`。
下载的是 `.zip` 的话，先「全部提取」到空文件夹，再双击 `start.bat`；**不要在压缩包预览里直接双击 bat**。

</details>

<details>
<summary><b>③ 读取并框选我的 QQ 群（v3.5.0）</b></summary>

顶栏「**群聊**」→ 弹窗里点「**读取我的 QQ 群**」→ 用搜索框按群名 / 群号筛选，可「全选 / 全不选」、可手动补群号 → 「**保存选中群**」。
在线时拉取本 QQ 加入的**全部群**（本机实测 28 个），离线时也能从本机目录元数据列出已缓存的真实群号。
保存后自动刷新分类树；左栏「群聊范围」下拉还能随时只看某一个群，AI 问答也跟随该范围。配置只写本机 `config.json`，不上传。

</details>

<details>
<summary><b>④ 从分类到 Obsidian 的完整闭环</b></summary>

1. 顶栏「刷新来源」：只读递归遍历群文件目录，自动按「**学科 / 类型 / 来源**」三个单值维度分类，**不下载任何文件**，任意层级计数之和严格等于文件总数。
2. 左栏展开分类树，中栏看文件列表；顶栏搜索框做全文检索。
3. 右侧「**AI 问答**」直接问任意学科：`lib/vocab.py` 从真实文件名里自动学词（不硬编码学科词表），「罗尔 / 马原 / 线代 / 复变函数」与「四六级」同样召回准确，回答列出「共命中 N 份」和可点击源索引。
4. 主页「**Obsidian 知识库**」卡片 → 「一键批量导入」：可挑**已有库或新建库**，导入需显式确认；完成后**自动用 `obsidian://open` 打开库并定位「00-本次导入.md」报告**。
5. 在原有分类大纲里，本次新增文件带 **🆕** 标记；每篇笔记写入**完整正文**，AI 插件（v1.2.0）自动部署。
6. 库内 AI 可选「AI 问答 · 全部资料 / 全部资料清单 / 仅已导入正文」，点源索引「读取全文」看已导入文件的完整正文。

</details>

<details>
<summary><b>⑤ 日常操作与排障</b></summary>

| 我想… | 怎么做 |
| --- | --- |
| 启动 | 进程序文件夹双击 `start.bat` |
| 停止 | 双击 `tools\\stop.bat` 或关闭 python 服务窗口 |
| 更新 | 重新下载最新安装器双击；`config.json` / `state/` / Obsidian 库都会保留 |
| 卸载 | 停服务 → 删程序目录；不写注册表、不设自启 |
| 验证 | `python tools/smoke_test.py` 看到 `ALL PASS`；`python tools/test_v3.py` 看到全 PASS |

双击没反应 → 九成是 Python 没勾 PATH；提示「离线快照」→ 检查 NapCat 后点「刷新来源」；导入后没自动打开 → 确认已装 Obsidian，或点主页「在 Obsidian 打开」手动拉起；搜不到内容 → 该文件还没下载（未下载只有元数据）。
更多见 [完整教程的常见问题]({web}/blob/main/docs/INSTALL.md#-常见问题)。

</details>

**全部内容都在这里**：源码、文档、安装器、教程、开发者日志都在 `resource-manager-full.zip` 与本仓库；`state/`（你的资料与密钥）永不打包、永不上传。
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
    # 本机代理偶发 RemoteDisconnected / ConnectionReset，重试一次即可恢复；
    # 不重试会导致某个历史 Release 正文更新失败，进而连带跳过资产上传。
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode()[:500]}
        except Exception as e:
            if attempt == 1:
                return -1, {"error": f"{type(e).__name__}: {e}"}
    return -1, {"error": "unreachable"}


def changelog_sections() -> dict[str, str]:
    text = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    out = {}
    for chunk in re.split(r"(?=^## \[v[^\]]+\])", text, flags=re.M):
        m = re.match(r"^## \[(v[^\]]+)\]", chunk)
        if m:
            out[m.group(1)] = chunk.strip()
    return out


def short_subject(section: str, fallback: str) -> str:
    """从 CHANGELOG 段落里取一句干净的 Release 标题。

    v3.5.0 的首行是加粗长句（「**主线：……**」），旧实现会把它拦腰截断，
    在 Releases 列表里显示成半截 Markdown；这里统一去强调符、去「主线：」前缀，
    并优先在自然标点处断句。
    """
    lines = [l.strip() for l in section.splitlines()[1:] if l.strip()]
    for l in lines:
        if l.startswith(("#", "|", "-", ">")):
            continue
        s = re.sub(r"[*_`]", "", l)
        s = re.sub(r"^主线[:：]\s*", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s).strip()
        if not s:
            continue
        for sep in ("——", "。", "；", "，", ","):
            i = s.find(sep)
            if 12 <= i <= 46:
                s = s[:i]
                break
        return s[:46].rstrip("。 ·、：-—")
    return fallback


def build_body(tag: str, sections: dict[str, str], latest: str = "") -> str:
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
    if tag == latest:
        body += LATEST_GUIDE
    return head + body


ASSET_NAMES = ("resource-manager-installer.bat", "resource-manager-full.zip", "SHA256SUMS.txt")


def upload_release_assets(tok: str, latest_tag: str, dist: Path) -> int:
    """把 dist/ 的资产幂等上传到最新版 Release（同名先删后传）。返回失败数。"""
    # 按 tag 精确查询（列表接口可能有缓存延迟，新建的 Release 会短暂查不到）
    st, rel = request("GET", API + "/releases/tags/" + urllib.parse.quote(latest_tag), tok)
    if st != 200:
        print(f"NOTE: 按 tag 查询 {latest_tag} 返回 {st}，回退到列表查询")
        st, rels = request("GET", API + "/releases?per_page=100", tok)
        if st != 200:
            print("ERROR: 读取 Releases 失败:", rels)
            return 1
        rel = next((r for r in rels if r["tag_name"] == latest_tag), None)
    if not rel or not isinstance(rel, dict) or "upload_url" not in rel:
        print(f"ERROR: 找不到最新版 Release {latest_tag}")
        return 1
    upload_url = rel["upload_url"].split("{")[0]
    existing = {a["name"]: a["id"] for a in rel.get("assets", [])}
    failed = 0
    for name in ASSET_NAMES:
        p = dist / name
        if not p.is_file():
            print(f"  [skip] {name} 不存在")
            continue
        if name in existing:
            s, _ = request("DELETE", API + "/releases/assets/" + str(existing[name]), tok)
            if s != 204:
                print(f"  [WARN] 删除同名旧资产失败 {name} -> {s}")
        data = p.read_bytes()
        url = upload_url + "?name=" + urllib.parse.quote(name)
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": "Bearer " + tok,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
            "User-Agent": "resource-manager-release-sync",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read().decode())
            print(f"  [upload] {name:42s} {len(data):>9,d} B -> {r.status} "
                  f"({WEB}/releases/download/{latest_tag}/{name})")
            _ = out
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"  [FAIL-upload] {name} -> {e.code} {e.read().decode()[:300]}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL-upload] {name} -> {type(e).__name__}: {e}")
    return failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--assets-dir", help="把该目录中的资产上传到最新版 Release（幂等）")
    ap.add_argument("--assets-only", action="store_true", help="只上传资产，不改动仓库元信息与 Release 正文")
    ap.add_argument("--asset-tags", help="额外把资产覆盖上传到指定 tag（逗号分隔）。"
                                        "用于修复历史 Release 里已发布的坏附件，例如 --asset-tags v2.9.0")
    a = ap.parse_args()
    extra_tags = [t.strip() for t in (a.asset_tags or "").split(",") if t.strip()]
    if not a.apply and not a.dry_run and not a.assets_only:
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
    stable = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    latest = (max(stable, key=lambda t: tuple(int(x) for x in t[1:].split(".")))
              if stable else tags[-1])

    print(f"本地 tags={len(tags)}  远端 releases={len(existing)}  latest={latest}")
    if a.assets_only and not a.dry_run:
        d = Path(a.assets_dir or "dist")
        if not d.is_absolute():
            d = ROOT / d
        print(f"仅上传资产（不改动正文）→ {[latest] + extra_tags}，目录 {d}")
        failed = 0
        for t in [latest] + extra_tags:
            print(f"\n上传到 {t} …")
            failed += upload_release_assets(tok, t, d)
        return 0 if failed == 0 else 1
    if a.dry_run:
        for t in tags:
            print(("  UPDATE " if t in by_tag else "  CREATE ") + t)
        print("  METADATA description + topics")
        if a.assets_dir:
            d = Path(a.assets_dir)
            if not d.is_absolute():
                d = ROOT / d
            for t in [latest] + extra_tags:
                for n in ASSET_NAMES:
                    print(f"  ASSET {n}: {'存在' if (d / n).is_file() else '缺失'} -> {t}")
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
        body = build_body(t, sections, latest)
        if t in by_tag:
            if a.skip_existing:
                continue
            rel = by_tag[t]
            s, r = request("PATCH", API + "/releases/" + str(rel["id"]), tok, {
                "name": f"{t} · {short_subject(sections.get(t, ''), '历史补丁' if t.endswith('-p1') else '版本更新')}",
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
    if a.assets_dir:
        # 历史 Release 正文偶发失败不应阻断最新版的资产上传；失败数仍计入退出码。
        if failed:
            print(f"\n注意：{failed} 个历史 Release 正文更新失败，继续上传最新版资产")
        d = Path(a.assets_dir)
        if not d.is_absolute():
            d = ROOT / d
        print(f"\n上传发布资产到 {[latest] + extra_tags}（目录 {d}）…")
        for t in [latest] + extra_tags:
            print(f"  → {t}")
            failed += upload_release_assets(tok, t, d)
    print(f"Releases 页面： {WEB}/releases")
    print(f"一键安装器直链： {WEB}/releases/latest/download/resource-manager-installer.bat")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

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

### 📥 下载与安装（3 分钟闭环）

| 下载 | 适合谁 | 怎么用 |
| --- | --- | --- |
| ⭐ [resource-manager-installer.bat]({web}/releases/latest/download/resource-manager-installer.bat) | **小白首选** | 下载后**直接双击**，自动解压 + 启动服务 + 打开浏览器，无需先解压 |
| [resource-manager-full.zip]({web}/releases/latest/download/resource-manager-full.zip) | 想拿到**仓库全部内容** / 离线保存 / 改代码 | 先解压整个 zip，再双击里面的 `start.bat` |
| [SHA256SUMS.txt]({web}/releases/latest/download/SHA256SUMS.txt) | 想核对文件完整性 | 见 [教程「校验」一节]({web}/blob/main/docs/INSTALL.md#-校验文件完整性可选) |

> 上面三条直链**永远指向最新版**。要拿本页面这个历史版本，请点本页下方的 `Source code (zip)`，或 `git checkout <tag>`。

**三步速通**：① 装 Python 3.10+（Windows 安装时勾选 `Add python.exe to PATH`）→ ② 双击安装器 → ③ 浏览器打开 `http://127.0.0.1:8787`，点顶部「首次配置」，按向导装 NapCat、勾选 QQ 群。

**完整使用闭环**：刷新来源 → 三级分类浏览（领域 / 科目 / 类型）→ 勾选并**显式确认下载** → 全文检索 / 问 AI → Obsidian 打开生成的独立知识库 → 「系统诊断」检查运行状态。

📖 **零基础图文教程（含常见问题、启动/停止/更新/卸载、macOS / Linux）**：[{web}/blob/main/docs/INSTALL.md]({web}/blob/main/docs/INSTALL.md)

### 文档

- [项目主页（README）]({web}#readme) · [零基础安装教程]({web}/blob/main/docs/INSTALL.md)
- [新增功能详解：微信监听采集 / 群文件分类]({web}/blob/main/docs/FEATURES.md)
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
- QQ 群文件需要本机 [NapCat](https://napneko.github.io/) 扫码登录；**不用提前装**，首次配置向导会带你做。
- Obsidian、本地大模型、WeChatFerry 都是可选增强，缺了程序照常跑。

</details>

<details>
<summary><b>② 安装并启动</b></summary>

双击 `resource-manager-installer.bat`：自动解压到 `C:\\Users\\你的用户名\\resource-manager`，启动仅监听 `127.0.0.1:8787` 的本地服务并打开浏览器。
若浏览器没自动打开，手动访问 `http://127.0.0.1:8787`。
下载的是 `.zip` 的话，先「全部提取」到空文件夹，再双击 `start.bat`；**不要在压缩包预览里直接双击 bat**。

</details>

<details>
<summary><b>③ 首次配置向导（界面点 3 下）</b></summary>

顶部「首次配置」→「开始配置」：① 装 NapCat 并手机 QQ 扫码 → ② 点「自动列出我的群并勾选」或手填 `群名,群号` → ③ 完成。
配置只写本机 `config.json`，不上传。没有 NapCat 也能进「离线快照」模式先浏览分类。

</details>

<details>
<summary><b>④ 从下载到可问答的完整闭环</b></summary>

1. 顶栏「刷新来源」：只读列群文件，自动三级分类，**不下载任何文件**。
2. 左栏展开分类树，中栏预览元数据 / 摘要。
3. 勾选文件 → 「下载已选」→ 在确认框确认（下载闸门必须显式确认）。
4. 顶栏搜索框回车做全文检索，或点「问 AI」；AI 只依据已下载正文，标注来源，找不到就直说。
5. Obsidian「打开文件夹作为库」选界面显示的库路径（默认 `~/Desktop/资源管理`，**独立新库，不动原有笔记**）。
6. 顶栏「系统诊断」随时看配置 / QQ 在线 / 索引篇数 / 库路径。

</details>

<details>
<summary><b>⑤ 日常操作与排障</b></summary>

| 我想… | 怎么做 |
| --- | --- |
| 启动 | 进程序文件夹双击 `start.bat` |
| 停止 | 双击 `tools\\stop.bat` 或关闭 python 服务窗口 |
| 更新 | 重新下载最新安装器双击；`config.json` / `state/` / Obsidian 库都会保留 |
| 卸载 | 停服务 → 删程序目录；不写注册表、不设自启 |
| 验证 | `python tools/smoke_test.py` 看到 `ALL PASS` |

双击没反应 → 九成是 Python 没勾 PATH；提示「离线快照」→ 点「QQ 登录」扫码；搜不到内容 → 该文件还没下载（未下载只有元数据）。
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
    a = ap.parse_args()
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
        print(f"仅上传资产（不改动正文）→ {latest}，目录 {d}")
        return 0 if upload_release_assets(tok, latest, d) == 0 else 1
    if a.dry_run:
        for t in tags:
            print(("  UPDATE " if t in by_tag else "  CREATE ") + t)
        print("  METADATA description + topics")
        if a.assets_dir:
            d = Path(a.assets_dir)
            if not d.is_absolute():
                d = ROOT / d
            for n in ASSET_NAMES:
                print(f"  ASSET {n}: {'存在' if (d / n).is_file() else '缺失'} -> {latest}")
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
    if a.assets_dir and failed == 0:
        d = Path(a.assets_dir)
        if not d.is_absolute():
            d = ROOT / d
        print(f"\n上传发布资产到 {latest}（目录 {d}）…")
        failed += upload_release_assets(tok, latest, d)
    print(f"Releases 页面： {WEB}/releases")
    print(f"一键安装器直链： {WEB}/releases/latest/download/resource-manager-installer.bat")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""一键发布 GitHub Release 并上传自解压安装器 resource-manager-installer.bat。

前置条件（只需一次）：
  - 本机已用 GitHub 凭证登录过（Git Credential Manager 已缓存 token）。
    若未登录：在终端执行 `git credential fill` 或 `gh auth login` 完成授权。
  - 在「有外网」的普通终端里运行本脚本（不要在 WorkBuddy 沙箱内运行，沙箱无外网）。

用法：
  python tools/publish_release.py
可选参数：
  --tag v1.2.3                 指定要发布的标签（默认取最新 tag）
  --asset 路径/installer.bat    指定安装器（默认按 resource-manager-installer.bat 在仓库外层查找）
  --repo owner/name             覆盖目标仓库（默认取当前 git remote origin）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def run(cmd, capture=True, check=True, input_text=None):
    return subprocess.run(cmd, shell=True, capture_output=capture, text=True,
                          input=input_text, encoding="utf-8", errors="replace",
                          check=check)


def repo_from_remote() -> str:
    r = run("git remote get-url origin", check=False)
    url = (r.stdout or "").strip()
    # https://github.com/owner/name.git  -> owner/name
    if "github.com" in url:
        part = url.split("github.com", 1)[1].strip("/")
        part = part[:-4] if part.endswith(".git") else part
        return part
    raise SystemExit("[错误] 无法从 remote origin 解析 GitHub 仓库，请用 --repo owner/name 指定。")


def latest_tag() -> str:
    r = run("git describe --tags --abbrev=0", check=False)
    t = (r.stdout or "").strip()
    if not t:
        raise SystemExit("[错误] 没有找到任何 tag，请先打 tag（git tag -a vX.Y.Z -m ...）。")
    return t


def find_asset(tag: str, explicit: str | None) -> str:
    if explicit:
        if not os.path.isfile(explicit):
            raise SystemExit(f"[错误] 指定安装器不存在：{explicit}")
        return os.path.abspath(explicit)
    here = os.path.dirname(os.path.abspath(__file__))  # tools/
    candidates = [
        os.path.join(here, "..", "..", "resource-manager-installer.bat"),  # 工作区外层
        os.path.join(here, "..", "resource-manager-installer.bat"),
        os.path.join(here, "resource-manager-installer.bat"),
        os.path.join(here, "..", "..", f"resource-manager-{tag}.zip"),  # 兼容旧 zip
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    raise SystemExit(
        f"[错误] 没找到 resource-manager-installer.bat。请先运行：\n"
        f"  python tools/build_installer.py\n"
        f"它会在仓库外层生成 resource-manager-installer.bat。"
    )


def get_token() -> str:
    """从 Git Credential Manager 取 GitHub token。"""
    out = run(
        'git credential fill',
        input_text="protocol=https\nhost=github.com\n\n",
        check=False,
    )
    for line in (out.stdout or "").splitlines():
        if line.lower().startswith("password="):
            return line.split("=", 1)[1].strip()
    # 兼容 username 即 token（部分配置）
    for line in (out.stdout or "").splitlines():
        if line.lower().startswith("username="):
            u = line.split("=", 1)[1].strip()
            if u.startswith("ghp_") or u.startswith("github_pat_"):
                return u
    raise SystemExit(
        "[错误] 取不到 GitHub 凭证。请先在终端执行 `git push` 触发登录，\n"
        "或安装并运行 `gh auth login` 完成 GitHub 授权，再重试。"
    )


def api(method: str, url: str, token: str, data=None, headers=None, binary=None):
    hdrs = {"Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "resource-manager-publisher"}
    if headers:
        hdrs.update(headers)
    if isinstance(data, (dict, list)):
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif isinstance(data, str):
        body = data.encode("utf-8")
    else:
        body = data
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    return urllib.request.urlopen(req, timeout=60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    ap.add_argument("--asset", default=None)
    ap.add_argument("--repo", default=None)
    args = ap.parse_args()

    tag = args.tag or latest_tag()
    repo = args.repo or repo_from_remote()
    asset_path = find_asset(tag, args.asset)
    print(f"[信息] 仓库={repo}  标签={tag}  附件={asset_path}")

    # 重复发布同一版本时，把本地 tag 同步到最新提交并推送（个人仓库 force-push tag 安全）
    try:
        run(f"git tag -f {tag}")
        run(f"git push -f origin {tag}")
        print(f"[信息] 已将标签 {tag} 更新并推送到最新提交")
    except Exception as e:
        print(f"[警告] 更新标签失败（可忽略，不影响发布）：{e}")

    token = get_token()
    print("[信息] 已取得 GitHub 凭证。")

    # 1) 创建 Release（幂等：若已存在则复用，不报错）
    rel_url = f"https://api.github.com/repos/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": f"资源管理 {tag}",
        "body": (
            f"## {tag}\n\n"
            "面向零配置新手的 QQ 群文件 → Obsidian 知识库闭环。\n\n"
            "### 主要修复\n"
            "- **自解压安装器**：下载 `resource-manager-installer.bat` 后**直接双击即可**，无论你是在压缩包里双击还是先解压，它都会自动解压到用户目录并启动，无需任何手动解压步骤。\n"
            "- 修复 install.bat / start.bat 双击后命令行闪退（input/EOF 兜底 + .bat pause）。\n"
            "- 修复扫码登录后主界面「页面加载失败」：服务改为独立控制台窗口运行，关闭启动器不影响服务。\n"
            "- 登录页跳转前先探活 /api/health，失败给出可点链接而非死页。\n"
            "- 修复 /api/qqlogin/restore 在 NapCat 未运行时卡住 20+ 秒（新增端口探活，未运行立即提示）。\n\n"
            "### 使用\n"
            "下载 `resource-manager-installer.bat` → **双击它** → 自动安装并打开 http://127.0.0.1:8787 按向导扫码登录。"
        ),
        "draft": False,
        "prerelease": False,
    }
    rel = None
    try:
        resp = api("POST", rel_url, token, data=payload)
        rel = json.loads(resp.read().decode("utf-8"))
        print(f"[信息] Release 已创建：{rel.get('html_url')}")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            # 已存在同名 tag 的 Release，尝试取出复用
            try:
                r2 = api("GET", f"{rel_url}/tags/{tag}", token)
                rel = json.loads(r2.read().decode("utf-8"))
                print(f"[信息] 该标签的 Release 已存在，复用：{rel.get('html_url')}")
            except Exception:
                detail = e.read().decode("utf-8", "replace")[:300]
                raise SystemExit(f"[错误] 创建 Release 失败（{e.code}）：{detail}")
        else:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"[错误] 创建 Release 失败（{e.code}）：{detail}")
    if not rel:
        raise SystemExit("[错误] 未能获取 Release 信息，发布终止。")
    upload_url = rel.get("upload_url", "").split("{", 1)[0]
    rel_id = rel.get("id")

    # 若该 Release 已存在附件（重复发布同一版本），先删掉所有旧附件，避免新旧并存
    if rel_id:
        try:
            r = api("GET", f"https://api.github.com/repos/{repo}/releases/{rel_id}/assets", token)
            for a in json.loads(r.read().decode("utf-8")):
                try:
                    api("DELETE", f"https://api.github.com/repos/{repo}/releases/assets/{a['id']}", token)
                    print(f"[信息] 已删除旧附件 {a.get('name')}")
                except Exception as e2:
                    print(f"[警告] 删除旧附件 {a.get('name')} 失败：{e2}")
        except Exception as e:
            print(f"[警告] 列举旧附件失败（可忽略，继续上传）：{e}")

    # 2) 上传附件
    name = os.path.basename(asset_path)
    with open(asset_path, "rb") as f:
        bin_data = f.read()
    up = f"{upload_url}?name={name}"
    ctype = "application/octet-stream" if name.endswith(".bat") else "application/zip"
    try:
        api("POST", up, token, data=bin_data, headers={"Content-Type": ctype})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"[错误] 上传附件失败（{e.code}）：{detail}")
    print(f"[完成] 已上传附件 {name}")
    print(f"[完成] Release 发布成功：{rel.get('html_url')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[异常] {type(e).__name__}: {e}")
        sys.exit(1)

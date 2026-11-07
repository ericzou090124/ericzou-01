"""生成 Release 可下载资产（可复现、闭环自校验）。

产出（全部写入 `dist/`，该目录已 gitignore）：
    resource-manager-installer.bat   一键自解压安装器（稳定文件名，直链永远指向最新版）
    resource-manager-full.zip        仓库全部内容（源码 + 文档 + 安装器 + 教程）
    SHA256SUMS.txt                   上面两个文件的 SHA256

zip 内额外注入两个便于小白的文件：
    START_HERE.txt   解压后第一眼看到的说明（指向 start.bat 与 docs/INSTALL.md）
    VERSION.txt      版本与内容说明

用法：
    python tools/build_release_assets.py                  # 版本自动从 CHANGELOG 取
    python tools/build_release_assets.py --version v2.9.0
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_installer  # noqa: E402  (复用同一套收集规则，避免两份清单漂移)

DIST = ROOT / "dist"
INSTALLER = ROOT / "resource-manager-installer.bat"
INSTALLER_NAME = "resource-manager-installer.bat"
ZIP_NAME = "resource-manager-full.zip"
SUMS_NAME = "SHA256SUMS.txt"

REQUIRED_IN_ZIP = (
    "server.py", "config.json", "README.md", "LICENSE", "start.bat", "install.bat",
    "docs/INSTALL.md", "docs/FEATURES.md", "docs/CHANGELOG.md", "docs/DEVLOG.md",
    "tools/smoke_test.py", "web/index.html", "web/app.js", "lib/index.py",
    "START_HERE.txt", "VERSION.txt", INSTALLER_NAME,
)

START_HERE = """资源管理 · 从这里开始（START HERE）
======================================

你已经拿到了本项目的【完整内容】：全部源码 + 全部文档 + 一键安装器 + 教程。

【现在只做两件事】

  1) 确认这个文件夹里能同时看到：
       server.py / start.bat / install.bat / tools\\ / docs\\
     （如果看不到，说明你是在压缩包预览里打开的，请先右键 zip → 全部提取）

  2) 双击 start.bat
       会自动启动本地服务，并打开浏览器到 http://127.0.0.1:8787
       第一次使用：点页面顶部的「首次配置」，按向导装 NapCat、勾选 QQ 群即可。

【只想一键装好？】
  本压缩包里的 resource-manager-installer.bat 也可以直接双击，
  它会自动把程序解压到 C:\\Users\\你的用户名\\resource-manager 并启动。

【完整图文教程】
  docs\\INSTALL.md（零基础，从下载到 Obsidian 的完整闭环）
  在线版：https://github.com/ericzou090124/ericzou-01/blob/main/docs/INSTALL.md

【要注意】
  - 需要 Python 3.10+，安装时务必勾选 Add python.exe to PATH。
  - 服务只监听 127.0.0.1，资料全部留在本机，不会上传。
  - 停止服务：双击 tools\\stop.bat，或关闭名为 python 的服务窗口。
  - Windows 以外的系统：运行 bash install.sh 或 python3 server.py。

版本：{version}
许可：MIT（见 LICENSE）
"""

VERSION_TXT = """Resource Manager {version}

本压缩包包含仓库全部内容：
  - 程序：server.py / lib/ / web/ / obsidian_plugin/
  - 启动：start.bat / install.bat / install.sh / 一键登录.bat
  - 安装器：resource-manager-installer.bat（自解压，直接双击）
  - 文档：README.md / docs/（INSTALL.md 为零基础完整教程）/ CHANGELOG / DEVLOG
  - 工具：tools/（自测、基准、全版本审计、Release 同步、发布包构建）

不包含：.git/、state/（你的本地资料与密钥）、__pycache__/、dist/
这些目录永远不会被打包，你的数据不会被分发。

在线教程：https://github.com/ericzou090124/ericzou-01/blob/main/docs/INSTALL.md
"""


def detect_version() -> str:
    text = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[(v[\d.]+)\]", text, re.M)
    if not m:
        raise RuntimeError("CHANGELOG.md 中找不到版本标题")
    return m.group(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_zip(path: Path) -> None:
    """构建完立即自校验，避免把坏包传到 Release。"""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        missing = [n for n in REQUIRED_IN_ZIP if n not in names]
        bad = z.testzip()
    if missing or bad:
        raise RuntimeError(f"发布包自检失败：缺失={missing} CRC异常={bad}")
    print(f"  [verify] zip 内容自检通过（{len(names)} 个文件，关键文件齐全，CRC 正常）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="版本号，默认从 CHANGELOG.md 顶部解析")
    a = ap.parse_args()
    version = a.version or detect_version()

    DIST.mkdir(exist_ok=True)
    print(f"构建 Release 资产：{version}")

    # 1) 重新生成根目录安装器（包含本轮新增的教程/文档/License）
    print("[1/4] 重建自解压安装器 …")
    build_installer.main()
    shutil.copyfile(INSTALLER, DIST / INSTALLER_NAME)

    # 2) 组装完整 zip（复用 build_installer 的排除规则，杜绝把 state/ 打进去）
    print("[2/4] 组装完整内容包 …")
    files = build_installer.collect()
    zpath = DIST / ZIP_NAME
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, str(p.relative_to(ROOT)).replace("\\", "/"))
        z.write(INSTALLER, INSTALLER_NAME)
        z.writestr("START_HERE.txt", START_HERE.format(version=version).encode("utf-8"))
        z.writestr("VERSION.txt", VERSION_TXT.format(version=version).encode("utf-8"))
    verify_zip(zpath)

    # 3) 校验和
    print("[3/4] 生成 SHA256SUMS.txt …")
    lines = [f"{sha256(DIST / n)}  {n}" for n in (INSTALLER_NAME, ZIP_NAME)]
    (DIST / SUMS_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 4) 输出清单
    print("[4/4] 产出：")
    for n in (INSTALLER_NAME, ZIP_NAME, SUMS_NAME):
        p = DIST / n
        print(f"  {n:42s} {p.stat().st_size:>9,d} B")
    print(f"\n下一步：python tools/sync_github_releases.py --apply --assets-dir dist")
    return 0


if __name__ == "__main__":
    sys.exit(main())

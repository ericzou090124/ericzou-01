"""生成自解压安装器 resource-manager-installer.bat。

设计要点（v2.9.1 加固，修复小白双击报 '-ExecutionPolicy' 的问题）
------------------------------------------------------------------
历史缺陷（务必不要回退）：
1. 旧版把 800+ 字节的 PowerShell 源码内联在 `powershell -Command "..."` 里，且命令中含中文。
   在 `chcp 65001` 的 cmd 下，多字节字符按 OEM/GBK 解析会让双引号配对错乱、整行被拆断，
   于是 `-ExecutionPolicy` 被当成独立命令执行 → "is not recognized as an internal or external command"。
2. 旧版 PS 代码里的标记是占位符 '__M_P__'+'__M_S__'，main() 从未替换，必然 marker-not-found。
3. 旧版 RM_NO_LAUNCH=1 分支执行完 :done 的 echo 后未终止批处理，会继续把 30 万字节的
   base64 payload 当命令执行，刷出一屏错误并以非 0 退出。

现在的做法：
- PowerShell 脚本以 **UTF-16LE + Base64** 通过 `-EncodedCommand` 传入：
  命令行只有纯 ASCII（base64 字符集），彻底绕开 cmd 的引号 / 管道 / 多字节解析。
- 标记表达式由 Python 注入，构建时自检（verify_installer）确认与标记行一致。
- 解压用 .NET `System.IO.Compression`（而非 Expand-Archive），中文文件名不乱码、可覆盖写入。
- 所有分支都用 `exit /b` 显式终止，绝不落到 payload 行。
- 构建完立即做静态自检：命令行 ASCII、EncodedCommand 可解码、内嵌 zip 关键文件齐全。

环境变量（可选、向后兼容）：
    RM_INSTALL_TARGET  安装目录，默认 %USERPROFILE%\\resource-manager
    RM_NO_LAUNCH       设为 1 则只解压不启动服务（便于自动化测试）
"""
from __future__ import annotations

import base64
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "resource-manager-installer.bat"

# 不纳入安装包的路径片段（相对 ROOT）
EXCLUDE_DIRS = {".git", "state", "venv", "tools/venv", ".venv", "__pycache__",
                ".wbapp", "node_modules", ".idea", ".vscode", "dist", "build"}
EXCLUDE_FILES = {"secrets.json", "resource-manager-installer.bat",
                 ".coverage", "pytest.ini"}
EXCLUDE_SUFFIX = {".pyc", ".tmp", ".log", ".bak", ".swp"}

MARKER_PREFIX = "RMX1_"
MARKER_SUFFIX = "PAYLOAD_BOUNDARY_9F3A"


def collect() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        parts = rel.parts
        if parts and parts[0] in EXCLUDE_DIRS:
            continue
        # 任意层级的 __pycache__ / .venv 等
        if any(seg in EXCLUDE_DIRS for seg in parts):
            continue
        if rel.name in EXCLUDE_FILES:
            continue
        if rel.suffix.lower() in EXCLUDE_SUFFIX:
            continue
        out.append(p)
    return out


def build_zip() -> bytes:
    files = collect()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            z.write(p, rel)
    return buf.getvalue()


# PowerShell 脚本：Unicode 源码，经 -EncodedCommand 传入，完全不经过 cmd 的字符串解析。
# __MARKER_EXPR__ 由 main() 注入成 'RMX1_'+'PAYLOAD_BOUNDARY_9F3A'（拼接形式，避免明文重复）。
PS_SCRIPT_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# RM-Log 在 -EncodedCommand / 重定向宿主下会把 information 流序列化成 CLIXML 刷屏，
# 因此统一走 Console 直接输出，保证 stdout 干净、双击时也不出现 XML。
function RM-Log([string]$msg) { [Console]::Out.WriteLine($msg) }
try {
  $self   = $env:SELF
  $target = $env:TARGET
  if ([string]::IsNullOrEmpty($self) -or [string]::IsNullOrEmpty($target)) {
    RM-Log '[RM][ERROR] SELF/TARGET env missing'; exit 2
  }
  $text   = [System.IO.File]::ReadAllText($self, [System.Text.Encoding]::UTF8)
  $marker = __MARKER_EXPR__
  $i = $text.IndexOf($marker)
  if ($i -lt 0) { RM-Log '[RM][ERROR] payload marker missing (incomplete download?)'; exit 3 }
  # 用 LF 定位，CRLF / LF 行尾都能工作（构建机可能是 Linux）
  $j = $text.IndexOf("`n", $i)
  if ($j -lt 0) { RM-Log '[RM][ERROR] payload line missing'; exit 3 }
  $payload = $text.Substring($j + 1).Trim()
  if ([string]::IsNullOrWhiteSpace($payload)) { RM-Log '[RM][ERROR] payload empty'; exit 3 }
  $bytes  = [System.Convert]::FromBase64String($payload)
  $tmpzip = Join-Path $env:TEMP ('rm_payload_' + [guid]::NewGuid().ToString('N') + '.zip')
  [System.IO.File]::WriteAllBytes($tmpzip, $bytes)
  if (-not (Test-Path $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }

  Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
  $zip = [System.IO.Compression.ZipFile]::OpenRead($tmpzip)
  $n = 0
  try {
    foreach ($e in $zip.Entries) {
      if ([string]::IsNullOrEmpty($e.Name)) { continue }
      $rel  = $e.FullName.Replace('/', '\')
      $dest = Join-Path $target $rel
      $dir  = Split-Path -Parent $dest
      if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
      [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dest, $true)
      $n = $n + 1
    }
  } finally {
    $zip.Dispose()
    Remove-Item $tmpzip -Force -ErrorAction SilentlyContinue
  }
  if ($n -lt 10) { RM-Log '[RM][ERROR] extracted too few files'; exit 4 }
  RM-Log ('[RM] extracted ' + $n + ' files')
  exit 0
} catch {
  RM-Log ('[RM][ERROR] ' + $_.Exception.Message)
  exit 5
}
"""

# 头部：所有「命令行」都是纯 ASCII（中文只出现在 echo 的文本里，且 PS 命令行在其后仍为纯 ASCII）。
# __PS_COMMAND__ 由 main() 替换成 `powershell ... -EncodedCommand <base64>`。
BAT_HEADER = """@echo off
chcp 65001 >nul 2>&1
setlocal
set "SELF=%~f0"
set "TARGET=%RM_INSTALL_TARGET%"
if "%TARGET%"=="" set "TARGET=%USERPROFILE%\\resource-manager"
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
echo [资源管理] 正在解压安装包，请稍候…
__PS_COMMAND__
if errorlevel 1 (
  echo 解压失败，请确认你完整地获取了 resource-manager-installer.bat，或手动解压后双击 install.bat。
  echo 常见原因：下载中断、被安全软件截断、或在网盘/聊天工具里被二次转存。
  pause
  exit /b 1
)
if not exist "%TARGET%\\server.py" (
  echo 解压结果不完整（缺少 server.py），请重新下载安装器。
  pause
  exit /b 1
)
echo [资源管理] 解压完成：%TARGET%
if "%RM_NO_LAUNCH%"=="1" goto :done
where python >nul 2>&1
if errorlevel 1 (
  echo 未检测到 Python。请先安装 Python 3.10+ 并勾选“Add to PATH”，然后进入 %TARGET% 双击 install.bat。
  start "" "%TARGET%"
  pause
  exit /b 1
)
cd /d "%TARGET%"
echo [资源管理] 正在启动本地服务（仅本机 127.0.0.1:8787）…
start "" python server.py
timeout /t 3 >nul
start "" http://127.0.0.1:8787
echo [资源管理] 浏览器已打开 http://127.0.0.1:8787 。若未自动打开，请手动访问。
echo 关闭服务：在弹出的 python 窗口按 Ctrl+C，或直接关闭该窗口。
echo 完整教程：docs\\INSTALL.md
exit /b 0
:done
echo [资源管理] 仅解压完成（RM_NO_LAUNCH=1）。进入 %TARGET% 双击 install.bat 或 start.bat 启动。
exit /b 0
"""


def ps_command(ps_code: str) -> str:
    """把 PS 脚本编码成一条纯 ASCII 的 -EncodedCommand 命令行。"""
    enc = base64.b64encode(ps_code.encode("utf-16-le")).decode("ascii")
    return "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + enc


def verify_installer(content: str, zip_bytes: bytes) -> None:
    """生成后静态自检，杜绝再次把带中文/特殊字符的命令行发布出去。"""
    lines = content.splitlines()
    ps_lines = [l for l in lines if l.startswith("powershell ")]
    if len(ps_lines) != 1:
        raise RuntimeError(f"自检失败：应有且仅有一条 powershell 命令行，实际 {len(ps_lines)}")
    cmd = ps_lines[0]
    if not cmd.isascii():
        raise RuntimeError("自检失败：powershell 命令行含非 ASCII 字符（会触发 cmd GBK 解析错乱）")
    if "-EncodedCommand " not in cmd:
        raise RuntimeError("自检失败：未使用 -EncodedCommand")
    payload = cmd.split("-EncodedCommand ", 1)[1]
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", payload):
        raise RuntimeError("自检失败：EncodedCommand 载荷不是纯 base64")
    decoded = base64.b64decode(payload).decode("utf-16-le")
    marker_expr = "'" + MARKER_PREFIX + "'+'" + MARKER_SUFFIX + "'"
    if marker_expr not in decoded:
        raise RuntimeError("自检失败：PS 脚本里的标记表达式与标记行不一致")
    if "ReadAllText" not in decoded or "ExtractToFile" not in decoded:
        raise RuntimeError("自检失败：PS 解压逻辑缺失")

    # 所有非 echo/rem/payload 的命令行都必须是 ASCII（中文只允许出现在 echo 文本中）
    for l in lines[:30]:
        if not l.strip() or l.lstrip().lower().startswith(("echo ", "rem ", "@echo")):
            continue
        if l.startswith("RMX1_"):
            break
        if not l.isascii():
            raise RuntimeError(f"自检失败：命令行含非 ASCII 字符 -> {l[:60]!r}")

    marker_line = MARKER_PREFIX + MARKER_SUFFIX
    if content.count(marker_line) != 1:
        raise RuntimeError("自检失败：标记行必须物理上只出现一次")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = set(z.namelist())
        for need in ("server.py", "config.json", "start.bat", "install.bat", "LICENSE"):
            if need not in names:
                raise RuntimeError(f"自检失败：内嵌包缺少 {need}")
        if z.testzip():
            raise RuntimeError("自检失败：内嵌 zip CRC 异常")


def main() -> int:
    data = build_zip()
    b64 = base64.b64encode(data).decode("ascii")
    marker_expr = "'" + MARKER_PREFIX + "'+'" + MARKER_SUFFIX + "'"
    ps_code = PS_SCRIPT_TEMPLATE.replace("__MARKER_EXPR__", marker_expr)
    header = BAT_HEADER.replace("__PS_COMMAND__", ps_command(ps_code))
    marker_line = MARKER_PREFIX + MARKER_SUFFIX + "\n"
    content = header + marker_line + b64 + "\n"
    verify_installer(content, data)
    OUT.write_text(content, encoding="utf-8")  # Windows 文本模式自动写 CRLF
    print(f"installer written: {OUT}")
    print(f"  bundled files : {len(collect())}")
    print(f"  zip bytes     : {len(data)}")
    print(f"  bat bytes     : {len(content.encode('utf-8'))}")
    print("  self-check    : ASCII command line / EncodedCommand / marker / payload CRC OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

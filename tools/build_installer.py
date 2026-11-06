"""生成自解压安装器 resource-manager-installer.bat。

设计要点（吸取历史教训，已加固）：
- 纯 ASCII 头部 + chcp 65001；以 UTF-8 无 BOM 写出（避免 cmd 首行 ï»¿ 报错）。
- 全程序 base64 内嵌在 .bat 自身，标记行之后。双击 .bat（即使在压缩包内被 Windows 临时抽取）
  仍能读取自身、解出 zip。
- 唯一标记 'RMX1_'+'PAYLOAD_BOUNDARY_9F3A' 仅以拼接形式出现在 PS 代码里，物理上只出现一次
  （标记行），杜绝 IndexOf 误命中。
- 支持环境变量（均为可选、向后兼容）：
    RM_INSTALL_TARGET  安装目录，默认 %USERPROFILE%\resource-manager
    RM_NO_LAUNCH      设为 1 则只解压不启动服务（便于自动化测试）
"""
from __future__ import annotations

import base64
import io
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


MARKER_PREFIX = "RMX1_"
MARKER_SUFFIX = "PAYLOAD_BOUNDARY_9F3A"

BAT_HEADER = """@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
set "SELF=%~f0"
set "TARGET=%RM_INSTALL_TARGET%"
if "%TARGET%"=="" set "TARGET=%USERPROFILE%\\resource-manager"
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
echo [资源管理] 正在解压安装包，请稍候…
powershell -NoProfile -ExecutionPolicy Bypass -Command "$b=[System.IO.File]::ReadAllText($env:SELF); $m='__M_P__'+'__M_S__'; $i=$b.IndexOf($m); if($i -lt 0){Write-Error 'marker-not-found'; exit 2}; $nl=[Environment]::NewLine; $j=$b.IndexOf($nl,$i); if($j -lt 0){$j=$i} else {$j=$j+$nl.Length}; $payload=$b.Substring($j).Trim(); $bytes=[System.Convert]::FromBase64String($payload); $tmp=Join-Path $env:TEMP ('rm_payload_'+[guid]::NewGuid().ToString('N')+'.zip'); [System.IO.File]::WriteAllBytes($tmp,$bytes); if(-not (Test-Path $env:TARGET)){New-Item -ItemType Directory -Path $env:TARGET -Force|Out-Null}; Expand-Archive -Path $tmp -DestinationPath $env:TARGET -Force; Remove-Item $tmp; Write-Host ('[资源管理] 已解压 '+[System.IO.Directory]::GetFiles($env:TARGET).Count+' 个文件到 '+$env:TARGET)"
if errorlevel 1 (
  echo 解压失败，请确认你完整地获取了 resource-manager-installer.bat，或手动解压后双击 install.bat。
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
  goto :done
)
cd /d "%TARGET%"
echo [资源管理] 正在启动本地服务（仅本机 127.0.0.1:8787）…
start "" python server.py
timeout /t 3 >nul
start "" http://127.0.0.1:8787
echo [资源管理] 浏览器已打开 http://127.0.0.1:8787 。若未自动打开，请手动访问。
echo 关闭服务：在弹出的 python 窗口按 Ctrl+C，或直接关闭该窗口。
goto :eof
:done
echo [资源管理] 仅解压完成（RM_NO_LAUNCH=1）。进入 %TARGET% 双击 install.bat 或 start.bat 启动。
"""


def main() -> int:
    data = build_zip()
    b64 = base64.b64encode(data).decode("ascii")
    # 标记行：物理上唯一出现一次。PS 用拼接形式 'RMX1_'+'PAYLOAD_BOUNDARY_9F3A' 引用，
    # 因此该完整字面量不会出现在 PS 源码中，IndexOf 只会命中下面这行。
    marker_line = MARKER_PREFIX + MARKER_SUFFIX + "\n"
    content = BAT_HEADER + marker_line + b64 + "\n"
    OUT.write_text(content, encoding="utf-8")  # UTF-8 无 BOM
    print(f"installer written: {OUT}")
    print(f"  bundled files : {len(collect())}")
    print(f"  zip bytes     : {len(data)}")
    print(f"  bat bytes     : {len(content.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

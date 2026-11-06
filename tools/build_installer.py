# -*- coding: utf-8 -*-
"""构建自解压安装器 resource-manager-installer.bat。

把当前 git 提交树（git archive，自动排除 .gitattributes 中 export-ignore 的开发脚本）
打成 zip，再 base64 内嵌进一个纯 ASCII 的 .bat。用户双击该 .bat（即使在压缩包里直接
双击也行），它会自动解压到 %USERPROFILE%\resource-manager 并启动真正的安装向导，
无需用户手动解压。

要点：
- 整个 .bat 保持纯 ASCII（无 BOM），避免 cmd 把 BOM 当成命令首字符。
- 中文提示通过 base64(UTF-16LE) 内嵌，由 PowerShell 解码后用 MessageBox 弹出，
  彻底摆脱 GBK/UTF-8 代码页乱码。
- 内嵌载荷的起始标记是唯一的 RESOURCE_MANAGER_PAYLOAD_V1，不会与 PowerShell
  代码里的字符串冲突。
"""
from __future__ import annotations

import base64
import io
import os
import subprocess
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = r"C:\Users\ERICZOU\WorkBuddy\2026-11-06-15-42-58\resource-manager-installer.bat"

# 注意：分隔符不能以其完整字面量出现在 PowerShell 代码里（否则 IndexOf 会命中代码中的那次）。
# 因此 PS 中通过拼接构造搜索串，使完整分隔符只存在于下面那一行。
PAYLOAD_MARKER = "ENDOFBATCH_RESOURCE_MANAGER_PAYLOAD"

# 中文提示先编码为 base64(UTF-16LE)，在 .bat 中以纯 ASCII 形式存在，PowerShell 解码后弹窗。
MSG_EXTRACT_FAIL = (
    "解压安装包失败。请右键安装包，选择“解压到”后，手动运行解压出来的文件夹里的 install.bat。"
)
MSG_NEED_PYTHON = (
    "未检测到 Python。请先安装 Python 3.8 以上，并在安装时勾选 Add Python to PATH，"
    "然后重新运行本程序。"
)


def b64u16(s: str) -> str:
    return base64.b64encode(s.encode("utf-16-le")).decode("ascii")


def build_payload() -> bytes:
    zip_path = os.path.join(REPO, "_payload_tmp.zip")
    subprocess.run(
        ["git", "archive", "--format=zip", "--output", zip_path, "HEAD"],
        cwd=REPO,
        check=True,
    )
    try:
        with open(zip_path, "rb") as f:
            raw = f.read()
    finally:
        os.remove(zip_path)
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    for must in ("server.py", "tools/install_helper.py", "tools/launcher.py", "config.json"):
        assert must in names, f"payload 缺少 {must}"
    for banned in ("tools/publish_release.py", "tools/publish_release.bat", "selfcheck_v123.py"):
        assert banned not in names, f"payload 不应包含 {banned}"
    # 确保载荷里不包含标记字符串（base64 字母表不含该串，这里仅作保险）
    assert PAYLOAD_MARKER not in raw.decode("latin-1"), "payload 意外包含标记串"
    return raw


WRAPPER = r"""@echo off
setlocal
set "SELF=%~f0"
set "ROOT=%~dp0"

rem If already extracted (tools\install_helper.py beside this bat), run directly.
if exist "%ROOT%tools\install_helper.py" (
    call :run_helper "%ROOT%tools\install_helper.py"
    goto :eof
)

rem Otherwise this was launched from inside the .zip: self-extract then run.
set "DEST=%USERPROFILE%\resource-manager"
if not exist "%DEST%" mkdir "%DEST%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$b=[System.IO.File]::ReadAllText('%SELF%'); $m='ENDOFBATCH_'+'RESOURCE_MANAGER_PAYLOAD'; $i=$b.IndexOf($m); if($i -lt 0){exit 1}; $i=$i+$m.Length; $b64=$b.Substring($i).Trim(); $bytes=[Convert]::FromBase64String($b64); $z=Join-Path '%DEST%' '_payload.zip'; [System.IO.File]::WriteAllBytes($z,$bytes); Expand-Archive -Force $z '%DEST%'; Remove-Item $z;"
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$m=[System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('MSG_EXTRACT_FAIL')); Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($m,'Install Failed','OK','Error')"
    pause
    goto :eof
)
call :run_helper "%DEST%\tools\install_helper.py"
goto :eof

:run_helper
set "HELPER=%~1"
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$m=[System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('MSG_NEED_PYTHON')); Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($m,'Need Python','OK','Error')"
    pause
    goto :eof
)
"%PY%" "%HELPER%"
if errorlevel 1 pause
goto :eof

ENDOFBATCH_RESOURCE_MANAGER_PAYLOAD
"""


def main() -> None:
    raw = build_payload()
    b64 = base64.b64encode(raw).decode("ascii")
    wrapper = (
        WRAPPER
        .replace("MSG_EXTRACT_FAIL", b64u16(MSG_EXTRACT_FAIL))
        .replace("MSG_NEED_PYTHON", b64u16(MSG_NEED_PYTHON))
    )
    with open(OUT, "w", encoding="ascii") as f:
        f.write(wrapper)
        f.write(b64)
        f.write("\n")
    size = os.path.getsize(OUT)
    print(f"[完成] 已生成自解压安装器: {OUT}")
    print(f"        大小: {size/1024:.1f} KB  (程序数据 {len(raw)/1024:.1f} KB)")


if __name__ == "__main__":
    main()

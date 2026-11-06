"""QQ 数据源：NapCat OneBot 11 只读遍历 + 定向下载。

令牌从本机 NapCat 配置自动读取，不写入项目、不输出到日志。
接口不可用时由上层回落到 state/qq_manifest.json 离线快照。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime
from pathlib import Path

CONFIG_GLOB = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "OmniQQ-MCP", "napcat_runtime", "shell_node", "napcat", "config", "onebot11_*.json",
)


def _endpoint() -> tuple[str, str]:
    for f in sorted(glob.glob(CONFIG_GLOB)):
        try:
            cfg = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in cfg.get("network", {}).get("httpServers", []):
            if s.get("enable") and s.get("token"):
                return f"http://127.0.0.1:{s.get('port', 3000)}", s["token"]
    return "http://127.0.0.1:3000", ""


BASE, TOKEN = _endpoint()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path: str, payload: dict, timeout: int = 30, retries: int = 1) -> dict:
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                BASE + path, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
            )
            with OPENER.open(req, timeout=timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
            if out.get("retcode", 0) not in (0, None) or out.get("status") == "failed":
                raise RuntimeError(str(out.get("wording") or out.get("message") or out)[:160])
            return out.get("data") or {}
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"{path} 失败：{last}")


def online() -> bool:
    try:
        call("/get_login_info", {}, timeout=3, retries=0)
        return True
    except Exception:
        return False


def _safe(name: str) -> str:
    return (name or "unnamed").replace("/", "_").replace("\\", "_").strip()


def fmt_size(n) -> str:
    try:
        n = int(n)
    except Exception:
        return ""
    for unit, base in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= base:
            return f"{n / base:.1f} {unit}"
    return f"{n} B"


def _row(f: dict, folder: str) -> dict:
    name = _safe(f.get("file_name", ""))
    size = f.get("file_size", f.get("size", 0)) or 0
    ts = f.get("upload_time", 0)
    try:
        when = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if int(ts) > 0 else ""
    except Exception:
        when = ""
    return {
        "path": f"{folder}/{name}" if folder else name,
        "name": name, "folder": folder or "(根目录)",
        "size": fmt_size(size), "size_bytes": int(size) if str(size).isdigit() else 0,
        "uploader": f.get("uploader_name", "") or "", "uploaded_at": when,
        "ext": os.path.splitext(name)[1].lower(),
        "file_id": f.get("file_id", ""), "busid": f.get("busid", 102),
    }


def walk(group_id: int) -> tuple[list[dict], int]:
    """递归只读遍历群文件全部目录，返回 (清单, 文件夹数)。不下载任何文件内容。"""
    rows: list[dict] = []
    root = call("/get_group_root_files", {"group_id": group_id}, timeout=30)
    for f in root.get("files", []):
        rows.append(_row(f, ""))
    queue = [(d["folder_id"], _safe(d.get("folder_name", ""))) for d in root.get("folders", [])]
    visited, n = set(), 0
    while queue:
        fid, folder = queue.pop(0)
        if fid in visited:
            continue
        visited.add(fid)
        n += 1
        try:
            data = call("/get_group_files_by_folder", {"group_id": group_id, "folder_id": fid})
        except Exception:
            continue
        for f in data.get("files", []):
            rows.append(_row(f, folder))
        for d in data.get("folders", []):
            queue.append((d["folder_id"], f"{folder}/{_safe(d.get('folder_name', ''))}"))
    return rows, n


def fetch_url(group_id: int, file_id: str, busid: int = 102) -> str:
    data = call("/get_group_file_url", {"group_id": group_id, "file_id": file_id, "busid": busid})
    return data.get("url", "")


def download_to(url: str, dest: Path, timeout: int = 240) -> Path:
    """优先用 NapCat 内置下载器缓存，再复制到目标；失败则直连 URL 下载。绝不覆盖已有文件。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cached = ""
    try:
        data = call("/download_file", {"url": url, "thread_count": 3}, timeout=timeout, retries=0)
        cached = data.get("file") or data.get("path") or ""
    except Exception:
        cached = ""
    if cached and Path(cached).is_file():
        shutil.copy2(cached, dest)
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with OPENER.open(req, timeout=timeout) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest

"""微信数据源：能力评估结论 + 预留的「本地授权目录」只读适配器。

重要：本机是微信 4.x（Weixin.exe），没有 OneBot/Bot 协议端，也没有个人微信开放 API。
- db_storage/*.db 为加密 SQLite，聊天内容与群归属不可读，也不应读取；
- msg/file/ 下只有「已落地本地」的明文文件，只有文件名/大小/月份，
  看不到云端未下载文件、看不到群归属与发送者；
- 企业微信连接器需要企业管理员 corpid/secret 授权，且是企业微信生态，不对等。

微信登录在电脑版微信客户端里扫码完成，本模块负责检测登录态、列出可选群、
监听所选群内的文件消息（见 wechat_wcf.py），不代扫码、不读取聊天数据库。
只有在用户显式填写 authorized_local_dir 并开启后，才额外只读扫描该目录。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

LIMITS = {
    "login": "扫码在微信 PC 客户端完成；本程序提供登录状态检测与接入引导",
    "cloud": "监听式采集：只登记监听开启后群内新出现的文件消息，看不到云端历史文件",
    "group": "群清单来自微信客户端联系人，只监听你勾选的群",
    "chatdb": "聊天数据库加密，程序不读取",
    "local": "可选：经显式授权只读扫描本地已落地文件名 / 大小 / 时间",
    "version": "WeChatFerry 需微信 PC 3.9.x；微信 4.x 暂不支持，请继续使用 QQ 群文件通道",
}


def status(cfg: dict) -> dict:
    w = (cfg.get("sources") or {}).get("wechat") or {}
    d = (w.get("authorized_local_dir") or "").strip()
    return {
        "connected": False,
        "enabled": bool(w.get("enabled")),
        "reason": w.get("reason", ""),
        "limits": LIMITS,
        "authorized_local_dir": d,
        "local_files": len(scan_authorized(Path(d))) if d and Path(d).is_dir() and w.get("enabled") else 0,
    }


def scan_authorized(root: Path) -> list[dict]:
    """只读枚举已落地文件。不打开数据库、不解析聊天记录、不猜测群归属。"""
    out = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("~$") or p.suffix.lower() in (".db", ".db-wal", ".db-shm"):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out.append({
            "id": "wx-" + hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:16],
            "source": "微信本地授权目录", "group": "本地已落地文件",
            "path": str(p.relative_to(root)).replace("\\", "/"),
            "name": p.name, "folder": p.parent.name, "ext": p.suffix.lower(),
            "size_bytes": st.st_size, "uploader": "", "uploaded_at": "",
            "file_id": "", "busid": 0, "local_path": str(p),
        })
    return out

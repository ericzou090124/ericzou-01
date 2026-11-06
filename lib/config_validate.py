"""启动期配置自检：在 server 启动早期运行，给出可读的告警/错误。

目的：避免在某个请求用到配置时才 KeyError/静默异常；把「配置问题」集中暴露成人类可读的清单。
不擅自改写配置，只报告；是否纠正交由用户/向导决定。
"""
from __future__ import annotations

from pathlib import Path

from . import config


def validate() -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    cfg = config.CFG

    # 1) vault 路径
    v = (cfg.get("vault") or "").strip()
    if not v:
        warnings.append("config.vault 未设置，将默认使用 ~/Desktop/资源管理（首次启动自动创建）")
    else:
        p = Path(v)
        if not p.exists():
            warnings.append(f"vault 路径不存在：{v}（首次启动将自动创建，也可在设置中修改）")

    # 2) QQ 群来源
    groups = (cfg.get("sources", {}).get("qq", {}) or {}).get("groups", {})
    if not groups:
        warnings.append("未配置任何 QQ 群（sources.qq.groups 为空）：群文件来源为空，可在新手向导中添加。")
    else:
        for k, g in groups.items():
            gid = str((g or {}).get("qq_group", "")).strip()
            if not gid.isdigit():
                errors.append(f"群「{k}」的 qq_group 不是纯数字：{gid!r}（会导致刷新来源失败）")

    # 3) 下载白名单
    ae = cfg.get("allowed_ext") or []
    if not ae:
        errors.append("allowed_ext 为空：下载白名单未定义，所有下载都会被拒绝。请至少包含 ['.pdf', '.docx', ...]")
    else:
        bad = [e for e in ae if not str(e).startswith(".")]
        if bad:
            warnings.append(f"allowed_ext 中有不带点的项（将按字面匹配）：{bad}；建议统一写成 '.pdf' 形式")

    # 4) AI 配置
    ai = cfg.get("ai") or {}
    prov = ai.get("provider")
    if prov not in (None, "", "local", "openai"):
        warnings.append(f"ai.provider={prov!r} 未知，将按本地模型处理")
    if prov == "openai" and not (ai.get("endpoint") or ai.get("base_url")):
        warnings.append("ai.provider=openai 但未设置 endpoint/base_url：问答将不可用")

    # 5) 单次下载上限
    m = cfg.get("max_download_per_batch")
    if not isinstance(m, int) or m <= 0:
        warnings.append(f"max_download_per_batch={m!r} 非法，运行时会回退为 30")

    # 6) 监听地址/端口
    host = cfg.get("host", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        warnings.append(f"host={host!r} 非回环地址：服务将监听外部网络，仅在你确需远程访问时这样做")
    port = cfg.get("port")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        errors.append(f"port={port!r} 非法（应为 1-65535 整数）")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "checked": ["vault", "qq_groups", "allowed_ext", "ai", "max_download_per_batch", "host/port"]}

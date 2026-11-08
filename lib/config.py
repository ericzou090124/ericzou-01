"""配置与路径。零第三方依赖；密钥只在 state/secrets.json，不进仓库。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
STATE = ROOT / "state"
WEB = ROOT / "web"
PLUGIN_SRC = ROOT / "obsidian_plugin"

CFG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def vault() -> Path:
    """独立的新 Obsidian 库。默认 ~/Desktop/<vault_name>，绝不覆盖用户已有的资料库。

    config.json 的 vault 留空即可在新机器上自动建同名新库；需要换位置时填绝对路径。
    """
    v = (CFG.get("vault") or "").strip()
    if v:
        return Path(v)
    name = (CFG.get("vault_name") or "QQ群资料Obsidian库").strip() or "QQ群资料Obsidian库"
    return Path.home() / "Desktop" / name


def vault_name() -> str:
    return vault().name


def state(name: str) -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    return STATE / name


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def settings() -> dict:
    """运行时设置覆盖配置默认值。api_key 单独放 secrets.json。"""
    s = dict(CFG.get("ai") or {})
    s.update(read_json(state("settings.json"), {}) or {})
    s["local"] = dict((CFG.get("ai") or {}).get("local") or {}, **(s.get("local") or {}))
    return s


def save_settings(patch: dict) -> dict:
    cur = read_json(state("settings.json"), {}) or {}
    key = patch.pop("api_key", None)
    cur.update(patch)
    write_json(state("settings.json"), cur)
    if key is not None:
        secrets = read_json(state("secrets.json"), {}) or {}
        secrets["api_key"] = key
        write_json(state("secrets.json"), secrets)
    return settings()


def api_key(s: dict) -> str:
    if s.get("provider") == "local":
        return (s.get("local") or {}).get("api_key") or "local"
    return (read_json(state("secrets.json"), {}) or {}).get("api_key") or ""


def public_settings() -> dict:
    s = settings()
    return {
        "provider": s.get("provider", "local"),
        "base_url": (s.get("local") or {}).get("base_url", ""),
        "model": s.get("model") or (s.get("local") or {}).get("model", ""),
        "disable_thinking": (s.get("local") or {}).get("disable_thinking", True),
        "has_api_key": bool(api_key(s)),
        "min_relevance": s.get("min_relevance", 0.22),
        "top_k": s.get("top_k", 5),
    }


def save_qq_groups(groups: list[dict]) -> dict:
    """新手向导保存 QQ 群配置（覆盖 sources.qq.groups）。原子写盘并同步内存。

    仅接受「群号是纯数字」的条目，避免误把说明文字写进配置。
    """
    cleaned = {}
    for i, g in enumerate(groups):
        gid = str((g or {}).get("qq_group", "")).strip()
        if not gid.isdigit():
            continue
        name = str((g or {}).get("display", "")).strip() or f"群{gid}"
        cleaned[f"g{i + 1}"] = {"display": name, "qq_group": gid}
    CFG.setdefault("sources", {}).setdefault("qq", {})["groups"] = cleaned
    write_json(CONFIG_PATH, CFG)
    return cleaned


def _qq_groups() -> dict:
    return (CFG.setdefault("sources", {}).setdefault("qq", {})).setdefault("groups", {})


def add_qq_group(code: str, display: str, qq_group: str) -> dict:
    """增量新增一个 QQ 群到搜索池，保留既有群代号不重排（与 save_qq_groups 的整段覆盖不同）。

    返回更新后的 groups 字典。群号必须是纯数字；代号留空或冲突时自动生成 gN。
    """
    gid = str(qq_group or "").strip()
    if not gid.isdigit():
        raise ValueError("群号必须是纯数字")
    groups = _qq_groups()
    code = str(code or "").strip()
    if not code or code in groups:
        i = len(groups) + 1
        while f"g{i}" in groups:
            i += 1
        code = f"g{i}"
    name = str(display or "").strip() or f"群{gid}"
    groups[code] = {"display": name, "qq_group": gid}
    write_json(CONFIG_PATH, CFG)
    return dict(groups)


def remove_qq_group(code: str) -> dict:
    """从搜索池移除一个 QQ 群（按代号）。返回更新后的 groups 字典。"""
    groups = _qq_groups()
    groups.pop(str(code or "").strip(), None)
    write_json(CONFIG_PATH, CFG)
    return dict(groups)


def set_qq_groups(selected: list[dict]) -> dict:
    """v3.5.0 群聊框选：一次保存用户勾选的全部群，供任意 QQ 账号使用。

    - 只接受纯数字群号；重复群号去重；
    - 已在配置里的群保留原代号（分类树/快照里的 group 名不因保存而漂移）；
    - 新勾选的群自动分配 gN 代号；
    - 未勾选的群从搜索池移除（不动任何已入库文件）。
    """
    old = _qq_groups()
    by_gid = {str(v.get("qq_group", "")): (k, v) for k, v in old.items()}
    cleaned: dict[str, dict] = {}
    used: set[str] = set()
    for g in selected or []:
        gid = str((g or {}).get("qq_group", "")).strip()
        if not gid.isdigit() or gid in used:
            continue
        used.add(gid)
        name = str((g or {}).get("display", "") or "").strip()
        if gid in by_gid:
            code, prev = by_gid[gid]
            cleaned[code] = {"display": name or prev.get("display") or f"群{gid}", "qq_group": gid}
        else:
            i = 1
            while f"g{i}" in cleaned:
                i += 1
            cleaned[f"g{i}"] = {"display": name or f"群{gid}", "qq_group": gid}
    old.clear()
    old.update(cleaned)
    write_json(CONFIG_PATH, CFG)
    return dict(cleaned)


def setup_done() -> bool:
    return state("setup_done.json").is_file()


def mark_setup_done() -> None:
    write_json(state("setup_done.json"), {"done": True, "at": datetime.now().isoformat()})

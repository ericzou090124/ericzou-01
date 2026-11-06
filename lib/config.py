"""配置与路径。零第三方依赖；密钥只在 state/secrets.json，不进仓库。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
STATE = ROOT / "state"
WEB = ROOT / "web"
PLUGIN_SRC = ROOT / "obsidian_plugin"

CFG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def vault() -> Path:
    v = (CFG.get("vault") or "").strip()
    return Path(v) if v else Path.home() / "Desktop" / "资源管理"


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

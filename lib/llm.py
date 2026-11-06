"""大模型适配：本地 Bonsai2 / 任意 OpenAI 兼容外部 API。

本地模型必须关闭思考模式，否则单问 51–325 秒；关闭后 2–4 秒。
密钥只从 settings + secrets.json 读取，不写日志、不回显。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _base(s: dict) -> str:
    if s.get("provider") == "local":
        return (s.get("local") or {}).get("base_url", "http://127.0.0.1:8080/v1").rstrip("/")
    return (s.get("base_url") or "").rstrip("/")


def _model(s: dict) -> str:
    if s.get("provider") == "local":
        return (s.get("local") or {}).get("model", "ternary-bonsai-2-27b")
    return s.get("model") or ""


def chat(system: str, user: str, s: dict | None = None) -> tuple[str | None, str]:
    s = s or config.settings()
    base, model = _base(s), _model(s)
    if not base or not model:
        return None, "未配置模型"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.3, "top_p": 0.8, "stream": False,
        "max_tokens": int(s.get("max_tokens", 512)),
    }
    if s.get("provider") == "local" and (s.get("local") or {}).get("disable_thinking", True):
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (config.api_key(s) or "local")}
    req = urllib.request.Request(base + "/chat/completions",
                                  data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                  headers=headers)
    try:
        with OPENER.open(req, timeout=float(s.get("timeout", 60))) as r:
            out = json.loads(r.read().decode("utf-8"))
        text = out["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}（密钥或模型名可能不正确）"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:90]}"
    text = re.sub(r"<think>[\s\S]*?</think>", "", text or "", flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:int(s.get("max_answer_chars", 260)) * 3] or None), ""


def test(s: dict | None = None) -> dict:
    s = s or config.settings()
    base = _base(s)
    if not base:
        return {"ok": False, "message": "未填写 base_url"}
    req = urllib.request.Request(base + "/models",
                                  headers={"Authorization": "Bearer " + (config.api_key(s) or "local")})
    try:
        with OPENER.open(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
        names = [m.get("id") or m.get("name") for m in data.get("data", data.get("models", []))]
        return {"ok": True, "provider": s.get("provider"), "model": _model(s),
                "models": names[:5], "message": "接口可达"}
    except Exception as e:
        return {"ok": False, "provider": s.get("provider"),
                "message": f"不可达：{type(e).__name__} {str(e)[:80]}"}

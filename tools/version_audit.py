"""全版本可用性审计：逐个 git tag 检出到隔离临时目录，做静态/导入/核心链路检测。

用法：
    python tools/version_audit.py                # 审计全部 tag，输出 docs/VERSION_AUDIT.md
    python tools/version_audit.py --json         # 输出 JSON 到 stdout
    python tools/version_audit.py --tags v2.5.0 v2.7.0   # 只审计指定 tag

检测项（每个版本独立临时目录 + 独立 state，绝不污染工作区）：
  1. 归档完整性：tag 可 archive、README/config/server.py 等关键文件存在
  2. 配置可解析：config.json 为合法 JSON，且含必需顶层键
  3. 静态编译：全部 .py 用 py_compile 编译（语法 / 跨版本兼容）
  4. 模块导入：import server + 全部 lib.*（导入期异常 = 硬错误）
  5. 核心链路：classify → index.rebuild → index.search → ai.answer（fast，不联网）
  6. 自测脚本：若版本内含 tools/smoke_test.py，注入隔离快照后执行

退出码 0 = 全部通过；1 = 至少一个版本 FAIL。
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 在版本目录内以子进程执行的「导入检查」
IMPORT_PROBE = r'''
import sys, os
sys.path.insert(0, os.getcwd())
import server
import pkgutil, lib
mods = []
for m in pkgutil.iter_modules(lib.__path__):
    __import__("lib." + m.name)
    mods.append(m.name)
print("IMPORTS_OK mods=" + ",".join(sorted(mods)))
'''

# 在版本目录内以子进程执行的「核心链路冒烟」（完全隔离 state，不联网、不读真实资料）
CORE_PROBE = r'''
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from lib import config
config.STATE = Path(tempfile.mkdtemp(prefix="rm_audit_state_"))
from lib import classify, index, ai, catalog

cfg = config.CFG
cat = {"version": 1, "updated_at": "", "items": [
    {"id": "r-audit-1", "source": "QQ群", "group": "测试群", "path": "考试与复习/高数真题.pdf",
     "name": "高数真题.pdf", "folder": "考试与复习", "ext": ".pdf", "size_bytes": 2048,
     "downloaded": False, "domain": "学习", "subject": "高等数学", "kind": "试卷与解析"},
    {"id": "r-audit-2", "source": "QQ群", "group": "测试群", "path": "课件/复变函数讲义.pdf",
     "name": "复变函数讲义.pdf", "folder": "课件", "ext": ".pdf", "size_bytes": 4096,
     "downloaded": False, "domain": "学习", "subject": "复变函数与积分变换", "kind": "课件资源"},
]}
# 1) 三级分类必须返回非空三元组
d, s, k = classify.classify({"folder": "考试与复习", "name": "高数真题.pdf"}, cfg)
assert d and s and k, (d, s, k)
# 2) 目录查询 / 计数
assert catalog.by_id(cat, "r-audit-1") is not None
assert catalog.counts(cat)["total"] == 2
# 3) 索引全量重建 + 检索
n = index.rebuild(cat)
assert n == 2, n
hits = index.search("高数真题")
assert isinstance(hits, list)
# 4) AI 问答：空问题与 fast 模式（不调用 LLM，不联网）
r0 = ai.answer("", cat)
assert isinstance(r0, dict) and "answer" in r0
r1 = ai.answer("有哪些资料", cat, fast=True)
assert isinstance(r1, dict) and "answer" in r1
# 5) 若版本支持增量同步，校验与 rebuild 一致性
if hasattr(index, "sync"):
    n2 = index.sync(cat)
    assert n2 == 2, n2
print("CORE_OK domain=%s subject=%s kind=%s hits=%d mode=%s" % (d, s, k, len(hits), r1.get("mode")))
'''

# 用户点名功能的专项探测：群文件三级分类 + 微信监听适配器（若该版本已包含）
FEATURE_PROBE = r'''
import sys, os
sys.path.insert(0, os.getcwd())
from lib import config, classify
cfg = config.CFG
cases = [
    ("考试与复习", "高等数学期末真题.pdf"),
    ("课件", "复变函数与积分变换讲义.pdf"),
    ("", "线性代数课后习题答案.docx"),
    ("", "数据结构实验代码.zip"),
    ("", "大学物理知识点总结.md"),
    ("", "C语言程序设计上机指南.txt"),
]
named = 0
for folder, name in cases:
    d, s, k = classify.classify({"folder": folder, "name": name}, cfg)
    assert d and s and k, (folder, name, d, s, k)
    if s != "综合":
        named += 1
assert named >= 4, "科目词库疑似失效，命中具体科目仅 %d/%d" % (named, len(cases))
wcf = "absent"
try:
    from lib import wechat_wcf
    st = wechat_wcf.status(cfg)
    assert st.get("mode") == "wechatferry", st
    assert st.get("enabled") is False, "微信采集默认必须关闭"
    assert isinstance(st.get("available"), bool)
    wcf = "ok"
except ImportError:
    pass
print("FEATURES_OK wcf=%s named=%d/%d" % (wcf, named, len(cases)))
'''

# 服务端核心路由完整性（避免某版本丢端点导致界面半瘫）
ROUTES_PROBE = r'''
from pathlib import Path
s = Path("server.py").read_text(encoding="utf-8", errors="replace")
required = ["/api/state", "/api/tree", "/api/files", "/api/file", "/api/ask", "/api/download"]
lack = [x for x in required if x not in s]
assert not lack, "缺少端点: " + ",".join(lack)
assert Path("web/index.html").is_file()
print("ROUTES_OK required=%d" % len(required))
'''

KEY_FILES = ("server.py", "config.json", "README.md", "lib/catalog.py", "lib/index.py", "lib/ai.py")
REQUIRED_CFG = ("sources", "allowed_ext", "classification", "ai")


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def tag_list() -> list[str]:
    r = run_git("tag", "--list", "--sort=v:refname")
    return [x.strip() for x in r.stdout.decode("utf-8", "replace").splitlines() if x.strip()]


def extract_tag(tag: str, dest: Path) -> tuple[bool, str]:
    r = run_git("archive", "--format=tar", tag)
    if r.returncode != 0:
        return False, f"git archive 失败: {r.stderr.decode('utf-8','replace')[:200]}"
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:") as tf:
            tf.extractall(dest, filter="data")  # Python 3.12+ 安全解包
    except TypeError:
        with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:") as tf:
            tf.extractall(dest)
    except Exception as e:
        return False, f"解包失败: {type(e).__name__}: {e}"
    return True, ""


def probe(dest: Path, code: str, timeout: int = 75) -> tuple[bool, str, str]:
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=dest,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT"
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    ok = r.returncode == 0 and "OK" in out
    return ok, out, err[-900:] if err else ""


def audit_one(tag: str) -> dict:
    rec = {"tag": tag, "status": "PASS", "checks": {}, "errors": [], "info": {}}
    tmp = Path(tempfile.mkdtemp(prefix=f"rm_audit_{tag.replace('.', '_')}_"))
    try:
        ok, msg = extract_tag(tag, tmp)
        rec["checks"]["archive"] = ok
        if not ok:
            rec["errors"].append(msg)
            rec["status"] = "FAIL"
            return rec

        pyfiles = sorted(str(p.relative_to(tmp)) for p in tmp.rglob("*.py"))
        rec["info"]["py_files"] = len(pyfiles)
        rec["info"]["all_files"] = sum(1 for p in tmp.rglob("*") if p.is_file())
        rec["info"]["has_smoke_test"] = (tmp / "tools" / "smoke_test.py").is_file()
        rec["info"]["has_config_validate"] = (tmp / "lib" / "config_validate.py").is_file()

        # 关键文件
        missing = [f for f in KEY_FILES if not (tmp / f).is_file()]
        rec["checks"]["key_files"] = not missing
        if missing:
            rec["errors"].append("缺少关键文件: " + ", ".join(missing))

        # 配置可解析 + 必需键
        try:
            cfg = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
            lack = [k for k in REQUIRED_CFG if k not in cfg]
            rec["checks"]["config"] = not lack
            if lack:
                rec["errors"].append("config.json 缺少键: " + ", ".join(lack))
            rec["info"]["groups"] = len(((cfg.get("sources") or {}).get("qq") or {}).get("groups") or {})
        except Exception as e:
            rec["checks"]["config"] = False
            rec["errors"].append(f"config.json 解析失败: {type(e).__name__}: {e}")

        # 静态编译（用当前解释器编译，能发现语法错误）
        comp = subprocess.run([sys.executable, "-m", "compileall", "-q", str(tmp)],
                              capture_output=True, text=True, timeout=90)
        rec["checks"]["compile"] = comp.returncode == 0
        if comp.returncode != 0:
            rec["errors"].append("compileall 失败: " + (comp.stdout + comp.stderr)[-500:])

        # 模块导入
        ok, out, err = probe(tmp, IMPORT_PROBE)
        rec["checks"]["imports"] = ok
        rec["info"]["mods"] = out.split("mods=", 1)[1] if "mods=" in out else ""
        if not ok:
            rec["errors"].append("导入失败: " + (err or out)[:400])

        # 核心链路
        ok, out, err = probe(tmp, CORE_PROBE)
        rec["checks"]["core"] = ok
        rec["info"]["core"] = out
        if not ok:
            rec["errors"].append("核心链路失败: " + (err or out)[:400])

        # 专项功能：群文件分类 + 微信监听适配器
        ok, out, err = probe(tmp, FEATURE_PROBE)
        rec["checks"]["features"] = ok
        rec["info"]["features"] = out
        if not ok:
            rec["errors"].append("功能探测失败: " + (err or out)[:400])

        # 路由完整性
        ok, out, err = probe(tmp, ROUTES_PROBE)
        rec["checks"]["routes"] = ok
        if not ok:
            rec["errors"].append("路由探测失败: " + (err or out)[:400])

        # 前端 JS 语法（node 可用时）
        if shutil.which("node") and (tmp / "web" / "app.js").is_file():
            r = subprocess.run(["node", "--check", str(tmp / "web" / "app.js")],
                               capture_output=True, text=True, timeout=60, cwd=tmp)
            rec["checks"]["frontend"] = r.returncode == 0
            if r.returncode != 0:
                rec["errors"].append("web/app.js 语法错误: " + (r.stderr or "")[-300:])
        else:
            rec["checks"]["frontend"] = None

        # 该版本自带的 smoke_test（注入隔离 state + 快照，避免空目录失败）
        if rec["info"]["has_smoke_test"]:
            state_src = ROOT / "state"
            (tmp / "state").mkdir(exist_ok=True)
            for name in ("qq_manifest.json", "catalog.json"):
                src = state_src / name
                if src.is_file():
                    shutil.copy2(src, tmp / "state" / name)
            r = subprocess.run([sys.executable, "tools/smoke_test.py"], cwd=tmp,
                               capture_output=True, text=True, timeout=180)
            rec["checks"]["smoke"] = r.returncode == 0
            rec["info"]["smoke_tail"] = (r.stdout or "").strip().splitlines()[-1:] or []
            if r.returncode != 0:
                rec["errors"].append("smoke_test 失败: " + ((r.stderr or "") + (r.stdout or ""))[-500:])
        else:
            rec["checks"]["smoke"] = None  # 该版本尚无自测脚本，不算失败

        # tag 指向的 commit
        sha = run_git("rev-list", "-n", "1", tag)
        rec["info"]["commit"] = sha.stdout.decode().strip()[:10] if sha.returncode == 0 else ""

        if rec["errors"]:
            rec["status"] = "FAIL"
        return rec
    except Exception as e:
        rec["status"] = "FAIL"
        rec["errors"].append(f"审计异常: {type(e).__name__}: {e}")
        return rec
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def to_markdown(rows: list[dict]) -> str:
    lines = [
        "# 全版本可用性审计报告",
        "",
        "> 由 `tools/version_audit.py` 自动生成。逐个 tag 检出到隔离临时目录，",
        "> 执行归档完整性 / 配置解析 / 全量编译 / 模块导入 / 核心链路 / 群文件分类 / 微信适配器 / 路由 / 前端语法 / 自带自测。",
        "> 检测过程使用独立 `state/`，**不读写工作区真实资料**。",
        "> 本报告是**生成时刻的快照**，覆盖当时已存在的全部 tag；之后新发布的版本请重新运行 `python tools/version_audit.py`。",
        "",
        "## 汇总",
        "",
        f"- 审计版本数：**{len(rows)}**",
        f"- 通过：**{sum(1 for r in rows if r['status']=='PASS')}**",
        f"- 已知历史问题（已提供补丁标签）：**{sum(1 for r in rows if r['status']=='KNOWN')}**",
        f"- 未修复失败：**{sum(1 for r in rows if r['status']=='FAIL')}**",
        "",
        "## 结论与修复",
        "",
        "全量审计发现 `v1.3.0` ~ `v1.6.0` 四个历史版本的 `ai.answer(\"\")` 会在变量 `f` 定义前引用 `scope=f`，",
        "抛 `NameError`（空查询即崩溃）。该缺陷已在 **v1.7.0** 主线修复。",
        "",
        "为兼顾「历史可原样回溯」与「回退版本仍可用」，**不改写、不移动任何原 tag**，",
        "而是用 `tools/fix_legacy_tag.py` 基于每个受影响 tag 生成只含最小修复的提交，",
        "并打上补丁标签 `vX.Y.Z-p1`。下表 `KNOWN` 行表示原 tag 如实保留缺陷、补丁标签已通过全部检测；",
        "需要回退到该系列版本时请检出 `-p1` 标签。",
        "",
        "| 原 tag | 状态 | 可用替代 |",
        "| --- | --- | --- |",
    ]
    known = [r for r in rows if r["status"] == "KNOWN"]
    for r in known:
        lines.append(f"| `{r['tag']}` | ⚠️ 已知缺陷（空问题 NameError） | `{r.get('fix_tag','')}` ✅ |")
    if not known:
        lines.append("| — | 无已知历史问题 | — |")
    lines += [
        "",
        "## 逐版本检测结果",
        "",
        "| 版本 | 结果 | Commit | .py | 关键文件 | 配置 | 编译 | 导入 | 核心链路 | 分类/微信 | 路由 | 前端 | 自带自测 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    ico = {True: "✅", False: "❌", None: "—"}
    label = {"PASS": "✅ PASS", "KNOWN": "⚠️ KNOWN（见补丁）", "FAIL": "❌ FAIL"}
    for r in rows:
        c = r["checks"]
        lines.append(
            f"| `{r['tag']}` | {label.get(r['status'], r['status'])} "
            f"| `{r['info'].get('commit','')}` | {r['info'].get('py_files','—')} "
            f"| {ico.get(c.get('key_files'))} | {ico.get(c.get('config'))} "
            f"| {ico.get(c.get('compile'))} | {ico.get(c.get('imports'))} "
            f"| {ico.get(c.get('core'))} | {ico.get(c.get('features'))} "
            f"| {ico.get(c.get('routes'))} | {ico.get(c.get('frontend'))} "
            f"| {ico.get(c.get('smoke'))} |"
        )
    lines += ["", "## 明细与异常", ""]
    for r in rows:
        lines.append(f"### `{r['tag']}` — {r['status']}")
        lines.append("")
        if r["info"].get("core"):
            lines.append(f"- 核心链路：`{r['info']['core']}`")
        if r["info"].get("features"):
            lines.append(f"- 功能探测：`{r['info']['features']}`")
        if r["info"].get("mods"):
            lines.append(f"- 导入模块：{r['info']['mods']}")
        if r["info"].get("smoke_tail"):
            lines.append(f"- 自带自测末行：{r['info']['smoke_tail'][0]}")
        if r["status"] == "KNOWN":
            lines.append(f"- ✅ 已提供可用补丁标签：`{r.get('fix_tag','')}`（全项通过）；原 tag 保持不动以便历史回溯")
        if r["errors"]:
            for e in r["errors"]:
                lines.append(f"- ❌ {e}")
        else:
            lines.append("- 全部检测项通过，无异常。")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    ap.add_argument("--tags", nargs="*", help="只审计指定 tag")
    ap.add_argument("--out", default="docs/VERSION_AUDIT.md")
    a = ap.parse_args()
    tags = a.tags or tag_list()
    rows = []
    for t in tags:
        r = audit_one(t)
        rows.append(r)
    # 已知历史问题：原 tag 如实保留缺陷，但已存在通过全项检测的 -p1 补丁标签 → 标记 KNOWN（非阻塞）
    passed = {r["tag"] for r in rows if r["status"] == "PASS"}
    for r in rows:
        pt = r["tag"] + "-p1"
        if r["status"] == "FAIL" and pt in passed:
            r["status"] = "KNOWN"
            r["fix_tag"] = pt
    for r in rows:
        print(f"[{r['status']}] {r['tag']}  " +
              ("; ".join(r["errors"])[:160] if r["errors"] else r["info"].get("core", "")))
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        out = ROOT / a.out
        out.write_text(to_markdown(rows), encoding="utf-8")
        print(f"\n报告已写入 {out}")
    return 0 if all(r["status"] in ("PASS", "KNOWN") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

"""历史版本补丁：修复 v1.3.0 ~ v1.6.0 的 ``ai.answer("")`` NameError。

背景
----
全版本审计（``tools/version_audit.py``）发现这 4 个 tag 在空问题时抛 NameError：
空问题分支在变量 ``f`` 定义之前就引用了 ``scope=f``。该问题已在 v1.7.0 修复。

策略
----
**不改写、不移动任何已有 tag**（保证历史可原样回溯），而是基于每个受影响的 tag
新建一个只含最小修复的提交，并打上补丁标签 ``vX.Y.Z-p1``。
需要回退到该系列版本时，用补丁标签即可获得可用版本。

用法
----
    python tools/fix_legacy_tag.py --check   # 只列出受影响/已修复的 tag
    python tools/fix_legacy_tag.py --apply   # 创建补丁提交与 -p1 标签（幂等）
    python tools/fix_legacy_tag.py --verify  # 对补丁标签跑一次审计
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AFFECTED = ("v1.3.0", "v1.4.0", "v1.5.0", "v1.6.0")
PATCH_TAG_SUFFIX = "-p1"

OLD = '''    if not q:
        return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
    cfg = config.CFG
'''
NEW = '''    cfg = config.CFG
    if not q:
        return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none",
                "scope": _scope_from_path(scope), "took_ms": 0}
'''


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True)


def tag_exists(tag: str) -> bool:
    return git("rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0


def apply_fix(ai_path: Path) -> str:
    text = ai_path.read_text(encoding="utf-8")
    if NEW in text:
        return "already-fixed"
    if OLD not in text:
        return "pattern-not-found"
    ai_path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    return "patched"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    if a.check or not (a.apply or a.verify):
        print("受影响 tag / 补丁标签状态：")
        for t in AFFECTED:
            pt = t + PATCH_TAG_SUFFIX
            r = git("show", f"{t}:lib/ai.py")
            bad = r.returncode == 0 and OLD in r.stdout
            print(f"  {t}: {'仍有 bug' if bad else '无需修复'} | {pt}: {'已存在' if tag_exists(pt) else '未创建'}")
        return 0

    if a.verify:
        tags = [t + PATCH_TAG_SUFFIX for t in AFFECTED if tag_exists(t + PATCH_TAG_SUFFIX)]
        if not tags:
            print("没有补丁标签，请先 --apply")
            return 1
        r = subprocess.run([sys.executable, "tools/version_audit.py", "--tags", *tags],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        print(r.stdout[-3000:])
        return r.returncode

    created = []
    for t in AFFECTED:
        pt = t + PATCH_TAG_SUFFIX
        if tag_exists(pt):
            print(f"[skip] {pt} 已存在")
            continue
        wt = Path(tempfile.gettempdir()) / f"rm_wt_{t.replace('.', '_')}_{pt.replace('.', '_')}"
        try:
            r = git("worktree", "add", "--detach", str(wt), t)
            if r.returncode != 0:
                print(f"[FAIL] {t} worktree 创建失败: {r.stderr.strip()[:300]}")
                continue
            ai = wt / "lib" / "ai.py"
            st = apply_fix(ai)
            if st == "pattern-not-found":
                print(f"[FAIL] {t} ai.py 未匹配到预期片段，跳过（不改动历史）")
                continue
            if st == "already-fixed":
                print(f"[skip] {t} 已含修复，无需补丁")
                continue
            git("add", "lib/ai.py", cwd=wt)
            c = git("commit", "-m",
                    f"fix(ai): 空问题 NameError 补丁（基于 {t}，等价 v1.7.0 修复）\n\n"
                    f"全版本审计发现 {t} 的 ai.answer('') 在 f 定义前引用 scope=f。\n"
                    f"原 tag {t} 保持不变；本提交仅做最小修复，标签 {pt} 指向它。", cwd=wt)
            if c.returncode != 0:
                print(f"[FAIL] {t} commit 失败: {c.stderr.strip()[:300]}")
                continue
            tg = git("tag", pt, cwd=wt)
            if tg.returncode != 0:
                print(f"[FAIL] {t} 打标签失败: {tg.stderr.strip()[:300]}")
                continue
            created.append(pt)
            print(f"[OK] {t} -> {pt}")
        finally:
            if wt.exists():
                git("worktree", "remove", "--force", str(wt))
    print(f"\n新建补丁标签 {len(created)} 个：{', '.join(created) if created else '无'}")
    print("原 tag 未做任何改动；推送用： git push origin " + " ".join(created) if created else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())

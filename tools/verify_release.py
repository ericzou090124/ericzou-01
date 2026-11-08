"""Release 端到端验证：像真实用户一样下载、双击、启动、访问。

为什么要这个脚本
----------------
v2.9.0 的一键安装器发布后用户双击报 `'-ExecutionPolicy' is not recognized ...`。
事后复盘发现：只做「Python 解码内嵌 zip / CRC 校验」是**不够**的——真正执行 .bat 的是
cmd.exe，它会按 OEM 代码页解析命令行；含中文的超长 `powershell -Command "..."` 会被拆断。
因此发行前必须**真的让 cmd 跑一遍**，并继续把解压出来的程序起成服务打 HTTP 端点。

验证链条（7 步，全部隔离，绝不写真实 state/）
---------------------------------------------
[1] 取资产：本地 dist/，或 `--from-github` 从 Release 直链真实下载
[2] SHA256SUMS.txt 校验
[3] 把安装器复制到独立「下载目录」，用 cmd 真实执行（RM_NO_LAUNCH=1）
    → 断言退出码 0、无 CLIXML/报错、文件齐全、中文文件名正确、无 state/
[4] 完整包解压 → 断言 START_HERE.txt / VERSION.txt / 关键文件，compileall + import server
[5] 在 [3] 解压出来的目录里，用隔离 state + 空闲端口起**真实 HTTP 服务**
    → 打 /api/health /diagnose /tree /files /state 与静态页 / /app.js /style.css
[6] 真实 catalog 前后条数一致（零污染）
[7] 汇总，任一失败返回非 0

用法
----
    python tools/verify_release.py                       # 验证本地 dist/
    python tools/verify_release.py --from-github         # 从 latest 直链下载后验证
    python tools/verify_release.py --from-github --tag v2.9.1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = "https://github.com/ericzou090124/ericzou-01"
INSTALLER = "resource-manager-installer.bat"
ZIP = "resource-manager-full.zip"
SUMS = "SHA256SUMS.txt"
ASSETS = (INSTALLER, ZIP, SUMS)

KEY_FILES = (
    "server.py", "config.json", "README.md", "LICENSE", "start.bat", "install.bat",
    "docs/INSTALL.md", "docs/FEATURES.md", "web/index.html", "web/app.js",
    "web/login.html", "web/setup.html",
    "lib/index.py", "lib/ai.py", "lib/napcat_setup.py", "lib/classify.py",
    "lib/catalog.py", "lib/vault.py", "lib/vocab.py", "lib/localimport.py", "lib/download.py",
    "tools/smoke_test.py", "tools/test_v3.py", "tools/setup_napcat.bat",
)
API_PATHS = ("/api/health", "/api/state", "/api/tree?dim=subject&node=%5B%5D",
             "/api/tree?dim=kind&node=%5B%5D", "/api/tree?dim=source&node=%5B%5D",
             "/api/files?dim=subject&node=%5B%5D&limit=5",
             "/api/qqlogin/status", "/api/napcat/setup",
             "/api/vault/status", "/api/vault/search?q=%E5%9B%9B%E5%85%AD%E7%BA%A7",
             "/api/vault/search?q=%E7%BD%97%E5%B0%94&scope=all", "/api/vault/targets",
             "/api/local/scan", "/api/groups")
STATIC_PATHS = ("/", "/app.js", "/style.css", "/login", "/setup")

# 子进程引导脚本：在「解压出来的程序」里起服务，state/vault/端口全部隔离
BOOTSTRAP = r'''
import json, sys
from pathlib import Path
root, state, vault, port, snapshot = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
sys.path.insert(0, root)
from lib import config
config.STATE = state
config.vault = lambda: Path(vault)
config.CFG["port"] = port
config.CFG["host"] = "127.0.0.1"
state.mkdir(parents=True, exist_ok=True)
Path(vault).mkdir(parents=True, exist_ok=True)
if snapshot and Path(snapshot).is_file():
    import shutil
    shutil.copy2(snapshot, state / "qq_manifest.json")
import server
r = server.refresh(force_snapshot=True)
print("REFRESH", r.get("mode"), r.get("items"), flush=True)
srv = server.ThreadingHTTPServer(("127.0.0.1", port), server.Handler)
print("READY", flush=True)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
'''


class Failure(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failure(msg)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def download(url: str) -> tuple[bytes, int]:
    """CDN 偶发 RemoteDisconnected，做有界重试（0.5s / 1s / 2s）。"""
    import time
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "resource-manager-verify"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.status
        except Exception as e:
            last = e
            if attempt < 3:
                print(f"  ⟳ 下载重试 {attempt + 1}/3（{type(e).__name__}）")
                time.sleep(0.5 * (2 ** attempt))
    raise Failure(f"下载失败（重试 3 次仍不通）：{url} -> {type(last).__name__}: {last}")


def fetch_assets(args, dl: Path) -> None:
    if args.from_github:
        base = f"{WEB}/releases/download/{args.tag}" if args.tag else f"{WEB}/releases/latest/download"
        for name in ASSETS:
            url = f"{base}/{name}"
            data, status = download(url)
            (dl / name).write_bytes(data)
            print(f"  ↓ {name:42s} {len(data):>9,d} B  ({status})")
    else:
        dist = ROOT / "dist"
        for name in ASSETS:
            p = dist / name
            check(p.is_file(), f"本地缺少 {p}，请先运行 python tools/build_release_assets.py")
            shutil.copy2(p, dl / name)
            print(f"  ← {name:42s} {p.stat().st_size:>9,d} B  (dist/)")


def step(name, fn):
    print(f"\n[{name}]")
    return fn()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-github", action="store_true", help="从 GitHub Release 直链真实下载")
    ap.add_argument("--tag", help="指定 tag（默认 latest 直链）")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="rm_verify_"))
    dl = tmp / "downloads"
    dl.mkdir()
    print(f"验证沙箱：{tmp}")
    print("来源：" + ("GitHub " + (args.tag or "latest 直链") if args.from_github else "本地 dist/"))

    # 记录真实资料条数，最后确认未被污染
    sys.path.insert(0, str(ROOT))
    from lib import catalog
    before_items = len(catalog.load()["items"])

    proc = None
    try:
        step("1/7 获取发布资产", lambda: fetch_assets(args, dl))

        def verify_sums():
            lines = (dl / SUMS).read_text(encoding="utf-8").strip().splitlines()
            check(len(lines) == 2, "SHA256SUMS.txt 应有 2 行")
            for line in lines:
                h, name = line.split()
                real = sha256(dl / name)
                check(real == h, f"{name} 校验和不匹配：{real} != {h}")
                print(f"  ✓ {name:42s} SHA256 OK")
        step("2/7 校验 SHA256", verify_sums)

        # 模拟用户：把安装器单独放到「下载」文件夹再双击
        target = tmp / "installed"
        installer_copy = dl / INSTALLER

        def run_installer():
            env = dict(os.environ)
            env["RM_INSTALL_TARGET"] = str(target)
            env["RM_NO_LAUNCH"] = "1"
            r = subprocess.run(["cmd", "/c", str(installer_copy)], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=240)
            text = (r.stdout + r.stderr).decode("utf-8", errors="replace")
            print("  --- 安装器输出 ---")
            for line in text.strip().splitlines()[:12]:
                print("  |", line)
            check(r.returncode == 0, f"安装器退出码 {r.returncode}（应为 0）")
            check("解压完成" in text, "安装器未报告解压完成")
            check("-ExecutionPolicy" not in text and "not recognized" not in text,
                  "仍出现 cmd 命令解析错误")
            check("#< CLIXML" not in text, "输出混入了 PowerShell CLIXML 结构化流")
            check("[RM] extracted" in text, "PowerShell 未报告解压文件数")
            files = list(target.rglob("*"))
            check(len(files) > 50, f"解压文件过少：{len(files)}")
            for k in KEY_FILES:
                check((target / k).is_file(), f"解压结果缺少 {k}")
            check(not any(p.name == "state" and p.is_dir() for p in target.rglob("*")),
                  "发布包里混入了 state/")
            cn = [p.name for p in target.rglob("*") if any("\u4e00" <= c <= "\u9fff" for c in p.name)]
            check("新手必读.txt" in cn and "一键登录.bat" in cn, f"中文文件名乱码或缺失：{cn[:8]}")
            print(f"  ✓ 解压 {len(files)} 项，关键文件齐全，中文名正确：{cn[:4]}")

        step("3/7 真实双击安装器（cmd 执行）", run_installer)

        def verify_zip():
            out = tmp / "unzipped"
            with zipfile.ZipFile(dl / ZIP) as z:
                names = z.namelist()
                check(z.testzip() is None, "完整包 CRC 异常")
                z.extractall(out)
            for k in ("START_HERE.txt", "VERSION.txt", INSTALLER) + KEY_FILES:
                check((out / k).is_file(), f"完整包缺少 {k}")
            check(not any(n.startswith("state/") or n.startswith("dist/") for n in names),
                  "完整包混入 state/ 或 dist/")
            r1 = subprocess.run([sys.executable, "-m", "compileall", "-q", str(out)],
                                capture_output=True, text=True, timeout=180)
            check(r1.returncode == 0, f"完整包 compileall 失败：{r1.stderr[:200]}")
            r2 = subprocess.run([sys.executable, "-c", "import server; print('import OK')"],
                                cwd=out, capture_output=True, text=True, timeout=120)
            check(r2.returncode == 0, f"完整包 import server 失败：{r2.stderr[:300]}")
            print(f"  ✓ {len(names)} 文件 / CRC OK / compileall OK / import server OK")
            print("  | " + (out / "START_HERE.txt").read_text(encoding="utf-8").splitlines()[0])

        step("4/7 完整内容包解压与编译", verify_zip)

        def verify_http():
            nonlocal proc
            port = free_port()
            state = tmp / "isolated_state"
            vault = tmp / "isolated_vault"
            snapshot = str(ROOT / "state" / "qq_manifest.json")
            boot = tmp / "_bootstrap.py"
            boot.write_text(BOOTSTRAP, encoding="utf-8")
            log = (tmp / "server.log").open("w", encoding="utf-8")
            proc = subprocess.Popen([sys.executable, str(boot), str(target), str(state),
                                     str(vault), str(port), snapshot],
                                    cwd=target, stdout=log, stderr=subprocess.STDOUT)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = f"http://127.0.0.1:{port}"

            def get(path, json_body=True):
                with opener.open(base + path, timeout=30) as r:
                    data = r.read()
                    return (json.loads(data.decode("utf-8")) if json_body else data), r.status

            ready = False
            for _ in range(80):
                if proc.poll() is not None:
                    break
                try:
                    get("/api/health")
                    ready = True
                    break
                except Exception:
                    import time
                    time.sleep(0.3)
            check(ready, "解压出来的 server 未能启动（见 server.log）")
            for p in API_PATHS:
                body, status = get(p)
                check(status == 200 and body.get("ok"), f"{p} 返回 {status} / {str(body)[:160]}")
                print(f"  ✓ {p:52s} ok=true")
            for p in STATIC_PATHS:
                data, status = get(p, json_body=False)
                check(status == 200 and len(data) > 200, f"静态资源 {p} 异常：{status} / {len(data)} B")
                print(f"  ✓ {p:52s} {len(data):>7,d} B")
            print(f"  ✓ 真实 HTTP 服务在隔离端口 {port} 上全链路通过")

        step("5/7 启动解压出的程序并访问页面/API", verify_http)

        def verify_no_pollution():
            after = len(catalog.load()["items"])
            check(after == before_items, f"真实 catalog 被污染：{before_items} -> {after}")
            print(f"  ✓ 真实 catalog 仍为 {after} 条，零污染")

        step("6/7 真实数据零污染", verify_no_pollution)

        step("7/7 汇总", lambda: print("  ALL CHECKS PASSED —— 下载 / 解压 / 启动 / 访问 / 数据隔离 全部通过"))
        print(f"\n验证通过。来源：{'GitHub ' + (args.tag or 'latest') if args.from_github else '本地 dist/'}")
        return 0
    except Failure as e:
        print(f"\n❌ 验证失败：{e}")
        return 1
    except Exception as e:
        print(f"\n❌ 未预期异常：{type(e).__name__}: {e}")
        return 1
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

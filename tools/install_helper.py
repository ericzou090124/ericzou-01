# -*- coding: utf-8 -*-
"""资源管理 · 一键安装与启动（中文提示全部放在 Python，避开 .bat 中文乱码）。

被仓库根目录 install.bat 调用：检查 Python、按需安装可选增强、以独立窗口启动服务并打开界面。
服务以独立窗口运行——关闭本启动窗口不会杀掉服务（修复“扫码登录后页面加载失败”）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launcher import launch_server, server_up, port_listening  # noqa: E402

BASE = "http://127.0.0.1:8787"


def safe_input(prompt: str, default: str = "") -> str:
    """input() 在非交互（无键盘）环境下会抛 EOFError，必须兜底，否则窗口直接闪退。"""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default


def find_root() -> str | None:
    """从本文件向上有限层查找包含 server.py 的目录（不递归整棵目录树，避免卡死）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(5):
        if os.path.isfile(os.path.join(cur, "server.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # 兜底：向下查一层直接子目录（兼容解压时多套了一层文件夹）
    try:
        for name in os.listdir(here):
            sub = os.path.join(here, name)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "server.py")):
                return sub
    except OSError:
        pass
    return None


def main() -> None:
    root = find_root()
    if not root:
        print("")
        print("[错误] 没有找到 server.py。")
        print("请先把整个压缩包解压到一个文件夹，然后双击该文件夹里的 install.bat。")
        print("不要直接在压缩包（.zip）里双击运行本程序。")
        safe_input("按回车退出…")
        sys.exit(1)

    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    py = sys.executable

    print("=" * 44)
    print("  资源管理 · 一键安装与启动")
    print("=" * 44)
    print("")

    # ---- [1/3] NapCat 网关：真正做安装自检 + 自动修配置，而不只是打印一句提示 ----
    print("[1/3] 检测并配置 NapCat（QQ 群文件的本地网关，必需）…")
    nap = {}
    try:
        from lib import napcat_setup
        nap = napcat_setup.ensure(fix=True, start=False)
        if nap["installed"]:
            print("      ✓ 已检测到 NapCat 运行时：" + (nap["runtime_dir"] or "-"))
            print("      ✓ 启动脚本：" + (nap["launcher"] or "（NapCat 首次启动后生成）"))
        else:
            print("      ✗ 本机还没检测到 NapCat 运行时。")
        for f in nap.get("fixed", []):
            print("      ✓ 已自动修复：" + f)
        for i in nap.get("issues", []):
            print("      ✗ 待处理：" + i)
        for w in nap.get("warnings", []):
            print("      ! 提醒：" + w)
        if nap.get("report"):
            print("      自检报告：" + nap["report"])
        if not nap.get("installed"):
            print("")
            print("      【需要你做一次】安装 NapCat：")
            print("       方式 A：在 WorkBuddy 里启用 OmniQQ 插件（自带 NapCat 运行时，推荐）")
            print("       方式 B：到 https://napneko.github.io/ 下载 Windows 一键包，解压后运行一次 napcat.bat")
            print("       装好后再双击本 install.bat，程序会自动完成剩下的配置。")
        elif not nap.get("running") and os.environ.get("RM_NO_NAPCAT_START") != "1":
            a = safe_input("      是否现在启动 NapCat 并准备扫码登录？[Y/n]：", "y").strip().lower()
            if a in ("", "y"):
                from lib import napcat_launch
                r = napcat_launch.start()
                print("      " + (r.get("msg") or r.get("error") or "已提交启动"))
    except Exception as e:  # 自检失败不能阻断主程序
        print("      ! NapCat 自检未完成：" + type(e).__name__ + ": " + str(e))
        print("        可稍后双击 tools/setup_napcat.bat 单独检测。")
    print("")

    # ---- [2/3] 可选 Python 增强 ----
    print("[2/3] 依赖检查：核心功能只用 Python 标准库，无需安装任何包。")
    ans = safe_input("是否安装可选增强（PDF 正文抽取 / 本机渲染二维码）？建议装 [Y/n]：", "y").strip().lower()
    if ans in ("", "y"):
        req = os.path.join(root, "requirements-optional.txt")
        if os.path.exists(req):
            print("正在安装可选增强（可能需要一两分钟，请耐心等待）…")
            rc = subprocess.run([py, "-m", "pip", "install", "-r", req], check=False)
            if rc.returncode != 0:
                print("[提示] 可选增强安装失败，程序仍可使用基础功能（PDF 只登记元数据）。")
        else:
            print("[提示] 未找到 requirements-optional.txt，跳过可选增强。")
    else:
        print("已跳过可选增强。程序可正常运行（PDF 只登记元数据，二维码用 NapCat 缓存图）。")

    print("")
    print("[3/3] 启动本地服务并打开界面…")
    print("界面地址： " + BASE)
    print("（服务运行在独立窗口，关闭它即可停止；本服务仅监听本机 127.0.0.1）")
    print("")

    if port_listening() and server_up():
        print("[提示] 检测到服务已在运行，直接打开界面（无需重复启动）。")
        try:
            webbrowser.open(BASE)
        except Exception:
            pass
    else:
        started = launch_server(py, root)
        if started:
            print("服务已启动，正在打开界面…")
            time.sleep(1.5)
            try:
                webbrowser.open(BASE)
            except Exception:
                pass
        else:
            print("[错误] 服务启动失败。请查看 server.log，或手动运行：python server.py")
            safe_input("按回车退出…")
            sys.exit(1)

    safe_input(
        "操作完成。\n关闭本窗口不会影响服务运行；按回车关闭本窗口即可。\n"
        "（要停止服务：双击 tools/stop.bat，或关闭名为 python 的服务窗口）\n"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback

        print("")
        print("[安装向导运行出错] " + type(e).__name__ + ": " + str(e))
        traceback.print_exc()
        print("")
        print("若无法自行解决，请把上面的红色报错截图发给我。")
        safe_input("按回车退出…")
        sys.exit(1)

# -*- coding: utf-8 -*-
"""资源管理 · 启动本地服务（中文提示放在 Python，避开 .bat 中文乱码）。

被仓库根目录 start.bat 调用：以独立窗口定位并启动 server.py、打开界面。
服务运行在独立窗口——关闭本启动窗口不会杀掉服务。
"""
from __future__ import annotations

import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launcher import launch_server, server_up, port_listening  # noqa: E402

BASE = "http://127.0.0.1:8787"


def safe_input(prompt: str, default: str = "") -> str:
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
        print("[错误] 没有找到 server.py，请确认本文件与 server.py 在同一程序目录。")
        safe_input("按回车退出…")
        sys.exit(1)

    os.chdir(root)
    py = sys.executable

    print("正在启动「资源管理」本地服务…")
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "资源管理")
    except Exception:
        desktop = "桌面/资源管理"
    print("统一资源库：" + desktop)
    print("界面地址： " + BASE)
    print("（服务运行在独立窗口，关闭它即可停止；本服务仅监听本机 127.0.0.1）")
    print("")

    if port_listening() and server_up():
        print("[提示] 检测到服务已在运行，直接打开界面。")
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
        print("[启动失败] " + type(e).__name__ + ": " + str(e))
        traceback.print_exc()
        print("")
        print("若无法自行解决，请把上面的红色报错截图发给我。")
        safe_input("按回车退出…")
        sys.exit(1)

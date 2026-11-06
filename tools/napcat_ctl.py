"""NapCat 启动/状态查询命令行封装（供 start_napcat.bat / start_napcat.sh 调用）。

用法：
  python tools/napcat_ctl.py start     # 拉起 NapCat 并等待 WebUI 就绪
  python tools/napcat_ctl.py status    # 仅查询是否在运行
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import napcat_launch  # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        print(json.dumps(napcat_launch.start(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "status":
        print(json.dumps({"running": napcat_launch.is_running(),
                          "url": napcat_launch.webui_url()}, ensure_ascii=False, indent=2))
        return 0
    print("用法：napcat_ctl.py [start|status]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

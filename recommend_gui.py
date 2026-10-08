# -*- coding: utf-8 -*-
"""薄入口：干员 TAG 名单维护面板（实现见 gui/ 包，等价于 python -m gui）。

    python -X utf8 recommend_gui.py                  # 启动并打开浏览器
    python -X utf8 recommend_gui.py --port 8520 --no-browser
    python -X utf8 recommend_gui.py --check          # 只解析自检，不起服务
"""

from __future__ import annotations

import sys

from gui.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

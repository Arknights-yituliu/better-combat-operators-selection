# -*- coding: utf-8 -*-
"""干员 TAG 名单维护面板（本地网页版）的应用包。

模块划分：config/errors/md 为底层；tags/roster/recommends/merges/results_json 为数据层；
writeback/model 为业务层；server 只做 HTTP 路由；selfcheck 是 --check 的只读自检；
静态资源在 static/（index.html + app.css + app.js）。
"""

from __future__ import annotations

import sys

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

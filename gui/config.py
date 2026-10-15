# -*- coding: utf-8 -*-
"""路径常量与第三方脚本引导：本包所有模块都从这里取路径。"""

from __future__ import annotations

import json
import pathlib
import sys

PKG = pathlib.Path(__file__).resolve().parent
ROOT = PKG.parent
sys.path.insert(0, str(ROOT / "tools"))
import recommend as rec  # noqa: E402  （复用 TAG 扫描 / 荐读写）
PARTS = rec.PARTS
PIPE = PARTS.parent
sys.path.insert(0, str(PIPE))
import partdoc  # noqa: E402  （分文件 JSON 的唯一读写实现）
import tag_order  # noqa: E402  （TAG 展示顺序的唯一维护处）
ORDER_FILE = tag_order.ORDER_FILE
OFFICIAL_DIR = PIPE / "official_tags"
PRTS_DIR = ROOT / "material_datas" / "PRTS"
ROSTER_FILE = ROOT / "docs" / "operators.txt"
DATES_FILE = PARTS / "_launch_dates.json"
MERGE_PLAYER = PARTS / "_merge_to_docs.py"
MERGE_OFFICIAL = OFFICIAL_DIR / "_merge_official_to_docs.py"
sys.path.insert(0, str(OFFICIAL_DIR))
import _merge_official_to_docs as offm  # noqa: E402  （复用官方模块清单与实装时间）
OFFICIAL_FILES: list[tuple[str, str]] = [(cat, fn) for cat, fns in offm.FILES for fn in fns]

# 可写表格的列白名单（唯一来源 partdoc.KNOWN_COLS）：其它结构的表不参与写回
KNOWN_COLS = partdoc.KNOWN_COLS

# 干员名 → charId：成员表「编号」列的唯一来源（插入新行时按干员名自动填充）
CHAR_IDS_FILE = ROOT / "agent_workspace" / "tag_pipeline" / "char_ids.json"
try:
    CHAR_IDS: dict[str, str] = json.loads(CHAR_IDS_FILE.read_text(encoding="utf-8"))
except (OSError, ValueError):
    CHAR_IDS = {}

# 静态资源
STATIC_DIR = ROOT / "gui" / "static"
STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}

# -*- coding: utf-8 -*-
"""路径常量与第三方脚本引导：本包所有模块都从这里取路径。"""

from __future__ import annotations

import json
import pathlib
import re
import sys

PKG = pathlib.Path(__file__).resolve().parent
ROOT = PKG.parent
sys.path.insert(0, str(ROOT / "tools"))
import recommend as rec  # noqa: E402  （复用 TAG 扫描 / 荐读写）
PARTS = rec.PARTS
OFFICIAL_DIR = PARTS.parent / "official_tags"
PRTS_DIR = ROOT / "material_datas" / "PRTS"
ROSTER_FILE = ROOT / "docs" / "operators.txt"
DATES_FILE = PARTS / "_launch_dates.json"
MERGE_PLAYER = PARTS / "_merge_to_docs.py"
MERGE_OFFICIAL = OFFICIAL_DIR / "_merge_official_to_docs.py"
sys.path.insert(0, str(OFFICIAL_DIR))
import _merge_official_to_docs as offm  # noqa: E402  （复用官方模块清单与实装时间）
OFFICIAL_FILES: list[tuple[str, str]] = [(cat, fn) for cat, fns in offm.FILES for fn in fns]
H2_START = rec.START_MARKS
H2_STOP = rec.STOP_MARKS

# 可写表格的列白名单：其它结构的表不参与写回
KNOWN_COLS = {"干员", "编号", "子 TAG", "条件", "备注", "依据"}

# 干员名 → charId：成员表「编号」列的唯一来源（插入新行时按干员名自动填充）
CHAR_IDS_FILE = ROOT / "agent_workspace" / "tag_pipeline" / "char_ids.json"
try:
    CHAR_IDS: dict[str, str] = json.loads(CHAR_IDS_FILE.read_text(encoding="utf-8"))
except (OSError, ValueError):
    CHAR_IDS = {}

# 官方条目头：**名**（N 人 · 首现 日期）：定义
DEF_RE = re.compile(r"^\*\*(?P<name>.+?)\*\*（(?P<n>\d+) 人 · 首现 (?P<d>[\d-]+)）：(?P<rest>.*)$")
DEF_ANY = re.compile(r"^\*\*(?P<name>.+?)\*\*（.*?）：(?P<rest>.*)$")

# 静态资源
STATIC_DIR = ROOT / "gui" / "static"
STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}

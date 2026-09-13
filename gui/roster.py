# -*- coding: utf-8 -*-
"""全量干员表：PRTS 页解析（星级/职业/分支/势力）+ 实装时间 + 进程内缓存。"""

from __future__ import annotations

import pathlib
import re
import urllib.parse

from .config import DATES_FILE, PRTS_DIR, ROSTER_FILE, offm
from .md import is_sep_row, split_cells


def launch_date(name: str) -> str | None:
    """实装时间：与合并脚本同口径（原名 → 去形态括号）。"""
    name = name.strip()
    if name in offm.DATES:
        return offm.DATES[name]
    base = re.split(r"[（(]", name)[0].strip()
    return offm.DATES.get(base)


def parse_prts_brief(name: str) -> dict:
    """从 PRTS 干员页解析 稀有度/职业/分支/势力（星级 = 原始字段 + 1，原始字段 0 基）。"""
    out = {"star": None, "cls": "", "branch": "", "faction": ""}
    path = PRTS_DIR / name / f"{name}.md"
    if not path.exists():
        return out
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[:8]:
        m = re.match(r"^>\s*稀有度:\s*(\S+)\s*\|\s*职业:\s*(\S+)", line)
        if m:
            try:
                out["star"] = int(m.group(1)) + 1
            except ValueError:
                pass
            out["cls"] = m.group(2)
            break
    sec = ""
    faction = hidden = ""
    for line in lines:
        if line.startswith("## "):
            sec = line[3:].strip()
            continue
        if not line.lstrip().startswith("|") or is_sep_row(split_cells(line)):
            continue
        cells = split_cells(line)
        if sec == "特性" and not out["branch"] and cells and cells[0] not in ("分支", ""):
            out["branch"] = cells[0].split()[0]
        elif sec == "属性":
            for k, c in enumerate(cells):
                if c == "所属势力" and k + 1 < len(cells):
                    faction = faction or cells[k + 1]
                elif c == "隐藏势力" and k + 1 < len(cells):
                    hidden = hidden or cells[k + 1]
    for raw in (faction, hidden):  # 所属势力优先；为空时回退隐藏势力；多个并列以「、」连接
        text = "、".join(re.findall(r"\[([^\]]*)\]\([^)]*\)", raw))
        if not text and raw and raw not in ("*无*", "-"):
            text = raw
        if text and not out["faction"]:
            out["faction"] = text
    return out


_ROSTER: dict = {"stamp": None, "data": None}


def _roster_names() -> list[tuple[str, str]]:
    out = []
    for line in ROSTER_FILE.read_text(encoding="utf-8").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out.append((parts[0].strip(), parts[1].strip()))
    return out


def load_roster(force: bool = False) -> list[dict]:
    """全量干员表（名 / 星级 / 职业 / 分支 / 势力 / 实装时间 / PRTS 链接），进程内缓存。"""
    names = _roster_names()
    stamp = [ROSTER_FILE.stat().st_mtime_ns, DATES_FILE.stat().st_mtime_ns]
    for name, _ in names:
        p = PRTS_DIR / name / f"{name}.md"
        try:
            s = p.stat()
            stamp.append((s.st_mtime_ns, s.st_size))
        except OSError:
            stamp.append(None)
    stamp = tuple(stamp)
    if not force and _ROSTER["data"] is not None and _ROSTER["stamp"] == stamp:
        return _ROSTER["data"]
    data = []
    for name, _url in names:
        brief = parse_prts_brief(name)
        data.append({
            "name": name,
            "star": brief["star"],
            "cls": brief["cls"],
            "branch": brief["branch"],
            "faction": brief["faction"],
            "date": launch_date(name) or "",
            "url": "https://prts.wiki/w/" + urllib.parse.quote(name),
        })
    _ROSTER["data"], _ROSTER["stamp"] = data, stamp
    return data

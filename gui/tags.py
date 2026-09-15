# -*- coding: utf-8 -*-
"""玩家分文件的区块解析与官方分文件的条目解析。"""

from __future__ import annotations

import pathlib
import re

from .config import DEF_ANY, DEF_RE, H2_START, H2_STOP, KNOWN_COLS, OFFICIAL_DIR, OFFICIAL_FILES
from .md import is_sep_row, row_op, sig_of, split_cells


def parse_player_blocks(path: pathlib.Path, tag_name: str) -> list[dict]:
    """玩家分文件 → 区块（一张连续表 = 一个区块）。

    只认「## 成员表 / ## §A」区间内、表头首列为「干员」且列名在白名单内的表；
    列序与列数不限定（「编号」「子 TAG」有则带出，无则为空串）。
    每块给出 label（最近的 ###/#### 标题）、表头行号、排序方式与逐行条目。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[dict] = []
    h2 = h3 = h4 = ""
    inside = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            h2, h3, h4 = line, "", ""
            inside = line.startswith(H2_START) and not line.startswith(H2_STOP)
            i += 1
            continue
        if line.startswith("### "):
            h3, h4 = line, ""
            i += 1
            continue
        if line.startswith("#### "):
            h4 = line
            i += 1
            continue
        if not inside or not line.lstrip().startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        table = lines[i:j]
        header = split_cells(table[0])
        if not (header and header[0] == "干员" and "条件" in header and "备注" in header
                and all(c in KNOWN_COLS for c in header)):
            i = j
            continue
        ci, ni = header.index("条件"), header.index("备注")
        sub_col = header.index("子 TAG") if "子 TAG" in header else None
        cid_col = header.index("编号") if "编号" in header else None
        label = (h4 or h3 or h2).lstrip("#").strip()
        rows = []
        for k, raw in enumerate(table):
            if k == 0:
                continue
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            rows.append({
                "line": i + k + 1,
                "raw": raw,
                "op": row_op(cells),
                "cid": cells[cid_col] if cid_col is not None else "",
                "cond": cells[ci],
                "note": cells[ni],
                "src": cells[len(header) - 1] if len(header) > ni else "",
                "sub": cells[sub_col] if sub_col is not None else "",
            })
        blocks.append({
            "id": f"p:{path.name}#{len(blocks)}",
            "sig": sig_of(label, table[0]),
            "file": path.name,
            "tag": tag_name,
            "label": label,
            "header": header,
            "line": i + 1,
            "sort": "none" if path.name.startswith("12-") else "date",
            "rows": rows,
        })
        i = j
    return blocks


def parse_official_entries(path: pathlib.Path, category: str) -> list[dict]:
    """官方分文件 → 条目（粗体定义行 + 其后唯一一张成员表 = 一个区块）。

    官方成员表列头为「干员｜编号｜条件｜备注」4 列；列数按表头实读，
    未加「编号」列的 3 列表（干员｜条件｜备注）同样可解析。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []
    i = 0
    while i < len(lines):
        m = DEF_RE.match(lines[i].strip())
        declared = bool(m)
        if not m:
            m = DEF_ANY.match(lines[i].strip())
        if not m:
            i += 1
            continue
        j = i + 1
        notes = []
        while j < len(lines) and not lines[j].lstrip().startswith("|"):
            s = lines[j].strip()
            if s.startswith(">"):
                notes.append(s)
            j += 1
        k = j
        while k < len(lines) and lines[k].lstrip().startswith("|"):
            k += 1
        table = lines[j:k]
        header = split_cells(table[0]) if table else []
        if not (header and header[0] == "干员" and "条件" in header and "备注" in header
                and all(c in KNOWN_COLS for c in header)):
            i = k if k > i else i + 1
            continue
        ci, ni = header.index("条件"), header.index("备注")
        cid_col = header.index("编号") if "编号" in header else None
        rows = []
        for t, raw in enumerate(table[1:], start=1):
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            rows.append({
                "line": j + t + 1,
                "raw": raw,
                "op": row_op(cells),
                "cid": cells[cid_col] if cid_col is not None else "",
                "cond": cells[ci],
                "note": cells[ni],
                "src": "",
                "sub": "",
            })
        entries.append({
            "name": m.group("name"),
            "category": category,
            "file": path.name,
            "def_line": i + 1,
            "def_raw": lines[i],
            "declared": declared,
            "n_declared": int(m.group("n")) if declared else None,
            "first_declared": m.group("d") if declared else None,
            "notes": notes,
            "blocks": [{
                "id": f"o:{path.name}#{len(entries)}",
                "sig": sig_of(m.group("name"), table[0]),
                "file": path.name,
                "tag": m.group("name"),
                "cat": category,
                "label": m.group("name"),
                "header": header,
                "line": j + 1,
                "sort": "date",
                "rows": rows,
            }],
        })
        i = k
    return entries


def load_official_entries() -> list[dict]:
    out: list[dict] = []
    for cat, fn in OFFICIAL_FILES:
        path = OFFICIAL_DIR / fn
        if path.exists():
            out.extend(parse_official_entries(path, cat))
    return out

# -*- coding: utf-8 -*-
"""分文件（tag-part/1）→ 前端模型块：玩家成员表与官方条目表。

行不再携带行号/原文（写回改按「块 id + 行下标 i + 行现值」寻址）；每块带文件摘要 fd
（mtime/size/digest），供写回做乐观并发校验。块 id 形如 `p:<文件名>#<成员表序号>` /
`o:<文件名>#<条目序号>`，sig = partdoc.sig_of(label, columns)。
"""

from __future__ import annotations

import pathlib
import re

import partdoc
from .config import KNOWN_COLS, OFFICIAL_DIR, OFFICIAL_FILES


def _fd(path: pathlib.Path) -> dict:
    st = path.stat()
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "digest": partdoc.digest(path)}


def _clean_op(cell: str) -> str:
    return cell.replace("**", "").strip()


def leaf_values(subs: list[dict]) -> list[str]:
    """subTags → 末端取值（值不是任何其它条的 group）。与 output-standard §4.3「末端子 TAG 即可筛选项」同义。"""
    parents = {s.get("group") for s in subs}
    out: list[str] = []
    for s in subs:
        v = s.get("value")
        if v and v not in parents and v not in out:
            out.append(v)
    return out


def display_label(label: str) -> str:
    """成员表标题 → 树节点文案：去 md 强调、去序号前缀与人数括注，但保留后半句的短定义。

    `表 1 · 超远距离打击（本体 / 光束 / …）` → `超远距离打击（本体 / 光束 / …）`
    `一、治疗·减免·防御·法抗·庇护（41 人）`   → `治疗·减免·防御·法抗·庇护`
    `2B 陷阱（占用部署数 0、…）`               → `陷阱（占用部署数 0、…）`
    """
    s = label.replace("**", "").strip()
    s = re.sub(r"^表\s*\d+\s*·\s*", "", s)                 # 「表 1 · 」
    s = re.sub(r"^\d[A-Z]\s+", "", s)                      # 「2A 」「2B 」
    s = re.sub(r"^[一二三四五六七八九十]+、", "", s)        # 「一、」
    s = re.sub(r"（\s*\d+\s*人\s*）\s*$", "", s)            # 「（41 人）」
    return s.strip() or label


def _rows_of(columns: list[str], rows: list[list[str]], num: str = "",
             h3: str = "", h4: str = "") -> list[dict]:
    ci, ni = columns.index("条件"), columns.index("备注")
    sub_col = columns.index("子 TAG") if "子 TAG" in columns else (
        columns.index("范围") if "范围" in columns else None)
    cid_col = columns.index("编号") if "编号" in columns else None
    src_col = columns.index("依据") if "依据" in columns else None
    gen = _gen()
    out = []
    for k, cells in enumerate(rows):
        cons: list[dict] = []
        if num and gen is not None:
            clean = [gen.clean_cell(c) for c in cells]
            try:
                cons = gen.player_subtags(num, h3, h4, columns, clean, clean[ci], clean[ni])[1]
            except Exception:  # noqa: BLE001  （解析失败只影响筛选，不该让整页挂掉）
                cons = []
        out.append({
            "i": k,
            "op": _clean_op(cells[0]),
            "cid": cells[cid_col] if cid_col is not None else "",
            "cond": cells[ci],
            "note": cells[ni],
            "src": cells[src_col] if src_col is not None else "",
            "sub": cells[sub_col] if sub_col is not None else "",
            "subtags": cons,                      # 原始（组/值/detail），供树与子 TAG 计数
            "subs": leaf_values(cons),            # 末端取值，供干员列表按子 TAG 过滤
        })
    return out


def _gen():
    """生成器的 player_subtags（与产物、荐页作用域同源）。只在需要时导入，避免顶层循环。"""
    import generate_results as gen  # noqa: PLC0415
    return gen


def block_display(h3: str, h4: str, label: str) -> str:
    """树的区块文案：`####` 子表带上所属 `###` 父级（`远距控制 · 独立达成`），
    否则只显示自身；两者都经 display_label 规范化。"""
    own = display_label(label)
    if not h4:
        return own
    parent = display_label(h3)
    return own if parent == own else f"{parent} · {own}"


def parse_player_blocks(path: pathlib.Path, tag_name: str) -> list[dict]:
    """玩家分文件 → 区块（一张成员表 = 一个区块）。

    只认 `## 成员表…` 节内、表头首列为「干员」且列名在白名单内的表；
    label = 最近的 ###/#### 标题（与写回签名同源），display = 树节点文案。
    """
    doc = partdoc.load(path)
    fd = _fd(path)
    num = path.name[:2]
    sort = "none" if path.name.startswith("12-") else "date"
    blocks: list[dict] = []
    for t in partdoc.iter_member_tables(doc):
        if not all(c in KNOWN_COLS for c in t["columns"]):
            continue
        blocks.append({
            "id": f"p:{path.name}#{t['idx']}",
            "sig": partdoc.sig_of(t["label"], t["columns"]),
            "file": path.name,
            "tag": tag_name,
            "label": t["label"],
            "display": block_display(t["h3"], t["h4"], t["label"]),
            "header": t["columns"],
            "sort": sort,
            "fd": fd,
            "rows": _rows_of(t["columns"], t["rows"], num, t["h3"], t["h4"]),
        })
    return blocks


def scope_members(path: pathlib.Path) -> dict[str, list[str]]:
    """子作用域取值 → 该作用域内的干员名（按行出现顺序去重）。

    「子作用域」＝荐下沉用的子 TAG 取值（`_recommend.json` 键 `TAG/取值`）。判定与
    产物同源：直接用生成器 `tools/generate_results.py` 的 `player_subtags()`
    （取值＝行级 subTags 的 value，规则见 docs/output-standard.md §4.3），
    因此与 `results/operator-tags.json` 的 `recommendedBySub` 取值逐条一致。
    阵容组合（12）的行不带 subTags（其作用域取自组合元数据），返回空表。

    生成器只能就地导入：它以脚本方式运行时（`__main__`）会再以模块名导入一次自己，
    若改由 config 顶层导入，则在 `gui.roster → gui.config` 处形成循环。
    """
    import generate_results as gen  # noqa: PLC0415  （tools/ 已在 .config 引导进 sys.path）

    out: dict[str, list[str]] = {}
    if path.name.startswith("12-"):
        return out
    num = path.name[:2]
    for t in partdoc.iter_member_tables(partdoc.load(path)):
        cols = t["columns"]
        ci, ni = cols.index("条件"), cols.index("备注")
        for cells in t["rows"]:
            clean = [gen.clean_cell(c) for c in cells]
            op = clean[0]
            for s in gen.player_subtags(num, t["h3"], t["h4"], cols, clean, clean[ci], clean[ni])[1]:
                names = out.setdefault(s["value"], [])
                if op not in names:
                    names.append(op)
    return out


def parse_official_entries(path: pathlib.Path, category: str) -> list[dict]:
    """官方分文件 → 条目（定义行 + 唯一成员表 = 一个区块）。"""
    doc = partdoc.load(path)
    fd = _fd(path)
    entries: list[dict] = []
    for idx, e in enumerate(doc["entries"]):
        table = next(it for it in e["items"] if it["t"] == "table")
        columns = table["columns"]
        entries.append({
            "name": e["name"],
            "category": category,
            "file": path.name,
            "blocks": [{
                "id": f"o:{path.name}#{idx}",
                "sig": partdoc.sig_of(e["name"], columns),
                "file": path.name,
                "tag": e["name"],
                "cat": category,
                "label": e["name"],
                "display": e["name"],
                "header": columns,
                "sort": "date",
                "fd": fd,
                "rows": _rows_of(columns, table["rows"]),
            }],
        })
    return entries


def load_official_entries() -> list[dict]:
    out: list[dict] = []
    for cat, fn in OFFICIAL_FILES:
        path = OFFICIAL_DIR / fn
        if path.exists():
            out.extend(parse_official_entries(path, cat))
    return out

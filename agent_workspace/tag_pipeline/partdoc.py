# -*- coding: utf-8 -*-
"""分文件（tag-part/1）的读写、渲染与校验——TAG 中间产物的唯一读写实现。

格式：
- 一文件一 JSON；玩家文件 = {format, kind:"player", num, name, title, body:[Item], trailing_newlines}；
  官方文件 = {format, kind:"official", entries:[{name, rest, items:[Item]}], trailing_newlines}。
- Item = {"t":"p","lines":[…原文行…]}(散文/引用/空行，原样)
       | {"t":"heading","level":n,"text":"### …"}(原文行)
       | {"t":"table","columns":[…],"rows":[[单元格,…],…]}（单元格已去首尾空白、单行、无 ASCII 竖线）。
- 官方条目头（`**名**（N 人 · 首现 日期）：定义`）不落盘，渲染时按 rows 与 _launch_dates.json 派生。
- 规范写出：UTF-8 无 BOM、CRLF、缩进 2、ensure_ascii=False、文件尾一个换行、原子替换。

本模块只依赖标准库；GUI、工具、合并脚本、审计脚本的一切读写都应经此，不再直接动 md。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

FORMAT = "tag-part/1"
KNOWN_COLS = {"干员", "编号", "子 TAG", "范围", "条件", "备注", "依据"}
PLAYER_ORDER = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "13", "12")

TAG_DIR = Path(__file__).resolve().parent
PLAYER_DIR = TAG_DIR / "player_tags"
OFFICIAL_DIR = TAG_DIR / "official_tags"
DATES_FILE = PLAYER_DIR / "_launch_dates.json"

_MIDDOT = "·"  # 「N 人 · 首现」的间隔点（与合并脚本一致）
_dates_cache: dict[str, str] | None = None


# ---------------------------------------------------------------- 取数与校验

def dates() -> dict[str, str]:
    global _dates_cache
    if _dates_cache is None:
        _dates_cache = json.loads(DATES_FILE.read_text(encoding="utf-8"))
    return _dates_cache


def date_of(name: str) -> str | None:
    """实装日期：原名 → 去括号后缀名；查不到返回 None（与官方合并脚本 date_of 同义）。"""
    name = (name or "").strip()
    d = dates()
    if name in d:
        return d[name]
    base = re.split(r"[（(]", name)[0].strip()
    return d.get(base)


def clean_heading(text: str) -> str:
    return text.lstrip("#").strip()


def cell(row: list[str], columns: list[str], name: str) -> str:
    return row[columns.index(name)] if name in columns else ""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def validate(doc: dict, where: str = "") -> None:
    """结构自检：不合规即抛 ValueError（含定位信息）。"""
    tag = f"{where}: " if where else ""
    _require(doc.get("format") == FORMAT, f"{tag}format 应为 {FORMAT}")
    kind = doc.get("kind")
    _require(kind in ("player", "official"), f"{tag}kind 非法：{kind!r}")
    tn = doc.get("trailing_newlines")
    _require(isinstance(tn, int) and tn >= 0, f"{tag}trailing_newlines 非法：{tn!r}")

    def check_item(it: dict, in_members: bool) -> bool:
        t = it.get("t")
        if t == "p":
            _require(isinstance(it.get("lines"), list) and
                     all(isinstance(x, str) and "\n" not in x and "\r" not in x for x in it["lines"]),
                     f"{tag}p.lines 非法")
        elif t == "heading":
            _require(isinstance(it.get("level"), int) and 2 <= it["level"] <= 6 and
                     isinstance(it.get("text"), str) and
                     it["text"].startswith("#" * it["level"] + " "),
                     f"{tag}heading 非法：{it.get('text')!r}")
            h = clean_heading(it["text"])
            if it["level"] == 2:
                in_members = h.startswith("成员表")
        elif t == "table":
            cols, rows = it.get("columns"), it.get("rows")
            _require(isinstance(cols, list) and cols and all(isinstance(c, str) and c for c in cols),
                     f"{tag}table.columns 非法：{cols!r}")
            _require(isinstance(rows, list), f"{tag}table.rows 非法")
            for r in rows:
                _require(isinstance(r, list) and len(r) == len(cols),
                         f"{tag}table 行宽 {len(r) if isinstance(r, list) else r!r} ≠ 列数 {len(cols)}")
                for c in r:
                    _require(isinstance(c, str) and "\n" not in c and "\r" not in c and "|" not in c,
                             f"{tag}table 单元格非法：{c!r}")
            if in_members and cols[0] == "干员" and "条件" in cols and "备注" in cols:
                _require(set(cols) <= KNOWN_COLS,
                         f"{tag}成员表列超出白名单：{sorted(set(cols) - KNOWN_COLS)}")
        else:
            raise ValueError(f"{tag}未知元素类型：{t!r}")
        return in_members

    if kind == "player":
        _require(isinstance(doc.get("title"), str) and doc["title"].startswith("# "), f"{tag}title 非法")
        _require(isinstance(doc.get("num"), str) and isinstance(doc.get("name"), str),
                 f"{tag}num/name 非法")
        in_members = False
        for it in doc.get("body") or []:
            in_members = check_item(it, in_members)
    else:
        entries = doc.get("entries")
        _require(isinstance(entries, list) and entries, f"{tag}entries 非法")
        for e in entries:
            _require(isinstance(e.get("name"), str) and e["name"] and isinstance(e.get("rest"), str),
                     f"{tag}条目 name/rest 非法：{e.get('name')!r}")
            tables = [it for it in e.get("items") or [] if it.get("t") == "table"]
            _require(len(tables) == 1, f"{tag}条目「{e['name']}」应恰有 1 张表，实为 {len(tables)}")
            _require(tables[0]["columns"] == ["干员", "编号", "条件", "备注"],
                     f"{tag}条目「{e['name']}」列头异常：{tables[0]['columns']}")
            for it in e["items"]:
                check_item(it, False)


# ---------------------------------------------------------------- 读 / 写 / 渲染

def load(path: str | Path) -> dict:
    p = Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    validate(doc, p.name)
    return doc


def dump(doc: dict) -> str:
    """规范 JSON 文本（LF 行尾；落盘时经 save 转 CRLF）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2)


def save(doc: dict, path: str | Path) -> None:
    """原子写：同目录 .tmp + os.replace（PermissionError 重试，镜像 gui/md.write_atomic）。"""
    validate(doc, Path(path).name)
    p = Path(path)
    blob = (dump(doc).replace("\n", "\r\n") + "\r\n").encode("utf-8")
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(blob)
    for attempt in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    os.replace(tmp, p)


def digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def sig_of(label: str, columns: list[str]) -> str:
    return hashlib.sha1((label + "\n" + "|".join(columns)).encode("utf-8")).hexdigest()[:8]


def _render_item(it: dict) -> list[str]:
    t = it["t"]
    if t == "p":
        return list(it["lines"])
    if t == "heading":
        return [it["text"]]
    cols = it["columns"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out.extend("| " + " | ".join(r) + " |" for r in it["rows"])
    return out


def official_stat(entry: dict) -> tuple[int, str]:
    """官方条目 → (人数, 首现)：行数与前两列取日期（与合并脚本重算规则同义）。"""
    rows = [r for it in entry["items"] if it["t"] == "table" for r in it["rows"]]
    ds = [d for d in (date_of(r[0]) for r in rows) if d]
    return len(rows), (min(ds) if ds else "—")


def order_official_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """官方成员行 → (视图同序的行, 无日期者的姓名列表)。

    排序语义与官方合并脚本一致：有日期者按实装时间倒序（稳定排序，同日保持原文序），
    无日期者按原文序置后——合并脚本与生成器共用本函数，防止两处排序漂移。
    """
    dated = [(date_of(r[0]), r) for r in rows]
    known = [t for t in dated if t[0] is not None]
    unknown = [t for t in dated if t[0] is None]
    known.sort(key=lambda t: t[0], reverse=True)
    return [t[1] for t in known] + [t[1] for t in unknown], [t[1][0] for t in unknown]


def render(doc: dict) -> str:
    """JSON → md 文本（CRLF 行尾 + trailing_newlines 个结尾换行）。"""
    parts: list[str] = []
    if doc["kind"] == "player":
        parts.append(doc["title"])
        for it in doc["body"]:
            parts.extend(_render_item(it))
    else:
        for e in doc["entries"]:
            n, first = official_stat(e)
            parts.append(f"**{e['name']}**（{n} 人 · 首现 {first}）：{e['rest']}")
            for it in e["items"]:
                parts.extend(_render_item(it))
    return "\r\n".join(parts) + "\r\n" * doc["trailing_newlines"]


# ---------------------------------------------------------------- 遍历辅助

def player_files(directory: str | Path | None = None) -> list[tuple[str, str, Path]]:
    """[(num, name, path)]，按 PLAYER_ORDER 序（01..09,13,12），文件名须与编号一致。"""
    d = Path(directory) if directory else PLAYER_DIR
    out: list[tuple[str, str, Path]] = []
    for num in PLAYER_ORDER:
        hits = sorted(d.glob(f"{num}-*.json"))
        _require(len(hits) == 1, f"{d}: 编号 {num} 应恰有 1 个 .json，实为 {len(hits)}")
        out.append((num, hits[0].stem.split("-", 1)[1], hits[0]))
    extra = [p.name for p in d.glob("[0-9][0-9]-*.json") if p.stem[:2] not in PLAYER_ORDER]
    _require(not extra, f"{d}: 存在未登记编号的分文件：{extra}")
    return out


def member_tables(doc: dict):
    """玩家文件 → 逐张成员表 yield (h3, h4, columns, rows, idx)。

    h3/h4 语义与合并视图一致：进入 `## 成员表…` 节后，节标题即 h3；更深一级 ### 取代 h3；
    #### 记 h4（更高级标题到来即清空）。idx 为成员表序号（0 起）。
    """
    _require(doc.get("kind") == "player", "member_tables 仅适用于玩家文件")
    h3 = h4 = ""
    in_members = False
    idx = 0
    for it in doc["body"]:
        if it["t"] == "heading":
            lv, txt = it["level"], clean_heading(it["text"])
            if lv == 2:
                in_members = txt.startswith("成员表")
                h3, h4 = (txt if in_members else ""), ""
            elif lv == 3:
                if in_members:
                    h3, h4 = txt, ""
            elif lv == 4 and in_members:
                h4 = txt
        elif it["t"] == "table" and in_members:
            cols = it["columns"]
            if cols and cols[0] == "干员" and "条件" in cols and "备注" in cols:
                yield h3, h4, cols, it["rows"], idx
                idx += 1

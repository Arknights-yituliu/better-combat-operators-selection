# -*- coding: utf-8 -*-
"""干员 TAG 名单维护面板（本地网页版）。三个页签：

「荐」  只管玩家体感 TAG 的荐：左键干员 = 加荐，右键 = 取消荐，荐箱可排序。
「人工归纳」  上半筛选（左 TAG 树 / 右干员列表）、下半临时区、右侧全量干员摘选区：
    · 摘选区左键 = 以「扩展」方式放入临时区（并入后新行的条件/备注为空，自行填写）。
    · 干员行右键 = 扩展 / 移动 / 移除；移动会把源行的条件/备注/依据带到新行，
      落点成功后再删除源行；移除 = 直接删除该行。
    · 选中 TAG 子表（区块）后点临时区条目即并入；Ctrl 多选可一次并入多个区块，
      移动只允许落到一个区块。
    · 干员卡片内点击 条件 / 备注 即可编辑（Enter/✓ 保存，Esc/× 取消，不自动保存）。
「结果 JSON」  编辑 results/ 下的结果 JSON（规范：docs/output-standard.md）：
    · 「加载…」选 results/*.json，或「新建骨架」起一份符合规范的空文档；
    · 编辑只发生在内存（结构化卡片 + 源码视图共用同一份数据），点「保存…」才写盘，
      保存可选「覆盖已有文件」或「新建自定义文件名」，写盘前按规范列出问题但不阻断。

写入的文件（前两页即时落盘，「结果 JSON」页仅在点保存时写）：
    material_datas/tag_pipeline/player_tags/_recommend.json   （荐）
    material_datas/tag_pipeline/player_tags/NN-*.md           （成员行增删、条件/备注）
    material_datas/tag_pipeline/official_tags/[A-I]-*.md      （成员行增删、条件/备注、条目头人数重算）
    results/*.json                                             （结果 JSON 页保存）
    docs/player-tags-members.md、docs/official-tags-members.md 由合并脚本重新生成（只读）。

用法：
    .venv/Scripts/python.exe -X utf8 recommend_gui.py                  # 启动并打开浏览器
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --port 8520 --no-browser
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --check          # 只解析自检，不起服务
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
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

# 官方分模块清单（类别标题, 文件名），顺序与合并脚本一致
OFFICIAL_FILES: list[tuple[str, str]] = [(cat, fn) for cat, fns in offm.FILES for fn in fns]

# 成员表区间：与 recommend.py 保持一致
H2_START = rec.START_MARKS
H2_STOP = rec.STOP_MARKS

# 可写表格的列白名单：其它结构的表不参与写回
KNOWN_COLS = {"干员", "子 TAG", "条件", "备注", "依据"}

# 官方条目头：**名**（N 人 · 首现 日期）：定义
DEF_RE = re.compile(r"^\*\*(?P<name>.+?)\*\*（(?P<n>\d+) 人 · 首现 (?P<d>[\d-]+)）：(?P<rest>.*)$")
DEF_ANY = re.compile(r"^\*\*(?P<name>.+?)\*\*（.*?）：(?P<rest>.*)$")

LOCK = threading.RLock()
TOKEN = secrets.token_urlsafe(18)


class UserError(Exception):
    """可以直接展示给使用者的错误（code 供前端区分处理，如漂移 / 重名 / 解析失败）。"""

    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- 通用


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def row_op(cells: list[str]) -> str:
    return cells[0].replace("**", "").strip() if cells else ""


def sig_of(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:8]


def launch_date(name: str) -> str | None:
    """实装时间：与合并脚本同口径（原名 → 去形态括号）。"""
    name = name.strip()
    if name in offm.DATES:
        return offm.DATES[name]
    base = re.split(r"[（(]", name)[0].strip()
    return offm.DATES.get(base)


# ---------------------------------------------------------------- 文档注册表


def doc_registry() -> dict[str, dict]:
    """可写文件（basename → 描述）。玩家 13 + 官方 13，白名单解析，无路径穿越。"""
    reg: dict[str, dict] = {}
    for name, path in rec.load_tags():
        reg[path.name] = {"kind": "player", "path": path, "tag": name, "num": path.name[:2]}
    for cat, fn in OFFICIAL_FILES:
        path = OFFICIAL_DIR / fn
        reg.setdefault(fn, {"kind": "official", "path": path, "category": cat})
    return reg


# ---------------------------------------------------------------- 解析


def parse_player_blocks(path: pathlib.Path, tag_name: str) -> list[dict]:
    """玩家分文件 → 区块（一张连续表 = 一个区块）。

    只认「## 成员表 / ## §A」区间内、表头首列为「干员」且列名在白名单内的表。
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
            "sort": "none" if path.name.startswith("13-") else "date",
            "rows": rows,
        })
        i = j
    return blocks


def parse_official_entries(path: pathlib.Path, category: str) -> list[dict]:
    """官方分文件 → 条目（粗体定义行 + 其后唯一一张 3 列表 = 一个区块）。"""
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
        rows = []
        for t, raw in enumerate(table[1:], start=1):
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            rows.append({
                "line": j + t + 1,
                "raw": raw,
                "op": row_op(cells),
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


# ---------------------------------------------------------------- 干员基本信息


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


# ---------------------------------------------------------------- 模型


def build_model(fresh: bool = False) -> dict:
    recommend = rec.load_recommend()
    player_tags = []
    for name, path in rec.load_tags():
        player_tags.append({
            "num": path.name[:2],
            "name": name,
            "file": path.name,
            "recommend": recommend.get(name, []),
            "blocks": parse_player_blocks(path, name),
        })
    official_entries = load_official_entries()
    for n, e in enumerate(official_entries):
        e["id"] = f"o:{e['file']}#e{n}"
    known = {t["name"] for t in player_tags}
    members_of = {
        t["name"]: {r["op"] for b in t["blocks"] for r in b["rows"]}
        for t in player_tags
    }
    stale = [
        {"tag": tag, "op": op}
        for tag, ops in recommend.items() if tag in known
        for op in ops if op not in members_of[tag]
    ]
    return {
        "player_tags": player_tags,
        "official_entries": official_entries,
        "roster": load_roster(fresh),
        "recommend": recommend,
        "stale": stale,
        "unknown_tags": [t for t in recommend if t not in known],
    }


# ---------------------------------------------------------------- 写回


def write_atomic(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    os.replace(tmp, path)


class Doc:
    """一次读入的文档：按原始行号（uid）寻址增删改，最后整体原子写回。"""

    def __init__(self, path: pathlib.Path, kind: str):
        self.path, self.kind = path, kind
        self.text = path.read_text(encoding="utf-8", newline="")
        self.eol = "\r\n" if "\r\n" in self.text else "\n"
        self.units: list[list] = [[i + 1, t] for i, t in enumerate(self.text.splitlines(keepends=True))]

    def text_of(self, uid: int) -> str:
        for u in self.units:
            if u[0] == uid:
                return u[1].rstrip("\r\n")
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def replace(self, uid: int, text_no_eol: str) -> None:
        for u in self.units:
            if u[0] == uid:
                eol = "\r\n" if u[1].endswith("\r\n") else ("\n" if u[1].endswith("\n") else "")
                u[1] = text_no_eol + eol
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def insert_before(self, uid: int, text_no_eol: str) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                self.units.insert(i, [-1, text_no_eol + self.eol])
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def insert_after(self, uid: int, text_no_eol: str) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                if not u[1].endswith(("\n", "\r")):
                    u[1] += self.eol
                self.units.insert(i + 1, [-1, text_no_eol + self.eol])
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def delete(self, uid: int) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                del self.units[i]
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def rows_after(self, header_uid: int) -> list[list]:
        """表头之后连续以 | 开头的行（含分隔行）。"""
        out, started = [], False
        for u in self.units:
            if u[0] == header_uid:
                started = True
                continue
            if not started:
                continue
            if u[1].lstrip().startswith("|"):
                out.append(u)
            else:
                break
        return out

    def render(self) -> str:
        return "".join(u[1] for u in self.units)


def parse_block_id(bid: str) -> tuple[str, str, int]:
    kind, _, rest = bid.partition(":")
    fname, _, idx = rest.rpartition("#")
    try:
        return kind, fname, int(idx)
    except ValueError:
        raise UserError(f"无效的子表编号：{bid}") from None


def resolve_block(reg: dict[str, dict], bid: str, sig: str, fname: str | None = None) -> tuple[dict, dict]:
    """校验并取回区块（含所在文件描述）。"""
    kind, fname2, idx = parse_block_id(bid)
    fname = fname2 or fname or ""
    if fname not in reg:
        raise UserError(f"未知文件：{fname}")
    info = reg[fname]
    if info["kind"] == "player":
        blocks = parse_player_blocks(info["path"], info["tag"])
    else:
        blocks = [b for e in parse_official_entries(info["path"], info["category"]) for b in e["blocks"]]
    if not 0 <= idx < len(blocks):
        raise UserError("目标子表已不存在，请点「刷新数据」后重试")
    block = blocks[idx]
    if block["sig"] != sig:
        raise UserError("目标子表已被外部改动（标题或表头变化），请点「刷新数据」后重试")
    return block, info


def verify_row(doc: Doc, block: dict, line: int, raw: str) -> str:
    """校验行号与原始行一致、且该行属于目标区块，返回该行文本。"""
    cur = doc.text_of(line)
    if cur != raw:
        raise UserError("这一行已被外部改动（或行号已偏移），请点「刷新数据」后重试")
    table_lines = {u[0] for u in doc.rows_after(block["line"])}
    if line not in table_lines:
        raise UserError("该行已不在目标子表内，请点「刷新数据」后重试")
    return cur


def build_row(header: list[str], op: str, cells: dict[str, str]) -> str:
    parts = []
    for c in header:
        v = op if c == "干员" else (cells.get(c, "") or "")
        parts.append(f" {v} " if v else "  ")
    return "|" + "|".join(parts) + "|"


def check_value(label: str, value: str) -> str:
    if "|" in value:
        raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if "\n" in value or "\r" in value:
        raise UserError(f"{label}不能包含换行（表格单元格必须单行）")
    return value.strip()


def row_date(text: str) -> str | None:
    return launch_date(row_op(split_cells(text)))


def insert_position(doc: Doc, block: dict, op: str) -> tuple[str, int]:
    """返回 (before|after, uid)：按实装时间倒序插入；阵容组合或无日期则追加表尾。"""
    units = doc.rows_after(block["line"])
    data = [u for u in units if not is_sep_row(split_cells(u[1]))]
    if not data:
        seps = [u for u in units if is_sep_row(split_cells(u[1]))]
        return ("after", seps[0][0] if seps else block["line"])
    d = launch_date(op)
    if block["sort"] == "none" or not d:
        return ("after", data[-1][0])
    for uid, text in data:
        rd = row_date(text)
        if rd is None or rd < d:
            return ("before", uid)
    return ("after", data[-1][0])


def insert_into(doc: Doc, block: dict, op: str, cells: dict[str, str]) -> dict:
    existing = {r["op"] for r in block["rows"]}
    for uid, text in doc.rows_after(block["line"]):
        cells_now = split_cells(text)
        if not is_sep_row(cells_now) and cells_now:
            existing.add(row_op(cells_now))
    if op in existing:
        return {"skipped": True, "reason": "already-present"}
    text = build_row(block["header"], op, cells)
    where, uid = insert_position(doc, block, op)
    (doc.insert_before if where == "before" else doc.insert_after)(uid, text)
    return {"skipped": False, "raw": text}


def recompute_official_headers(doc: Doc) -> list[dict]:
    """重算官方条目头的（N 人 · 首现 日期）；只替换该段，格式自检不过则跳过。"""
    changed = []
    for entry in parse_official_entries(doc.path, ""):
        rows = [r for b in entry["blocks"] for r in b["rows"]]
        n = len(rows)
        dates = [launch_date(r["op"]) for r in rows]
        first = min([d for d in dates if d], default=None) or "—"
        if entry["n_declared"] == n and entry["first_declared"] == first:
            continue
        m = DEF_RE.match(entry["def_raw"])
        if not m:
            continue
        new = f"**{m.group('name')}**（{n} 人 · 首现 {first}）：{m.group('rest')}"
        if not DEF_RE.match(new):
            continue
        doc.replace(entry["def_line"], new)
        changed.append({"file": doc.path.name, "name": m.group("name"), "n": n, "first": first})
    return changed


def prune_recommend(removed: dict[str, set[str]]) -> dict[str, list[str]]:
    if not removed:
        return {}
    data = rec.load_recommend()
    pruned: dict[str, list[str]] = {}
    for tag, names in removed.items():
        ops = data.get(tag)
        if not ops:
            continue
        keep = [o for o in ops if o not in names]
        if len(keep) != len(ops):
            pruned[tag] = [o for o in ops if o in names]
            data[tag] = keep
    if pruned:
        rec.save_recommend(data, [t for t, _ in rec.load_tags()])
    return pruned


def apply_ops(payload: dict, dry_run: bool = False) -> dict:
    """人工归纳的批量变更：先全部校验、再在内存中执行、最后逐文件原子写回。"""
    ops = payload.get("ops") or []
    if not isinstance(ops, list) or not ops:
        raise UserError("没有要执行的操作")
    reg = doc_registry()
    docs: dict[str, Doc] = {}

    def doc_of(fname: str) -> Doc:
        if fname not in reg:
            raise UserError(f"未知文件：{fname}")
        if fname not in docs:
            docs[fname] = Doc(reg[fname]["path"], reg[fname]["kind"])
        return docs[fname]

    results, warnings = [], []
    removed: dict[str, set[str]] = {}  # 玩家 TAG → 被移出的干员（用于剪除失效的荐）
    for op in ops:
        kind = op.get("kind")
        rid = op.get("op_id")
        if kind == "delete":
            src = op.get("from") or {}
            block, info = resolve_block(reg, (src.get("block") or {}).get("id", ""), (src.get("block") or {}).get("sig", ""))
            doc = doc_of(block["file"])
            sraw = verify_row(doc, block, int(src.get("line", 0)), src.get("raw", ""))
            if info["kind"] == "player":
                removed.setdefault(info["tag"], set()).add(row_op(split_cells(sraw)))
            if not dry_run:
                doc.delete(int(src["line"]))
            results.append({"op_id": rid, "kind": "delete", "op": row_op(split_cells(sraw)),
                            "deleted": {"block": block["id"], "line": src.get("line")}})
        elif kind == "insert":
            targets = []
            for t in op.get("targets") or []:
                block, info = resolve_block(reg, t.get("id", ""), t.get("sig", ""))
                doc = doc_of(block["file"])
                got = insert_into(doc, block, op["op"], {
                    "条件": check_value("条件", op.get("cond", "")),
                    "备注": check_value("备注", op.get("note", "")),
                    "子 TAG": check_value("子 TAG", op.get("sub", "") or ""),
                })
                targets.append({"block": block["id"], "tag": block["tag"], "label": block["label"],
                                "skipped": got.get("skipped", False), "reason": got.get("reason", "")})
            results.append({"op_id": rid, "kind": "insert", "op": op["op"], "targets": targets})
        elif kind == "move":
            targets = op.get("targets") or []
            if len(targets) != 1:
                raise UserError("移动只能指定一个目标子表")
            src = op.get("from") or {}
            sblock, sinfo = resolve_block(reg, (src.get("block") or {}).get("id", ""), (src.get("block") or {}).get("sig", ""))
            sdoc = doc_of(sblock["file"])
            sraw = verify_row(sdoc, sblock, int(src.get("line", 0)), src.get("raw", ""))
            scells = split_cells(sraw)
            tblock, tinfo = resolve_block(reg, targets[0].get("id", ""), targets[0].get("sig", ""))
            tdoc = doc_of(tblock["file"])
            if tblock["id"] == sblock["id"]:
                raise UserError("源与目标是同一个子表，无需移动")
            values = {}
            for col in KNOWN_COLS:
                if col in sblock["header"] and col != "干员":
                    values[col] = scells[sblock["header"].index(col)]
            opname = row_op(scells)
            if sinfo["kind"] == "player":
                removed.setdefault(sinfo["tag"], set()).add(opname)
            got = insert_into(tdoc, tblock, opname, values)
            dropped = {c: values[c] for c in ("子 TAG", "依据") if values.get(c) and c not in tblock["header"]}
            if got.get("skipped"):
                results.append({"op_id": rid, "kind": "move", "op": opname, "skipped": True,
                                "reason": f"「{opname}」已在目标子表内，源行未删除"})
            else:
                if not dry_run:
                    sdoc.delete(int(src["line"]))
                results.append({"op_id": rid, "kind": "move", "op": opname,
                                "from": {"block": sblock["id"], "file": sblock["file"], "line": src.get("line")},
                                "to": {"block": tblock["id"], "file": tblock["file"], "raw": got.get("raw")},
                                "dropped": dropped})
        else:
            raise UserError(f"未知操作：{kind}")

    changed_kinds = {docs[f].kind for f in docs} if docs else set()
    recomputed = []
    for doc in docs.values():
        if doc.kind == "official":
            recomputed.extend(recompute_official_headers(doc))

    empty_blocks = []
    for fname, doc in docs.items():
        info = reg[fname]
        if info["kind"] == "player":
            for b in parse_player_blocks(doc.path, info["tag"]):
                if not b["rows"]:
                    empty_blocks.append(b["id"])
    if empty_blocks:
        warnings.append("有子表变为空表：" + "、".join(empty_blocks))

    pruned = prune_recommend(removed) if not dry_run else {}

    merge = {}
    if not dry_run:
        for fname, doc in docs.items():
            write_atomic(doc.path, doc.render())
        if payload.get("automerge", True):
            if "player" in changed_kinds:
                merge["player"] = run_merge_script(MERGE_PLAYER)
            if "official" in changed_kinds:
                merge["official"] = run_merge_script(MERGE_OFFICIAL)
    return {"ok": True, "results": results, "files": sorted(docs),
            "recomputed_headers": recomputed, "pruned_recommend": pruned,
            "empty_blocks": empty_blocks, "merge": merge, "warnings": warnings}


def save_cell(file: str, line_no: int, original: str, cond: str, note: str) -> dict:
    """只替换成员表该行的条件/备注两格；行尾、依据列、其它行原样保留。"""
    reg = doc_registry()
    if file not in reg:
        raise UserError(f"未知文件：{file}")
    path = reg[file]["path"]
    text = path.read_text(encoding="utf-8", newline="")  # 保留原 CRLF
    lines = text.splitlines(keepends=True)
    if not 1 <= line_no <= len(lines):
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")
    cur = lines[line_no - 1].rstrip("\r\n")
    if cur != original:
        raise UserError("这一行已被外部改动（或行号已偏移），请点「刷新数据」后重试")

    warn = ""
    new_cond, new_note = cond, note
    for label, value in (("条件", cond), ("备注", note)):
        if "|" in value:
            raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if "\n" in cond or "\r" in cond or "\n" in note or "\r" in note:
        new_cond = re.sub(r"\s*[\r\n]+\s*", " ", cond)
        new_note = re.sub(r"\s*[\r\n]+\s*", " ", note)
        warn = "换行已转为空格（表格单元格必须单行）"
    new_cond, new_note = new_cond.strip(), new_note.strip()

    i = line_no - 1
    while i > 0 and lines[i - 1].lstrip().startswith("|"):
        i -= 1
    header = split_cells(lines[i].rstrip("\r\n"))
    cells = split_cells(cur)
    if len(cells) != len(header) or "条件" not in header or "备注" not in header:
        raise UserError("该行所在表格结构异常，无法安全写回（条件/备注列未识别）")
    parts = cur.split("|")  # 首尾为空串，第 k 格 = parts[k+1]（含原有空白）
    for idx, value in ((header.index("条件"), new_cond), (header.index("备注"), new_note)):
        parts[idx + 1] = f" {value} "
    new_line = "|".join(parts)
    lines[line_no - 1] = new_line + lines[line_no - 1][len(cur):]
    write_atomic(path, "".join(lines))
    return {"ok": True, "line": line_no, "raw": new_line, "cond": new_cond, "note": new_note, "warn": warn}


def run_merge_script(script: pathlib.Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {"ok": proc.returncode == 0, "returncode": proc.returncode,
            "out": (proc.stdout or "").strip(), "err": (proc.stderr or "").strip()}


def run_merge(which: str = "both") -> dict:
    out: dict = {}
    if which in ("player", "both"):
        out["player"] = run_merge_script(MERGE_PLAYER)
    if which in ("official", "both"):
        out["official"] = run_merge_script(MERGE_OFFICIAL)
    out["ok"] = all(v["ok"] for v in out.values())
    return out


def apply_recommend(payload: dict) -> dict:
    action = payload.get("action")
    tags = rec.load_tags()
    names = [t for t, _ in tags]
    tag = payload.get("tag", "")
    if tag not in names:
        raise UserError(f"未知 TAG：{tag}")
    data = rec.load_recommend()
    ops = data.setdefault(tag, [])
    op = payload.get("op", "")

    if action in ("add", "first", "remove", "move"):
        members = rec.main_table_members(dict(tags)[tag])
        if action != "remove" and op not in members:
            raise UserError(f"「{op}」不是「{tag}」成员表内的干员，不能设为荐")
        if action == "add":
            if op in ops:
                return {"ok": True, "noop": "已是荐", "recommend": data}
            ops.append(op)
        elif action == "first":
            if op in ops:
                ops.remove(op)
            ops.insert(0, op)
        elif action == "remove":
            if op not in ops:
                return {"ok": True, "noop": "本就不是荐", "recommend": data}
            ops.remove(op)
        elif action == "move":
            if op not in ops:
                raise UserError(f"「{op}」不在「{tag}」的荐名单中")
            k = ops.index(op)
            nk = min(max(k + int(payload.get("delta", 0)), 0), len(ops) - 1)
            ops.pop(k)
            ops.insert(nk, op)
    elif action == "clear":
        ops.clear()
    else:
        raise UserError(f"未知操作：{action}")

    rec.save_recommend(data, names)
    return {"ok": True, "recommend": {k: v for k, v in data.items() if v}}


# ---------------------------------------------------------------- 结果 JSON（results/）

RESULTS_DIR = ROOT / "results"
NAME_RE = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,100}\.json$', re.IGNORECASE)
WIN_RESERVED = {"con", "prn", "aux", "nul",
                *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
RESULT_CATEGORIES = ["A 控制·异常", "B 伤害类型", "C 生存与增益", "D 部署与编队", "E 技力与技能资源",
                     "F 治疗与支援", "G 召唤物", "H 攻击行为特征", "I 全场光环"]
RESULT_CLASSES = ["先锋", "近卫", "狙击", "重装", "医疗", "辅助", "术师", "特种"]
RESULT_TOP_KEYS = ("version", "updated", "operators", "tags")
DOC_LEAK_HINTS = ("依据", "评定标准", "证据", "检索记录", "边界与排除", "待开发者确认")
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DOC_LINE_RE = re.compile(r"\.md:\d+")


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def safe_name(name) -> str:
    """results/ 下的文件名白名单：无路径分隔符/控制字符，必须 .json 结尾，不出目录。"""
    if not isinstance(name, str) or not name or name != name.strip():
        raise UserError("文件名不合法（不能为空或首尾有空白）", "filename")
    if name.startswith(".") or not NAME_RE.fullmatch(name):
        raise UserError('文件名只能含中文/字母/数字/空格/._-，且必须以 .json 结尾', "filename")
    if name.endswith((".", " ")) or pathlib.PurePath(name).stem.lower() in WIN_RESERVED:
        raise UserError("文件名不合法（Windows 保留名，或以点/空格结尾）", "filename")
    path = (RESULTS_DIR / name).resolve()
    if path.parent != RESULTS_DIR.resolve() or path.name != name:
        raise UserError("文件名不合法（越出 results/ 目录）", "filename")
    return name


def list_results() -> dict:
    files = []
    if RESULTS_DIR.exists():
        for entry in os.scandir(RESULTS_DIR):
            if entry.is_file() and entry.name.lower().endswith(".json"):
                st = entry.stat()
                files.append({"name": entry.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns})
    files.sort(key=lambda f: -f["mtime_ns"])
    return {"ok": True, "dir": "results", "exists": RESULTS_DIR.exists(), "today": today_str(),
            "default": "operator-tags.json", "files": files}


def load_results(payload: dict) -> dict:
    name = safe_name(payload.get("file", ""))
    path = RESULTS_DIR / name
    if not path.exists() or not path.is_file():
        raise UserError(f"文件不存在：{name}", "notfound")
    raw = path.read_text(encoding="utf-8-sig", newline="")  # utf-8-sig 顺手吃掉 BOM
    eol = "crlf" if "\r\n" in raw else "lf"
    text = raw.replace("\r\n", "\n")
    parsed, error = True, ""
    try:
        json.loads(text)
    except Exception as exc:  # noqa: BLE001
        parsed, error = False, str(exc)
    st = path.stat()
    return {"ok": True, "file": name, "text": text, "parsed": parsed, "error": error, "eol": eol,
            "mtime_ns": st.st_mtime_ns, "size": st.st_size, "today": today_str()}


def render_results(doc, eol: str = "crlf") -> str:
    """仓库既有落盘风格：ensure_ascii=False、2 空格缩进、末尾换行（eol 决定 LF/CRLF）。"""
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", "\r\n") if eol == "crlf" else text


def validate_results(doc) -> tuple[list[dict], dict | None]:
    """按 docs/output-standard.md 校验结果 JSON；只列问题，不做阻断。"""
    problems: list[dict] = []

    def add(level, code, path, loc, label, msg):
        problems.append({"level": level, "code": code, "path": path, "loc": loc,
                         "label": label, "message": msg})

    if not isinstance(doc, dict):
        add("error", "T1", "", [], "", f"顶层必须是 JSON 对象（当前是 {type(doc).__name__}）")
        return problems, None

    for key in RESULT_TOP_KEYS:
        if key not in doc:
            add("error", "T2", key, [key], "", f"缺少顶层字段 {key}")
    for key in doc:
        if key not in RESULT_TOP_KEYS:
            add("warn", "T6", key, [key], "", f"顶层出现规范之外的字段「{key}」")
    version = doc.get("version")
    if not (isinstance(version, str) and re.fullmatch(r"v[1-9]\d*", version)):
        add("error", "T3", "version", ["version"], "", f"version 应为 v1、v2…（当前 {version!r}）")
    updated = doc.get("updated")
    try:
        ok_date = isinstance(updated, str) and bool(DATE_RE.match(updated)) and bool(time.strptime(updated, "%Y-%m-%d"))
    except ValueError:
        ok_date = False
    if not ok_date:
        add("error", "T4", "updated", ["updated"], "", f"updated 应为 yyyy-MM-dd 的真实日期（当前 {updated!r}）")

    raw_ops, raw_tags = doc.get("operators"), doc.get("tags")
    if not isinstance(raw_ops, list):
        add("error", "T5", "operators", ["operators"], "", "operators 必须是数组")
        raw_ops = []
    if not isinstance(raw_tags, list):
        add("error", "T5", "tags", ["tags"], "", "tags 必须是数组")
        raw_tags = []

    # ---- operators[] ----
    names: dict[str, int] = {}
    dates: dict[str, str] = {}
    for i, op in enumerate(raw_ops):
        plc = ["operators", i]
        if not isinstance(op, dict):
            add("error", "O1", f"operators[{i}]", plc, "", "干员条目必须是对象")
            continue
        nm = op.get("name")
        if not isinstance(nm, str) or not nm.strip():
            add("error", "O2", f"operators[{i}].name", plc + ["name"], "", "缺少干员名 name")
        else:
            if nm in names:
                add("error", "O4", f"operators[{i}].name", plc + ["name"], nm, f"干员名重复（首次出现在 operators[{names[nm]}]）")
            else:
                names[nm] = i
            dates[nm] = op.get("releaseDate", "") if isinstance(op.get("releaseDate"), str) else ""
        for field in ("rarity", "class", "branch", "faction", "releaseDate", "prtsUrl"):
            if field not in op:
                add("error", "O2", f"operators[{i}].{field}", plc + [field], str(nm or ""), f"缺少字段 {field}")
        rarity = op.get("rarity")
        if "rarity" in op and (not isinstance(rarity, int) or isinstance(rarity, bool) or not 1 <= rarity <= 6):
            add("error", "O3", f"operators[{i}].rarity", plc + ["rarity"], str(nm or ""), f"rarity 应为 1–6 的整数（当前 {rarity!r}）")
        cls = op.get("class")
        if "class" in op and cls not in RESULT_CLASSES:
            add("error", "O3", f"operators[{i}].class", plc + ["class"], str(nm or ""), f"class 应为八个职业之一（当前 {cls!r}）")
        if op.get("releaseDate") == "":
            add("warn", "O7", f"operators[{i}].releaseDate", plc + ["releaseDate"], str(nm or ""), "releaseDate 为空串")
        elif isinstance(op.get("releaseDate"), str) and not DATE_RE.match(op["releaseDate"]):
            add("error", "O3", f"operators[{i}].releaseDate", plc + ["releaseDate"], str(nm or ""), f"releaseDate 应为 yyyy-MM-dd（当前 {op['releaseDate']!r}）")
        if "prtsUrl" in op and not isinstance(op.get("prtsUrl"), str):
            add("error", "O3", f"operators[{i}].prtsUrl", plc + ["prtsUrl"], str(nm or ""), "prtsUrl 应为字符串")
        for key in op:
            if key not in ("name", "rarity", "class", "branch", "faction", "releaseDate", "prtsUrl"):
                add("warn", "O6", f"operators[{i}].{key}", plc + [key], str(nm or ""), f"规范之外的字段「{key}」")
    for i in range(1, len(raw_ops)):
        a, b = raw_ops[i - 1], raw_ops[i]
        if isinstance(a, dict) and isinstance(b, dict):
            da, db = a.get("releaseDate") or "", b.get("releaseDate") or ""
            if DATE_RE.match(da) and DATE_RE.match(db) and da < db:
                add("warn", "O5", f"operators[{i}].releaseDate", ["operators", i, "releaseDate"], str(b.get("name", "")),
                    f"未按实装时间倒序（{b.get('name')} {db} 排在 {a.get('name')} {da} 之后）")

    # ---- tags[] ----
    ids: dict[str, int] = {}
    prev_cat = ""
    seen_player = False
    stats = {"operators": len(raw_ops), "tags": len(raw_tags), "members": 0, "official": 0, "player": 0, "recommended": 0}
    for ti, tag in enumerate(raw_tags):
        plc = ["tags", ti]
        if not isinstance(tag, dict):
            add("error", "G1", f"tags[{ti}]", plc, "", "TAG 条目必须是对象")
            continue
        tid, tname, src = tag.get("id"), tag.get("name"), tag.get("source")
        label = str(tname or tid or "")
        for field in ("id", "name", "source", "members"):
            if field not in tag:
                add("error", "G2", f"tags[{ti}].{field}", plc + [field], label, f"缺少字段 {field}")
        if isinstance(tid, str):
            if tid in ids:
                add("error", "G4", f"tags[{ti}].id", plc + ["id"], label, f"id 重复（首次出现在 tags[{ids[tid]}]）")
            else:
                ids[tid] = ti
            if src == "official" and not re.fullmatch(r"[A-I]_[a-z0-9_]+", tid):
                add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"官方 id 形态应为 A_x 之类（当前 {tid!r}）")
            if src == "player" and not re.fullmatch(r"P(0[1-9]|1[0-3])", tid):
                add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"玩家 id 应为 P01–P13（当前 {tid!r}）")
        else:
            add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"id 应为字符串（当前 {tid!r}）")
        if src not in ("official", "player"):
            add("error", "G6", f"tags[{ti}].source", plc + ["source"], label, f'source 应为 "official" 或 "player"（当前 {src!r}）')
        if not isinstance(tname, str) or not tname.strip():
            add("error", "G2", f"tags[{ti}].name", plc + ["name"], label, "缺少 TAG 名 name")
        if src == "official":
            stats["official"] += 1
            cat = tag.get("category")
            if cat not in RESULT_CATEGORIES:
                add("error", "G7", f"tags[{ti}].category", plc + ["category"], label, f"category 应为九个类别之一（当前 {cat!r}）")
            else:
                if seen_player:
                    add("warn", "G12", f"tags[{ti}].source", plc + ["source"], label, "官方 TAG 出现在玩家 TAG 之后（规范：官方在前）")
                elif prev_cat and cat < prev_cat:
                    add("warn", "G12", f"tags[{ti}].category", plc + ["category"], label, f"官方 TAG 未按类别 A→I 排列（{cat} 排在 {prev_cat} 之后）")
                prev_cat = max(prev_cat, cat) if prev_cat else cat
            if "recommended" in tag:
                add("error", "G8", f"tags[{ti}].recommended", plc + ["recommended"], label, "官方 TAG 不应有 recommended 字段")
        elif src == "player":
            stats["player"] += 1
            seen_player = True
            if "recommended" not in tag:
                add("warn", "G9", f"tags[{ti}].recommended", plc + ["recommended"], label, "玩家 TAG 缺少 recommended（无荐时也应为空数组）")
        for key in tag:
            if key not in ("id", "name", "source", "category", "recommended", "members"):
                add("warn", "G11", f"tags[{ti}].{key}", plc + [key], label, f"规范之外的字段「{key}」")
        members = tag.get("members")
        if not isinstance(members, list):
            add("error", "G2", f"tags[{ti}].members", plc + ["members"], label, "members 必须是数组")
            members = []
        seen: dict[str, int] = {}
        for mi, mem in enumerate(members):
            mplc = plc + ["members", mi]
            stats["members"] += 1
            if not isinstance(mem, dict):
                add("error", "M1", f"tags[{ti}].members[{mi}]", mplc, label, "成员必须是对象")
                continue
            mname = mem.get("operator")
            if not isinstance(mname, str) or not mname.strip():
                add("error", "M2", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label, "缺少 operator")
                mname = ""
            else:
                if mname not in names:
                    add("error", "M3", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label + " · " + mname,
                        f"「{mname}」不在 operators[] 中")
                if mname in seen:
                    add("error", "M4", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label + " · " + mname,
                        f"同一 TAG 内重复（首次出现在 members[{seen[mname]}]）")
                else:
                    seen[mname] = mi
            cond = mem.get("condition")
            if not isinstance(cond, str) or not cond.strip():
                add("error", "M5", f"tags[{ti}].members[{mi}].condition", mplc + ["condition"], label + " · " + (mname or ""),
                    "condition 必填（精英 0·1 级即具备写「无」）")
            if "remark" in mem and (not isinstance(mem.get("remark"), str) or not mem.get("remark").strip()):
                add("warn", "M6", f"tags[{ti}].members[{mi}].remark", mplc + ["remark"], label + " · " + (mname or ""),
                    "remark 为空时应省略该字段")
            subs = mem.get("subTags")
            if subs is not None:
                if not isinstance(subs, list):
                    add("error", "M7", f"tags[{ti}].members[{mi}].subTags", mplc + ["subTags"], label + " · " + (mname or ""), "subTags 必须是数组")
                else:
                    pairs = set()
                    for si, sub in enumerate(subs):
                        splc = mplc + ["subTags", si]
                        if not isinstance(sub, dict) or not str(sub.get("group", "")).strip() or not str(sub.get("value", "")).strip():
                            add("error", "M7", f"tags[{ti}].members[{mi}].subTags[{si}]", splc, label + " · " + (mname or ""),
                                "子 TAG 需同时有 group 与 value")
                            continue
                        pairv = (sub["group"], sub["value"])
                        if pairv in pairs:
                            add("error", "M8", f"tags[{ti}].members[{mi}].subTags[{si}]", splc, label + " · " + (mname or ""),
                                f"同一组值重复：{sub['group']}／{sub['value']}")
                        pairs.add(pairv)
                        if "detail" in sub and sub["value"] != "触发时":
                            add("warn", "M9", f"tags[{ti}].members[{mi}].subTags[{si}].detail", splc + ["detail"], label + " · " + (mname or ""),
                                "detail 仅在 value 为「触发时」时使用")
            purl = mem.get("prtsUrl")
            if not isinstance(purl, str) or not purl.strip():
                add("error", "M10", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + (mname or ""), "prtsUrl 必填")
            else:
                head = purl.split("#", 1)[0]
                if not head.startswith("https://prts.wiki/w/"):
                    add("warn", "M11", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + (mname or ""),
                        "prtsUrl 应以 https://prts.wiki/w/ 开头")
                elif mname and urllib.parse.unquote(head[len("https://prts.wiki/w/"):]) != mname:
                    add("warn", "M11", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + mname,
                        "prtsUrl 的干员名与 operator 不一致（注意 percent 编码）")
            for key in mem:
                if key not in ("operator", "condition", "remark", "subTags", "prtsUrl"):
                    add("warn", "M12", f"tags[{ti}].members[{mi}].{key}", mplc + [key], label + " · " + (mname or ""),
                        f"规范之外的字段「{key}」")
        # 成员顺序（阵容组合按组合分组，跳过）
        if tid != "P13":
            for mi in range(1, len(members)):
                a, b = members[mi - 1], members[mi]
                if isinstance(a, dict) and isinstance(b, dict):
                    na, nb = a.get("operator"), b.get("operator")
                    da, db = dates.get(na, ""), dates.get(nb, "")
                    if DATE_RE.match(da) and DATE_RE.match(db) and da < db:
                        add("warn", "M13", f"tags[{ti}].members[{mi}]", plc + ["members", mi], label + " · " + str(nb),
                            f"成员未按实装时间倒序（{nb} {db} 排在 {na} {da} 之后）")
        rec = tag.get("recommended")
        if rec is not None:
            if not (isinstance(rec, list) and all(isinstance(x, str) for x in rec)):
                add("error", "G10", f"tags[{ti}].recommended", plc + ["recommended"], label, "recommended 应为字符串数组")
            else:
                stats["recommended"] += len(rec)
                dup = {x for x in rec if rec.count(x) > 1}
                for x in sorted(dup):
                    add("error", "R2", f"tags[{ti}].recommended", plc + ["recommended"], label, f"荐重复：{x}")
                for k, x in enumerate(rec):
                    if x not in seen:
                        add("error", "R1", f"tags[{ti}].recommended[{k}]", plc + ["recommended", k], label,
                            f"荐「{x}」不是本 TAG 的成员")

    # ---- 未被任何 TAG 引用的干员 ----
    used = set()
    for tag in raw_tags:
        if isinstance(tag, dict) and isinstance(tag.get("members"), list):
            for mem in tag["members"]:
                if isinstance(mem, dict) and isinstance(mem.get("operator"), str):
                    used.add(mem["operator"])
    for nm, i in names.items():
        if nm not in used:
            add("warn", "O8", f"operators[{i}]", ["operators", i], nm, f"「{nm}」未被任何 TAG 引用")

    # ---- 生产文档残留 / 非法字符 ----
    def walk(node, loc):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str):
                    for hint in DOC_LEAK_HINTS:
                        if hint in k:
                            add("warn", "T7", ".".join(str(x) for x in loc + [k]), loc + [k], "", f"键名含生产文档用语「{hint}」")
                    if SURROGATE_RE.search(k):
                        add("error", "X1", ".".join(str(x) for x in loc + [k]), loc + [k], "", "键名含非法字符（孤立代理项）")
                walk(v, loc + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, loc + [i])
        elif isinstance(node, str):
            if DOC_LINE_RE.search(node):
                add("warn", "T7", ".".join(str(x) for x in loc), loc, "", "文本里出现「文件:行号」形式的证据")
            if SURROGATE_RE.search(node):
                add("error", "X1", ".".join(str(x) for x in loc), loc, "", "文本含非法字符（孤立代理项），无法以 UTF-8 写出")

    walk(doc, [])
    return problems, stats


def check_results(payload: dict) -> dict:
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise UserError("文本缺失或过大（>800 万字符）", "too_big")
    try:
        doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "parsed": False, "stats": None,
                "problems": [{"level": "error", "code": "parse", "path": "", "loc": [], "label": "",
                              "message": f"JSON 解析失败：{exc}"}]}
    problems, stats = validate_results(doc)
    return {"ok": True, "parsed": True, "problems": problems, "stats": stats}


def save_results(payload: dict) -> dict:
    """把内存中的文本写回 results/。只有「不是合法 JSON」才硬拦，规范问题只列不挡。"""
    name = safe_name(payload.get("file", ""))
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise UserError("文本缺失或过大（>800 万字符）", "too_big")
    try:
        doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"内容不是合法 JSON，未写盘：{exc}", "parse") from None
    mode = payload.get("mode", "overwrite")
    if mode not in ("overwrite", "new"):
        raise UserError(f"未知保存方式：{mode}", "mode")
    eol = "lf" if payload.get("eol") == "lf" else "crlf"
    path = RESULTS_DIR / name
    if path.is_dir():
        raise UserError(f"results/{name} 是一个目录，不能作为文件保存", "exists")
    exists = path.exists()
    if mode == "new" and exists:
        raise UserError(f"已存在同名文件：{name}，请改用「覆盖」或换个名字", "exists")
    if mode == "overwrite" and not exists:
        raise UserError(f"文件不存在：{name}（可能已被删除或改名），请改用「新建」", "missing")
    expect = payload.get("expect")
    if mode == "overwrite" and isinstance(expect, dict) and not payload.get("force"):
        st = path.stat()
        if (st.st_mtime_ns, st.st_size) != (int(expect.get("mtime_ns", -1)), int(expect.get("size", -1))):
            raise UserError("文件已被外部改动（大小或修改时间不符），请重新载入，或确认后强制覆盖", "drift")
    out_lf = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    text_out = out_lf.replace("\n", "\r\n") if eol == "crlf" else out_lf
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        write_atomic(path, text_out)
    except UnicodeEncodeError:
        raise UserError("内容含非法字符（孤立代理项 \\ud800–\\udfff），无法以 UTF-8 写出", "encoding") from None
    st = path.stat()
    problems, stats = validate_results(doc)
    return {"ok": True, "file": name, "created": not exists, "bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns, "size": st.st_size, "eol": eol,
            "normalized": out_lf != text, "saved": {"text": out_lf},
            "problems": problems, "stats": stats, "today": today_str()}


# ---------------------------------------------------------------- HTTP

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>干员 TAG 名单维护</title>
<style>
:root{--bg:#f5f6f8;--panel:#fff;--line:#e4e7ec;--txt:#1f2430;--dim:#6b7280;--acc:#2f6fed;--rec:#d98a00;--ok:#12805c;--err:#c0392b;--off:#7a5bd6}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:flex;flex-direction:column;font:14px/1.55 "Microsoft YaHei","PingFang SC","Noto Sans SC",system-ui,sans-serif;color:var(--txt);background:var(--bg)}
header{display:flex;align-items:center;gap:10px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:15px;margin:0;font-weight:600}
header .hint{font-size:12px;color:var(--dim)}
header .sp{flex:1}
.tabs{display:flex;gap:4px;margin-left:6px}
.tab{font:inherit;padding:4px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;cursor:pointer}
.tab:hover{border-color:var(--acc);color:var(--acc)}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
button:hover{border-color:var(--acc);color:var(--acc)}
button.mini{padding:0 6px;line-height:1.5;font-size:12px}
#status{font-size:12px;color:var(--dim);min-width:120px;text-align:right}
#status.ok{color:var(--ok)}#status.err{color:var(--err)}
main{flex:1;display:grid;min-height:0}
main[hidden]{display:none}
main>*{min-height:0;overflow:auto;background:var(--panel)}
#page-zhen{grid-template-columns:200px minmax(0,1fr) 420px}
#tagcol{border-right:1px solid var(--line);padding:8px}
#editcol{border-left:1px solid var(--line);padding:10px}
#page-induce{grid-template-columns:270px minmax(0,1fr) 330px;grid-template-rows:minmax(0,1.3fr) minmax(0,.85fr);
  grid-template-areas:"tags ops pick" "stage stage pick"}
#itagcol{grid-area:tags;border-right:1px solid var(--line);padding:6px 8px}
#iopcol{grid-area:ops;display:flex;flex-direction:column;border-right:1px solid var(--line)}
#stagecol{grid-area:stage;border-top:1px solid var(--line);padding:8px 12px;background:#fbfcfe}
#pickcol{grid-area:pick;display:flex;flex-direction:column;border-left:1px solid var(--line);background:#fcfcfd}
.tag{padding:7px 9px;border-radius:8px;cursor:pointer;display:flex;align-items:baseline;gap:6px}
.tag:hover{background:#f0f3f8}
.tag.on{background:#e8effd;color:var(--acc);font-weight:600}
.tag .n{font-size:11px;color:var(--dim);margin-left:auto;font-weight:400}
.tag .num{font-size:11px;color:#9aa3af}
.grouphdr{font-size:12px;font-weight:600;color:var(--dim);margin:10px 2px 4px;display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.catrow{font-size:12px;color:var(--dim);margin:6px 2px 2px;padding-left:6px;display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.blk{padding:5px 8px 5px 20px;border-radius:8px;cursor:pointer;display:flex;align-items:baseline;gap:6px;font-size:13px}
.blk:hover{background:#f0f3f8}
.blk.on{background:#e8effd;color:var(--acc);font-weight:600}
.blk .n{font-size:11px;color:var(--dim);margin-left:auto;font-weight:400}
.blk .caret{font-size:10px;color:#9aa3af;width:10px}
.lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag,.blk{min-width:0}
#opcol{display:flex;flex-direction:column}
.toolbar{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding:8px 12px;display:flex;gap:10px;align-items:center;z-index:2}
#itagcol .toolbar,#pickcol .toolbar{border-bottom:1px solid var(--line);padding:8px 8px}
.toolbar input{flex:1;font:inherit;padding:5px 9px;border:1px solid var(--line);border-radius:6px;min-width:0}
.toolbar .cnt{font-size:12px;color:var(--dim);white-space:nowrap}
#oplist,#ioplist{padding:8px 12px 24px}
#picklist{padding:6px 8px 20px}
.card{display:flex;align-items:center;gap:8px;padding:6px 9px;border:1px solid transparent;border-radius:8px;cursor:pointer;user-select:none}
.card:hover{background:#f0f3f8}
.card.rec{background:#fff8e8;border-color:#f2ddb0}
.card.rec .name{font-weight:600}
.card.open{background:#f2f6ff;border-color:#cddffb}
.card .name{min-width:4em}
.card .rank{width:18px;text-align:center;color:var(--rec);font-weight:700;font-size:12px}
.card .chips{display:flex;gap:5px;flex-wrap:wrap;min-width:0}
.chip{font-size:11px;color:var(--dim);background:#f1f3f6;border-radius:9px;padding:0 7px;white-space:nowrap;max-width:22em;overflow:hidden;text-overflow:ellipsis}
.card .tail{margin-left:auto;display:flex;gap:4px;opacity:.35}
.card:hover .tail{opacity:1}
.split{margin:10px 2px 6px;font-size:12px;color:var(--dim);border-top:1px dashed var(--line);padding-top:8px}
h3.sec{font-size:13px;margin:2px 0 8px;color:var(--dim);font-weight:600}
#recbox{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-bottom:12px;background:#fcfcfd}
#recbox h3{margin:0 0 6px;font-size:13px}
#recbox ol{margin:0;padding-left:20px}
#recbox li{margin:2px 0;display:flex;align-items:center;gap:4px}
#recbox li span.op{flex:1}
#recbox .empty{color:var(--dim);font-size:12px}
#recbox .note{color:var(--dim);font-size:11px;margin-top:6px}
.guide{font-size:12px;color:var(--dim);background:#f7f9fc;border:1px solid var(--line);border-radius:8px;padding:7px 9px;margin-bottom:12px;line-height:1.65}
.guide code{background:#eef1f6;border-radius:4px;padding:0 4px}
.detail{margin:2px 4px 12px 28px}
.brief{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--dim);background:#f7f9fc;border:1px solid var(--line);border-radius:8px;padding:6px 9px;margin-bottom:8px}
.brief b{font-size:13px;color:var(--txt)}
.brief a{color:var(--acc);text-decoration:none}
.row{border:1px solid var(--line);border-radius:10px;padding:8px 11px;margin-bottom:8px;background:#fff}
.row .head{display:flex;align-items:center;gap:7px;margin-bottom:4px;flex-wrap:wrap}
.row .head b{font-size:13px}
.row .loc{font-size:11px;color:#9aa3af;margin-left:auto}
.badge{font-size:10px;border-radius:4px;padding:0 4px;color:#fff}
.badge.p{background:var(--acc)}.badge.o{background:var(--off)}
.vlabel{font-size:12px;color:var(--dim);margin-top:6px}
.val{font-size:13px;border:1px solid transparent;border-radius:6px;padding:3px 6px;margin-left:-6px;cursor:text;white-space:pre-wrap;word-break:break-word}
.val:hover{border-color:var(--line);background:#fafbfd}
.val.empty{color:#b0863b;background:#fff8e8}
.row .src{font-size:11px;color:#9aa3af;margin-top:6px;word-break:break-all}
.editline{display:flex;gap:6px;align-items:center;margin-top:2px}
.editline input{flex:1;font:inherit;font-size:13px;padding:4px 7px;border:1px solid var(--acc);border-radius:6px;min-width:0}
#stagecol .hd{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
#stagecol .hd h3{margin:0;font-size:13px}
#stagecol .hd .tip{font-size:12px;color:var(--dim)}
#stagelist{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}
.stage-item{border:1px solid var(--line);border-radius:8px;padding:4px 8px;background:#fff;cursor:pointer;display:flex;align-items:center;gap:6px;font-size:13px}
.stage-item:hover{border-color:var(--acc)}
.stage-item.mv{background:#f6f2ff;border-color:#ded2f7}
.stage-item.stale{border-color:var(--err);background:#fdf1ef}
.stage-item .badge{background:var(--acc)}
.stage-item.mv .badge{background:var(--off)}
.stage-item .x{border:none;background:transparent;color:var(--dim);padding:0 2px;cursor:pointer}
#stagelist .empty{color:var(--dim);font-size:12px}
.menu{position:fixed;z-index:20;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 6px 20px rgba(20,30,60,.14);padding:4px;min-width:120px}
.menu button{display:block;width:100%;text-align:left;border:none;background:transparent;padding:5px 9px;border-radius:6px}
.menu button:hover{background:#f0f3f8;color:var(--acc)}
.menu .sep{height:1px;background:var(--line);margin:4px 2px}
#toast{position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:6px;z-index:30}
.tmsg{background:#1f2430;color:#fff;font-size:13px;padding:6px 12px;border-radius:8px;opacity:.94}
.tmsg.err{background:#a5281b}
/* ---- 结果 JSON 页 ---- */
#page-json{display:flex;flex-direction:column}
#resbar{display:flex;align-items:center;gap:8px;padding:7px 12px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
#resbar .sp{flex:1}
#resbar .dot{width:9px;height:9px;border-radius:50%;background:#d0d5dd;flex:none}
#resbar .dot.on{background:var(--rec)}
#resbar b{font-size:13px}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
button.primary:hover{color:#fff;opacity:.9}
button.primary:disabled{opacity:.45;cursor:not-allowed}
#resbody{flex:1;display:grid;grid-template-columns:250px minmax(0,1fr) 420px;min-height:0}
#resbody[hidden],#resrc[hidden]{display:none}
#rtagcol{border-right:1px solid var(--line);padding:6px 8px}
#rmemcol{display:flex;flex-direction:column;border-right:1px solid var(--line)}
#rpanel{border-left:1px solid var(--line);padding:10px}
#rmembers,#rtags,#ropcol{padding:6px 8px 20px}
#resrc{flex:1;display:flex;flex-direction:column;min-height:0;background:var(--panel)}
#resrc .srchead{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid var(--line);font-size:12px;color:var(--dim)}
#rstext{flex:1;width:100%;min-height:0;border:0;outline:none;resize:none;padding:10px 12px;
  font:12.5px/1.5 ui-monospace,Consolas,"Cascadia Mono",monospace;color:var(--txt)}
#rserr{color:var(--err);font-size:12px;padding:6px 12px;border-top:1px solid var(--line);white-space:pre-wrap}
#rserr:empty{display:none}
.rsec{margin:2px 2px 6px;font-size:12px;color:var(--dim);font-weight:600}
.kv{display:flex;gap:7px;align-items:baseline;font-size:12px;color:var(--dim);padding:3px 0;flex-wrap:wrap}
.kv>b{color:var(--txt);font-weight:600;font-size:12px;flex:none;min-width:4.5em}
.kv .ro{color:#9aa3af;font-size:11px}
.kv select{font:inherit;font-size:12px;padding:2px 5px;border:1px solid var(--line);border-radius:6px}
.tagline{display:flex;align-items:center;gap:6px;padding:5px 7px;border-radius:8px;cursor:pointer;font-size:13px}
.tagline:hover{background:#f0f3f8}
.tagline.on{background:#e8effd;color:var(--acc);font-weight:600}
.tagline .n{font-size:11px;color:var(--dim);margin-left:auto;font-weight:400}
.tagline .dotid{font-size:11px;color:#9aa3af;font-family:ui-monospace,Consolas,monospace}
.subrow{display:flex;gap:5px;align-items:center;font-size:12px;margin:4px 0;flex-wrap:wrap}
.subrow .val{min-width:5em}
.pgroup{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-bottom:10px;background:#fff}
.pgroup h4{margin:0 0 6px;font-size:13px}
.warnbar{background:#fff8e8;border:1px solid #f2ddb0;color:#8a5a00;border-radius:8px;padding:6px 9px;font-size:12px;margin-bottom:8px}
#modal{position:fixed;inset:0;background:rgba(20,30,60,.28);display:flex;align-items:center;justify-content:center;z-index:40}
#modal[hidden]{display:none}
.modal-card{background:#fff;border-radius:12px;box-shadow:0 10px 40px rgba(20,30,60,.24);width:min(780px,93vw);max-height:88vh;overflow:auto;padding:14px 16px}
.modal-card h3{margin:0 0 8px;font-size:14px}
.mradio{display:flex;gap:8px;align-items:center;margin:8px 0;font-size:13px;flex-wrap:wrap}
.mradio select,.mradio input[type=text],.mradio input[type=date]{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line);border-radius:6px}
.mprobs{margin:10px 0;border:1px solid var(--line);border-radius:8px;max-height:240px;overflow:auto}
.mprob{display:flex;gap:8px;padding:5px 9px;border-bottom:1px solid var(--line);cursor:pointer;font-size:12px;align-items:baseline}
.mprob:last-child{border-bottom:0}
.mprob:hover{background:#f0f3f8}
.mprob .lv{font-weight:600;flex:none}
.mprob.error .lv{color:var(--err)}
.mprob.warn .lv{color:var(--rec)}
.mprob .pth{color:#9aa3af;font-size:11px;margin-left:auto;font-family:ui-monospace,Consolas,monospace}
.mfoot{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:10px}
.mfoot .sp{flex:1}
.mhint{font-size:12px;color:var(--dim)}
.mhint.err{color:var(--err)}
</style>
</head>
<body>
<header>
  <h1>干员 TAG 名单维护</h1>
  <nav class="tabs">
    <button class="tab on" data-tab="zhen">荐</button>
    <button class="tab" data-tab="induce">人工归纳</button>
    <button class="tab" data-tab="results">结果 JSON</button>
  </nav>
  <span class="hint" id="hint"></span>
  <span class="sp"></span>
  <label class="hint" id="automergewrap"><input type="checkbox" id="automerge" checked> 保存后自动重新生成名单文档</label>
  <button id="btmerge">重新生成名单文档</button>
  <button id="btreload">刷新数据</button>
  <span id="status"></span>
</header>
<main id="page-zhen">
  <aside id="tagcol"></aside>
  <section id="opcol">
    <div class="toolbar"><input id="search" placeholder="搜索干员名…"><span class="cnt" id="cnt"></span></div>
    <div id="oplist"></div>
  </section>
  <aside id="editcol">
    <div id="recbox"></div>
    <div class="guide">荐＝人工指定的「该 TAG 下推荐用」干员，只存在于玩家体感 TAG；本页只负责加/删/排序荐。<br>条件与备注请到「人工归纳」页查看与编辑（点干员行的「详情」直接跳过去）。</div>
  </aside>
</main>
<main id="page-induce" hidden>
  <aside id="itagcol">
    <div class="toolbar"><input id="tsearch" placeholder="搜索 TAG / 子表…"></div>
    <div id="tagtree"></div>
  </aside>
  <section id="iopcol">
    <div class="toolbar"><input id="isearch" placeholder="搜索干员名…"><span class="cnt" id="icnt"></span></div>
    <div id="ioplist"></div>
  </section>
  <aside id="stagecol">
    <div class="hd">
      <h3>临时区</h3>
      <span class="tip" id="stagetip"></span>
      <span class="sp" style="flex:1"></span>
      <button id="btclear">清空</button>
    </div>
    <div id="stagelist"></div>
  </aside>
  <aside id="pickcol">
    <div class="toolbar"><input id="psearch" placeholder="搜索干员名…"><span class="cnt" id="pcnt"></span></div>
    <div id="picklist"></div>
    <div class="guide" style="margin:8px">全部干员摘选区：左键 = 以「扩展」方式放入临时区（并入后新行条件/备注为空）。<br>条件＝硬性达成条件（精英化／技能／专精／模组与等级／模式限定／目标限制），精零 1 级即具备写「无」；备注＝加工后的信息（数值、持续时间、隐藏机制、用法）。单元格须单行、不含竖线 |；保存后并入名单文档，即最终 JSON 的 condition / remark。</div>
  </aside>
</main>
<main id="page-json" hidden>
  <div id="resbar">
    <span class="dot" id="resdot" title="有未保存的改动"></span>
    <b id="resfile">未载入</b>
    <span class="hint" id="resstats"></span>
    <span class="sp"></span>
    <span class="hint" id="reshint">编辑只发生在内存中，点「保存…」才会写盘</span>
    <button id="btmode">按干员</button>
    <button id="btload">加载…</button>
    <button id="btnew">新建骨架</button>
    <button id="btsort">按规范整理</button>
    <button id="btcheck">校验</button>
    <button id="btview">源码视图</button>
    <button id="btsave" class="primary">保存…</button>
  </div>
  <div id="resbody">
    <aside id="rtagcol">
      <div class="toolbar"><input id="rtsearch" placeholder="搜索 TAG / id…"><span class="cnt" id="rtcnt"></span></div>
      <div id="rtags"></div>
    </aside>
    <section id="rmemcol">
      <div class="toolbar"><input id="rsearch" placeholder="搜索干员…"><span class="cnt" id="rmcnt"></span></div>
      <div id="rmembers"></div>
    </section>
    <aside id="rpanel"></aside>
  </div>
  <div id="resrc" hidden>
    <div class="srchead"><span>源码视图：直接编辑 JSON 文本，切回结构化视图时生效</span><span class="sp" style="flex:1"></span><button id="btformat">格式化</button><button id="btback">结构化视图</button></div>
    <textarea id="rstext" spellcheck="false"></textarea>
    <div id="rserr"></div>
  </div>
</main>
<div id="modal" hidden><div class="modal-card" role="dialog" aria-modal="true"></div></div>
<div id="toast"></div>
<script>
const TOKEN = "__TOKEN__";
let DATA = null;
const IDX = {byId:new Map(), tagBlocks:new Map(), tree:[]};
const ST = {
  tab: "zhen",
  zhen: {tag: "__all__", q: ""},
  ind: {targets: [], browse: null, browseOpen: {}, openOp: null, q: "", pq: "", tq: "",
        collapsed: {}, stage: [], busy: false},
};

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function toast(msg, isErr) {
  const d = document.createElement("div");
  d.className = "tmsg" + (isErr ? " err" : "");
  d.textContent = msg;
  document.getElementById("toast").appendChild(d);
  setTimeout(() => d.remove(), isErr ? 4200 : 2000);
}
function status(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.className = kind || "";
}
function automergeOn() { return document.getElementById("automerge").checked; }
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Token": TOKEN},
    body: JSON.stringify(body),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { j = {error: "服务返回异常（HTTP " + r.status + "）"}; }
  if (!r.ok || j.ok === false) { const e = new Error(j.error || ("HTTP " + r.status)); e.code = j.code || ""; throw e; }
  return j;
}
function matches(name, q) { return !q || name.toLowerCase().includes(q); }

// ---------------------------------------------------------------- 加载 / 派生索引

async function load(fresh) {
  DATA = await (await fetch("/api/data" + (fresh ? "?fresh=1" : ""))).json();
  hydrate();
  if (DATA.stale.length) toast("有 " + DATA.stale.length + " 条荐已不在成员表中，请核对", true);
  renderAll();
}
function hydrate() {
  IDX.byId.clear(); IDX.tagBlocks.clear(); IDX.tree = [];
  const tagTree = [];
  for (const t of DATA.player_tags) {
    const blocks = t.blocks.map(b => b.id);
    IDX.tagBlocks.set("p:" + t.name, blocks);
    for (const b of t.blocks) IDX.byId.set(b.id, {...b, source: "player", tagKey: "p:" + t.name, tagName: t.name, multi: t.blocks.length > 1, tagNum: t.num});
    tagTree.push({key: "p:" + t.name, name: t.name, num: t.num, blocks, ops: new Set(t.blocks.flatMap(b => b.rows.map(r => r.op))).size});
  }
  IDX.tree.push({title: "玩家体感 TAG", tags: tagTree});
  const byCat = new Map();
  for (const e of DATA.official_entries) {
    const b = e.blocks[0];
    IDX.byId.set(b.id, {...b, source: "official", tagKey: "o:" + e.id, tagName: e.name, multi: false});
    IDX.tagBlocks.set("o:" + e.id, [b.id]);
    if (!byCat.has(e.category)) byCat.set(e.category, []);
    byCat.get(e.category).push({key: "o:" + e.id, name: e.name, blocks: [b.id], ops: new Set(b.rows.map(r => r.op)).size});
  }
  IDX.tree.push({title: "官方设定 TAG", cats: [...byCat.entries()].map(([title, tags]) => ({title, tags}))});
}
function tagOf(name) { return DATA.player_tags.find(t => t.name === name); }
function blockById(bid) { return IDX.byId.get(bid); }
function scopeBlocks() {
  if (ST.ind.targets.length) return ST.ind.targets.map(t => blockById(t.id)).filter(Boolean);
  if (ST.ind.browse) return (IDX.tagBlocks.get(ST.ind.browse) || []).map(blockById).filter(Boolean);
  return [];
}
function scopeRows() {
  const out = [];
  for (const b of scopeBlocks()) for (const r of b.rows) out.push({b, r});
  return out;
}
function inTargets(bid) { return ST.ind.targets.some(t => t.id === bid); }
function blkLabel(b) {  // 单子表 TAG 的区块标题就是「成员表…」，不再显示
  return (IDX.tagBlocks.get(b.tagKey) || []).length > 1 ? b.label : "";
}
function blkFull(b) { const l = blkLabel(b); return b.tagName + (l ? " · " + l : ""); }

// ---------------------------------------------------------------- 荐 页

function viewOps() {
  if (ST.zhen.tag === "__all__") {
    const names = [...new Set(DATA.player_tags.flatMap(t => t.blocks.flatMap(b => b.rows.map(r => r.op))))];
    names.sort((a, b) => a.localeCompare(b, "zh"));
    return names.map(op => ({op, rec: -1, rows: allRowsOf(op)}));
  }
  const t = tagOf(ST.zhen.tag);
  const recs = t.recommend.map((op, i) => ({op, rec: i, rows: allRowsOf(op)}));
  const members = [...new Set(t.blocks.flatMap(b => b.rows.map(r => r.op)))].filter(op => !t.recommend.includes(op));
  return recs.concat(members.map(op => ({op, rec: -1, rows: allRowsOf(op)})));
}
function allRowsOf(op) {
  const out = [];
  for (const t of DATA.player_tags) for (const b of t.blocks) for (const r of b.rows) if (r.op === op) out.push({b, r});
  return out;
}
function renderTags() {
  const col = document.getElementById("tagcol");
  col.innerHTML = "";
  const mk = (label, on, fn, badge) => {
    const el = document.createElement("div");
    el.className = "tag" + (on ? " on" : "");
    el.innerHTML = label + '<span class="n">' + badge + "</span>";
    el.onclick = fn;
    col.appendChild(el);
  };
  const total = new Set(DATA.player_tags.flatMap(t => t.blocks.flatMap(b => b.rows.map(r => r.op)))).size;
  mk('<span>全部干员</span>', ST.zhen.tag === "__all__", () => { ST.zhen.tag = "__all__"; renderAll(); }, total);
  for (const t of DATA.player_tags) {
    const n = new Set(t.blocks.flatMap(b => b.rows.map(r => r.op))).size;
    mk('<span class="num">' + t.num + '</span><span>' + esc(t.name) + "</span>",
       ST.zhen.tag === t.name, () => { ST.zhen.tag = t.name; renderAll(); },
       n + (t.recommend.length ? " · 荐" + t.recommend.length : ""));
  }
}
function renderOps() {
  const list = document.getElementById("oplist");
  list.innerHTML = "";
  const all = viewOps();
  const items = all.filter(it => matches(it.op, ST.zhen.q));
  document.getElementById("cnt").textContent = items.length + " / " + all.length + " 人";
  let recDone = false;
  for (const it of items) {
    if (ST.zhen.tag !== "__all__" && it.rec < 0 && !recDone && items.some(x => x.rec >= 0)) {
      recDone = true;
      const d = document.createElement("div");
      d.className = "split";
      d.textContent = "其余成员（成员表顺序）";
      list.appendChild(d);
    }
    const el = opRow(it, {
      rank: it.rec >= 0 ? it.rec + 1 : "",
      chips: [],
      buttons: [{label: "详情", title: "到「人工归纳」页查看条件与备注", fn: () => gotoInduce(it.op, ST.zhen.tag)}],
      onClick: () => addRec(it.op),
      onContext: () => removeRec(it.op),
    });
    list.appendChild(el);
  }
}
function renderRec() {
  const box = document.getElementById("recbox");
  if (ST.zhen.tag === "__all__") {
    box.innerHTML = "<h3>荐</h3><div class='empty'>在左侧选中一个 TAG 后，左键 / 右键干员即可增删荐。</div>";
    return;
  }
  const t = tagOf(ST.zhen.tag);
  let html = "<h3>「" + esc(t.name) + "」荐（" + t.recommend.length + " 人，按展示优先级）</h3>" +
    "<div class='note'>荐只能加在玩家体感 TAG（P01–P13）上；官方设定 TAG 无荐字段。</div>";
  if (!t.recommend.length) html += "<div class='empty'>暂无。左键下方任一干员即可加入。</div>";
  else {
    html += "<ol>";
    t.recommend.forEach(op => {
      html += "<li><span class='op'>" + esc(op) + "</span>" +
        "<button class='mini' data-act='up' data-op='" + esc(op) + "' title='上移'>↑</button>" +
        "<button class='mini' data-act='down' data-op='" + esc(op) + "' title='下移'>↓</button>" +
        "<button class='mini' data-act='first' data-op='" + esc(op) + "' title='置顶'>⤒</button>" +
        "<button class='mini' data-act='remove' data-op='" + esc(op) + "' title='取消荐'>×</button></li>";
    });
    html += "</ol>";
  }
  box.innerHTML = html;
  box.querySelectorAll("button[data-act]").forEach(b => {
    b.onclick = async () => {
      const act = b.dataset.act, op = b.dataset.op;
      try {
        if (act === "up" || act === "down") await api("/api/recommend", {tag: ST.zhen.tag, action: "move", op, delta: act === "up" ? -1 : 1});
        else if (act === "first") await api("/api/recommend", {tag: ST.zhen.tag, action: "first", op});
        else await api("/api/recommend", {tag: ST.zhen.tag, action: "remove", op});
        await load();
      } catch (e) { toast(e.message, true); }
    };
  });
}
async function addRec(op) {
  if (ST.zhen.tag === "__all__") { toast("请先在左侧选择一个 TAG，再加荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: ST.zhen.tag, action: "add", op});
    DATA.recommend = j.recommend;
    tagOf(ST.zhen.tag).recommend = j.recommend[ST.zhen.tag] || [];
    toast(j.noop ? ("「" + ST.zhen.tag + "」已是荐：" + op) : ("已设荐：" + op + " →「" + ST.zhen.tag + "」"));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}
async function removeRec(op) {
  if (ST.zhen.tag === "__all__") { toast("请先在左侧选择一个 TAG，再取消荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: ST.zhen.tag, action: "remove", op});
    DATA.recommend = j.recommend;
    tagOf(ST.zhen.tag).recommend = j.recommend[ST.zhen.tag] || [];
    toast(j.noop ? ("「" + ST.zhen.tag + "」本就没有荐：" + op) : ("已取消荐：" + op));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- 共用行组件

function opRow(rec, o) {
  const el = document.createElement("div");
  el.className = "card" + (o.cls ? " " + o.cls : "");
  el.innerHTML = '<span class="rank">' + esc(o.rank || "") + "</span>" +
    '<span class="name">' + esc(rec.op) + "</span>" +
    '<span class="chips">' + (o.chips || []).map(c => '<span class="chip">' + esc(c) + "</span>").join("") + "</span>" +
    '<span class="tail">' + (o.buttons || []).map((b, i) => '<button class="mini" data-i="' + i + '" title="' + esc(b.title || "") + '">' + esc(b.label) + "</button>").join("") + "</span>";
  el.onclick = e => {
    const b = e.target.closest("button[data-i]");
    if (b) { e.stopPropagation(); o.buttons[+b.dataset.i].fn(); return; }
    (o.onClick || (() => {}))();
  };
  if (o.onContext) el.oncontextmenu = e => { e.preventDefault(); o.onContext(e); };
  return el;
}
function bindSearch(id, get, set, render) {
  const el = document.getElementById(id);
  el.value = get();
  el.addEventListener("input", () => { set(el.value.trim().toLowerCase()); render(); });
}

// ---------------------------------------------------------------- 人工归纳：TAG 树

function renderTree() {
  const col = document.getElementById("tagtree");
  col.innerHTML = "";
  const q = ST.ind.tq;
  for (const group of IDX.tree) {
    const isOfficial = !!group.cats;
    const collapsed = !q && ST.ind.collapsed["g:" + group.title];
    const hdr = document.createElement("div");
    hdr.className = "grouphdr";
    hdr.innerHTML = '<span class="caret">' + (collapsed ? "▸" : "▾") + "</span><span>" + esc(group.title) + "</span>";
    hdr.onclick = () => { ST.ind.collapsed["g:" + group.title] = !collapsed; renderTree(); };
    col.appendChild(hdr);
    if (collapsed) continue;
    const cats = isOfficial ? group.cats : [{title: "", tags: group.tags}];
    for (const cat of cats) {
      if (cat.title) {
        const ck = "c:" + cat.title;
        const ccol = !q && ST.ind.collapsed[ck];
        const cel = document.createElement("div");
        cel.className = "catrow";
        cel.innerHTML = '<span class="caret">' + (ccol ? "▸" : "▾") + "</span><span>" + esc(cat.title) + "</span>";
        cel.onclick = () => { ST.ind.collapsed[ck] = !ccol; renderTree(); };
        col.appendChild(cel);
        if (ccol) continue;
      }
      for (const tag of cat.tags) {
        if (q && !tag.name.toLowerCase().includes(q) && !tag.blocks.some(b => ((blockById(b) || {}).label || "").toLowerCase().includes(q))) continue;
        const multi = tag.blocks.length > 1;
        if (multi) {
          const open = !!ST.ind.browseOpen[tag.key] || !!q;
          const el = document.createElement("div");
          el.className = "tag" + (ST.ind.browse === tag.key ? " on" : "");
          el.innerHTML = '<span class="caret">' + (open ? "▾" : "▸") + '</span><span class="lbl">' + esc(tag.name) + '</span><span class="n">' + tag.ops + "</span>";
          el.onclick = () => {
            ST.ind.browseOpen[tag.key] = !open;
            ST.ind.browse = tag.key;
            ST.ind.targets = [];
            renderInd();
          };
          col.appendChild(el);
          if (open) for (const bid of tag.blocks) col.appendChild(blockRow(blockById(bid), true));
        } else {
          col.appendChild(blockRow(blockById(tag.blocks[0]), false, tag.name));
        }
      }
    }
  }
}
function blockRow(b, indented, nameOverride) {
  const el = document.createElement("div");
  el.className = "blk" + (inTargets(b.id) ? " on" : "");
  const label = nameOverride || b.label;
  el.innerHTML = (indented ? '<span class="caret"></span>' : "") + '<span class="lbl">' + esc(label) + '</span><span class="n">' + b.rows.length + "</span>";
  el.title = (b.source === "official" ? "[官方] " : "[玩家] ") + blkFull(b);
  el.onclick = e => {
    if (e.ctrlKey || e.metaKey) {
      const k = ST.ind.targets.findIndex(t => t.id === b.id);
      if (k >= 0) ST.ind.targets.splice(k, 1);
      else ST.ind.targets.push({id: b.id, sig: b.sig});
      ST.ind.browse = null;
    } else {
      ST.ind.targets = [{id: b.id, sig: b.sig}];
      ST.ind.browse = null;
    }
    renderInd();
  };
  return el;
}

// ---------------------------------------------------------------- 人工归纳：干员列表

function renderInd() {
  renderTree(); renderIndList(); renderStage();
  const tip = document.getElementById("stagetip");
  const sel = ST.ind.targets.map(t => blockById(t.id)).filter(Boolean);
  tip.textContent = sel.length
    ? "目标：" + sel.map(blkFull).join("；") + (sel.length > 1 ? "（" + sel.length + " 个，移动只能落到一个）" : "")
    : (ST.ind.browse ? "浏览中（只读范围，点具体子表才能并入）" : "先在左侧选中目标子表");
}
function renderIndList() {
  const list = document.getElementById("ioplist");
  list.innerHTML = "";
  const rows = scopeRows();
  const byOp = new Map();
  for (const x of rows) {
    if (!byOp.has(x.r.op)) byOp.set(x.r.op, []);
    byOp.get(x.r.op).push(x);
  }
  const names = [...byOp.keys()];
  const items = names.filter(n => matches(n, ST.ind.q));
  document.getElementById("icnt").textContent = items.length + " / " + names.length + " 人";
  if (!scopeBlocks().length) {
    list.innerHTML = "<div class='split'>" + (ST.ind.openOp
      ? "「" + esc(ST.ind.openOp) + "」不在当前范围：请在左侧选中它所属的 TAG（含官方设定 TAG）后查看。"
      : "点左侧 TAG 查看其下干员；多子表 TAG 展开后点具体子表即可并入。") + "</div>";
    return;
  }
  const multi = scopeBlocks().length > 1;
  for (const op of items) {
    const recs = byOp.get(op);
    const open = ST.ind.openOp === op;
    const chips = recs.map(x => (x.r.sub || (multi ? x.b.label : ""))).filter(Boolean);
    const el = opRow({op}, {
      cls: open ? "open" : "",
      chips,
      buttons: [],
      onClick: () => { ST.ind.openOp = open ? null : op; renderIndList(); },
      onContext: e => rowMenu(e, op, recs),
    });
    list.appendChild(el);
    if (open) list.appendChild(detailEl(op, recs));
  }
}
function briefHtml(name) {
  const p = (DATA.roster || []).find(x => x.name === name);
  if (!p) return "<div class='brief'><b>" + esc(name) + "</b><span>（未在全量干员表中找到）</span></div>";
  return "<div class='brief'><b>" + esc(p.name) + "</b>" +
    "<span>" + (p.star ? "★".repeat(p.star) : "—") + "</span>" +
    "<span>" + esc([p.cls, p.branch].filter(Boolean).join("·")) + "</span>" +
    "<span>" + esc(p.faction || "—") + "</span>" +
    "<span>" + esc(p.date || "—") + "</span>" +
    "<span><a href='" + esc(p.url) + "' target='_blank' rel='noreferrer'>PRTS↗</a></span></div>";
}
function detailEl(op, recs) {
  const box = document.createElement("div");
  box.className = "detail";
  box.innerHTML = briefHtml(op);
  for (const x of recs) box.appendChild(recordCard(x));
  return box;
}
function recordCard(x) {
  const b = x.b, r = x.r;
  const el = document.createElement("div");
  el.className = "row";
  const badge = b.source === "player" ? "<span class='badge p'>玩家</span>" : "<span class='badge o'>官方</span>";
  el.innerHTML = "<div class='head'>" + badge + "<b>" + esc(b.tagName) + "</b>" +
    (blkLabel(b) ? "<span class='chip'>" + esc(b.label) + "</span>" : "") +
    "<span class='loc'>" + esc(b.file) + ":" + r.line + "</span></div>" +
    "<div class='vlabel'>条件</div><div class='val" + (r.cond ? "" : " empty") + "' data-k='cond'>" + esc(r.cond || "（待填）") + "</div>" +
    "<div class='vlabel'>备注</div><div class='val" + (r.note ? "" : " empty") + "' data-k='note'>" + esc(r.note || "（待填）") + "</div>" +
    (b.source === "player" ? "<div class='src'>依据：" + esc(r.src || "—") + "</div>" : "");
  el.querySelectorAll(".val").forEach(v => { v.onclick = () => startEdit(v, x); });
  return el;
}
function startEdit(el, x) {
  const key = el.dataset.k;
  const old = x.r[key];
  const line = document.createElement("div");
  line.className = "editline";
  const input = document.createElement("input");
  input.value = old;
  const ok = document.createElement("button"); ok.textContent = "✓"; ok.title = "保存（Enter）";
  const no = document.createElement("button"); no.textContent = "×"; no.title = "取消（Esc）";
  line.append(input, ok, no);
  el.replaceWith(line);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  let done = false;
  const cancel = () => { if (!done) { done = true; paintVal(el, old); line.replaceWith(el); } };
  const commit = async () => {
    if (done) return;
    done = true;
    const v = input.value;
    const cond = key === "cond" ? v : x.r.cond;
    const note = key === "note" ? v : x.r.note;
    if (v === old) { line.replaceWith(el); return; }
    try {
      const j = await api("/api/cell", {file: x.b.file, line: x.r.line, original: x.r.raw, cond, note});
      x.r.cond = j.cond; x.r.note = j.note; x.r.raw = j.raw;
      paintVal(el, x.r[key]);
      line.replaceWith(el);
      toast("已保存" + (j.warn ? "（" + j.warn + "）" : ""));
      if (automergeOn()) {
        const mr = await api("/api/merge", {which: x.b.source === "official" ? "official" : "player"});
        status(mr.ok ? "已保存并重新生成名单文档" : "已保存，但重新生成名单文档失败", mr.ok ? "ok" : "err");
      } else status("有未合并的单元格改动");
    } catch (e) {
      done = false;
      toast(e.message, true);
      status("保存失败", "err");
    }
  };
  ok.onclick = commit;
  no.onclick = cancel;
  input.onkeydown = e => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
  };
}
function paintVal(el, v) {
  el.textContent = v || "（待填）";
  el.classList.toggle("empty", !v);
}

// ---------------------------------------------------------------- 人工归纳：右键菜单 / 移除

function closeMenu() { const m = document.getElementById("menu"); if (m) m.remove(); }
function openMenu(x, y, items) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu"; m.id = "menu";
  for (const it of items) {
    if (it.sep) { const s = document.createElement("div"); s.className = "sep"; m.appendChild(s); continue; }
    const b = document.createElement("button");
    b.textContent = it.label;
    b.onclick = () => { closeMenu(); it.fn(); };
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const rect = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - rect.width - 8) + "px";
  m.style.top = Math.min(y, innerHeight - rect.height - 8) + "px";
}
function rowMenu(e, op, recs) {
  const items = [{label: "扩展（放入临时区）", fn: () => stageOp(op, "extend", null)}];
  if (recs.length === 1) {
    items.push({label: "移动（带走条件/备注，删除源行）", fn: () => stageOp(op, "move", recs[0])});
    items.push({label: "移除（删除该行）", fn: () => removeRow(recs[0])});
  } else {
    for (const x of recs) {
      items.push({sep: true});
      items.push({label: "移动：原行在「" + blkFull(x.b) + "」", fn: () => stageOp(op, "move", x)});
      items.push({label: "移除：原行在「" + blkFull(x.b) + "」", fn: () => removeRow(x)});
    }
  }
  openMenu(e.clientX, e.clientY, items);
}
async function removeRow(x) {
  if (!confirm("从「" + blkFull(x.b) + "」删除「" + x.r.op + "」的整行记录？\n（含条件/备注/依据，源文件 " + x.b.file + ":" + x.r.line + "，可用 git 恢复）")) return;
  try {
    const j = await api("/api/apply", {automerge: automergeOn(), ops: [{kind: "delete", op: x.r.op,
      from: {block: {id: x.b.id, sig: x.b.sig}, line: x.r.line, raw: x.r.raw}}]});
    afterApply(j, "已移除：" + x.r.op);
  } catch (e) { toast(e.message, true); if (e.code === "drift") load(true); }
}
function afterApply(j, prefix) {
  const msgs = [];
  for (const r of j.results || []) {
    if (r.targets) {
      const bad = r.targets.filter(t => t.skipped);
      msgs.push((prefix ? prefix + "：" : "") + r.op + " → 已并入 " + (r.targets.length - bad.length) + " 个子表" +
        (bad.length ? "，跳过 " + bad.map(t => t.label + "（已在表内）").join("、") : ""));
    } else if (r.skipped) msgs.push(r.op + "：" + r.reason);
    else if (r.kind === "move") msgs.push("已移动：" + r.op + " → " + (r.to ? r.to.file : "") +
      (r.dropped && Object.keys(r.dropped).length ? "（" + Object.keys(r.dropped).join("、") + " 列目标表没有，未随行）" : ""));
    else msgs.push(prefix || "已完成");
  }
  const pruned = Object.entries(j.pruned_recommend || {});
  if (pruned.length) msgs.push("同步取消了荐：" + pruned.map(([t, ops]) => "「" + t + "」" + ops.join("、")).join("；"));
  for (const m of msgs) toast(m);
  for (const w of j.warnings || []) toast(w, true);
  const mg = j.merge || {};
  const bad = Object.entries(mg).filter(([, v]) => !v.ok);
  if (bad.length) toast("重新生成名单文档失败：" + bad.map(([k, v]) => k + " " + (v.err || v.out || "")).join("；"), true);
  return load(true);
}

// ---------------------------------------------------------------- 人工归纳：临时区

function stageSave() {
  try {
    localStorage.setItem("induct.v1", JSON.stringify({targets: ST.ind.targets, stage: ST.ind.stage}));
  } catch (e) {}
}
function stageOp(op, mode, rec) {
  const k = ST.ind.stage.findIndex(s => s.op === op);
  if (k >= 0) {
    const cur = ST.ind.stage[k];
    const sameSrc = mode === "move" && cur.mode === "move" && rec && cur.src
      && cur.src.blockId === rec.b.id && cur.src.line === rec.r.line;
    if (mode !== "move" || sameSrc) {
      toast("「" + op + "」已在临时区" + (cur.mode === "move" ? "（移动）" : ""));
      return;
    }
    ST.ind.stage.splice(k, 1);  // 已暂存为「扩展」或来自别的行时，按新来源覆盖（移动会带上条件/备注）
    toast("临时区中「" + op + "」的来源已更新");
  }
  ST.ind.stage.push({
    sid: "st-" + Date.now() + "-" + Math.floor(Math.random() * 1000),
    op, mode,
    src: rec ? {blockId: rec.b.id, blockSig: rec.b.sig, file: rec.b.file, line: rec.r.line, raw: rec.r.raw,
                tagName: rec.b.tagName, label: blkLabel(rec.b), full: blkFull(rec.b), src: rec.r.src} : null,
    preview: rec ? {cond: rec.r.cond, note: rec.r.note} : null,
    stale: false,
  });
  stageSave();
  toast((mode === "move" ? "已放入临时区（移动）：" : "已放入临时区（扩展）：") + op);
  renderStage();
}
function renderStage() {
  const list = document.getElementById("stagelist");
  list.innerHTML = "";
  if (!ST.ind.stage.length) {
    list.innerHTML = "<span class='empty'>空。右侧摘选区左键、或干员行右键「扩展 / 移动」把干员放进来；选中目标子表后点这里的干员即可并入。</span>";
    return;
  }
  for (const it of ST.ind.stage) {
    const el = document.createElement("div");
    el.className = "stage-item" + (it.mode === "move" ? " mv" : "") + (it.stale ? " stale" : "");
    const tag = it.mode === "move" && it.src ? "移动·自 " + (it.src.full || it.src.tagName) : "扩展";
    el.innerHTML = "<b>" + esc(it.op) + '</b><span class="badge">' + esc(tag) + "</span>" +
      (it.stale ? "<span class='chip'>源行已变化，请重新摘取</span>" : "") +
      "<button class='x' title='移出临时区'>×</button>";
    el.title = it.mode === "move" && it.preview
      ? "将带走：条件＝" + (it.preview.cond || "（空）") + "\n备注＝" + (it.preview.note || "（空）")
      : "并入后新行的条件/备注为空，需自行填写";
    el.onclick = e => { if (e.target.closest(".x")) return; dropStage(it); };
    el.querySelector(".x").onclick = e => {
      e.stopPropagation();
      ST.ind.stage = ST.ind.stage.filter(s => s.sid !== it.sid);
      stageSave(); renderStage();
    };
    list.appendChild(el);
  }
}
async function dropStage(it) {
  if (ST.ind.busy) return;
  const targets = ST.ind.targets;
  if (!targets.length) { toast("请先在左侧选中目标子表", true); return; }
  if (it.stale) { toast("该条目所记的源行已变化，请重新摘取", true); return; }
  if (it.mode === "move" && targets.length !== 1) { toast("移动只能指定一个目标子表", true); return; }
  ST.ind.busy = true;
  try {
    const ops = it.mode === "move"
      ? [{kind: "move", op_id: it.sid, from: {block: {id: it.src.blockId, sig: it.src.blockSig}, line: it.src.line, raw: it.src.raw}, targets: targets.map(t => ({id: t.id, sig: t.sig}))}]
      : [{kind: "insert", op_id: it.sid, op: it.op, cond: "", note: "", sub: "", targets: targets.map(t => ({id: t.id, sig: t.sig}))}];
    const j = await api("/api/apply", {automerge: automergeOn(), ops});
    if (it.mode === "move") ST.ind.stage = ST.ind.stage.filter(s => s.sid !== it.sid);
    stageSave();
    await afterApply(j, "");
  } catch (e) {
    toast(e.message, true);
    if (e.code === "drift") { await load(true); markStageStale(); }
  } finally { ST.ind.busy = false; }
}
function markStageStale() {
  for (const it of ST.ind.stage) {
    if (it.mode !== "move" || !it.src) continue;
    const b = blockById(it.src.blockId);
    const r = b ? b.rows.find(r => r.raw === it.src.raw) : null;
    if (!b || !r) it.stale = true;
    else { it.src.line = r.line; it.src.raw = r.raw; it.stale = false; }
  }
  stageSave(); renderStage();
}

// ---------------------------------------------------------------- 人工归纳：摘选区

function renderPicker() {
  const list = document.getElementById("picklist");
  list.innerHTML = "";
  const all = (DATA.roster || []).slice().sort((a, b) => a.name.localeCompare(b.name, "zh"));
  const items = all.filter(p => matches(p.name, ST.ind.pq));
  document.getElementById("pcnt").textContent = items.length + " / " + all.length + " 人";
  for (const p of items) {
    const staged = ST.ind.stage.some(s => s.op === p.name);
    const el = opRow({op: p.name}, {
      rank: "",
      chips: [p.star ? "★".repeat(p.star) : "", [p.cls, p.branch].filter(Boolean).join("·"), p.date].filter(Boolean),
      cls: staged ? "open" : "",
      buttons: [],
      onClick: () => stageOp(p.name, "extend", null),
    });
    list.appendChild(el);
  }
}

// ---------------------------------------------------------------- 结果 JSON：状态与视图同步

const RES = {
  file: null, eol: "crlf", doc: null, base: "", expect: null, today: "",
  view: "card", mode: "tag", shape: "none", dirty: false, busy: false,
  src: "", srcParsed: true, srcErr: "", list: null, problems: null, stats: null,
  sel: {tag: -1, mi: -1, op: -1}, q: {t: "", m: "", o: ""}, opage: 1,
};
const RES_CLASSES = ["先锋", "近卫", "狙击", "重装", "医疗", "辅助", "术师", "特种"];
const RES_CATS = ["A 控制·异常", "B 伤害类型", "C 生存与增益", "D 部署与编队", "E 技力与技能资源",
  "F 治疗与支援", "G 召唤物", "H 攻击行为特征", "I 全场光环"];
const RES_ANCHORS = ["", "#技能", "#天赋", "#模组", "#召唤物信息"];

const serialize = d => JSON.stringify(d, null, 2);
function resShape(d) {
  if (d === null || typeof d !== "object" || Array.isArray(d)) return "notobject";
  if (!Array.isArray(d.tags) || !Array.isArray(d.operators)) return "foreign";
  return "ok";
}
function curText() { return RES.view === "src" ? RES.src : serialize(RES.doc); }
function resDirtyNow() { return RES.doc !== null && serialize(RES.doc) !== RES.base; }
function rootUrl(name) { return "https://prts.wiki/w/" + encodeURIComponent(name); }
function resTag() { return RES.doc && RES.doc.tags ? RES.doc.tags[RES.sel.tag] : null; }
function resMember() {
  const t = resTag();
  return t && t.members && RES.sel.mi >= 0 ? t.members[RES.sel.mi] : null;
}
let resDraftTimer = null;
function resDraft() {
  clearTimeout(resDraftTimer);
  resDraftTimer = setTimeout(() => {
    try {
      const text = curText();
      if (text.length > 1500000) return;  // 接近 localStorage 配额，放弃草稿
      localStorage.setItem("res.v1", JSON.stringify({file: RES.file, eol: RES.eol, text, savedAt: Date.now()}));
    } catch (e) {}
  }, 1000);
}
function resMark() { RES.dirty = true; resDraft(); renderResBar(); }
function resSet(doc, meta) {
  RES.doc = doc;
  RES.file = meta.file || null;
  RES.eol = meta.eol || "crlf";
  RES.expect = meta.mtime_ns ? {mtime_ns: meta.mtime_ns, size: meta.size} : null;
  RES.base = serialize(doc);
  RES.dirty = false;
  RES.shape = resShape(doc);
  RES.problems = null; RES.stats = null;
  RES.view = "card";  // 非结果 JSON 在结构化区显示只读摘要，可手动切源码视图
  RES.mode = "tag";
  RES.sel = {tag: RES.shape === "ok" && doc.tags.length ? 0 : -1, mi: -1,
             op: RES.shape === "ok" && doc.operators.length ? 0 : -1};
  RES.opage = 1;
  RES.src = serialize(doc);
  RES.srcParsed = true; RES.srcErr = "";
  localStorage.removeItem("res.v1");
}
function resEnsure() {  // 把源码视图的文本提交进 doc
  if (RES.view !== "src") return true;
  try {
    RES.doc = JSON.parse(RES.src);
    RES.shape = resShape(RES.doc);
    RES.srcParsed = true; RES.srcErr = "";
    return true;
  } catch (e) { RES.srcParsed = false; RES.srcErr = String(e && e.message || e); return false; }
}
function resGuard(what) {
  if (!RES.doc) return true;
  if (RES.view === "src" && !resEnsure()) { toast("源码不是合法 JSON，请先修正：" + RES.srcErr, true); return false; }
  if (!resDirtyNow()) return true;
  return confirm("「结果 JSON」有未保存的改动，" + what + "会丢弃它们（浏览器草稿仍保留）。继续？");
}
function switchView(next) {
  if (!RES.doc || next === RES.view) return;
  if (next === "src") {
    RES.src = serialize(RES.doc);           // 结构化改动优先，无条件重写源码缓冲
    RES.srcParsed = true; RES.srcErr = "";
    RES.view = "src";
  } else {
    if (!resEnsure()) { renderResSrcErr(); toast("源码不是合法 JSON，已留在源码视图：" + RES.srcErr, true); return; }
    RES.view = "card";
  }
  renderResults();
}
function resSkeleton() {
  const today = RES.today || (RES.list && RES.list.today) || new Date().toISOString().slice(0, 10);
  return {version: "v1", updated: today, operators: [], tags: []};
}

async function resLoadDialog() {
  try {
    const list = await api("/api/results/list", {});
    RES.list = list; RES.today = list.today;
    const rows = list.files.map(f =>
      '<div class="mprob" data-f="' + esc(f.name) + '"><b>' + esc(f.name) + '</b>' +
      '<span class="hint">' + Math.round(f.size / 1024) + " KB</span></div>").join("") ||
      '<div class="mprob"><span class="hint">results/ 下还没有 json 文件，可先「新建骨架」</span></div>';
    openModal(
      '<h3>加载结果 JSON</h3><div class="hint">只列出 results/ 目录下的 json；加载后所有编辑只在内存中。</div>' +
      '<div class="mprobs">' + rows + '</div>' +
      '<div class="mfoot"><span class="sp"></span><button data-act="cancel">取消</button></div>',
      card => {
        card.querySelector('[data-act=cancel]').onclick = closeModal;
        card.querySelectorAll(".mprob[data-f]").forEach(el => {
          el.onclick = async () => {
            const name = el.dataset.f;
            closeModal();
            if (!resGuard("加载其他文件")) return;
            try {
              const j = await api("/api/results/load", {file: name});
              let doc;
              try { doc = JSON.parse(j.text); }
              catch (e) { doc = null; }
              if (doc === null) {
                RES.doc = null; RES.file = j.file; RES.eol = j.eol;
                RES.expect = j.mtime_ns ? {mtime_ns: j.mtime_ns, size: j.size} : null;
                RES.src = j.text; RES.view = "src"; RES.shape = "notobject"; RES.srcParsed = false; RES.srcErr = j.error || "解析失败";
                RES.base = j.text; RES.dirty = false;
                renderResults();
                toast("文件不是合法 JSON，已用源码视图打开，可修正后保存", true);
                return;
              }
              resSet(doc, j);
              renderResults();
              toast("已载入 results/" + j.file + "（" + (j.eol === "crlf" ? "CRLF" : "LF") + "）");
              if (RES.shape !== "ok") toast("该文件不是结果 JSON（缺 tags/operators），已切到源码视图", true);
            } catch (e) { toast(e.message, true); }
          };
        });
      });
  } catch (e) { toast(e.message, true); }
}

// ---- 渲染

function renderResBar() {
  const f = document.getElementById("resfile");
  if (f) f.textContent = RES.file ? "results/" + RES.file : (RES.doc ? "未命名（内存）" : "未载入");
  const dot = document.getElementById("resdot");
  if (dot) dot.classList.toggle("on", !!RES.dirty);
  const st = document.getElementById("resstats");
  if (st) {
    if (RES.shape === "ok" && RES.doc) {
      const members = RES.doc.tags.reduce((a, t) => a + ((t.members || []).length), 0);
      st.textContent = "operators " + RES.doc.operators.length + " · tags " + RES.doc.tags.length + " · 关系 " + members;
    } else st.textContent = RES.doc ? "非结果 JSON（只读浏览，可改源码）" : "";
  }
}
function renderResEmpty() {
  document.getElementById("resbody").hidden = false;
  document.getElementById("resrc").hidden = true;
  let draft = null;
  try { draft = JSON.parse(localStorage.getItem("res.v1") || "null"); } catch (e) {}
  const banner = draft
    ? '<div class="warnbar">发现未保存的浏览器草稿（' + esc(draft.file || "未命名") + " · " +
      new Date(draft.savedAt || Date.now()).toLocaleString() + "）<br>" +
      "<button id='btdraft'>恢复草稿</button> <button id='btdrop'>丢弃</button></div>"
    : "";
  document.getElementById("rtags").innerHTML = banner + "<div class='split'>尚未载入任何 JSON。</div>";
  document.getElementById("rmembers").innerHTML = "";
  document.getElementById("rpanel").innerHTML = "<div class='guide'>点上方「加载…」选择 results/ 下的 json，或「新建骨架」开始一份符合 <code>docs/output-standard.md</code> 的空文档。<br>所有编辑只发生在内存里，点「保存…」才会写盘（可覆盖已有文件，也可另存为新名字）。</div>";
  const btd = document.getElementById("btdraft");
  if (btd) btd.onclick = () => {
    RES.doc = null;
    try { RES.doc = JSON.parse(draft.text); } catch (e) { return toast("草稿不是合法 JSON，无法恢复", true); }
    RES.file = draft.file || null;
    RES.eol = draft.eol || "crlf";
    RES.expect = null;
    RES.base = "";
    RES.dirty = true;
    RES.shape = resShape(RES.doc);
    RES.view = RES.shape === "ok" ? "card" : "src";
    RES.src = draft.text;
    RES.sel = {tag: RES.shape === "ok" && RES.doc.tags.length ? 0 : -1, mi: -1, op: 0};
    renderResults();
    toast("已恢复草稿（注意：它可能比磁盘上的文件旧）");
  };
  const btx = document.getElementById("btdrop");
  if (btx) btx.onclick = () => { localStorage.removeItem("res.v1"); renderResEmpty(); };
  renderResBar();
}
function renderResults() {
  if (!RES.doc && !RES.file) return renderResEmpty();
  document.getElementById("btview").textContent = RES.view === "src" ? "结构化视图" : "源码视图";
  document.getElementById("resbody").hidden = RES.view === "src";
  document.getElementById("resrc").hidden = RES.view !== "src";
  document.getElementById("btmode").hidden = RES.view === "src" || RES.shape !== "ok";
  document.getElementById("btmode").textContent = RES.mode === "tag" ? "按干员" : "按 TAG";
  renderResBar();
  if (RES.view === "src") { renderResSrc(); return; }
  if (RES.shape !== "ok") { renderResForeign(); return; }  // 非结果 JSON：只读摘要，可切源码视图
  renderResLeft(); renderResMem(); renderResPanel();
}
function renderResForeign() {
  const keys = RES.doc && typeof RES.doc === "object" ? Object.keys(RES.doc).slice(0, 12) : [];
  document.getElementById("rtags").innerHTML =
    "<div class='warnbar'>该文件不是结果 JSON（缺 <code>tags</code> / <code>operators</code>），结构化编辑已停用。</div>" +
    "<div class='split'>顶层键：" + esc(keys.join("、") || "（无）") + "</div>" +
    "<button id='btgosrc'>到源码视图</button>";
  document.getElementById("rmembers").innerHTML = "";
  document.getElementById("rpanel").innerHTML = "<div class='guide'>可以点「新建骨架」开始一份符合规范的空文档，或用源码视图只读查看此文件。</div>";
  const b = document.getElementById("btgosrc");
  if (b) b.onclick = () => switchView("src");
}
function renderResSrc() {
  document.getElementById("rstext").value = RES.src;
  renderResSrcErr();
}
function renderResSrcErr() {
  const el = document.getElementById("rserr");
  el.textContent = RES.srcParsed ? "" : "JSON 解析失败：" + RES.srcErr;
}
function renderResLeft() {
  const box = document.getElementById("rtags");
  box.innerHTML = "";
  const search = document.getElementById("rtsearch");
  if (RES.mode === "op") {
    search.placeholder = "搜索干员…";
    const q = RES.q.o;
    const all = RES.doc.operators;
    const items = all.map((o, i) => ({o, i})).filter(x => matches(String(x.o.name || ""), q));
    document.getElementById("rtcnt").textContent = items.length + " / " + all.length;
    const per = 80, pages = Math.max(1, Math.ceil(items.length / per));
    RES.opage = Math.min(Math.max(1, RES.opage), pages);
    const slice = items.slice((RES.opage - 1) * per, RES.opage * per);
    slice.forEach(x => box.appendChild(opLine(x.i, x.o)));
    if (pages > 1) {
      const d = document.createElement("div");
      d.className = "split";
      d.textContent = "第 " + RES.opage + " / " + pages + " 页";
      box.appendChild(d);
      const nav = document.createElement("div");
      nav.style.cssText = "display:flex;gap:6px;padding:0 2px";
      nav.append(miniBtn("上一页", "", () => { RES.opage--; renderResLeft(); }, RES.opage <= 1),
                 miniBtn("下一页", "", () => { RES.opage++; renderResLeft(); }, RES.opage >= pages));
      box.appendChild(nav);
    }
    const addOp = document.createElement("div");
    addOp.style.cssText = "padding:8px 2px";
    addOp.appendChild(miniBtn("＋ 新增干员条目", "从全量干员表挑一个，字段自动带出", addOperatorDialog));
    box.appendChild(addOp);
    return;
  }
  search.placeholder = "搜索 TAG / id…";
  const q = RES.q.t;
  const tags = RES.doc.tags;
  const hit = tags.map((t, i) => ({t, i})).filter(x =>
    !q || String(x.t.name || "").toLowerCase().includes(q) || String(x.t.id || "").toLowerCase().includes(q));
  document.getElementById("rtcnt").textContent = hit.length + " / " + tags.length;
  let lastSrc = null;
  for (const x of hit) {
    if (x.t.source !== lastSrc) {
      lastSrc = x.t.source;
      const h = document.createElement("div");
      h.className = "rsec";
      h.textContent = x.t.source === "official" ? "官方设定 TAG" : (x.t.source === "player" ? "玩家体感 TAG" : String(x.t.source || "未知 source"));
      box.appendChild(h);
    }
    const el = document.createElement("div");
    el.className = "tagline" + (RES.sel.tag === x.i ? " on" : "");
    el.innerHTML = '<span class="dotid">' + esc(x.t.id || "—") + '</span><span>' + esc(x.t.name || "（无名）") +
      '</span><span class="n">' + ((x.t.members || []).length) + "</span>";
    el.onclick = () => { RES.sel.tag = x.i; RES.sel.mi = -1; renderResMem(); renderResPanel(); renderResLeft(); };
    box.appendChild(el);
  }
}
function opLine(i, o) {
  const el = document.createElement("div");
  el.className = "tagline" + (RES.sel.op === i ? " on" : "");
  el.innerHTML = "<span>" + esc(o.name || "（无名）") + "</span>" +
    '<span class="n">' + esc([o.rarity ? o.rarity + "★" : "", o.class || ""].filter(Boolean).join(" · ")) + "</span>";
  el.onclick = () => { RES.sel.op = i; renderResMem(); renderResPanel(); renderResLeft(); };
  return el;
}
function renderResMem() {
  const box = document.getElementById("rmembers");
  box.innerHTML = "";
  if (RES.mode === "op") return renderResRefs(box);
  const t = resTag();
  if (!t) { box.innerHTML = "<div class='split'>左侧选一个 TAG。</div>"; document.getElementById("rmcnt").textContent = ""; return; }
  const q = RES.q.m;
  const members = t.members || [];
  const items = members.map((m, j) => ({m, j})).filter(x => matches(String(x.m.operator || ""), q));
  document.getElementById("rmcnt").textContent = items.length + " / " + members.length + " 人";
  const head = document.createElement("div");
  head.className = "split";
  head.innerHTML = esc(t.name || "") + " · <span class='dotid'>" + esc(t.id || "") + "</span>";
  box.appendChild(head);
  for (const x of items) {
    const el = document.createElement("div");
    el.className = "card" + (RES.sel.mi === x.j ? " open" : "");
    el.innerHTML = '<span class="rank"></span><span class="name">' + esc(x.m.operator || "（缺 operator）") + "</span>" +
      '<span class="chips">' + (x.m.condition ? '<span class="chip">' + esc(String(x.m.condition).slice(0, 40)) + "</span>" : '<span class="chip" style="color:#b0863b">条件待填</span>') +
      ((x.m.subTags || []).length ? '<span class="chip">' + (x.m.subTags || []).length + " 个子 TAG</span>" : "") + "</span>";
    el.onclick = () => { RES.sel.mi = RES.sel.mi === x.j ? -1 : x.j; renderResMem(); renderResPanel(); };
    box.appendChild(el);
  }
  const add = document.createElement("div");
  add.style.cssText = "padding:8px 2px";
  add.innerHTML = "<button id='btaddmem'>＋ 加成员</button>";
  box.appendChild(add);
  const btn = document.getElementById("btaddmem");
  if (btn) btn.onclick = () => addMemberDialog(RES.sel.tag);
}
function renderResRefs(box) {
  const o = RES.doc.operators[RES.sel.op];
  document.getElementById("rmcnt").textContent = "";
  if (!o) { box.innerHTML = "<div class='split'>左侧选一个干员。</div>"; return; }
  const head = document.createElement("div");
  head.className = "split";
  head.textContent = "「" + (o.name || "（无名）") + "」被以下 TAG 引用";
  box.appendChild(head);
  let n = 0;
  RES.doc.tags.forEach((t, i) => (t.members || []).forEach((m, j) => {
    if (m.operator !== o.name) return;
    n++;
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = '<span class="rank"></span><span class="name">' + esc(t.name || "") + "</span>" +
      '<span class="chips"><span class="chip">' + esc(t.id || "") + '</span><span class="chip">members[' + j + "]</span></span>";
    el.onclick = () => { RES.mode = "tag"; RES.sel.tag = i; RES.sel.mi = j; renderResults(); };
    box.appendChild(el);
  }));
  if (!n) box.innerHTML += "<div class='split'>没有任何 TAG 引用（规范要求 operators 只收录进过成员表的干员）。</div>";
}

// ---------------------------------------------------------------- 结果 JSON：编辑面板与操作

function field(el, get, set, opts) {
  el.classList.add("val");
  const paint = () => {
    const v = get() == null ? "" : String(get());
    el.textContent = v || (opts && opts.empty) || "（空）";
    el.classList.toggle("empty", !v);
  };
  paint();
  el.onclick = () => {
    const wrap = document.createElement("div");
    wrap.className = "editline";
    const inp = document.createElement(opts && opts.multi ? "textarea" : "input");
    if (!(opts && opts.multi)) inp.type = "text";
    if (opts && opts.multi) inp.rows = 2;
    inp.value = get() == null ? "" : String(get());
    const ok = document.createElement("button"); ok.textContent = "✓"; ok.title = "保存（Enter / Ctrl+Enter）";
    const no = document.createElement("button"); no.textContent = "×"; no.title = "取消（Esc）";
    wrap.append(inp, ok, no);
    el.replaceWith(wrap);
    inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
    const finish = commit => {
      wrap.replaceWith(el);
      if (commit) { set(inp.value); resMark(); renderResults(); } else paint();
    };
    ok.onclick = () => finish(true);
    no.onclick = () => finish(false);
    inp.onkeydown = e => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); }
      else if (e.key === "Enter" && (!(opts && opts.multi) || e.ctrlKey)) { e.preventDefault(); finish(true); }
    };
  };
  return el;
}
function kv(label, valueEl, note) {
  const d = document.createElement("div");
  d.className = "kv";
  d.innerHTML = "<b>" + esc(label) + "</b>";
  d.appendChild(valueEl);
  if (note) { const s = document.createElement("span"); s.className = "ro"; s.textContent = note; d.appendChild(s); }
  return d;
}
function roText(text) { const s = document.createElement("span"); s.className = "ro"; s.textContent = text; return s; }
function selectEl(value, options, onPick) {
  const sel = document.createElement("select");
  const opts = options.slice();
  if (value != null && value !== "" && !opts.includes(value)) opts.unshift(value);
  for (const o of opts) { const e = document.createElement("option"); e.value = o; e.textContent = o || "（空）"; sel.appendChild(e); }
  sel.value = value == null ? "" : value;
  sel.onchange = () => { onPick(sel.value); resMark(); renderResults(); };
  return sel;
}
function miniBtn(label, title, fn, dis) {
  const b = document.createElement("button");
  b.className = "mini"; b.textContent = label; b.title = title || ""; b.disabled = !!dis; b.onclick = fn;
  return b;
}

function renderResPanel() {
  const box = document.getElementById("rpanel");
  box.innerHTML = "";
  if (RES.mode === "op") return renderOpCard(box);
  const t = resTag();
  if (!t) { box.innerHTML = "<div class='guide'>左侧选一个 TAG。</div>"; return; }
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>TAG</h4>";
  g.appendChild(kv("id", roText(String(t.id || "—")), "规范：一经发布不得更改"));
  const nameEl = document.createElement("span");
  field(nameEl, () => t.name, v => { t.name = v; }, {});
  g.appendChild(kv("name", nameEl));
  g.appendChild(kv("source", roText(String(t.source || "—"))));
  if (t.source === "official") g.appendChild(kv("category", selectEl(t.category, RES_CATS, v => { t.category = v; })));
  else if (t.source === "player") g.appendChild(kv("recommended", roText(Array.isArray(t.recommended) ? t.recommended.length + " 人" : "（缺字段）")));
  g.appendChild(kv("members", roText(String((t.members || []).length) + " 人")));
  box.appendChild(g);

  if (t.source === "player") {
    const g2 = document.createElement("div");
    g2.className = "pgroup";
    g2.innerHTML = "<h4>荐（按展示优先级）</h4>";
    const rec = Array.isArray(t.recommended) ? t.recommended : null;
    if (!rec) g2.innerHTML += "<div class='hint'>缺 recommended 字段（点「按规范整理」可补空数组）。</div>";
    else if (!rec.length) g2.innerHTML += "<div class='hint'>暂无。</div>";
    else rec.forEach((name, k) => {
      const row = document.createElement("div");
      row.className = "subrow";
      const s = document.createElement("span"); s.style.flex = "1"; s.textContent = (k + 1) + ". " + name;
      row.appendChild(s);
      row.appendChild(miniBtn("↑", "上移", () => { rec.splice(k - 1, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === 0));
      row.appendChild(miniBtn("↓", "下移", () => { rec.splice(k + 1, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === rec.length - 1));
      row.appendChild(miniBtn("⤒", "置顶", () => { rec.splice(0, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === 0));
      row.appendChild(miniBtn("×", "取消荐", () => { rec.splice(k, 1); resMark(); renderResults(); }));
      g2.appendChild(row);
    });
    const add = document.createElement("div");
    add.style.marginTop = "6px";
    add.appendChild(miniBtn("＋ 加荐", "只能从本 TAG 的成员里选", () => recAddDialog(RES.sel.tag)));
    g2.appendChild(add);
    box.appendChild(g2);
  }

  const m = resMember();
  if (!m) {
    const hint = document.createElement("div");
    hint.className = "guide";
    hint.textContent = "点中间任一成员行即可编辑它的 条件 / 备注 / 子 TAG / prtsUrl。";
    box.appendChild(hint);
    return;
  }
  box.appendChild(memberCard(t, m));
}

function memberCard(t, m) {
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>成员：" + esc(String(m.operator || "（缺 operator）")) + "</h4>";
  const condEl = document.createElement("span");
  field(condEl, () => m.condition, v => { m.condition = v; }, {multi: true, empty: "（待填）"});
  g.appendChild(kv("条件", condEl));
  const noteEl = document.createElement("span");
  field(noteEl, () => m.remark, v => { if (v.trim()) m.remark = v; else delete m.remark; }, {multi: true, empty: "（空，保存时省略该字段）"});
  g.appendChild(kv("备注", noteEl));

  const sg = document.createElement("div");
  sg.style.marginTop = "8px";
  const h = document.createElement("div");
  h.innerHTML = "<b style='font-size:12px'>子 TAG</b>";
  sg.appendChild(h);
  const subs = m.subTags || [];
  subs.forEach((s, k) => {
    const row = document.createElement("div");
    row.className = "subrow";
    const ge = document.createElement("span"); field(ge, () => s.group, v => { s.group = v; }, {empty: "组"});
    const ve = document.createElement("span"); field(ve, () => s.value, v => { s.value = v; }, {empty: "值"});
    const de = document.createElement("span"); field(de, () => s.detail, v => { if (v.trim()) s.detail = v; else delete s.detail; }, {empty: "detail"});
    row.append(ge, ve, de);
    row.appendChild(miniBtn("×", "删除该子 TAG", () => {
      subs.splice(k, 1);
      if (!subs.length) delete m.subTags;
      resMark(); renderResults();
    }));
    sg.appendChild(row);
  });
  sg.appendChild(miniBtn("＋ 子 TAG", "", () => {
    m.subTags = Array.isArray(m.subTags) ? m.subTags : [];
    m.subTags.push({group: "", value: ""});
    resMark(); renderResults();
  }));
  g.appendChild(sg);

  const urlEl = document.createElement("span");
  field(urlEl, () => m.prtsUrl, v => { m.prtsUrl = v; }, {});
  g.appendChild(kv("prtsUrl", urlEl));
  const anch = document.createElement("div");
  anch.className = "subrow";
  RES_ANCHORS.forEach(a => anch.appendChild(miniBtn(a || "无锚点", "改用该锚点", () => {
    m.prtsUrl = String(m.prtsUrl || "").split("#")[0] + a;
    resMark(); renderResults();
  })));
  anch.appendChild(miniBtn("按干员名重建", "", () => {
    const tail = String(m.prtsUrl || "").includes("#") ? "#" + String(m.prtsUrl).split("#")[1] : "";
    m.prtsUrl = rootUrl(String(m.operator || "")) + tail;
    resMark(); renderResults();
  }));
  g.appendChild(anch);

  const acts = document.createElement("div");
  acts.className = "subrow";
  acts.style.marginTop = "8px";
  const move = (label, d, dis) => miniBtn(label, "", () => {
    const arr = t.members;
    const j = RES.sel.mi;
    const nk = Math.min(Math.max(j + d, 0), arr.length - 1);
    if (nk === j) return;
    arr.splice(nk, 0, arr.splice(j, 1)[0]);
    RES.sel.mi = nk;
    resMark(); renderResults();
  }, dis);
  acts.append(move("↑ 上移", -1, RES.sel.mi <= 0), move("↓ 下移", 1, RES.sel.mi >= (t.members || []).length - 1));
  acts.appendChild(miniBtn("删除成员", "", () => {
    if (!confirm("删除「" + String(m.operator || "") + "」在「" + String(t.name || "") + "」下的这条记录？\n（只改内存，保存前不会写盘）")) return;
    t.members.splice(RES.sel.mi, 1);
    RES.sel.mi = -1;
    resMark(); renderResults();
  }));
  g.appendChild(acts);
  return g;
}

function renderOpCard(box) {
  const i = RES.sel.op;
  const o = RES.doc.operators[i];
  if (!o) { box.innerHTML = "<div class='guide'>左侧选一个干员。</div>"; return; }
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>干员基本信息</h4>";
  const nameEl = document.createElement("span");
  field(nameEl, () => o.name, v => renameOperator(i, v), {});
  g.appendChild(kv("name", nameEl, "改名会级联更新成员与荐"));
  const rin = document.createElement("input");
  rin.type = "number"; rin.min = "1"; rin.max = "6";
  rin.value = o.rarity == null ? "" : o.rarity;
  rin.style.cssText = "width:4.5em;font:inherit;font-size:13px;padding:2px 5px;border:1px solid var(--line);border-radius:6px";
  rin.onchange = () => { const v = parseInt(rin.value, 10); if (!Number.isNaN(v)) { o.rarity = v; resMark(); renderResults(); } };
  g.appendChild(kv("rarity", rin));
  g.appendChild(kv("class", selectEl(o.class, RES_CLASSES, v => { o.class = v; })));
  for (const [label, key] of [["branch", "branch"], ["faction", "faction"], ["releaseDate", "releaseDate"], ["prtsUrl", "prtsUrl"]]) {
    const el = document.createElement("span");
    field(el, () => o[key], v => { o[key] = v; }, {});
    g.appendChild(kv(label, el));
  }
  const acts = document.createElement("div");
  acts.className = "subrow";
  acts.style.marginTop = "8px";
  acts.appendChild(miniBtn("从全量干员表补全", "", () => opFill(i)));
  acts.appendChild(miniBtn("删除条目", "", () => opDel(i)));
  g.appendChild(acts);
  box.appendChild(g);
}

function pickDialog(title, names, onPick) {
  openModal('<h3>' + esc(title) + '</h3>' +
    '<div class="mradio"><input id="mkq" type="text" placeholder="搜索干员名…" style="flex:1;font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px"></div>' +
    '<div class="mprobs" id="mklist"></div>' +
    '<div class="mfoot"><span class="sp"></span><button data-act="cancel">取消</button></div>',
    card => {
      const list = card.querySelector("#mklist");
      const inp = card.querySelector("#mkq");
      const draw = () => {
        const q = inp.value.trim().toLowerCase();
        const hit = names.filter(n => matches(n, q)).slice(0, 200);
        list.innerHTML = hit.map(n => '<div class="mprob" data-n="' + esc(n) + '">' + esc(n) + "</div>").join("") ||
          '<div class="mprob"><span class="hint">无匹配</span></div>';
        list.querySelectorAll(".mprob[data-n]").forEach(el => {
          el.onclick = () => { closeModal(); onPick(el.dataset.n); };
        });
      };
      inp.oninput = draw;
      draw();
      inp.focus();
      card.querySelector("[data-act=cancel]").onclick = closeModal;
    });
}
function addMemberDialog(ti) {
  const t = RES.doc.tags[ti];
  const names = RES.doc.operators.map(o => String(o.name || "")).filter(Boolean);
  if (!names.length) return toast("operators[] 还是空的：先到「按干员」视图新增干员条目", true);
  pickDialog("给「" + String(t.name || "") + "」加成员", names, name => {
    t.members = Array.isArray(t.members) ? t.members : [];
    t.members.push({operator: name, condition: "", prtsUrl: rootUrl(name)});
    RES.sel.mi = t.members.length - 1;
    resMark(); renderResults();
    toast("已加成员（条件留空，保存前请补上）");
  });
}
function recAddDialog(ti) {
  const t = RES.doc.tags[ti];
  const rec = Array.isArray(t.recommended) ? t.recommended : [];
  const names = (t.members || []).map(m => String(m.operator || "")).filter(n => n && !rec.includes(n));
  pickDialog("给「" + String(t.name || "") + "」加荐", names, name => {
    t.recommended = Array.isArray(t.recommended) ? t.recommended : [];
    t.recommended.push(name);
    resMark(); renderResults();
  });
}
function addOperatorDialog() {
  const names = (DATA.roster || []).map(p => p.name);
  pickDialog("新增干员条目", names, name => {
    const p = (DATA.roster || []).find(x => x.name === name) || {};
    RES.doc.operators.push({name, rarity: p.star || 1, class: p.cls || "", branch: p.branch || "",
      faction: p.faction || "", releaseDate: p.date || "", prtsUrl: p.url || rootUrl(name)});
    RES.sel.op = RES.doc.operators.length - 1;
    RES.opage = Math.ceil(RES.doc.operators.length / 80);
    resMark(); renderResults();
  });
}
function opFill(i) {
  const o = RES.doc.operators[i];
  const p = (DATA.roster || []).find(x => x.name === o.name);
  if (!p) return toast("全量干员表里没有「" + String(o.name || "") + "」", true);
  o.rarity = p.star || o.rarity;
  o.class = p.cls || o.class;
  o.branch = p.branch || o.branch;
  o.faction = p.faction || "";
  o.releaseDate = p.date || o.releaseDate;
  o.prtsUrl = p.url || rootUrl(String(o.name || ""));
  resMark(); renderResults();
  toast("已按全量干员表补全");
}
function opDel(i) {
  const o = RES.doc.operators[i];
  let refs = 0;
  RES.doc.tags.forEach(t => (t.members || []).forEach(m => { if (m.operator === o.name) refs++; }));
  if (!confirm("删除干员条目「" + String(o.name || "") + "」？" + (refs ? "仍有 " + refs + " 处成员引用，删除会产生悬空引用（校验会报错）。" : "（当前无引用）"))) return;
  RES.doc.operators.splice(i, 1);
  RES.sel.op = Math.min(i, RES.doc.operators.length - 1);
  resMark(); renderResults();
}
function renameOperator(i, value) {
  const o = RES.doc.operators[i];
  const old = String(o.name || "");
  const next = String(value || "").trim();
  if (!next || next === old) return;
  let n = 0;
  RES.doc.tags.forEach(t => {
    (t.members || []).forEach(m => { if (m.operator === old) { m.operator = next; n++; } });
    if (Array.isArray(t.recommended)) t.recommended = t.recommended.map(x => (x === old ? next : x));
  });
  o.name = next;
  resMark(); renderResults();
  toast("已改名（级联 " + n + " 处成员引用）");
}

// ---- 文档级整理 / 校验

function resSortAll() {
  const doc = RES.doc;
  const rank = t => (t.source === "official" ? 0 : 1) * 10000 +
    (t.source === "official" ? Math.max(0, RES_CATS.indexOf(t.category)) : (parseInt(String(t.id || "").replace(/\D/g, ""), 10) || 99));
  const ordered = doc.tags.map((t, i) => ({t, i})).sort((a, b) => rank(a.t) - rank(b.t));
  const tagOrder = ordered.filter((x, k) => x.i !== k).length;
  const opsSorted = doc.operators.slice().sort((a, b) => String(b.releaseDate || "").localeCompare(String(a.releaseDate || "")));
  const opOrder = opsSorted.filter((o, k) => doc.operators[k] !== o).length;
  let emptyRemark = 0, emptySub = 0, missingRec = 0;
  doc.tags.forEach(t => {
    (t.members || []).forEach(m => {
      if ("remark" in m && !String(m.remark || "").trim()) emptyRemark++;
      if ("subTags" in m && (!Array.isArray(m.subTags) || !m.subTags.length)) emptySub++;
    });
    if (t.source === "player" && !Array.isArray(t.recommended)) missingRec++;
  });
  const total = tagOrder + opOrder + emptyRemark + emptySub + missingRec;
  if (!total) return toast("已经符合规范，无需整理");
  if (!confirm("将调整：TAG 顺序 " + tagOrder + " 处、干员顺序 " + opOrder + " 处、删除空备注 " + emptyRemark +
      " 处、删除空子 TAG " + emptySub + " 处、补 recommended " + missingRec + " 处。\n（只改内存，保存前不写盘；阵容组合 P13 的成员顺序不动）继续？")) return;
  const keepId = resTag() ? resTag().id : null;
  doc.tags = ordered.map(x => x.t);
  doc.operators = opsSorted;
  doc.tags.forEach(t => {
    (t.members || []).forEach(m => {
      if ("remark" in m && !String(m.remark || "").trim()) delete m.remark;
      if ("subTags" in m && (!Array.isArray(m.subTags) || !m.subTags.length)) delete m.subTags;
    });
    if (t.source === "player" && !Array.isArray(t.recommended)) t.recommended = [];
  });
  RES.sel.tag = keepId ? Math.max(0, doc.tags.findIndex(t => t.id === keepId)) : 0;
  RES.sel.mi = -1;
  resMark(); renderResults();
  toast("已按规范整理（共 " + total + " 处）");
}
async function resDoCheck() {
  const text = curText();
  try {
    const j = await api("/api/results/check", {text});
    RES.problems = j.problems;
    RES.stats = j.stats;
    const errs = j.problems.filter(p => p.level === "error").length;
    if (!j.parsed) toast("JSON 解析失败：" + j.problems[0].message, true);
    else toast("校验：" + errs + " 个错误 / " + (j.problems.length - errs) + " 个提醒", errs > 0);
    return j;
  } catch (e) { toast(e.message, true); return null; }
}
function problemsHtml(problems, limit) {
  if (!problems) return '<div class="mprob"><span class="hint">正在校验…</span></div>';
  if (!problems.length) return '<div class="mprob"><span class="lv" style="color:var(--ok)">通过</span><span>没有发现问题</span></div>';
  const show = problems.slice(0, limit || 8);
  return show.map((p, k) => '<div class="mprob ' + esc(p.level) + '" data-k="' + k + '"><span class="lv">' +
      (p.level === "error" ? "错误" : "提醒") + "</span><span>" + esc(p.label ? p.label + " — " : "") + esc(p.message) +
      '</span><span class="pth">' + esc(p.path || "") + "</span></div>").join("") +
    (problems.length > show.length ? '<div class="mprob"><span class="hint">另有 ' + (problems.length - show.length) + " 条未列出</span></div>" : "");
}
function jumpTo(loc) {
  if (!Array.isArray(loc) || !loc.length || RES.shape !== "ok") return;
  if (loc[0] === "tags" && typeof loc[1] === "number") {
    RES.mode = "tag";
    RES.view = "card";
    RES.sel.tag = loc[1];
    RES.sel.mi = (loc[2] === "members" && typeof loc[3] === "number") ? loc[3] : -1;
  } else if (loc[0] === "operators" && typeof loc[1] === "number") {
    RES.mode = "op";
    RES.view = "card";
    RES.sel.op = loc[1];
    RES.opage = Math.floor(loc[1] / 80) + 1;
  } else return;
  renderResults();
  const el = document.querySelector("#rmembers .card.open") || document.querySelector("#rmembers .card") ||
    document.querySelector("#rtags .tagline.on");
  if (el) el.scrollIntoView({block: "center"});
}

// ---- 保存

function resContentChanged() {
  try {
    const b = JSON.parse(RES.base || "null");
    if (!b || !RES.doc) return true;
    const strip = d => serialize({operators: d.operators, tags: d.tags});
    return strip(RES.doc) !== strip(b);
  } catch (e) { return true; }
}
function resNextVersion(v) {
  const m = /^v([1-9]\d*)$/.exec(String(v || ""));
  return m ? "v" + (Number(m[1]) + 1) : null;
}
async function resSaveDialog() {
  if (!RES.doc && RES.src) {  // 载入时就是坏 JSON 的文件：先在源码视图里修好，再允许保存
    try { RES.doc = JSON.parse(RES.src); RES.shape = resShape(RES.doc); } catch (e) {}
  }
  if (!RES.doc) return toast("先载入或新建一个 JSON", true);
  if (RES.view === "src" && !resEnsure()) return toast("源码不是合法 JSON，先修正：" + RES.srcErr, true);
  RES.dirty = resDirtyNow();
  const changed = resContentChanged();
  const next = resNextVersion(RES.doc.version);
  let list = RES.list;
  try { list = await api("/api/results/list", {}); RES.list = list; RES.today = list.today; } catch (e) { toast(e.message, true); }
  const today = (list && list.today) || new Date().toISOString().slice(0, 10);
  const files = ((list && list.files) || []).map(f => f.name);
  const target = RES.file && files.includes(RES.file) ? RES.file
    : (files.includes("operator-tags.json") ? "operator-tags.json" : (files[0] || ""));
  const html =
    "<h3>保存结果 JSON</h3>" +
    '<div class="mhint">所有编辑都只在内存中，这一步才写盘。</div>' +
    '<div class="mradio"><label><input type="radio" name="mtarget" value="overwrite" checked' + (files.length ? "" : " disabled") + "> 覆盖已有文件</label>" +
    '<select id="mfile"' + (files.length ? "" : " disabled") + ">" + files.map(f => "<option" + (f === target ? " selected" : "") + ">" + esc(f) + "</option>").join("") + "</select>" +
    (files.length ? "" : '<span class="hint">（results/ 下暂无 json）</span>') + "</div>" +
    '<div class="mradio"><label><input type="radio" name="mtarget" value="new"' + (files.length ? "" : " checked") + "> 新建文件</label>" +
    '<input id="mnew" type="text" value="' + esc(RES.file || "operator-tags.json") + '" style="flex:1;min-width:12em"></div>' +
    '<div id="mcross" class="mhint err" hidden></div>' +
    '<div class="mradio"><label><input type="checkbox" id="mbump"' + (changed && next ? " checked" : "") + (changed && next ? "" : " disabled") + "> 内容有变时更新 version / updated</label>" +
    'version <input id="mver" type="text" style="width:5em" value="' + esc(next || RES.doc.version || "") + '">' +
    'updated <input id="mupd" type="date" value="' + esc(today) + '"></div>' +
    '<div class="mhint" id="mchg">' + (changed ? "内容有变化。" : "内容无变化，版本字段不变。") +
    (changed && !next ? "version 无法识别（规范：v1、v2…），请手动填写。" : "") + "</div>" +
    '<div class="mprobs" id="mprob">' + problemsHtml(RES.problems) + "</div>" +
    '<div class="mfoot"><label class="mhint"><input type="checkbox" id="mforce"> 强制覆盖（忽略外部改动）</label><span class="sp"></span>' +
    '<button data-act="cancel">取消</button><button class="primary" data-act="save" id="mok">保存</button></div>' +
    '<div class="mhint">Enter 保存 · Esc 关闭 · Ctrl+Enter 任意处保存</div>';
  openModal(html, card => bindSaveDialog(card, {files}));
  const j = await resDoCheck();
  const box = document.querySelector("#mprob");
  if (box && j) {
    box.innerHTML = problemsHtml(j.problems);
    bindProblemClicks(box, j.problems);
    const errs = j.problems.filter(p => p.level === "error").length;
    const ok = document.querySelector("#mok");
    if (ok && j.parsed && errs) ok.textContent = "仍有 " + errs + " 个问题，仍然保存";
    if (ok && !j.parsed) { ok.disabled = true; ok.textContent = "JSON 解析失败，无法保存"; }
  }
}
function bindProblemClicks(box, problems) {
  box.querySelectorAll(".mprob[data-k]").forEach(el => {
    el.onclick = () => {
      const p = problems[+el.dataset.k];
      if (!p) return;
      closeModal();
      jumpTo(p.loc);
    };
  });
}
function bindSaveDialog(card, ctx) {
  const radio = () => card.querySelector('input[name=mtarget]:checked').value;
  const sync = () => {
    const mode = radio();
    card.querySelector("#mfile").disabled = mode !== "overwrite";
    card.querySelector("#mnew").disabled = mode !== "new";
    const cross = mode === "overwrite" && card.querySelector("#mfile").value !== RES.file;
    const w = card.querySelector("#mcross");
    w.hidden = !cross;
    w.innerHTML = cross ? ("目标文件与当前载入的文件不同（当前：" + esc(RES.file || "未命名内存文档") +
      "），它的内容将被完全替换（可用 git 恢复）。" +
      '<label class="mhint"><input type="checkbox" id="mconfirm"> 我确认覆盖其他文件</label>') : "";
    if (cross) {
      const c = card.querySelector("#mconfirm");
      c.onchange = sync;
    }
    const crossOk = !cross || (card.querySelector("#mconfirm") && card.querySelector("#mconfirm").checked);
    card.querySelector("#mok").disabled = !crossOk;
    const exists = ctx.files.includes(card.querySelector("#mnew").value.trim());
    const nh = card.querySelector("#mnew");
    nh.classList.toggle("dirty", exists);
    nh.title = exists ? "已存在同名文件（请改用覆盖）" : "";
  };
  card.querySelectorAll('input[name=mtarget]').forEach(r => { r.onchange = sync; });
  card.querySelector("#mfile").onchange = sync;
  card.querySelector("#mnew").oninput = sync;
  card.querySelector("[data-act=cancel]").onclick = closeModal;
  card.querySelector("[data-act=save]").onclick = () => resDoSave(card);
  sync();
}
async function resDoSave(card) {
  const mode = card.querySelector('input[name=mtarget]:checked').value;
  const file = (mode === "overwrite" ? card.querySelector("#mfile").value : card.querySelector("#mnew").value).trim();
  const bumpBox = card.querySelector("#mbump");
  const bump = bumpBox.checked && !bumpBox.disabled;
  const ver = card.querySelector("#mver").value.trim();
  const upd = card.querySelector("#mupd").value.trim();
  const force = card.querySelector("#mforce").checked;
  const out = {...RES.doc};
  if (bump) {
    if (ver) out.version = ver;
    if (upd) out.updated = upd;
  }
  try {
    const j = await api("/api/results/save", {
      mode, file, text: serialize(out), eol: RES.eol,
      expect: mode === "overwrite" ? RES.expect : null, force,
    });
    RES.doc = out;
    RES.base = j.saved.text;
    RES.file = j.file;
    RES.expect = {mtime_ns: j.mtime_ns, size: j.size};
    RES.dirty = false;
    RES.problems = j.problems;
    RES.stats = j.stats;
    RES.shape = resShape(RES.doc);
    RES.src = serialize(RES.doc);
    localStorage.removeItem("res.v1");
    closeModal();
    renderResults();
    toast("已保存 results/" + j.file + (j.created ? "（新建）" : "（覆盖）") + " · " + Math.round(j.bytes / 1024) + " KB");
  } catch (e) {
    if (e.code === "drift") toast("文件已被外部改动：可勾「强制覆盖」再保存，或重新载入", true);
    else toast(e.message, true);
  }
}

// ---- 模态框

function openModal(html, onMount) {
  const m = document.getElementById("modal");
  const card = m.querySelector(".modal-card");
  card.innerHTML = html;
  m.hidden = false;
  if (onMount) onMount(card);
  return card;
}
function closeModal() {
  const m = document.getElementById("modal");
  if (m.hidden) return false;
  m.hidden = true;
  m.querySelector(".modal-card").innerHTML = "";
  return true;
}

// ---------------------------------------------------------------- 页签 / 跳转

function renderAll() {
  renderTags(); renderOps(); renderRec();
  renderInd(); renderIndList(); renderPicker();
}
function setTab(t) {
  ST.tab = t;
  document.getElementById("page-zhen").hidden = t !== "zhen";
  document.getElementById("page-induce").hidden = t !== "induce";
  document.getElementById("page-json").hidden = t !== "results";
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  for (const id of ("automergewrap,btmerge,btreload").split(",")) {
    const el = document.getElementById(id);
    if (el) el.hidden = t === "results";  // 这三个是前两页的控件
  }
  document.getElementById("hint").textContent = t === "zhen"
    ? "左键 = 加荐 · 右键 = 取消荐"
    : t === "induce"
      ? "选中目标子表后点临时区干员并入 · 干员行右键 = 扩展 / 移动 / 移除 · 卡片里点击条件或备注即可编辑"
      : "编辑只在内存中，点「保存…」才写盘（可覆盖已有文件，也可另存新名字）";
  if (t === "results") renderResults();
}
function gotoInduce(op, tagName) {
  if (tagName && tagName !== "__all__") {
    const t = tagOf(tagName);
    if (t) {
      ST.ind.browse = "p:" + t.name;
      ST.ind.browseOpen["p:" + t.name] = true;
      ST.ind.targets = [];
    }
  }
  ST.ind.openOp = op;
  setTab("induce");
  renderInd(); renderIndList();
  location.hash = "tab=induce&op=" + encodeURIComponent(op);
}

// ---------------------------------------------------------------- 启动

document.querySelectorAll(".tab").forEach(b => {
  b.onclick = () => {
    if (b.dataset.tab === ST.tab) return;
    if (ST.tab === "results" && !resGuard("切换页签")) return;
    setTab(b.dataset.tab);
  };
});
bindSearch("rtsearch", () => (RES.mode === "op" ? RES.q.o : RES.q.t),
  v => { if (RES.mode === "op") RES.q.o = v; else RES.q.t = v; }, renderResLeft);
bindSearch("rsearch", () => RES.q.m, v => RES.q.m = v, renderResMem);
document.getElementById("rstext").addEventListener("input", e => {
  RES.src = e.target.value;
  RES.srcParsed = true; RES.srcErr = "";
  RES.dirty = true;
  resDraft(); renderResBar(); renderResSrcErr();
});
document.getElementById("btload").onclick = () => { if (resGuard("加载其他文件")) resLoadDialog(); };
document.getElementById("btnew").onclick = () => {
  if (!resGuard("新建骨架")) return;
  resSet(resSkeleton(), {file: null, eol: "crlf"});
  renderResults();
  toast("已新建规范骨架（未命名，保存时选文件名）");
};
document.getElementById("btsort").onclick = () => {
  if (!RES.doc || RES.shape !== "ok") return toast("先载入结果 JSON", true);
  resSortAll();
};
document.getElementById("btcheck").onclick = () => resDoCheck();
document.getElementById("btview").onclick = () => { if (RES.doc) switchView(RES.view === "src" ? "card" : "src"); };
document.getElementById("btback").onclick = () => switchView("card");
document.getElementById("btformat").onclick = () => {
  try {
    RES.src = serialize(JSON.parse(document.getElementById("rstext").value));
    RES.srcParsed = true; RES.srcErr = "";
    renderResSrc();
    toast("已格式化");
  } catch (e) { toast("解析失败：" + e.message, true); }
};
document.getElementById("btmode").onclick = () => {
  RES.mode = RES.mode === "tag" ? "op" : "tag";
  RES.sel.mi = -1;
  renderResults();
};
document.getElementById("btsave").onclick = () => resSaveDialog();
document.getElementById("modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => {
  const m = document.getElementById("modal");
  if (m.hidden || e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
  const ok = m.querySelector("#mok");
  if (ok && !ok.disabled) ok.click();
});
window.addEventListener("beforeunload", e => {
  if (RES.doc && (RES.dirty || resDirtyNow())) { e.preventDefault(); e.returnValue = ""; return ""; }
});
bindSearch("search", () => ST.zhen.q, v => ST.zhen.q = v, renderOps);
bindSearch("isearch", () => ST.ind.q, v => ST.ind.q = v, renderIndList);
bindSearch("psearch", () => ST.ind.pq, v => ST.ind.pq = v, renderPicker);
bindSearch("tsearch", () => ST.ind.tq, v => ST.ind.tq = v, renderTree);
document.getElementById("btclear").onclick = () => {
  if (!ST.ind.stage.length) return;
  if (!confirm("清空临时区？（不会改动任何文件）")) return;
  ST.ind.stage = []; stageSave(); renderStage(); renderPicker();
};
document.getElementById("btreload").onclick = () => load(true).then(() => status("数据已刷新", "ok")).catch(e => toast(e.message, true));
document.getElementById("btmerge").onclick = async () => {
  status("正在重新生成…");
  try {
    const j = await api("/api/merge", {which: "both"});
    status(j.ok ? "名单文档已重新生成" : "重新生成失败", j.ok ? "ok" : "err");
    for (const [k, v] of Object.entries(j)) {
      if (k === "ok") continue;
      if (!v.ok) toast(k + " 重新生成失败：" + (v.err || v.out || ""), true);
    }
    if (j.ok) toast("docs/player-tags-members.md 与 docs/official-tags-members.md 已更新");
  } catch (e) { status("重新生成失败", "err"); toast(e.message, true); }
};
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (closeModal()) return;  // 模态框优先
  closeMenu();
  if (location.hash) history.replaceState(null, "", location.pathname);
  ST.ind.openOp = null;
  renderIndList();
});
document.addEventListener("click", e => { if (!e.target.closest(".menu")) closeMenu(); });
window.addEventListener("scroll", closeMenu, true);

(async function boot() {
  setTab("zhen");
  await load(false);
  try {
    const saved = JSON.parse(localStorage.getItem("induct.v1") || "null");
    if (saved) {
      ST.ind.targets = (saved.targets || []).filter(t => { const b = blockById(t.id); return b && b.sig === t.sig; });
      ST.ind.stage = (saved.stage || []).filter(s => s.op);
      markStageStale();
      renderInd(); renderIndList(); renderPicker();
    }
  } catch (e) {}
  const m = location.hash.match(/op=([^&]+)/);
  if (m) {
    const op = decodeURIComponent(m[1]);
    ST.ind.openOp = op;
    ST.ind.browse = ST.ind.browse || null;
    setTab("induce");
    renderInd(); renderIndList();
  }
})().catch(e => toast("加载失败：" + e.message, true));
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "RecommendGui"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 静默，不打访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        path, qs = parts.path, urllib.parse.parse_qs(parts.query)
        try:
            if path in ("/", "/index.html"):
                self._send(200, HTML.replace("__TOKEN__", TOKEN).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/data":
                with LOCK:
                    self._json(build_model(fresh=qs.get("fresh") == ["1"]))
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if self.headers.get("X-Token") != TOKEN:
            self._json({"ok": False, "error": "令牌无效，请刷新页面"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            with LOCK:
                if path == "/api/recommend":
                    self._json(apply_recommend(payload))
                elif path == "/api/cell":
                    self._json(save_cell(payload["file"], int(payload["line"]), payload["original"], payload["cond"], payload["note"]))
                elif path == "/api/apply":
                    self._json(apply_ops(payload))
                elif path == "/api/results/list":
                    self._json(list_results())
                elif path == "/api/results/load":
                    self._json(load_results(payload))
                elif path == "/api/results/check":
                    self._json(check_results(payload))
                elif path == "/api/results/save":
                    self._json(save_results(payload))
                elif path == "/api/merge":
                    self._json(run_merge(payload.get("which", "both")))
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
        except UserError as exc:
            self._json({"ok": False, "error": str(exc), "code": getattr(exc, "code", "")}, 400)
        except KeyError as exc:
            self._json({"ok": False, "error": f"请求缺少字段：{exc}"}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)


def run_check() -> int:
    """只解析自检，不写任何文件。"""
    problems: list[str] = []
    model = build_model(fresh=True)
    p_rows = sum(len(b["rows"]) for t in model["player_tags"] for b in t["blocks"])
    p_blocks = sum(len(t["blocks"]) for t in model["player_tags"])
    print(f"玩家体感 TAG {len(model['player_tags'])} 个／子表 {p_blocks} 张／成员行 {p_rows} 条；"
          f"荐 {sum(len(v) for v in model['recommend'].values())} 条")
    for t in model["player_tags"]:
        print(f"  {t['num']} {t['name']}：子表 {len(t['blocks'])} 张 / 行 {sum(len(b['rows']) for b in t['blocks'])} / 荐 {len(t['recommend'])}")
        for b in t["blocks"]:
            for r in b["rows"]:
                if not r["op"]:
                    problems.append(f"{b['file']} 有空干员名：{r['raw'][:40]}")
    o_rows = sum(len(b["rows"]) for e in model["official_entries"] for b in e["blocks"])
    print(f"官方设定 TAG {len(model['official_entries'])} 个／成员行 {o_rows} 条")
    stale_headers = []
    for e in model["official_entries"]:
        b = e["blocks"][0]
        if len(b["header"]) != 3:
            problems.append(f"{e['file']}｜{e['name']}：官方表应为 3 列，实为 {len(b['header'])}")
        dates = [launch_date(r["op"]) for r in b["rows"]]
        first = min([d for d in dates if d], default=None) or "—"
        if e["n_declared"] != len(b["rows"]) or e["first_declared"] != first:
            stale_headers.append(f"{e['name']}（{e['file']}）：条目头 {e['n_declared']} 人 · 首现 {e['first_declared']}"
                                 f" → 实为 {len(b['rows'])} 人 · 首现 {first}")
    for s in stale_headers:
        print("  [条目头待重算] " + s)
    roster = {p["name"] for p in model["roster"]}
    print(f"全量干员 {len(roster)} 人；缺基本信息 {sum(1 for p in model['roster'] if not (p['star'] and p['cls'] and p['branch']))} 人")
    hist: dict[int, int] = {}
    for p in model["roster"]:
        hist[p["star"]] = hist.get(p["star"], 0) + 1
    print("  星级直方图：" + "，".join(f"{k}★×{hist.get(k, 0)}" for k in range(1, 7)))
    for t in model["player_tags"]:
        for b in t["blocks"]:
            for r in b["rows"]:
                if r["op"] not in roster:
                    problems.append(f"{b['file']} 的「{r['op']}」不在全量干员表")
    for e in model["official_entries"]:
        for r in e["blocks"][0]["rows"]:
            if r["op"] not in roster:
                problems.append(f"{e['file']} 的「{r['op']}」不在全量干员表")
    for s in model["stale"]:
        print(f"  [悬空荐] {s['tag']} -> {s['op']}")
    for t in model["unknown_tags"]:
        print(f"  [未知 TAG] {t}")

    # 注册表一致性：官方文件集须与合并脚本一致
    reg = doc_registry()
    want = {fn for _cat, fn in OFFICIAL_FILES}
    got = {k for k, v in reg.items() if v["kind"] == "official"}
    if want != got:
        problems.append(f"官方文件集与合并脚本不一致：缺 {want - got}，多 {got - want}")

    # 干跑（不落盘）：原文往返渲染须逐字节一致；插入一行后可解析且列数正确
    t0 = model["player_tags"][0]
    b0 = t0["blocks"][0]
    path0 = PARTS / b0["file"]
    before = path0.read_text(encoding="utf-8", newline="")
    if Doc(path0, "player").render() != before:
        problems.append(f"{b0['file']}：按行读写往返后与原文不一致（行尾处理有误）")
    probe = next((p for p in model["roster"] if p["name"] not in {r["op"] for r in b0["rows"]}), None)
    if probe:
        doc = Doc(path0, "player")
        got = insert_into(doc, b0, probe["name"], {"条件": "", "备注": "", "子 TAG": ""})
        text = doc.render()
        if got.get("skipped"):
            problems.append("干跑插入被误判为重复")
        if len(text.splitlines()) != len(before.splitlines()) + 1:
            problems.append("干跑插入后行数不符（应 +1）")
        if text.count("\r\n") != before.count("\r\n") + (1 if "\r\n" in before else 0):
            problems.append("干跑插入后 CRLF 计数不符")
        new_row = next((l for l in text.splitlines() if l.startswith("|") and probe["name"] in l), None)
        if not new_row or len(split_cells(new_row)) != len(b0["header"]):
            problems.append(f"干跑新行列数不符：{(new_row or '')[:50]}")
        dry = apply_ops({"ops": [{"kind": "insert", "op": probe["name"], "cond": "", "note": "",
                                  "targets": [{"id": b0["id"], "sig": b0["sig"]}]}], "automerge": False}, dry_run=True)
        if not dry["results"] or dry["results"][0]["targets"][0]["skipped"]:
            problems.append("干跑 /api/apply 插入被误判为重复")
        if path0.read_text(encoding="utf-8", newline="") != before:
            problems.append("干跑改动了文件（不应写盘）")
    else:
        print("  [跳过] 未找到可用于干跑的干员")

    # ---- 结果 JSON：文件名白名单 / 落盘格式 / 校验器自检 ----
    for bad in ("../x.json", "a/b.json", "a\\b.json", "x.txt", "con.json", "x.json ", ".hidden.json", "x", ""):
        try:
            safe_name(bad)
            problems.append(f"safe_name 应拒绝却通过了：{bad!r}")
        except UserError:
            pass
    for good in ("operator-tags.json", "测试 结果.json", "v2.json", "_tmp.json"):
        try:
            safe_name(good)
        except UserError as exc:
            problems.append(f"safe_name 应通过却拒绝了：{good!r}（{exc}）")
    sample = {
        "version": "v1", "updated": "2026-01-01",
        "operators": [
            {"name": "甲", "rarity": 6, "class": "术师", "branch": "中坚术师", "faction": "罗德岛",
             "releaseDate": "2024-01-01", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"},
            {"name": "乙", "rarity": 5, "class": "重装", "branch": "铁卫", "faction": "",
             "releaseDate": "2023-01-01", "prtsUrl": "https://prts.wiki/w/%E4%B9%99"}],
        "tags": [{"id": "P01", "name": "决战歼灭", "source": "player", "recommended": ["乙"], "members": [
            {"operator": "甲", "condition": "无", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"},
            {"operator": "甲", "condition": "", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"}]}],
    }
    got, _stats = validate_results(sample)
    codes = {p["code"] for p in got}
    for want in ("M4", "M5", "R1"):
        if want not in codes:
            problems.append(f"校验器自检：样例应报出 {want}，实际只报出 {sorted(codes)}")
    text = render_results({"白铁": "OK"}, "crlf")
    if text.count("\r\n") != text.count("\n") or not text.endswith("\r\n") or "﻿" in text:
        problems.append("render_results 的 CRLF / BOM 处理有误")
    if json.loads(text) != {"白铁": "OK"} or '"白铁"' not in text:
        problems.append("render_results 往返解析不一致或未保持 ensure_ascii=False")
    target = RESULTS_DIR / "operator-tags.json"
    if target.exists():
        raw = target.read_text(encoding="utf-8-sig", newline="")
        try:
            probs, st = validate_results(json.loads(raw))
            n_err = sum(1 for p in probs if p["level"] == "error")
            print(f"结果 JSON：results/operator-tags.json（{len(raw)} 字符）→ {n_err} 错误 / {len(probs) - n_err} 提醒"
                  f"；operators {st['operators']} / tags {st['tags']} / 关系 {st['members']}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"results/operator-tags.json 解析失败：{exc}")
    else:
        print("[跳过] results/operator-tags.json 尚未生成（本工具只编辑，不生成）")

    if problems:
        print("发现问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("校验通过。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="干员 TAG 名单维护面板（荐 + 人工归纳 + 结果 JSON，本地网页版）")
    parser.add_argument("--port", type=int, default=8520, help="监听端口（默认 8520，被占用时自动换一个）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="只解析自检一次，不起服务")
    args = parser.parse_args()

    if args.check:
        return run_check()

    port = args.port
    for candidate in (port, 0):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = srv.server_address[1]
            break
        except OSError:
            continue
    else:
        print("无法绑定本地端口", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}/"
    print(f"名单维护面板已启动：{url}")
    print("   「荐」页：左键加荐 / 右键取消荐；「人工归纳」页：选子表后并入、右键扩展/移动/移除；")
    print("   「结果 JSON」页：载入 results/*.json 后在内存中编辑，点「保存…」选覆盖或另存；Ctrl+C 退出")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

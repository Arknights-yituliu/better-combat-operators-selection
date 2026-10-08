# -*- coding: utf-8 -*-
"""写回层：成员行/单元格的结构化写回（tag-part/1）。

寻址 = 块 id（`p/o:<文件名>#<块序号>`）+ 行下标 `i` + 行现值 `orig`（cond/note/sub 三元组）；
块签名（label+列头）或行现值任一不符 → UserError(code="drift")（前端据此提示刷新）。
全部写入经 partdoc.save 原子落盘；官方条目头为派生值，无需重算。
"""

from __future__ import annotations

import pathlib
import re

import partdoc
from .config import CHAR_IDS, KNOWN_COLS, MERGE_OFFICIAL, MERGE_PLAYER, OFFICIAL_DIR, OFFICIAL_FILES, rec
from .errors import UserError
from .md import parse_block_id
from .merges import run_merge_script
from .recommends import prune_recommend
from .roster import launch_date


def doc_registry() -> dict[str, dict]:
    """可写文件（basename → 描述）。玩家 11 + 官方 14，白名单解析，无路径穿越。"""
    reg: dict[str, dict] = {}
    for name, path in rec.load_tags():
        reg[path.name] = {"kind": "player", "path": path, "tag": name, "num": path.name[:2]}
    for cat, fn in OFFICIAL_FILES:
        path = OFFICIAL_DIR / fn
        reg.setdefault(fn, {"kind": "official", "path": path, "category": cat})
    return reg


def _clean_op(cell: str) -> str:
    return cell.replace("**", "").strip()


class _Doc:
    """一个文件的内存句柄：doc + 成员表引用（rows 与文档同对象，就地增删改即改文档）。"""

    def __init__(self, info: dict):
        self.info = info
        self.kind = info["kind"]
        self.path: pathlib.Path = info["path"]
        self.doc = partdoc.load(self.path)
        if self.kind == "player":
            self.tables = [{"label": t["label"], "columns": t["columns"], "rows": t["rows"],
                            "idx": t["idx"]} for t in partdoc.iter_member_tables(self.doc)]
        else:
            self.tables = []
            for idx, e in enumerate(self.doc["entries"]):
                table = next(it for it in e["items"] if it["t"] == "table")
                self.tables.append({"label": e["name"], "columns": table["columns"],
                                    "rows": table["rows"], "idx": idx,
                                    "tag": e["name"], "category": self.info.get("category", "")})

    def table(self, idx: int) -> dict:
        if not 0 <= idx < len(self.tables):
            raise UserError("目标子表已不存在，请点「刷新数据」后重试", "drift")
        return self.tables[idx]

    def sig(self, t: dict) -> str:
        return partdoc.sig_of(t["label"], t["columns"])

    def sort_of(self, t: dict) -> str:
        return "none" if self.kind == "player" and self.path.name.startswith("12-") else "date"

    def tag_name_of(self, t: dict) -> str:
        return self.info["tag"] if self.kind == "player" else t.get("tag", "")


def _resolve(reg: dict, handle, bid: str, sig: str) -> tuple[_Doc, dict]:
    """块 id + 签名 → (文件句柄, 表)；签名不符即 drift（乐观并发）。"""
    _kind, fname, idx = parse_block_id(bid)
    if fname not in reg:
        raise UserError(f"未知文件：{fname}")
    dh = handle(fname)
    t = dh.table(idx)
    if dh.sig(t) != sig:
        raise UserError("目标子表已被外部改动（标题或列头变化），请点「刷新数据」后重试", "drift")
    return dh, t


def _row_view(t: dict, cells: list[str]) -> dict:
    cols = t["columns"]
    sub_col = cols.index("子 TAG") if "子 TAG" in cols else (cols.index("范围") if "范围" in cols else None)
    return {
        "op": _clean_op(cells[0]),
        "cond": cells[cols.index("条件")],
        "note": cells[cols.index("备注")],
        "sub": cells[sub_col] if sub_col is not None else "",
        "cid": cells[cols.index("编号")] if "编号" in cols else "",
        "src": cells[cols.index("依据")] if "依据" in cols else "",
    }


def _row_of(t: dict, i, op: str, orig: dict | None) -> tuple[list[str], dict]:
    """按行下标取行并校验（干员名 + 行现值），不符即 drift；返回 (cells, 视图)。"""
    rows = t["rows"]
    if not isinstance(i, int) or not 0 <= i < len(rows):
        raise UserError("该行已不在目标子表内，请点「刷新数据」后重试", "drift")
    cells = rows[i]
    cur = _row_view(t, cells)
    if cur["op"] != op:
        raise UserError("这一行已被外部改动（干员不符），请点「刷新数据」后重试", "drift")
    if orig is not None:
        for k in ("cond", "note", "sub"):
            if str(orig.get(k, "")) != cur[k]:
                raise UserError("这一行已被外部改动（条件/备注已变化），请点「刷新数据」后重试", "drift")
    return cells, cur


def _insert_index(dh: _Doc, t: dict, op: str) -> int:
    """按实装时间倒序的插入位置（append 至表尾的情形：阵容组合或无日期）。"""
    if dh.sort_of(t) == "none":
        return len(t["rows"])
    d = launch_date(op)
    if not d:
        return len(t["rows"])
    for k, r in enumerate(t["rows"]):
        rd = launch_date(_clean_op(r[0]))
        if rd is None or rd < d:
            return k
    return len(t["rows"])


def _insert(dh: _Doc, t: dict, op: str, cells: dict[str, str]) -> dict:
    """插入一行；「编号」列由干员名自动填充（查无该干员则留空），其余列取 cells。"""
    existing = {_clean_op(r[0]) for r in t["rows"]}
    if op in existing:
        return {"skipped": True, "reason": "already-present"}
    values = {c: (cells.get(c, "") or "") for c in t["columns"]}
    values["干员"] = op
    if "编号" in t["columns"] and not values.get("编号"):
        values["编号"] = CHAR_IDS.get(op, "")
    row = [values[c] for c in t["columns"]]
    t["rows"].insert(_insert_index(dh, t, op), row)
    return {"skipped": False, "row": row}


def _check_value(label: str, value: str) -> str:
    if "|" in value:
        raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    return value.strip()


def apply_ops(payload: dict, dry_run: bool = False) -> dict:
    """人工归纳的批量变更：先全部校验、再在内存中执行、最后逐文件原子写回。"""
    ops = payload.get("ops") or []
    if not isinstance(ops, list) or not ops:
        raise UserError("没有要执行的操作")
    reg = doc_registry()
    handles: dict[str, _Doc] = {}

    def handle(fname: str) -> _Doc:
        if fname not in reg:
            raise UserError(f"未知文件：{fname}")
        if fname not in handles:
            handles[fname] = _Doc(reg[fname])
        return handles[fname]

    results, warnings = [], []
    removed: dict[str, set[str]] = {}  # 玩家 TAG → 被移出的干员（用于剪除失效的荐）
    for op in ops:
        kind = op.get("kind")
        rid = op.get("op_id")
        if kind == "delete":
            src = op.get("from") or {}
            b = src.get("block") or {}
            dh, t = _resolve(reg, handle, b.get("id", ""), b.get("sig", ""))
            _cells, cur = _row_of(t, src.get("i"), src.get("op", ""), src.get("orig"))
            if dh.kind == "player":
                removed.setdefault(dh.info["tag"], set()).add(cur["op"])
            if not dry_run:
                t["rows"].pop(src["i"])
            results.append({"op_id": rid, "kind": "delete", "op": cur["op"],
                            "deleted": {"block": b.get("id"), "i": src.get("i")}})
        elif kind == "insert":
            targets = []
            for tg in op.get("targets") or []:
                dh, t = _resolve(reg, handle, tg.get("id", ""), tg.get("sig", ""))
                got = _insert(dh, t, op["op"], {
                    "条件": _check_value("条件", op.get("cond", "")),
                    "备注": _check_value("备注", op.get("note", "")),
                    "子 TAG": _check_value("子 TAG", op.get("sub", "") or ""),
                })
                targets.append({"block": tg.get("id"), "tag": dh.tag_name_of(t), "label": t["label"],
                                "skipped": got.get("skipped", False), "reason": got.get("reason", "")})
            results.append({"op_id": rid, "kind": "insert", "op": op["op"], "targets": targets})
        elif kind == "move":
            targets = op.get("targets") or []
            if len(targets) != 1:
                raise UserError("移动只能指定一个目标子表")
            src = op.get("from") or {}
            b = src.get("block") or {}
            sdh, st = _resolve(reg, handle, b.get("id", ""), b.get("sig", ""))
            scells, cur = _row_of(st, src.get("i"), src.get("op", ""), src.get("orig"))
            tdh, tt = _resolve(reg, handle, targets[0].get("id", ""), targets[0].get("sig", ""))
            if b.get("id") == targets[0].get("id"):
                raise UserError("源与目标是同一个子表，无需移动")
            values = {}
            for col in KNOWN_COLS:
                if col in st["columns"] and col != "干员":
                    values[col] = scells[st["columns"].index(col)]
            opname = cur["op"]
            if sdh.kind == "player":
                removed.setdefault(sdh.info["tag"], set()).add(opname)
            got = _insert(tdh, tt, opname, values)
            dropped = {c: values[c] for c in ("编号", "子 TAG", "依据")
                       if values.get(c) and c not in tt["columns"]}
            if got.get("skipped"):
                results.append({"op_id": rid, "kind": "move", "op": opname, "skipped": True,
                                "reason": f"「{opname}」已在目标子表内，源行未删除"})
            else:
                if not dry_run:
                    st["rows"].pop(src["i"])
                results.append({"op_id": rid, "kind": "move", "op": opname,
                                "from": {"block": b.get("id"), "file": sdh.path.name, "i": src.get("i")},
                                "to": {"block": targets[0].get("id"), "file": tdh.path.name},
                                "dropped": dropped})
        else:
            raise UserError(f"未知操作：{kind}")

    empty_blocks = []
    for fname, dh in handles.items():
        if dh.kind == "player":
            for t in dh.tables:
                if not t["rows"]:
                    empty_blocks.append(f"p:{fname}#{t['idx']}")
    if empty_blocks:
        warnings.append("有子表变为空表：" + "、".join(empty_blocks))

    pruned = prune_recommend(removed) if not dry_run else {}

    merge = {}
    if not dry_run:
        for dh in handles.values():
            partdoc.save(dh.doc, dh.path)
        if payload.get("automerge", True):
            kinds = {dh.kind for dh in handles.values()}
            if "player" in kinds:
                merge["player"] = run_merge_script(MERGE_PLAYER)
            if "official" in kinds:
                merge["official"] = run_merge_script(MERGE_OFFICIAL)
    return {"ok": True, "results": results, "files": sorted(handles),
            "recomputed_headers": [], "pruned_recommend": pruned,
            "empty_blocks": empty_blocks, "merge": merge, "warnings": warnings}


def save_row(file: str, bid: str, sig: str, i, op: str, orig: dict,
             cond: str, note: str, sub: str | None = None, subcol: str = "子 TAG") -> dict:
    """只替换该行的条件/备注格（表格有 subcol 列且传入 sub 时一并替换该格，默认列名「子 TAG」）；
    干员、编号、依据等其余单元格原样保留。"""
    reg = doc_registry()
    if file not in reg:
        raise UserError(f"未知文件：{file}")
    _kind, fname, idx = parse_block_id(bid)
    if fname != file:
        raise UserError(f"未知文件：{file}")
    dh = _Doc(reg[fname])
    t = dh.table(idx)
    if dh.sig(t) != sig:
        raise UserError("目标子表已被外部改动（标题或列头变化），请点「刷新数据」后重试", "drift")
    cells, _cur = _row_of(t, i, op, orig)

    warn = ""
    checks = [("条件", cond), ("备注", note)] + ([(subcol, sub)] if sub is not None else [])
    for label, value in checks:
        if "|" in value:
            raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if any(("\n" in v or "\r" in v) for v in (cond, note) + ((sub,) if sub is not None else ())):
        cond = re.sub(r"\s*[\r\n]+\s*", " ", cond)
        note = re.sub(r"\s*[\r\n]+\s*", " ", note)
        if sub is not None:
            sub = re.sub(r"\s*[\r\n]+\s*", " ", sub)
        warn = "换行已转为空格（表格单元格必须单行）"
    cond, note = cond.strip(), note.strip()
    if sub is not None:
        sub = sub.strip()
    if sub is not None and subcol not in t["columns"]:
        raise UserError(f"该行所在表格没有「{subcol}」列，无法写回")

    cols = t["columns"]
    cells[cols.index("条件")] = cond
    cells[cols.index("备注")] = note
    if sub is not None:
        cells[cols.index(subcol)] = sub
    partdoc.save(dh.doc, dh.path)
    out = {"ok": True, "cond": cond, "note": note, "warn": warn}
    if sub is not None:
        out["sub"] = sub
    return out

# -*- coding: utf-8 -*-
"""写回层：成员行的增删改（apply_ops / save_cell）与官方条目头重算。"""

from __future__ import annotations

import pathlib
import re

from .config import CHAR_IDS, DEF_RE, KNOWN_COLS, MERGE_OFFICIAL, MERGE_PLAYER, OFFICIAL_DIR, OFFICIAL_FILES, rec
from .errors import UserError
from .md import Doc, build_row, check_value, is_sep_row, parse_block_id, row_op, sig_of, split_cells, write_atomic
from .merges import run_merge_script
from .recommends import prune_recommend
from .roster import launch_date
from .tags import parse_official_entries, parse_player_blocks


def doc_registry() -> dict[str, dict]:
    """可写文件（basename → 描述）。玩家 13 + 官方 13，白名单解析，无路径穿越。"""
    reg: dict[str, dict] = {}
    for name, path in rec.load_tags():
        reg[path.name] = {"kind": "player", "path": path, "tag": name, "num": path.name[:2]}
    for cat, fn in OFFICIAL_FILES:
        path = OFFICIAL_DIR / fn
        reg.setdefault(fn, {"kind": "official", "path": path, "category": cat})
    return reg


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
    """插入一行；「编号」列由干员名自动填充（查无该干员则留空），其余列取 cells。"""
    existing = {r["op"] for r in block["rows"]}
    for uid, text in doc.rows_after(block["line"]):
        cells_now = split_cells(text)
        if not is_sep_row(cells_now) and cells_now:
            existing.add(row_op(cells_now))
    if op in existing:
        return {"skipped": True, "reason": "already-present"}
    values = dict(cells)
    if "编号" in block["header"] and not values.get("编号"):
        values["编号"] = CHAR_IDS.get(op, "")
    text = build_row(block["header"], op, values)
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
            dropped = {c: values[c] for c in ("编号", "子 TAG", "依据") if values.get(c) and c not in tblock["header"]}
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

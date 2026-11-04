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
from .tags import display_label


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
        self.num = info.get("num", "")
        self.doc = partdoc.load(self.path)
        if self.kind == "player":
            self.tables = [{"label": t["label"], "columns": t["columns"], "rows": t["rows"],
                            "idx": t["idx"], "h3": t["h3"], "h4": t["h4"]}
                           for t in partdoc.iter_member_tables(self.doc)]
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


def _leaf_subs(dh: _Doc, t: dict, cells: list[str]) -> set[str]:
    """该行末端子 TAG 取值（组, 值, 明细）三元组集合——与产物、荐作用域同源。

    去重键用它而不是只用干员名：同一干员在同一张表里可以有多行，只要末端子 TAG 不全相同
    （如 08 拐杖的冻河：攻速行与攻击力行；余：两种减益行），库内不变量就是这么定的。
    """
    if dh.kind != "player" or not dh.num:
        return set()
    gen = _gen()
    cols = t["columns"]
    ci, ni = cols.index("条件"), cols.index("备注")
    clean = [gen.clean_cell(c) for c in cells]
    try:
        _, cons = gen.player_subtags(dh.num, t.get("h3", ""), t.get("h4", ""),
                                     cols, clean, clean[ci], clean[ni])
    except Exception:  # noqa: BLE001
        return set()
    parents = {s.get("group") for s in cons}
    return {f"{s.get('group')}/{s.get('value')}/{s.get('detail') or ''}"
            for s in cons if s.get("value") and s.get("value") not in parents}


def _sub_view(leaves: set[str]) -> list[str]:
    """去重报告用的可读值（`组/值`，明细只在其能区分时附上）。"""
    return sorted({"/".join(x.split("/")[:2]) for x in leaves})


def _gen():
    import generate_results as gen  # noqa: PLC0415
    return gen


def _insert(dh: _Doc, t: dict, op: str, cells: dict[str, str]) -> dict:
    """插入一行；「编号」列由干员名自动填充（查无该干员则留空），其余列取 cells。

    去重按「干员 ＋ 末端子 TAG（组/值/明细）集合」：同干员、同一组末端子 TAG 视为重复；
    子 TAG 不全相同则允许并存（08 拐杖的冻河、余都是这种形态）。
    """
    values = {c: (cells.get(c, "") or "") for c in t["columns"]}
    values["干员"] = op
    if "编号" in t["columns"] and not values.get("编号"):
        values["编号"] = CHAR_IDS.get(op, "")
    row = [values[c] for c in t["columns"]]
    want = _leaf_subs(dh, t, row)
    for r in t["rows"]:
        if _clean_op(r[0]) != op:
            continue
        have = _leaf_subs(dh, t, r)
        same = (want == have) if (want or have) else True   # 没有子 TAG 的表：同干员即重复
        if same:
            return {"skipped": True, "reason": "already-present", "subs": _sub_view(have)}
    t["rows"].insert(_insert_index(dh, t, op), row)
    return {"skipped": False, "row": row, "subs": _sub_view(want)}


def _check_value(label: str, value: str) -> str:
    if "|" in value:
        raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if "\n" in value or "\r" in value:
        raise UserError(f"{label}不能包含换行（表格单元格必须单行）")
    return value.strip()


def _fill_sub(cells: dict[str, str], sub: str, prefix: str, t: dict) -> None:
    """把「选中子 TAG」落进要插入的行。

    - 表有 `子 TAG` 列（08 拐杖）→ 直接写该列。
    - 表没有该列但该 TAG 的子 TAG 存在备注前缀里（05 插拔容错的「救急路径：…；」）→ 补前缀。
    - 其余情况（子 TAG 写在子表标题里，如 01/04/13）→ 无需写，子表本身就是子 TAG。
    """
    sub = sub.strip()
    if not sub:
        return
    if "子 TAG" in t["columns"]:
        if not cells.get("子 TAG"):
            cells["子 TAG"] = sub
        return
    if prefix and prefix not in (cells.get("备注") or ""):
        note = cells.get("备注") or ""
        cells["备注"] = f"{prefix}：{sub}；" + note if note else f"{prefix}：{sub}；"


def _registered_subs(dh: _Doc, t: dict) -> set[str]:
    """该 TAG 已登记的末端子 TAG 取值（tag_order.json）。未登记的回空，调用方视为「无法判定、不告警」。"""
    if dh.kind != "player" or not dh.num:
        return set()
    import tag_order  # noqa: PLC0415
    try:
        subs = tag_order.sub_list(tag_order.load(), f"P{dh.num}")
    except Exception:  # noqa: BLE001
        return set()
    return {v for _g, v in subs}


def _warn_unregistered(dh: _Doc, t: dict, cells: dict[str, str], warnings: list[str]) -> None:
    """插入行带出的子 TAG 不在登记闭集里 → 只告警、不阻断（作者可能正想新增取值）。"""
    raw = (cells.get("子 TAG") or "").strip()
    if not raw:
        return
    known = _registered_subs(dh, t)
    if not known:
        return
    for item in raw.split("、"):
        item = item.strip()
        if not item:
            continue
        _g, _, v = item.partition("/")
        v = v.strip()
        if v.startswith("触发时(") and v.endswith(")"):
            v = "触发时"
        if v and v not in known:
            warnings.append(f"子 TAG 取值「{v}」未在 tag_order.json 登记，请到「TAG 排序」页纳入")


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
                cells = {
                    "条件": _check_value("条件", op.get("cond", "")),
                    "备注": _check_value("备注", op.get("note", "")),
                    "子 TAG": _check_value("子 TAG", op.get("sub", "") or ""),
                }
                _fill_sub(cells, op.get("sub", "") or "", op.get("prefix", "") or "", t)
                _warn_unregistered(dh, t, cells, warnings)
                if not CHAR_IDS.get(op["op"]):
                    warnings.append(f"「{op['op']}」不在 char_ids.json 中，编号列留空")
                got = _insert(dh, t, op["op"], cells)
                targets.append({"block": tg.get("id"), "tag": dh.tag_name_of(t), "label": t["label"],
                                "display": display_label(t["label"]),
                                "skipped": got.get("skipped", False), "reason": got.get("reason", ""),
                                "subs": got.get("subs", [])})
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
            _fill_sub(values, targets[0].get("sub") or "", targets[0].get("prefix") or "", tt)
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
        # 全部先校验、再落盘：避免「第二个文件校验失败、第一个已写」的半成品状态
        for dh in handles.values():
            partdoc.validate(dh.doc, dh.path.name)
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

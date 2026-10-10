# -*- coding: utf-8 -*-
"""结构化回填（tag-part/1）：插行 / 既有行改列 / 正文行替换 / 正文行后插入 / 新建子表。

与 `_apply_batch.py` 的分工：后者只改**既有行**的「条件／备注」两格；
本脚本承担它不能做的四类结构操作（插新成员行、改「依据」等任意列、改/插正文行、新建玩家子表）。

插入语义镜像 `gui/writeback`（按实装时间倒序定位、编号按 `char_ids.json` 自动填、同表去重 skip；
`12-阵容组合` 与无日期者 append 至表尾）。全部读写经 `partdoc.load/save`（结构校验 + 原子落盘）。
默认 **dry-run**（只打印计划、不落盘）；`--write` 才写入。每类操作带逐条断言，任一不符即中止。

用法：
    .venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/apply_ops.py \
        --input agent_workspace/_out/<批名>-ops.json [--write] [--root <仓库根，测试用>]

输入 JSON（`<批名>-ops.json`；各数组可缺省）：
{
  "new_tables": [                          # 仅玩家文件；在锚表（及其后空 p）之后插入 标题+表+空行
    {"file": "01-决战歼灭.json", "kind": "player",
     "after_table_label": "物真混伤", "label": "物元混伤",
     "columns": ["干员","编号","范围","条件","备注","依据"], "rows": [], "why": "…"}
  ],
  "inserts": [                             # 插入成员行（玩家表 label=小节标题；官方表 label=条目名）
    {"file": "02-次数对策.json", "kind": "player", "table_label": "间隔伤害", "op": "某干员",
     "cells": {"条件": "…", "备注": "…", "依据": "…", "范围": "…"},
     "position": "auto",                   # 缺省 auto（实装倒序）；"append" 强制表尾（12 与无日期本即表尾）
     "why": "…"}
  ],
  "patches": [                             # 既有行按列名整体替换（常用：依据整段追加）
    {"file": "08-拐杖.json", "kind": "player", "table_label": "成员表（按实装时间倒序）",
     "op": "乌尔比安", "expect_contains": "（守卫：备注现值须含该片段）",
     "set": {"依据": "旧段；另起一段新引用"}, "why": "…"}
  ],
  "p_patches": [                           # 玩家文件正文行：整行精确替换（须恰 1 处）
    {"file": "13-高档控制.json", "kind": "player", "old": "……", "new": "……", "why": "…"}
  ],
  "p_insert_after": [                      # 玩家文件正文行：在锚行之后插入若干行（须恰 1 处）
    {"file": "13-高档控制.json", "kind": "player", "anchor": "……", "lines": ["……"], "why": "…"}
  ]
}
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def clean_op(cell: str) -> str:
    return cell.replace("**", "").strip()


class Ctx:
    """按 --root 解析的仓库上下文（partdoc 与两本登记簿均取自该根）。"""

    def __init__(self, root: Path):
        self.root = root
        self.tagdir = root / "agent_workspace" / "tag_pipeline"
        sys.path.insert(0, str(self.tagdir))
        self.partdoc = importlib.import_module("partdoc")
        self.char_ids = json.loads((self.tagdir / "char_ids.json").read_text(encoding="utf-8"))
        self.launch = json.loads((self.tagdir / "player_tags" / "_launch_dates.json").read_text(encoding="utf-8"))

    def path_of(self, fname: str, kind: str) -> Path:
        sub = "player_tags" if kind == "player" else "official_tags"
        return self.tagdir / sub / fname

    def member_tables(self, doc: dict) -> list[dict]:
        out = []
        if doc["kind"] == "player":
            for t in self.partdoc.iter_member_tables(doc):
                out.append({"label": t["label"], "columns": t["columns"], "rows": t["rows"], "item": t["item"]})
        else:
            for e in doc["entries"]:
                table = next(it for it in e["items"] if it["t"] == "table")
                out.append({"label": e["name"], "columns": table["columns"], "rows": table["rows"], "item": table})
        return out

    def table_by_label(self, doc: dict, label: str) -> dict:
        hits = [t for t in self.member_tables(doc) if t["label"] == label]
        if len(hits) != 1:
            raise SystemExit(f"表定位失败：label={label!r} 命中 {len(hits)} 张（需恰 1 张）")
        return hits[0]


def do_new_table(ctx: Ctx, doc: dict, spec: dict) -> list[str]:
    if doc["kind"] != "player":
        raise SystemExit("new_tables 仅支持玩家文件")
    if any(t["label"] == spec["label"] for t in ctx.member_tables(doc)):
        return [f"[skip] 新子表「{spec['label']}」已存在"]
    anchor = ctx.table_by_label(doc, spec["after_table_label"])
    body = doc["body"]
    j = next(i for i, el in enumerate(body) if el is anchor["item"])
    k = j + 1
    if k < len(body) and body[k].get("t") == "p" and body[k]["lines"] == [""]:
        k += 1
    body[k:k] = [{"t": "heading", "level": 3, "text": "### " + spec["label"]},
                 {"t": "table", "columns": spec["columns"], "rows": spec["rows"]},
                 {"t": "p", "lines": [""]}]
    return [f"新子表「{spec['label']}」插入于「{spec['after_table_label']}」之后（body 位 {k}）"]


def insert_index(ctx: Ctx, doc: dict, fname: str, t: dict, op: str, position: str) -> int:
    if position == "append" or (doc["kind"] == "player" and fname.startswith("12-")):
        return len(t["rows"])
    d = ctx.launch.get(op)
    if not d:
        return len(t["rows"])
    for k, r in enumerate(t["rows"]):
        rd = ctx.launch.get(clean_op(r[0]))
        if rd is None or rd < d:
            return k
    return len(t["rows"])


def do_insert(ctx: Ctx, doc: dict, fname: str, spec: dict) -> list[str]:
    t = ctx.table_by_label(doc, spec["table_label"])
    op = spec["op"]
    if any(clean_op(r[0]) == op for r in t["rows"]):
        return [f"[skip] {fname} 「{spec['table_label']}」已含 {op}"]
    values = {c: (spec["cells"].get(c, "") or "") for c in t["columns"]}
    values["干员"] = op
    if "编号" in t["columns"] and not values.get("编号"):
        values["编号"] = ctx.char_ids.get(op, "")
    row = [values[c] for c in t["columns"]]
    idx = insert_index(ctx, doc, fname, t, op, spec.get("position", "auto"))
    t["rows"].insert(idx, row)
    nb = [clean_op(x[0]) for x in t["rows"][max(0, idx - 1): idx + 2]]
    return [f"[insert] {fname} 「{spec['table_label']}」{op} 落位 {idx}（邻行：{' / '.join(nb)}）"]


def do_patch(ctx: Ctx, doc: dict, fname: str, spec: dict) -> list[str]:
    t = ctx.table_by_label(doc, spec["table_label"])
    hits = [r for r in t["rows"] if clean_op(r[0]) == spec["op"]]
    if len(hits) != 1:
        raise SystemExit(f"{fname}「{spec['table_label']}」中 {spec['op']} 命中 {len(hits)} 行（需恰 1 行）")
    row = hits[0]
    exp = spec.get("expect_contains")
    if exp and "备注" in spec["set"]:
        ci = t["columns"].index("备注")
        if exp not in row[ci]:
            raise SystemExit(f"{fname} {spec['op']} 的「备注」现值不含期望片段 {exp!r}，现值：{row[ci]!r}")
    msgs = []
    for col, new in spec["set"].items():
        ci = t["columns"].index(col)
        old = row[ci]
        if old == new:
            msgs.append(f"[patch] {fname} {spec['op']}「{col}」无变化（跳过）")
            continue
        row[ci] = new
        msgs.append(f"[patch] {fname} {spec['op']}「{col}」：{old[:60]!r} -> {new[:60]!r}")
    return msgs


def do_p_patch(doc: dict, fname: str, spec: dict) -> list[str]:
    if doc["kind"] != "player":
        raise SystemExit(f"p_patch 仅支持玩家文件：{fname}")
    n = 0
    for el in doc["body"]:
        if el.get("t") == "p":
            for i, ln in enumerate(el["lines"]):
                if ln == spec["old"]:
                    el["lines"][i] = spec["new"]
                    n += 1
    if n != 1:
        raise SystemExit(f"{fname}: p_patch 命中 {n} 次（需恰 1）: {spec['old'][:70]!r}")
    return [f"[p_patch] {fname}: {spec['old'][:40]!r} -> {spec['new'][:40]!r}"]


def do_insert_after(doc: dict, fname: str, spec: dict) -> list[str]:
    if doc["kind"] != "player":
        raise SystemExit(f"p_insert_after 仅支持玩家文件：{fname}")
    n = 0
    for el in doc["body"]:
        if el.get("t") == "p":
            for i, ln in enumerate(el["lines"]):
                if ln == spec["anchor"]:
                    el["lines"][i + 1:i + 1] = spec["lines"]
                    n += 1
    if n != 1:
        raise SystemExit(f"{fname}: p_insert_after 锚点命中 {n} 次（需恰 1）: {spec['anchor'][:70]!r}")
    return [f"[insert_after] {fname}: +{len(spec['lines'])} 行（锚：{spec['anchor'][:40]!r}）"]


def main() -> None:
    ap = argparse.ArgumentParser(description="结构化回填：插行/改列/正文行替换与插入/新建子表（默认 dry-run）")
    ap.add_argument("--input", required=True, help="ops JSON 路径")
    ap.add_argument("--write", action="store_true", help="落盘（缺省只 dry-run 打印计划）")
    ap.add_argument("--root", default=None, help="仓库根（缺省取本脚本上四级；测试时可指向副本）")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[4]
    ctx = Ctx(root)
    plan = json.loads(Path(args.input).read_text(encoding="utf-8"))

    files: dict[tuple, dict] = {}
    for key in ("new_tables", "inserts", "patches", "p_patches", "p_insert_after"):
        for spec in plan.get(key, []):
            files.setdefault((spec["file"], spec["kind"]), {}).setdefault(key, []).append(spec)

    for (fname, kind), specs in files.items():
        path = ctx.path_of(fname, kind)
        doc = ctx.partdoc.load(path)

        def emit(msgs: list[str]) -> None:
            for m in msgs:
                print(m)

        for spec in specs.get("new_tables", []):
            emit(do_new_table(ctx, doc, spec))
        for spec in specs.get("inserts", []):
            emit(do_insert(ctx, doc, fname, spec))
        for spec in specs.get("patches", []):
            emit(do_patch(ctx, doc, fname, spec))
        for spec in specs.get("p_patches", []):
            emit(do_p_patch(doc, fname, spec))
        for spec in specs.get("p_insert_after", []):
            emit(do_insert_after(doc, fname, spec))
        if args.write:
            ctx.partdoc.save(doc, path)
            print(f"[saved] {path}")
    if not args.write:
        print("（dry-run，未落盘；加 --write 落盘）")


if __name__ == "__main__":
    main()

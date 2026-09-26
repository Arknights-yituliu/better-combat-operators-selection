# -*- coding: utf-8 -*-
"""把 `_out/<TAG>.json` 里的重写结果回填进对应分文件。

**按表头定位列**（各 TAG 的成员表列数不同：多数是 干员｜编号｜条件｜备注｜依据，02/03/04/08/10… 多一列「子 TAG」），
并以 **HEAD 版本**为底重建整行——只替换「条件」「备注」两格，其余列（编号／子 TAG／依据）原样取 HEAD。
这样既能避免写错列，也能修复历史上写错列的行。

用法：
    .venv/Scripts/python.exe -X utf8 _apply_batch.py --tag P03 --file 03-吃拐一轮秒.md --out _out/P03-A.json ...

JSON 的键＝成员表「干员」列的名字；同一分文件内同一干员有多行时（如 次数对策的
「多段伤害」「间隔伤害」两张子表），键写成 `干员名（子表名）` 以消歧。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
PLAYER = ROOT / "material_datas" / "tag_pipeline" / "player_tags"


def cells_of(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")[1:-1]]


def index_rows(lines: list[str]) -> tuple[dict[str, tuple[int, list[str]]],
                                          dict[str, list[tuple[int, list[str], str]]]]:
    """成员表行 → 位置＋该行的表头，按当前表定位（多张表各自有表头）。

    返回 `(out, named)`：`out` 按干员名索引（同名多行时后者覆盖前者）；
    `named` 保留每个名字的全部行及其**上方最近的小节标题**，供「干员（子表名）」形式的键消歧
    （如 次数对策的「机械师（多段伤害）」「机械师（间隔伤害）」）。
    """
    out: dict[str, tuple[int, list[str]]] = {}
    named: dict[str, list[tuple[int, list[str], str]]] = {}
    header: list[str] | None = None
    heading = ""
    for i, line in enumerate(lines):
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            continue
        if not line.startswith("|"):
            continue
        cs = cells_of(line)
        if "条件" in cs and "备注" in cs:
            header = cs
            continue
        if not header or len(cs) != len(header) or set("".join(cs)) <= set("-: "):
            continue
        name = cs[0].replace("**", "").strip()
        out[name] = (i, header)
        named.setdefault(name, []).append((i, header, heading))
    return out, named


def find_row(idx, op: str) -> tuple[int | None, list[str] | None]:
    """在 `index_rows` 的结果里定位 `op`；支持「干员（子表名）」形式消歧（同名多行时用）。"""
    out, named = idx
    if op in out:
        return out[op]
    m = re.match(r"^(.*?)（(.+)）$", op)
    if m:
        for i, header, heading in named.get(m.group(1).strip(), []):
            if m.group(2).strip() in heading:
                return i, header
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="回填批量重写结果")
    ap.add_argument("--tag", required=True, help="TAG 编号，如 P03")
    ap.add_argument("--file", required=True, help="分文件名，如 03-吃拐一轮秒.md")
    ap.add_argument("--out", nargs="+", required=True, help="代理产出的 JSON")
    ap.add_argument("--no-head", action="store_true", help="不以 HEAD 为底（仅当该文件本轮未被先前批次的错误写法污染）")
    ap.add_argument("--keep-prefix", action="store_true",
                    help="保留原备注行首的机器协议前缀（P05 的「救急路径：…；」、P07 的「子 TAG：…。」）——"
                         "生成器靠它解析 subTags，新文本若不带就整批丢子 TAG")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows: dict[str, dict] = {}
    for path in args.out:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for tag, ops in data.items():
            if tag.upper() != args.tag.upper():
                print(f"  跳过 {path}：TAG 标记为 {tag}")
                continue
            for op, rec in ops.items():
                if op in rows:
                    print(f"  ⚠ {op} 出现在多份产出里，取后一份")
                rows[op] = rec
    if not rows:
        print("没有可回填的条目")
        return 1

    rel = f"material_datas/tag_pipeline/player_tags/{args.file}"
    target = PLAYER / args.file
    cur = target.read_bytes().decode("utf-8").split("\r\n")
    base = cur
    if not args.no_head:
        got = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
        if got.returncode == 0:
            base = got.stdout.decode("utf-8").replace("\r\n", "\n").split("\n")
        else:
            print("  ⚠ 取不到 HEAD 版本，改以工作区为底")
    base_idx = index_rows(base)
    cur_idx = index_rows(cur)

    hit, miss = [], set(rows)
    for op, rec in rows.items():
        cond, note = str(rec["condition"]).strip(), str(rec["remark"]).strip()
        for field, text in (("条件", cond), ("备注", note)):
            if "\n" in text or "\r" in text:
                print(f"  ❌ {op} 的{field}含换行，跳过")
                return 1
            if "|" in text.replace("｜", ""):
                print(f"  ❌ {op} 的{field}含 ASCII 竖线，跳过")
                return 1
        src, idx = find_row(base_idx, op)
        if src is None:
            pos = find_row(cur_idx, op)
            if pos[0] is None:
                miss.add(op)
                continue
            src, idx = pos
            row = cells_of(cur[src])
        else:
            row = cells_of(base[src])
        if args.keep_prefix:
            old_note = row[idx.index("备注")]
            m = re.match(r"^(?:\*{0,2}救急路径[:：][^；。]*\*{0,2}[；。]|(?:\*\*)?子\s?TAG[:：][^。]*。)", old_note)
            if m:
                note = m.group(0) + note
        row[idx.index("条件")] = cond
        row[idx.index("备注")] = note
        line = "| " + " | ".join(row) + " |"
        pos = find_row(cur_idx, op)
        if pos[0] is None:
            miss.add(op)
            continue
        cur[pos[0]] = line
        hit.append(op)
        miss.discard(op)
    if miss:
        print(f"  ⚠ 表里找不到：{sorted(miss)}")
    if args.dry_run:
        print(f"[dry-run] 将回填 {len(hit)} 条：{hit}")
        return 0
    target.write_bytes("\r\n".join(cur).encode("utf-8"))
    print(f"已回填 {len(hit)} 条：{'、'.join(hit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

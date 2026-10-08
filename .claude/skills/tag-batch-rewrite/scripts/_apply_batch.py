# -*- coding: utf-8 -*-
"""把 `agent_workspace/_out/<批名>.json` 里的重写结果回填进对应分文件（tag-part/1 JSON）。

**结构化定位**：按「干员」列名定位行（列名即 JSON 字段，不存在写错列的可能）；
同名多行（如 01 的真言、02 的两张子表）时，键写成 `干员名（子表名）` 消歧——
子表名对行所在块的标题（h3/h4）做子串匹配。

用法：
    .venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/_apply_batch.py --tag P03 --file 03-吃拐一轮秒.json --out agent_workspace/_out/P03-A.json ...

JSON 的键＝成员表「干员」列的名字：{"<Pn>": {"<干员名>": {"condition": …, "remark": …, "why": …}}}。
只替换「条件」「备注」两个字段；编号/子 TAG/范围/依据原样保留。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "agent_workspace" / "tag_pipeline"))
import partdoc  # noqa: E402  （分文件 JSON 的唯一读写实现）

PLAYER = ROOT / "agent_workspace" / "tag_pipeline" / "player_tags"

# 行首机器协议前缀（P05 的「救急路径：…；」、备注开头的「子 TAG：…。」——后者玩家侧当前无数据，
# 但生成器靠此前缀解析 subTags，保留两条分支以维持与历史批次一致的行为）。
PREFIX_RE = re.compile(r"^(?:\*{0,2}救急路径[:：][^；。]*\*{0,2}[；。]|(?:\*\*)?子\s?TAG[:：][^。]*。)")
_CLEAN = lambda cell: cell.replace("**", "").strip()  # noqa: E731


def find_row(tables: list[dict], op: str):
    """定位 `op`；同名多行取文档序最后者，`干员（子表名）` 形式对块标题做子串消歧。

    返回 (table, 行下标) 或 None。
    """
    idx: dict[str, tuple[dict, int]] = {}
    named: dict[str, list[tuple[dict, int, str]]] = {}
    for t in tables:
        for k, row in enumerate(t["rows"]):
            name = _CLEAN(row[0])
            idx[name] = (t, k)
            named.setdefault(name, []).append((t, k, t["label"]))
    if op in idx:
        return idx[op]
    m = re.match(r"^(.*?)（(.+)）$", op)
    if m:
        for t, k, label in named.get(m.group(1).strip(), []):
            if m.group(2).strip() in label:
                return t, k
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="回填批量重写结果（tag-part/1）")
    ap.add_argument("--tag", required=True, help="TAG 编号，如 P03")
    ap.add_argument("--file", required=True, help="分文件名，如 03-吃拐一轮秒.json")
    ap.add_argument("--out", nargs="+", required=True, help="代理产出的 JSON")
    ap.add_argument("--keep-prefix", action="store_true",
                    help="保留原备注行首的机器协议前缀（P05 的「救急路径：…；」、备注开头的「子 TAG：…。」）——"
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

    target = PLAYER / args.file
    doc = partdoc.load(target)
    tables = list(partdoc.iter_member_tables(doc))

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
        found = find_row(tables, op)
        if found is None:
            miss.add(op)
            continue
        t, k = found
        cols = t["columns"]
        row = t["rows"][k]
        if args.keep_prefix:
            m = PREFIX_RE.match(row[cols.index("备注")])
            if m:
                note = m.group(0) + note
        row[cols.index("条件")] = cond
        row[cols.index("备注")] = note
        hit.append(op)
        miss.discard(op)
    if miss:
        print(f"  ⚠ 表里找不到：{sorted(miss)}")
    if args.dry_run:
        print(f"[dry-run] 将回填 {len(hit)} 条：{hit}")
        return 0
    partdoc.save(doc, target)
    print(f"已回填 {len(hit)} 条：{'、'.join(hit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

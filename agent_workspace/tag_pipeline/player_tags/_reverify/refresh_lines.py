# -*- coding: utf-8 -*-
"""刷新 items.jsonl 的 loc 字段（按 tag/干员/备注 重定位）。

用途：分文件在复算期间有手工修订（评定标准补注、行内文字改写等），成员行位置可能变化。
本脚本**只重定位并更新 items.jsonl 的 `loc`**（b<块序>r<行序>，见 reverify.iter_part_rows），
不重跑 `.claude/skills/reverify-numbers/scripts/reverify.py extract`——避免重新抽取
把已由 parts 记录的旧片段/备注与当前文件文本脱钩（片段与 parts 的对应关系保持不变）。

匹配顺序：① 干员＋备注文本（含 P05 路径剥离变换）一致；② 本节内该干员的成员行按 occ 取定
（供备注文本已被手工修订的条目兜底）；均未命中者保留原定位并报告。

运行（Windows 控制台 GBK，务必带 -X utf8）：
    .venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/player_tags/_reverify/refresh_lines.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

RV_DIR = pathlib.Path(__file__).resolve().parent
ROOT = RV_DIR.parents[3]          # agent_workspace/tag_pipeline/player_tags/_reverify → player_tags → tag_pipeline → agent_workspace → 仓库根
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "reverify-numbers" / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from reverify import PARTS_DIR, ITEMS_FILE, iter_part_rows, member_row_remark  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="刷新 items.jsonl 的 loc 字段")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写盘")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

    by_file: dict[str, list[dict]] = {}
    for it in items:
        by_file.setdefault(it["file"], []).append(it)

    rows_by_file: dict[str, list[tuple[str, list[str], list[str]]]] = {}
    for fname in by_file:
        path = PARTS_DIR / fname
        rows = []
        for loc, _h2, _h3, _h4, header, cells in iter_part_rows(path):
            rows.append((loc, header, cells))
        rows_by_file[fname] = rows

    changed: list[str] = []
    missed: list[str] = []
    for it in items:
        fname = it["file"]
        cands = [r for r in rows_by_file[fname]
                 if r[2] and r[2][0].strip() == it["operator"]
                 and member_row_remark(it["tag"], r[1], r[2]) == it["json_remark"]]
        if not cands:
            cands = [r for r in rows_by_file[fname]
                     if r[2] and r[2][0].strip() == it["operator"]]
            if cands:
                missed.append(f"{it['id']}: 按干员兜底定位（备注文本已改动）")
        if not cands:
            missed.append(f"{it['id']}: 未定位（保留原定位 {it['loc']}）")
            continue
        if len(cands) > 1:
            occ = int(it.get("occ") or 1)
            cands = [cands[min(occ, len(cands)) - 1]]
            missed.append(f"{it['id']}: 多候选按 occ={it.get('occ')} 取定")
        new_loc = cands[0][0]
        if new_loc != it["loc"]:
            changed.append(f"{it['id']}: {it['loc']} → {new_loc}")
            it["loc"] = new_loc

    out = "\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n"
    if not args.dry_run:
        ITEMS_FILE.write_text(out, encoding="utf-8")

    print(f"items={len(items)} 定位更新={len(changed)} 未定位/提示={len(missed)}")
    for c in changed:
        print(f"  ~ {c}")
    for m in missed:
        print(f"  ! {m}")
    if args.dry_run:
        print("（--dry-run：未写盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

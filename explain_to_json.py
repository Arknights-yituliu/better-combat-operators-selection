# -*- coding: utf-8 -*-
"""玩家体感 TAG 通俗说明 → results/player-tags-explain.json

源文件：docs/player-tags-explain.md
    ## <TAG 名>                        —— 顶级 TAG 说明
    ### <TAG 名> · <组> / <值>         —— 子项说明（组/值取自结果 JSON 的 subTags）

生成后与 results/operator-tags.json 双向核对：玩家 TAG、以及成员里出现的每个
（组，值）都必须有文案；文案里多出的条目同样报错。前端按 tagId 与 `组|值` 取用。
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DOC = ROOT / "docs" / "player-tags-explain.md"
RESULTS = ROOT / "results" / "operator-tags.json"
OUT = ROOT / "results" / "player-tags-explain.json"

TOP_RE = re.compile(r"^## (.+?)\s*$")
SUB_RE = re.compile(r"^### (.+?) · (.+?) / (.+?)\s*$")


def parse_doc() -> tuple[dict[str, str], dict[tuple[str, str, str], str], list[str]]:
    tags: dict[str, str] = {}
    subs: dict[tuple[str, str, str], str] = {}
    order: list[str] = []
    cur_key: tuple[str, str, str] | None = None
    cur_top = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        text = " ".join(x.strip() for x in buf if x.strip())
        if cur_key is not None:
            subs[cur_key] = text
        elif cur_top:
            tags[cur_top] = text
        buf = []

    for line in io.open(DOC, encoding="utf-8").read().splitlines():
        m_top = TOP_RE.match(line)
        m_sub = SUB_RE.match(line)
        if m_sub:
            flush()
            cur_key = (m_sub.group(1).strip(), m_sub.group(2).strip(), m_sub.group(3).strip())
            cur_top = ""
            continue
        if m_top:
            flush()
            cur_top = m_top.group(1).strip()
            cur_key = None
            order.append(cur_top)
            continue
        buf.append(line)
    flush()
    return tags, subs, order


def main() -> int:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    tags, subs, order = parse_doc()

    tag_ids: dict[str, str] = {}
    expected_subs: set[tuple[str, str, str]] = set()
    for t in data.get("tags", []):
        if t.get("source") != "player":
            continue
        tag_ids[t["name"]] = t["id"]
        for m in t.get("members", []):
            for s in m.get("subTags", []):
                expected_subs.add((t["name"], s["group"], s["value"]))

    problems: list[str] = []
    for name, tid in tag_ids.items():
        if not tags.get(name):
            problems.append(f"缺少顶级说明：## {name}")
    for name in tags:
        if name not in tag_ids:
            problems.append(f"说明多于产物：## {name}（结果 JSON 中无此玩家 TAG）")
    for key in sorted(expected_subs):
        if not subs.get(key):
            problems.append(f"缺少子项说明：### {key[0]} · {key[1]} / {key[2]}")
    for key in subs:
        if key[0] not in tag_ids:
            problems.append(f"子项说明多于产物：### {key[0]} · {key[1]} / {key[2]}")
        elif key not in expected_subs:
            problems.append(f"子项说明在产物中未出现（组/值对不上）：### {key[0]} · {key[1]} / {key[2]}")

    out = {
        "note": "玩家体感 TAG 通俗说明（前端悬浮工具提示文案）；源文件 docs/player-tags-explain.md，生成脚本 explain_to_json.py",
        "tags": [{"id": tag_ids[n], "name": n, "text": tags[n]} for n in order if n in tags and n in tag_ids],
        "subs": [
            {"tagId": tag_ids[k[0]], "group": k[1], "value": k[2], "text": v}
            for k, v in sorted(subs.items(), key=lambda kv: (tag_ids.get(kv[0][0], ""), kv[0][1], kv[0][2]))
            if k[0] in tag_ids
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}：{len(out['tags'])} 个 TAG、{len(out['subs'])} 条子项")
    if problems:
        print("发现问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("覆盖校验通过（与 results/operator-tags.json 双向一致）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

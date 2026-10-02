# -*- coding: utf-8 -*-
"""/api/data 的数据模型：玩家 TAG + 官方条目 + 全量干员 + 荐。"""

from __future__ import annotations

import re

from .config import CHAR_IDS, rec
from .roster import load_roster
from .tags import load_official_entries, parse_player_blocks


def fill_cid(blocks: list[dict]) -> None:
    """给每行带上「编号」（charId）：优先取行内值，缺列或空值时按干员名回查 char_ids.json。"""
    for b in blocks:
        for r in b["rows"]:
            if not r.get("cid"):
                r["cid"] = CHAR_IDS.get(r["op"], "")


def build_model(fresh: bool = False) -> dict:
    recommend = rec.load_recommend()
    player_tags = []
    for name, path in rec.load_tags():
        blocks = parse_player_blocks(path, name)
        fill_cid(blocks)
        scopes = rec.tag_scope_values(name) or []
        scope_ops: dict = {}
        for v in [None] + list(scopes):
            key = name if v is None else f"{name}/{v}"
            scope_ops[v] = list(recommend.get(key, []))
        union: list[str] = []
        for ops in scope_ops.values():
            for op in ops:
                if op not in union:
                    union.append(op)
        player_tags.append({
            "num": path.name[:2],
            "name": name,
            "file": path.name,
            "recommend": union,  # 各作用域并集（徽标/计数用）
            "rec_scopes": [{"scope": v, "ops": scope_ops[v]} for v in scope_ops],  # 荐页编辑用
            "blocks": blocks,
        })
    official_entries = load_official_entries()
    for n, e in enumerate(official_entries):
        e["id"] = f"o:{e['file']}#e{n}"
        fill_cid(e["blocks"])
    known = {t["name"] for t in player_tags}

    def member_set(t: dict) -> set:
        ops = {r["op"] for b in t["blocks"] for r in b["rows"]}
        if t["num"] == "12":  # 阵容组合：荐可为组合名（组荐与组员荐独立，见 docs/output-standard.md §6）
            for b in t["blocks"]:
                m = re.match(r"[AB]\d+\.\s*(.+)", str(b.get("label", "")))
                if m:
                    ops.add(m.group(1).strip())
        return ops

    members_of = {t["name"]: member_set(t) for t in player_tags}
    stale = []
    for key, ops in recommend.items():
        tag, scope = rec.split_key(key)
        if tag not in known:
            continue
        if scope is not None and scope not in (rec.tag_scope_values(tag) or []):
            stale.append({"tag": key, "op": scope, "kind": "scope"})
        for op in ops:
            if op not in members_of[tag]:
                stale.append({"tag": key, "op": op, "kind": "op"})
    return {
        "player_tags": player_tags,
        "official_entries": official_entries,
        "roster": load_roster(fresh),
        "recommend": recommend,
        "stale": stale,
        "unknown_tags": [k for k in recommend if rec.split_key(k)[0] not in known],
    }

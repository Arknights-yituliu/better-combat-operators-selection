# -*- coding: utf-8 -*-
"""/api/data 的数据模型：玩家 TAG + 官方条目 + 全量干员 + 荐。"""

from __future__ import annotations

from .config import rec
from .roster import load_roster
from .tags import load_official_entries, parse_player_blocks


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

# -*- coding: utf-8 -*-
"""/api/data 的数据模型：玩家 TAG + 官方条目 + 全量干员 + 荐。"""

from __future__ import annotations

import re

from .config import CHAR_IDS, rec
from .roster import load_roster
from .tags import load_official_entries, parse_player_blocks, scope_members


def fill_cid(blocks: list[dict]) -> None:
    """给每行带上「编号」（charId）：优先取行内值，缺列或空值时按干员名回查 char_ids.json。"""
    for b in blocks:
        for r in b["rows"]:
            if not r.get("cid"):
                r["cid"] = CHAR_IDS.get(r["op"], "")


def sub_values_of(t: dict) -> list[dict]:
    """该玩家 TAG 成员行实际用到的末端子 TAG 取值 → [{group, value, count}]。

    顺序取自 tag_order.json（未登记的回退到首次出现序）；与产物 subOrder、荐页作用域同源。
    """
    import tag_order  # noqa: PLC0415
    seen: dict[str, dict] = {}
    for b in t["blocks"]:
        for r in b["rows"]:
            for v in r.get("subs") or []:
                item = seen.setdefault(v, {"group": "", "value": v, "count": 0})
                item["count"] += 1
    if not seen:
        return []
    # 组名：从成员的 subTags 反查（同一取值只属一个组）
    for b in t["blocks"]:
        for r in b["rows"]:
            for s in r.get("subtags") or []:
                g, v = s.get("group") or "", s.get("value") or ""
                if v in seen and not seen[v]["group"]:
                    seen[v]["group"] = g
    rank = tag_order.sub_rank(tag_order.load(), f"P{t['num']}")
    out = sorted(seen.values(), key=lambda x: rank.get((x["group"], x["value"]), len(rank)))
    return out


def build_model(fresh: bool = False) -> dict:
    recommend = rec.load_recommend()
    player_tags = []
    scope_members_of: dict[str, dict[str, list[str]]] = {}
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
        sm = scope_members(path)  # 各子作用域的成员（荐页过滤 + 荐的归属校验）
        scope_members_of[name] = sm
        entry = {
            "num": path.name[:2],
            "name": name,
            "file": path.name,
            "recommend": union,  # 各作用域并集（徽标/计数用）
            "rec_scopes": [{"scope": v, "ops": scope_ops[v]} for v in scope_ops],  # 荐页编辑用
            "scope_members": sm,  # 子作用域 → 该作用域内的干员（荐页据此只列本作用域的干员）
            "blocks": blocks,
        }
        entry["sub_values"] = sub_values_of(entry)  # 树里的子 TAG 行（列式/备注前缀式的 TAG 才有）
        player_tags.append(entry)
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
        pool = (scope_members_of.get(tag) or {}).get(scope) if scope is not None else None
        for op in ops:
            if op not in members_of[tag]:
                stale.append({"tag": key, "op": op, "kind": "op"})
            elif pool is not None and op not in pool:
                # 荐落在了本 TAG、但不在所选子作用域内的干员上（荐页只列该作用域的干员，故须核对）
                stale.append({"tag": key, "op": op, "kind": "scope-member"})
    return {
        "player_tags": player_tags,
        "official_entries": official_entries,
        "roster": load_roster(fresh),
        "recommend": recommend,
        "stale": stale,
        "unknown_tags": [k for k in recommend if rec.split_key(k)[0] not in known],
    }

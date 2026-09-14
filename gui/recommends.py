# -*- coding: utf-8 -*-
"""玩家体感 TAG 的「荐」：接口层（apply_recommend）与成员变动后的失效剪除。"""

from __future__ import annotations

from .config import rec
from .errors import UserError


def prune_recommend(removed: dict[str, set[str]]) -> dict[str, list[str]]:
    if not removed:
        return {}
    data = rec.load_recommend()
    pruned: dict[str, list[str]] = {}
    for tag, names in removed.items():
        ops = data.get(tag)
        if not ops:
            continue
        keep = [o for o in ops if o not in names]
        if len(keep) != len(ops):
            pruned[tag] = [o for o in ops if o in names]
            data[tag] = keep
    if pruned:
        rec.save_recommend(data, [t for t, _ in rec.load_tags()])
    return pruned


def apply_recommend(payload: dict) -> dict:
    action = payload.get("action")
    tags = rec.load_tags()
    names = [t for t, _ in tags]
    tag = payload.get("tag", "")
    if tag not in names:
        raise UserError(f"未知 TAG：{tag}")
    data = rec.load_recommend()
    ops = data.setdefault(tag, [])
    op = payload.get("op", "")

    if action in ("add", "remove"):
        if action == "add" and op not in rec.main_table_members(dict(tags)[tag]):
            raise UserError(f"「{op}」不是「{tag}」成员表内的干员，不能设为荐")
        if action == "add":
            if op in ops:
                return {"ok": True, "noop": "已是荐", "recommend": data}
            ops.append(op)
        elif action == "remove":
            if op not in ops:
                return {"ok": True, "noop": "本就不是荐", "recommend": data}
            ops.remove(op)
    elif action == "clear":
        ops.clear()
    else:
        raise UserError(f"未知操作：{action}")

    rec.save_recommend(data, names)
    return {"ok": True, "recommend": {k: v for k, v in data.items() if v}}

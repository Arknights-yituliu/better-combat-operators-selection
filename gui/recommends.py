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
    changed = False
    for key in list(data):
        tag, _scope = rec.split_key(key)
        names = removed.get(tag)
        if not names:
            continue
        ops = data[key]
        keep = [o for o in ops if o not in names]
        if len(keep) != len(ops):
            pruned[key] = [o for o in ops if o in names]
            data[key] = keep
            changed = True
    if changed:
        rec.save_recommend(data, [t for t, _ in rec.load_tags()])
    return pruned


def apply_recommend(payload: dict) -> dict:
    action = payload.get("action")
    tags = rec.load_tags()
    names = [t for t, _ in tags]
    tag = payload.get("tag", "")
    scope = payload.get("scope") or None
    if tag not in names:
        raise UserError(f"未知 TAG：{tag}")
    if scope is not None:
        vals = rec.tag_scope_values(tag) or []
        if scope not in vals:
            raise UserError(f"「{tag}」没有子 TAG「{scope}」")
        key = f"{tag}/{scope}"
    else:
        key = tag
    data = rec.load_recommend()
    ops = data.setdefault(key, [])
    op = payload.get("op", "")

    if action in ("add", "remove"):
        if action == "add" and op not in rec.recommendable_members(dict(tags)[tag]):
            raise UserError(f"「{op}」不是「{tag}」的成员或组合名，不能设为荐")
        if action == "add":
            if op in ops:
                return {"ok": True, "noop": "已是荐", "key": key, "recommend": {k: v for k, v in data.items() if v}}
            ops.append(op)
        elif action == "remove":
            if op not in ops:
                return {"ok": True, "noop": "本就不是荐", "key": key, "recommend": {k: v for k, v in data.items() if v}}
            ops.remove(op)
    elif action == "clear":
        ops.clear()
    else:
        raise UserError(f"未知操作：{action}")

    rec.save_recommend(data, names)
    return {"ok": True, "key": key, "recommend": {k: v for k, v in data.items() if v}}

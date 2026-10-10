# -*- coding: utf-8 -*-
"""结果 JSON 的荐字段：按 _recommend.json／_recommend_fallback.json 重算。

荐只维护在两份荐文件里（docs/output-standard.md §6）；结果 JSON 的
recommended／recommendedFallback／recommendedBySub／recommendedFallbackBySub
是生成物。「结果 JSON」页保存时用本模块重算（加载／校验时给出不一致提示），
保证产物与荐文件一致。

重算规则与生成器 tools/generate_results.py 的 rec_fields() 同源（就地复用，不复制逻辑）。
"""

from __future__ import annotations

import copy

from .config import rec

# 玩家 TAG 的荐字段：无子 TAG 的用 TAG 级数组，有子 TAG 的用 BySub
_FIELD_NAMES = {
    "recommended": "荐",
    "recommendedFallback": "兜底荐",
    "recommendedBySub": "荐（按子 TAG）",
    "recommendedFallbackBySub": "兜底荐（按子 TAG）",
}


def _generator():
    import generate_results as gen  # noqa: PLC0415 （与 gui/tags.py 同因：生成器须就地导入，见其注释）
    return gen


def _load_maps() -> tuple[dict, dict]:
    return rec.load_recommend(), rec.load_recommend(rec.RECOMMEND_FALLBACK)


def _clean_members(raw) -> list[dict]:
    """rec_fields 只读成员表：过滤非对象成员与非对象 subTags，避免畸形文档把重算打断。"""
    members = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        m = dict(m)
        if isinstance(m.get("subTags"), list):
            m["subTags"] = [s for s in m["subTags"] if isinstance(s, dict)]
        members.append(m)
    return members


def _list_changes(field: str, cur, want: list[str]) -> str:
    label = _FIELD_NAMES[field]
    if not isinstance(cur, list):
        return f"{label}：补齐（{'、'.join(want) if want else '空数组'}）"
    before = [x for x in cur if isinstance(x, str)]
    add = [x for x in want if x not in before]
    rem = [x for x in before if x not in want]
    parts = []
    if add:
        parts.append("＋" + "、".join(add))
    if rem:
        parts.append("－" + "、".join(rem))
    if not parts:
        parts.append("顺序调整")
    return f"{label}：" + "；".join(parts)


def _by_sub_changes(field: str, cur, want: list[dict]) -> str:
    def names_of(entries) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and isinstance(e.get("value"), str):
                out[e["value"]] = [x for x in (e.get("names") or []) if isinstance(x, str)]
        return out

    cur_map, want_map = names_of(cur), names_of(want)
    parts = []
    for value, names in want_map.items():
        before = cur_map.get(value, [])
        seg = []
        add = [x for x in names if x not in before]
        rem = [x for x in before if x not in names]
        if add:
            seg.append("＋" + "、".join(add))
        if rem:
            seg.append("－" + "、".join(rem))
        if seg:
            parts.append(value + " " + "；".join(seg))
    for value, names in cur_map.items():
        if value not in want_map and names:
            parts.append(value + " －" + "、".join(names))
    if not parts:
        parts.append("顺序调整")
    return f"{_FIELD_NAMES[field]}：" + "；".join(parts)


def _store_notes(name: str, members: list[dict], rec_map: dict, fb_map: dict, gen) -> list[str]:
    """荐文件里、重算后不会出现在产物里的条目：子 TAG 取值不在当前文档的成员中。"""
    scope_values = {value for _group, value in gen.collect_sub_scopes(members)}
    notes = []
    for store, label in ((rec_map, "荐"), (fb_map, "兜底荐")):
        for key, ops in store.items():
            tag, scope = rec.split_key(key)
            if tag != name or scope is None or not ops:
                continue
            if scope not in scope_values:
                notes.append(f"{label}：「{key}」的子 TAG 不在当前文档的成员中，未落入产物")
    return notes


def sync_recommend(doc) -> dict:
    """就地重算 doc 里各玩家 TAG 的荐字段。

    返回报告 {"tags": [{"index", "name", "changes": [...]}], "notes": [...]}；
    与荐文件一致时报告为空。官方 TAG 与其它字段不动。
    """
    report: dict = {"tags": [], "notes": []}
    if not isinstance(doc, dict) or not isinstance(doc.get("tags"), list):
        return report
    gen = _generator()
    rec_map, fb_map = _load_maps()
    for ti, t in enumerate(doc["tags"]):
        if not isinstance(t, dict) or t.get("source") != "player":
            continue
        name = str(t.get("name") or "")
        members = _clean_members(t.get("members"))
        want = gen.rec_fields(name, members, rec_map, fb_map)
        changes = []
        for field in ("recommended", "recommendedFallback"):
            w = list(want.get(field, []))
            if t.get(field) != w:
                changes.append(_list_changes(field, t.get(field), w))
                t[field] = w
        for field in ("recommendedBySub", "recommendedFallbackBySub"):
            w = want.get(field)
            if w is None:
                if field in t:
                    changes.append(f"{_FIELD_NAMES[field]}：移除（荐文件无此名单）")
                    del t[field]
            elif t.get(field) != w:
                changes.append(_by_sub_changes(field, t.get(field), w))
                t[field] = w
        if changes:
            report["tags"].append({"index": ti, "name": name, "changes": changes})
        report["notes"].extend(_store_notes(name, members, rec_map, fb_map, gen))
    return report


def preview_sync(doc) -> dict:
    """在副本上重算，返回同样的报告（doc 不变）；供「加载／校验」提示用。"""
    return sync_recommend(copy.deepcopy(doc))

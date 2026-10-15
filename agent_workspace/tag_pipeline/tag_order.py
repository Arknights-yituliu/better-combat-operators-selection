# -*- coding: utf-8 -*-
"""TAG 展示顺序的唯一维护处（`tag-order/1`）。

顺序分四层，各由本文件的一处结构决定：

1. **官方类别序** —— `official.categories[]` 的数组序；
2. **官方类内 TAG 序** —— 每个类别 `tags[]` 的数组序（TAG 嵌在其类别内，两层序不会互相漂移）；
3. **玩家 TAG 序** —— `player[]` 的数组序；
4. **玩家 TAG 的子 TAG 取值序** —— 每个 TAG `subs[]` 的数组序，以 `(组, 值)` 为键
   （只按「值」会在同名值落在两个组时静默出错）。

约定：

- **一律按 id 索引**（TAG 改名保留 id，故改名不丢位置）；`name` 仅供阅读，由 `--seed` 与面板刷新。
- **未登记的 TAG／取值一律追加到所属段末尾**（保持其现有相对序）——新 TAG 与新取值永不丢失，
  开发者随后在面板里拖到位即可。
- **纯排序变化只更新 `updated`，不升 `version`**（见 `docs/output-standard.md` §1）。

本模块只依赖标准库，且**不得** import `partdoc` 或 `gui`（沿用 `partdoc.py` 自身的纪律）——
它被 `tools/` 与 `gui/` 两侧共用，任何一侧的导入都不应牵出另一侧。
"""
from __future__ import annotations

import json
import os
import pathlib
import time

FORMAT = "tag-order/1"

TAG_DIR = pathlib.Path(__file__).resolve().parent
ORDER_FILE = TAG_DIR / "tag_order.json"

# 官方类别键的合法闭集（去括号形式，＝产物 `category` 的写法）。
# 与 `gui/results_json.py` 的 RESULT_CATEGORIES 同源；此处保留一份独立定义以免本模块依赖 gui。
CATEGORIES: tuple[str, ...] = (
    "A 控制·异常", "B 伤害类型", "C 生存与增益", "D 部署与编队", "E 技力与技能资源",
    "F 治疗与支援", "G 召唤物", "H 攻击行为特征", "I 全场光环",
)

_NOTE = (
    "TAG 展示顺序的唯一维护处（手写权威源）。官方类＝类别序＋类内 TAG 序；"
    "玩家类＝TAG 序＋每 TAG 的子 TAG 取值序（键为 组＋值）。一律按 id 索引，改名不丢位置；"
    "未登记的 TAG／取值会被追加到所属段末尾。改本文件后跑 tools/apply_tag_order.py 投影到两处产物；"
    "纯排序变化只更新 updated，不升 version。"
)


class OrderError(ValueError):
    """顺序文件的结构错误（供调用方转成用户可读提示）。"""


# ----------------------------------------------------------------- 读写


def empty_order() -> dict:
    """空序：一切按产物现有顺序输出（等价于未启用排序层）。"""
    return {"format": FORMAT, "note": _NOTE, "official": {"categories": []}, "player": []}


def normalize(order: object) -> dict:
    """把读入的结构规范化成「对象数组」形态（容错裸字符串写法），并补默认键。"""
    if not isinstance(order, dict):
        raise OrderError("顺序文件的顶层应为对象")
    fmt = order.get("format", FORMAT)
    if fmt != FORMAT:
        raise OrderError(f"顺序文件的 format 应为 {FORMAT!r}，实为 {fmt!r}")

    off = order.get("official") or {}
    if not isinstance(off, dict):
        raise OrderError("official 应为对象")
    cats_in = off.get("categories") or []
    if not isinstance(cats_in, list):
        raise OrderError("official.categories 应为数组")
    cats: list[dict] = []
    for c in cats_in:
        if isinstance(c, str):
            c = {"key": c, "tags": []}
        if not isinstance(c, dict) or not str(c.get("key") or "").strip():
            raise OrderError("official.categories 的每一项须含非空 key")
        tags: list[dict] = []
        for t in c.get("tags") or []:
            t = {"id": t} if isinstance(t, str) else t
            if not isinstance(t, dict) or not str(t.get("id") or "").strip():
                raise OrderError(f"类别「{c['key']}」下有缺 id 的 TAG")
            tags.append({"id": str(t["id"]).strip(), "name": str(t.get("name") or "")})
        cats.append({"key": str(c["key"]).strip(), "tags": tags})

    pl_in = order.get("player") or []
    if not isinstance(pl_in, list):
        raise OrderError("player 应为数组")
    players: list[dict] = []
    for t in pl_in:
        t = {"id": t} if isinstance(t, str) else t
        if not isinstance(t, dict) or not str(t.get("id") or "").strip():
            raise OrderError("player 下有缺 id 的 TAG")
        subs: list[dict] = []
        for s in t.get("subs") or []:
            if isinstance(s, str):
                s = {"group": "子 TAG", "value": s}
            if not isinstance(s, dict):
                raise OrderError(f"{t['id']} 的 subs 项应为对象")
            g, v = str(s.get("group") or "").strip(), str(s.get("value") or "").strip()
            if not g or not v:
                raise OrderError(f"{t['id']} 的 subs 项缺 group 或 value")
            subs.append({"group": g, "value": v})
        players.append({"id": str(t["id"]).strip(), "name": str(t.get("name") or ""), "subs": subs})

    return {"format": FORMAT, "note": str(order.get("note") or _NOTE),
            "official": {"categories": cats}, "player": players}


def load(path: pathlib.Path | None = None) -> dict:
    """读顺序文件。**文件不存在→空序**（等价于未启用排序层，不报错）；
    文件存在但结构错→抛 `OrderError`。"""
    p = pathlib.Path(path) if path else ORDER_FILE
    if not p.exists():
        return empty_order()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise OrderError(f"{p.name} 不是合法 JSON：{exc}") from exc
    return normalize(raw)


def save(order: dict, path: pathlib.Path | None = None) -> None:
    """规范化后原子写（同目录 .tmp ＋ os.replace；PermissionError 重试，镜像 partdoc.save）。"""
    p = pathlib.Path(path) if path else ORDER_FILE
    doc = normalize(order)
    blob = (json.dumps(doc, ensure_ascii=False, indent=2).replace("\n", "\r\n") + "\r\n").encode("utf-8")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(blob)
    for attempt in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    os.replace(tmp, p)


# ----------------------------------------------------------------- 位次


def category_rank(order: dict) -> dict[str, int]:
    return {c["key"]: i for i, c in enumerate(order["official"]["categories"])}


def official_rank(order: dict) -> dict[tuple[str, str], int]:
    """(类别键, TAG id) → 位次（全表扁平编号，类内相对序即由它决定）。"""
    out: dict[tuple[str, str], int] = {}
    n = 0
    for c in order["official"]["categories"]:
        for t in c["tags"]:
            out[(c["key"], t["id"])] = n
            n += 1
    return out


def player_rank(order: dict) -> dict[str, int]:
    return {t["id"]: i for i, t in enumerate(order["player"])}


def sub_list(order: dict, tag_id: str) -> list[tuple[str, str]]:
    for t in order["player"]:
        if t["id"] == tag_id:
            return [(s["group"], s["value"]) for s in t["subs"]]
    return []


def sub_rank(order: dict, tag_id: str) -> dict[tuple[str, str], int]:
    return {k: i for i, k in enumerate(sub_list(order, tag_id))}


def sort_scopes(order: dict, tag_id: str, scopes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """按顺序文件排 [(组, 值)]；未登记的排末尾（稳定，保持原相对序）。"""
    rank = sub_rank(order, tag_id)
    return sorted(scopes, key=lambda gv: rank.get(gv, len(rank)))


def observed_subs(tag: dict) -> list[tuple[str, str]]:
    """该 TAG 的成员实际用到的 (组, 值)，按首次出现去重。"""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in tag.get("members") or []:
        for s in m.get("subTags") or []:
            g, v = str(s.get("group") or ""), str(s.get("value") or "")
            if not g or not v or (g, v) in seen:
                continue
            seen.add((g, v))
            out.append((g, v))
    return out


# ----------------------------------------------------------------- 套用


def _ordered_subs(order: dict, tag_id: str, obs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """顺序文件里登记且实际出现的取值（保序），其后接未登记的实到取值（保持首次出现序）。"""
    rank = sub_rank(order, tag_id)
    known = [kv for kv in sorted(rank, key=rank.get) if kv in set(obs)]
    seen = set(known)
    return known + [kv for kv in obs if kv not in seen]


def apply(doc: dict, order: dict | None = None) -> dict:
    """就地把产物重排为顺序文件规定的次序；返回变更计数。

    四件事：官方段（类别序×类内序）、玩家段（id 序）、每个玩家 TAG 的 `subOrder`、
    以及每 TAG 内**成员行 `subTags`／`recommendedBySub` 的取值序**。
    未登记的 TAG／取值一律追加到所属段末尾（稳定排序）。
    """
    if order is None:
        order = load()
    tags = doc.get("tags") or []
    counts = {"tags": 0, "subOrder": 0, "subTags": 0, "recommendedBySub": 0}

    off = [t for t in tags if t.get("source") == "official"]
    rest = [t for t in tags if t.get("source") != "official"]

    craw, orank = category_rank(order), official_rank(order)
    off_sorted = sorted(off, key=lambda t: (
        craw.get(str(t.get("category")), len(craw)),
        orank.get((str(t.get("category")), str(t.get("id"))), len(orank)),
    ))
    prank = player_rank(order)
    rest_sorted = sorted(rest, key=lambda t: prank.get(str(t.get("id")), len(prank)))

    new_tags = off_sorted + rest_sorted
    if [id(t) for t in new_tags] != [id(t) for t in tags]:
        counts["tags"] = sum(1 for a, b in zip(new_tags, tags) if a is not b)
    doc["tags"] = new_tags

    for t in rest_sorted:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        obs = observed_subs(t)
        rank = sub_rank(order, tid)
        ordered = _ordered_subs(order, tid, obs)

        # 1) 子 TAG 取值序（供前端筛选项排序）
        sub = [{"group": g, "value": v} for g, v in ordered]
        if t.get("subOrder") != sub:
            counts["subOrder"] += 1
        if sub:
            _set_key_before(t, "subOrder", sub, "members")
        elif "subOrder" in t:
            del t["subOrder"]

        # 2) 成员行 subTags 的取值序
        for m in t.get("members") or []:
            arr = m.get("subTags") or []
            if len(arr) < 2:
                continue
            keyed = [(str(s.get("group") or ""), str(s.get("value") or "")) for s in arr]
            want = sorted(range(len(arr)), key=lambda i: (rank.get(keyed[i], len(rank)), i))
            if want != list(range(len(arr))):
                m["subTags"] = [arr[i] for i in want]
                counts["subTags"] += 1

        # 3) 荐的作用域取值序
        for field in ("recommendedBySub", "recommendedFallbackBySub"):
            if not t.get(field):
                continue
            keyed = [(str(s.get("group") or ""), str(s.get("value") or "")) for s in t[field]]
            want = sorted(range(len(keyed)), key=lambda i: (rank.get(keyed[i], len(rank)), i))
            if want != list(range(len(keyed))):
                t[field] = [t[field][i] for i in want]
                counts["recommendedBySub"] += 1

    return counts


def _set_key_before(d: dict, key: str, value, before: str) -> None:
    """把 key 插到 before 之前（重建字典以保其它键的相对序 → diff 只有一行）。"""
    if key in d:
        d[key] = value
        return
    out: dict = {}
    for k, v in d.items():
        if k == before:
            out[key] = value
        out[k] = v
    if before not in d:
        out[key] = value
    d.clear()
    d.update(out)


# ----------------------------------------------------------------- 校验


def validate_order(order: dict) -> list[dict]:
    """顺序文件自身的结构问题（与产物无关）。"""
    probs: list[dict] = []

    def add(level: str, code: str, path: str, message: str) -> None:
        probs.append({"level": level, "code": code, "path": path, "label": "", "message": message})

    known = set(CATEGORIES)
    seen_cat: set[str] = set()
    seen_tag: dict[str, str] = {}
    for i, c in enumerate(order["official"]["categories"]):
        key = c["key"]
        if key in seen_cat:
            add("error", "T01", f"official.categories[{i}].key", f"类别「{key}」重复出现")
        seen_cat.add(key)
        if known and key not in known:
            add("warn", "T02", f"official.categories[{i}].key",
                f"类别键「{key}」不在闭集 {list(CATEGORIES)} 内")
        ids: set[str] = set()
        for j, t in enumerate(c["tags"]):
            if t["id"] in ids:
                add("error", "T03", f"official.categories[{i}].tags[{j}].id",
                    f"类别「{key}」内 TAG id「{t['id']}」重复")
            ids.add(t["id"])
            if t["id"] in seen_tag:
                add("error", "T04", f"official.categories[{i}].tags[{j}].id",
                    f"TAG id「{t['id']}」已在类别「{seen_tag[t['id']]}」出现（同一 TAG 只能登记一次）")
            else:
                seen_tag[t["id"]] = key

    seen_p: set[str] = set()
    for i, t in enumerate(order["player"]):
        if t["id"] in seen_p:
            add("error", "T05", f"player[{i}].id", f"玩家 TAG「{t['id']}」重复出现")
        seen_p.add(t["id"])
        if t["id"] in seen_tag:
            add("error", "T06", f"player[{i}].id", f"id「{t['id']}」与官方 TAG 重复")
        kvs: set[tuple[str, str]] = set()
        for j, s in enumerate(t["subs"]):
            kv = (s["group"], s["value"])
            if kv in kvs:
                add("error", "T07", f"player[{i}].subs[{j}]",
                    f"{t['id']} 的取值「{s['group']}／{s['value']}」重复登记")
            kvs.add(kv)
    return probs


def check_doc(doc: dict, order: dict) -> list[dict]:
    """产物与顺序文件的一致性（不改动 doc）。"""
    probs: list[dict] = []

    def add(level: str, code: str, path: str, message: str) -> None:
        probs.append({"level": level, "code": code, "path": path, "label": "", "message": message})

    tags = doc.get("tags") or []
    craw, orank = category_rank(order), official_rank(order)
    prank = player_rank(order)
    seen_official, seen_player = [], []
    seen_cat: set[str] = set()
    for i, t in enumerate(tags):
        if t.get("source") == "official":
            if seen_player:
                add("error", "T11", f"tags[{i}]", "官方 TAG 出现在玩家 TAG 之后（官方须整体在前）")
            cat = str(t.get("category"))
            if seen_official and cat != seen_official[-1][1] and cat in seen_cat:
                add("error", "T12", f"tags[{i}]", f"类别「{cat}」的 TAG 不连续（同类须相邻）")
            seen_cat.add(cat)
            seen_official.append((t.get("id"), cat))
        else:
            seen_player.append(t.get("id"))

    # 官方/@ 玩家 段序＝顺序文件序（不动点检查的廉价版：只看已登记者）
    want_off = [tid for tid in sorted(orank, key=orank.get)
                if any(x[0] == tid for x in seen_official)]
    got_off = [x[0] for x in seen_official if x[0] in orank]
    if got_off != want_off:
        add("error", "T13", "tags[]", "官方 TAG 顺序与顺序文件不一致（跑 tools/apply_tag_order.py）")
    want_p = [tid for tid in sorted(prank, key=prank.get) if tid in seen_player]
    got_p = [x for x in seen_player if x in prank]
    if got_p != want_p:
        add("error", "T14", "tags[]", "玩家 TAG 顺序与顺序文件不一致（跑 tools/apply_tag_order.py）")

    for i, t in enumerate(tags):
        if t.get("source") == "official":
            if t.get("subOrder"):
                add("error", "T15", f"tags[{i}].subOrder", "官方 TAG 不应带 subOrder")
            continue
        tid = str(t.get("id") or "")
        obs = observed_subs(t)
        rank = sub_rank(order, tid)
        want = _ordered_subs(order, tid, obs)
        sub = [(str(s.get("group") or ""), str(s.get("value") or "")) for s in (t.get("subOrder") or [])]
        if sub != want:
            add("error", "T16", f"tags[{i}].subOrder",
                f"{tid} 的 subOrder 与顺序文件不一致（应为 {'、'.join(v for _g, v in want) or '（空）'}）")
        for g, v in obs:
            if rank and (g, v) not in rank:
                add("warn", "T17", f"tags[{i}]", f"{tid} 的取值「{g}／{v}」未登记（已追加到末尾）")
        for g, v in rank:
            if (g, v) not in set(obs):
                add("error", "T18", f"tags[{i}]", f"{tid} 登记的取值「{g}／{v}」在产物中已不存在（失效项）")

    for c in order["official"]["categories"]:
        for t in c["tags"]:
            if not any(x[0] == t["id"] for x in seen_official):
                add("error", "T19", "official", f"登记了官方 TAG「{t['id']}」，产物中不存在")
    for t in order["player"]:
        if t["id"] not in seen_player:
            add("error", "T20", "player", f"登记了玩家 TAG「{t['id']}」，产物中不存在")

    return probs

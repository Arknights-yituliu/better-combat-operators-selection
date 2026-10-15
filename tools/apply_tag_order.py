# -*- coding: utf-8 -*-
"""把 `results/` 的两处产物重排为 `tag_order.json` 规定的顺序。

    .venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py            # 套用（只重排，不重生成）
    .venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --check    # 一致性校验，不写盘
    .venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --seed     # 把产物有、顺序文件没登记的项补到各段末尾
    .venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --seed --rebuild   # 按产物当前顺序整体重建
    .venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --report   # 只看统计

职责边界（重要）：

- 本脚本**只重排，不重生成**。改了分文件后它不会刷新内容——那要跑 `tools/generate_results.py`。
- 因此产物的**顺序**有两个写者（本脚本与 `tools/generate_results.py`），但二者同读一个顺序文件，
  不可能给出不同的顺序；`generate_results.py` 在 `build()` 里就已套用同一排序，故重生成不会打乱。
- 纯排序变化**只更新 `updated`，不升 `version`**（见 `docs/output-standard.md` §1）。
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIPE = ROOT / "agent_workspace" / "tag_pipeline"
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PIPE))

import tag_order                                    # noqa: E402  （顺序文件与套用逻辑的唯一实现）
from gui.md import write_atomic                     # noqa: E402
from gui import results_json as rj                  # noqa: E402

OPERATOR_TAGS = RESULTS / "operator-tags.json"
CRITERIA = RESULTS / "player-tags-criteria.json"


# ----------------------------------------------------------------- 读写（逐文件保真）


def read_styled(path: pathlib.Path) -> tuple[dict, str, int]:
    """读 JSON 并记下**原文件的换行与缩进**，写回时照原样还原（不得归一化）。"""
    raw = path.read_bytes().decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in raw else "\n"
    indent = 2
    for line in raw.split("\n"):
        if line.startswith(" "):
            indent = len(line) - len(line.lstrip(" "))
            break
    return json.loads(raw), eol, indent


def render(doc: dict, eol: str, indent: int) -> str:
    """与各自的生成器逐字一致：`operator-tags.json` 与 `criteria_to_json.py` 都是「dumps ＋ 末尾换行」。"""
    text = json.dumps(doc, ensure_ascii=False, indent=indent) + "\n"
    return text.replace("\n", "\r\n") if eol == "crlf" else text


def _load_order(path: pathlib.Path | None) -> dict:
    try:
        return tag_order.load(path)
    except tag_order.OrderError as exc:
        print(f"顺序文件有误：{exc}")
        raise SystemExit(2)


# ----------------------------------------------------------------- 套用


def _order_criteria(doc: dict, order: dict) -> dict:
    """criteria 产物只重排 tags[] 与每个 TAG 的 subs[]（其余键原样）。"""
    counts = {"tags": 0, "subs": 0}
    tags = doc.get("tags") or []
    prank = tag_order.player_rank(order)
    want = sorted(tags, key=lambda t: prank.get(str(t.get("id")), len(prank)))
    if [id(t) for t in want] != [id(t) for t in tags]:
        counts["tags"] = sum(1 for a, b in zip(want, tags) if a is not b)
    for i, t in enumerate(want):
        tid = str(t.get("id") or "")
        subs = t.get("subs") or []
        keyed = [(str(s.get("group") or ""), str(s.get("value") or "")) for s in subs]
        rank = tag_order.sub_rank(order, tid)
        order_idx = sorted(range(len(subs)), key=lambda j: (rank.get(keyed[j], len(rank)), j))
        if order_idx != list(range(len(subs))):
            t["subs"] = [subs[j] for j in order_idx]
            counts["subs"] += 1
    doc["tags"] = want
    return counts


def apply_to_products(order_path: pathlib.Path | None = None, *, write: bool = True) -> dict:
    """把两处产物重排为顺序文件规定的次序。**无变化则不写盘**（幂等：稳定字节、稳定 mtime）。"""
    order = _load_order(order_path)
    out: dict = {"order_file": str((order_path or tag_order.ORDER_FILE).relative_to(ROOT)), "products": {}}

    doc, eol, indent = read_styled(OPERATOR_TAGS)
    before = copy.deepcopy(doc)
    counts = tag_order.apply(doc, order)
    changed = doc != before
    if changed:
        doc["updated"] = rj.today_str()          # 只更新日期，**不动 version**
        if write:
            write_atomic(OPERATOR_TAGS, render(doc, eol, indent))
    out["products"]["operator-tags.json"] = {"changed": changed, "counts": counts,
                                             "updated": doc.get("updated") if changed else None}

    if CRITERIA.exists():
        cdoc, ceol, cindent = read_styled(CRITERIA)
        cbefore = copy.deepcopy(cdoc)
        ccounts = _order_criteria(cdoc, order)
        cchanged = cdoc != cbefore
        if cchanged and write:
            write_atomic(CRITERIA, render(cdoc, ceol, cindent))
        out["products"]["player-tags-criteria.json"] = {"changed": cchanged, "counts": ccounts}
    return out


# ----------------------------------------------------------------- 校验


def check(order_path: pathlib.Path | None = None) -> int:
    """顺序文件结构 ＋ 两处产物是否为套用后的不动点。失效项＝错误；未登记项＝提示。"""
    order = _load_order(order_path)
    probs = list(tag_order.validate_order(order))

    doc, _eol, _ind = read_styled(OPERATOR_TAGS)
    probs += tag_order.check_doc(doc, order)
    # 不动点：再套用一次应当毫无变化
    again = copy.deepcopy(doc)
    tag_order.apply(again, order)
    if again != doc:
        probs.append({"level": "error", "code": "T21", "path": "results/operator-tags.json",
                      "label": "", "message": "产物不是套用后的形态（跑 tools/apply_tag_order.py）"})
    if CRITERIA.exists():
        cdoc, _c, _ci = read_styled(CRITERIA)
        cagain = copy.deepcopy(cdoc)
        _order_criteria(cagain, order)
        if cagain != cdoc:
            probs.append({"level": "error", "code": "T22", "path": "results/player-tags-criteria.json",
                          "label": "", "message": "criteria 产物的子项序未随顺序文件（跑 tools/apply_tag_order.py）"})

    errors = [p for p in probs if p["level"] == "error"]
    warns = [p for p in probs if p["level"] != "error"]
    for p in errors:
        print(f"  ✗ [{p['code']}] {p['path']}：{p['message']}")
    for p in warns:
        print(f"  · [{p['code']}] {p['path']}：{p['message']}")
    print(f"排序层校验：错误 {len(errors)} 条、提示 {len(warns)} 条")
    return 1 if errors else 0


# ----------------------------------------------------------------- seed


def seed(order_path: pathlib.Path | None = None, *, rebuild: bool = False) -> int:
    """把产物有、顺序文件没登记的项补到各段末尾（不动已有相对序）。

    `--rebuild`（或文件不存在时）改为按产物当前顺序整体重建。
    """
    doc, _eol, _ind = read_styled(OPERATOR_TAGS)
    try:
        order = tag_order.load(order_path)
        if not order["official"]["categories"] and not order["player"]:
            rebuild = True
    except tag_order.OrderError as exc:
        print(f"顺序文件有误（改为整体重建）：{exc}")
        rebuild = True
        order = tag_order.empty_order()

    off = [t for t in doc.get("tags") or [] if t.get("source") == "official"]
    pl = [t for t in doc.get("tags") or [] if t.get("source") != "official"]

    if rebuild:
        cats: list[dict] = []
        for t in off:
            key = str(t.get("category") or "")
            if not cats or cats[-1]["key"] != key:
                cats.append({"key": key, "tags": []})
            cats[-1]["tags"].append({"id": t.get("id"), "name": t.get("name")})
        order = {"format": tag_order.FORMAT, "note": tag_order._NOTE,
                 "official": {"categories": cats}, "player": []}
        for t in pl:
            order["player"].append({"id": t.get("id"), "name": t.get("name"),
                                    "subs": [{"group": g, "value": v} for g, v in tag_order.observed_subs(t)]})
        print("按产物当前顺序整体重建了顺序文件。")
    else:
        # 官方：补未登记的 TAG 到其类别末尾；补未登记的类别到官方段末尾（仍在玩家段之前）
        by_key = {c["key"]: c for c in order["official"]["categories"]}
        known_ids = {t["id"] for c in order["official"]["categories"] for t in c["tags"]}
        added = 0
        for t in off:
            key = str(t.get("category") or "")
            if key not in by_key:
                by_key[key] = {"key": key, "tags": []}
                order["official"]["categories"].append(by_key[key])
            if t.get("id") not in known_ids:
                by_key[key]["tags"].append({"id": t.get("id"), "name": t.get("name")})
                known_ids.add(t.get("id"))
                added += 1
        known_p = {t["id"] for t in order["player"]}
        for t in pl:
            if t.get("id") in known_p:
                for e in order["player"]:
                    if e["id"] == t["id"]:
                        e["name"] = t.get("name") or e.get("name") or ""
                        have = {(s["group"], s["value"]) for s in e["subs"]}
                        for g, v in tag_order.observed_subs(t):
                            if (g, v) not in have:
                                e["subs"].append({"group": g, "value": v})
                                added += 1
                        break
            else:
                order["player"].append({"id": t.get("id"), "name": t.get("name"),
                                        "subs": [{"group": g, "value": v} for g, v in tag_order.observed_subs(t)]})
                known_p.add(t.get("id"))
                added += 1
        print(f"补登记 {added} 项到各段末尾。")

    # 失效项只提示、不自动删（退役 id 不得复活，也不该被静默抹掉）
    stale = [p for p in tag_order.validate_order(order) if p["level"] == "error"]
    if stale:
        print("顺序文件仍有结构问题：")
        for p in stale:
            print(f"  ✗ [{p['code']}] {p['path']}：{p['message']}")
        return 1
    tag_order.save(order, order_path)
    print(f"已写出 {tag_order.ORDER_FILE.relative_to(ROOT)}"
          f"（官方 {sum(len(c['tags']) for c in order['official']['categories'])} 个 TAG／"
          f"{len(order['official']['categories'])} 类；玩家 {len(order['player'])} 个 TAG）。")
    return 0


# ----------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser(description="按 tag_order.json 重排 results/ 产物")
    ap.add_argument("--check", action="store_true", help="只校验一致性，不写盘")
    ap.add_argument("--seed", action="store_true", help="把产物有、顺序文件没登记的项补到各段末尾")
    ap.add_argument("--rebuild", action="store_true", help="配合 --seed：按产物当前顺序整体重建")
    ap.add_argument("--report", action="store_true", help="打印套用统计（写盘）")
    ap.add_argument("--order", type=pathlib.Path, default=None, help="指定顺序文件（默认 tag_order.json）")
    args = ap.parse_args()

    if args.seed:
        return seed(args.order, rebuild=args.rebuild)
    if args.check:
        return check(args.order)
    res = apply_to_products(args.order)
    for name, info in res["products"].items():
        c = info["counts"]
        detail = "、".join(f"{k} {v}" for k, v in c.items() if v)
        print(f"{name}：{'已重排' if info['changed'] else '无变化'}"
              f"{'（' + detail + '）' if detail else ''}")
    if not any(i["changed"] for i in res["products"].values()):
        print("两处产物均已符合顺序文件，未写盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""「TAG 排序」页签：顺序文件（`agent_workspace/tag_pipeline/tag_order.json`）的读写接口。

顺序的唯一维护处是那份文件；本模块只做三件事：把文件与**当前产物的实况**一起交给前端、
把前端拖出来的顺序校验后落盘（可选顺带把两处产物重排）、以及报告未登记／已失效项。

产物重排复用 `tools/apply_tag_order.apply_to_products`——与命令行同一实现，
故面板里排的顺序与 `tools/generate_results.py` 生成时的顺序不可能不一致。
"""
from __future__ import annotations

import copy
import json
import sys

from .config import ORDER_FILE, ROOT
from .errors import UserError
from .results_json import RESULTS_DIR, file_digest

sys.path.insert(0, str(ROOT / "tools"))
import apply_tag_order as ato  # noqa: E402  （套用逻辑的唯一实现）
import tag_order  # noqa: E402

OPERATOR_TAGS = RESULTS_DIR / "operator-tags.json"


def _read_order_file() -> tuple[dict, bool, str, list[dict]]:
    """→ (顺序文件, 文件是否存在, 摘要, 结构问题)。文件缺失或坏掉时退回空序并报问题。"""
    probs: list[dict] = []
    if not ORDER_FILE.exists():
        return tag_order.empty_order(), False, "", probs
    try:
        order = tag_order.load()
    except tag_order.OrderError as exc:
        probs.append({"level": "error", "code": "T00", "path": ORDER_FILE.name, "label": "", "message": str(exc)})
        return tag_order.empty_order(), True, file_digest(ORDER_FILE), probs
    probs += tag_order.validate_order(order)
    return order, True, file_digest(ORDER_FILE), probs


def _product() -> dict | None:
    if not OPERATOR_TAGS.exists():
        return None
    return json.loads(OPERATOR_TAGS.read_text(encoding="utf-8-sig"))


def _view(order: dict, doc: dict | None) -> dict:
    """顺序文件 × 产物实况：每项标出是否在产物里、产物里有而文件没登记的项单列。"""
    if doc is None:
        return {"official": [], "player": [], "missing": {"official": [], "player": [], "subs": []}}
    off = [t for t in doc.get("tags") or [] if t.get("source") == "official"]
    pl = [t for t in doc.get("tags") or [] if t.get("source") != "official"]
    by_id = {t.get("id"): t for t in off}
    p_by_id = {t.get("id"): t for t in pl}

    o_rank = tag_order.official_rank(order)
    cats = []
    for c in order["official"]["categories"]:
        cats.append({"key": c["key"], "tags": [
            {"id": t["id"], "name": (by_id.get(t["id"]) or {}).get("name") or t.get("name") or t["id"],
             "present": t["id"] in by_id,
             "members": len((by_id.get(t["id"]) or {}).get("members") or [])}
            for t in c["tags"]]})
    known_off = {tid for _cat, tid in o_rank}
    missing_off = [{"id": t.get("id"), "name": t.get("name"), "category": t.get("category"),
                    "members": len(t.get("members") or [])}
                   for t in off if t.get("id") not in known_off]

    prow, missing_p, missing_subs = [], [], []
    for t in order["player"]:
        p = p_by_id.get(t["id"])
        obs = tag_order.observed_subs(p) if p else []
        rank = {(s["group"], s["value"]) for s in t["subs"]}
        prow.append({
            "id": t["id"], "name": (p or {}).get("name") or t.get("name") or t["id"],
            "present": p is not None, "members": len((p or {}).get("members") or []),
            "subs": [{"group": s["group"], "value": s["value"], "inFile": True,
                      "members": sum(1 for m in (p or {}).get("members") or []
                                     if any((x.get("group"), x.get("value")) == (s["group"], s["value"])
                                            for x in m.get("subTags") or []))}
                     for s in t["subs"]],
        })
        for g, v in obs:
            if (g, v) not in rank:
                missing_subs.append({"tag": t["id"], "group": g, "value": v})
    known_p = set(tag_order.player_rank(order))
    for t in pl:
        if t.get("id") not in known_p:
            missing_p.append({"id": t.get("id"), "name": t.get("name"),
                              "members": len(t.get("members") or []),
                              "subs": [{"group": g, "value": v} for g, v in tag_order.observed_subs(t)]})
    return {"official": cats, "player": prow,
            "missing": {"official": missing_off, "player": missing_p, "subs": missing_subs}}


def load_order(_payload: dict) -> dict:
    """返回顺序文件 + 产物实况 + 未登记／失效清单 + 两处产物的状态。"""
    order, exists, digest, probs = _read_order_file()
    doc = _product()
    view = _view(order, doc)
    # 失效项：登记了但产物里已不存在（官方／玩家／取值三层）
    live_off = {t["id"] for c in view["official"] for t in c["tags"] if t["present"]}
    live_p = {t["id"] for t in view["player"] if t["present"]}
    stale = {
        "official": [t["id"] for c in order["official"]["categories"] for t in c["tags"] if t["id"] not in live_off],
        "player": [t["id"] for t in order["player"] if t["id"] not in live_p],
        "subs": [],
    }
    for t in order["player"]:
        if t["id"] not in live_p:
            continue
        obs = {(s["group"], s["value"]) for s in next(x for x in view["player"] if x["id"] == t["id"])["subs"]}
        for s in t["subs"]:
            if (s["group"], s["value"]) not in obs:
                stale["subs"].append({"tag": t["id"], "group": s["group"], "value": s["value"]})
    return {"ok": True, "path": str(ORDER_FILE.relative_to(ROOT)), "exists": exists, "digest": digest,
            "order": order, "view": view, "stale": stale,
            "products": {
                "operator_tags": {"exists": OPERATOR_TAGS.exists(),
                                  "version": (doc or {}).get("version"),
                                  "updated": (doc or {}).get("updated"),
                                  "digest": file_digest(OPERATOR_TAGS) if OPERATOR_TAGS.exists() else ""},
                "criteria": {"exists": (RESULTS_DIR / "player-tags-criteria.json").exists()},
            },
            "problems": probs}


def save_order(payload: dict) -> dict:
    """校验顺序文件并落盘；`apply` 为真时顺带把两处产物重排（同一把锁内完成）。"""
    order = payload.get("order")
    if not isinstance(order, dict):
        raise UserError("缺少 order", "missing")
    expect = payload.get("expect") or {}
    if expect.get("digest") and ORDER_FILE.exists() and not payload.get("force"):
        if expect["digest"] != file_digest(ORDER_FILE):
            raise UserError("顺序文件已被外部改动，请重新载入后再保存", "drift")
    try:
        norm = tag_order.normalize(order)
    except tag_order.OrderError as exc:
        raise UserError(f"顺序文件结构有误：{exc}", "order_format") from None
    probs = tag_order.validate_order(norm)
    if any(p["level"] == "error" for p in probs):
        raise UserError("顺序文件有结构错误（重复 id／重复取值／非法类别），未写盘", "order_format")

    tag_order.save(norm)
    applied: dict = {}
    if payload.get("apply", True):
        res = ato.apply_to_products()
        applied = res["products"]
    doc = _product()
    return {"ok": True, "digest": file_digest(ORDER_FILE),
            "written": True, "applied": applied,
            "view": _view(norm, doc), "problems": probs}


def sort_product_text(payload: dict) -> dict:
    """「整理」按钮：把内存里的产物文本按顺序文件重排（只改内存，不写盘）。

    算法放在服务端＝与生成器、命令行共用同一实现，浏览器侧不再需要第二份。
    """
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise UserError("文本缺失或过大", "too_big")
    try:
        doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"内容不是合法 JSON：{exc}", "parse") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("tags"), list):
        raise UserError("不是 operator-tags.json 的形态，未整理", "shape")
    before = copy.deepcopy(doc)
    counts = tag_order.apply(doc, tag_order.load())
    # 文本按前端同一序列化（JSON.stringify(d,null,2) 等价）；最终落盘样式由「结果 JSON」页决定
    return {"ok": True, "text": json.dumps(doc, ensure_ascii=False, indent=2),
            "changes": counts, "changed": doc != before,
            "version": doc.get("version"), "updated": before.get("updated")}

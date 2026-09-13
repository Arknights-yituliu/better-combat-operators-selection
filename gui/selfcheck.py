# -*- coding: utf-8 -*-
"""--check 的只读自检：解析断言、结果 JSON 校验器自测、静态资源与 DOM 契约检查。"""

from __future__ import annotations

import json
import pathlib
import re

from .config import OFFICIAL_FILES, PARTS, STATIC_DIR, rec
from .errors import UserError
from .md import Doc, split_cells, write_atomic  # noqa: F401
from .model import build_model
from .results_json import RESULTS_DIR, render_results, safe_name, validate_results
from .roster import launch_date
from .tags import parse_official_entries, parse_player_blocks  # noqa: F401
from .writeback import apply_ops, doc_registry, insert_into


def run_check() -> int:
    """只解析自检，不写任何文件。"""
    problems: list[str] = []
    model = build_model(fresh=True)
    p_rows = sum(len(b["rows"]) for t in model["player_tags"] for b in t["blocks"])
    p_blocks = sum(len(t["blocks"]) for t in model["player_tags"])
    print(f"玩家体感 TAG {len(model['player_tags'])} 个／子表 {p_blocks} 张／成员行 {p_rows} 条；"
          f"荐 {sum(len(v) for v in model['recommend'].values())} 条")
    for t in model["player_tags"]:
        print(f"  {t['num']} {t['name']}：子表 {len(t['blocks'])} 张 / 行 {sum(len(b['rows']) for b in t['blocks'])} / 荐 {len(t['recommend'])}")
        for b in t["blocks"]:
            for r in b["rows"]:
                if not r["op"]:
                    problems.append(f"{b['file']} 有空干员名：{r['raw'][:40]}")
    o_rows = sum(len(b["rows"]) for e in model["official_entries"] for b in e["blocks"])
    print(f"官方设定 TAG {len(model['official_entries'])} 个／成员行 {o_rows} 条")
    stale_headers = []
    for e in model["official_entries"]:
        b = e["blocks"][0]
        if len(b["header"]) != 3:
            problems.append(f"{e['file']}｜{e['name']}：官方表应为 3 列，实为 {len(b['header'])}")
        dates = [launch_date(r["op"]) for r in b["rows"]]
        first = min([d for d in dates if d], default=None) or "—"
        if e["n_declared"] != len(b["rows"]) or e["first_declared"] != first:
            stale_headers.append(f"{e['name']}（{e['file']}）：条目头 {e['n_declared']} 人 · 首现 {e['first_declared']}"
                                 f" → 实为 {len(b['rows'])} 人 · 首现 {first}")
    for s in stale_headers:
        print("  [条目头待重算] " + s)
    roster = {p["name"] for p in model["roster"]}
    print(f"全量干员 {len(roster)} 人；缺基本信息 {sum(1 for p in model['roster'] if not (p['star'] and p['cls'] and p['branch']))} 人")
    hist: dict[int, int] = {}
    for p in model["roster"]:
        hist[p["star"]] = hist.get(p["star"], 0) + 1
    print("  星级直方图：" + "，".join(f"{k}★×{hist.get(k, 0)}" for k in range(1, 7)))
    for t in model["player_tags"]:
        for b in t["blocks"]:
            for r in b["rows"]:
                if r["op"] not in roster:
                    problems.append(f"{b['file']} 的「{r['op']}」不在全量干员表")
    for e in model["official_entries"]:
        for r in e["blocks"][0]["rows"]:
            if r["op"] not in roster:
                problems.append(f"{e['file']} 的「{r['op']}」不在全量干员表")
    for s in model["stale"]:
        print(f"  [悬空荐] {s['tag']} -> {s['op']}")
    for t in model["unknown_tags"]:
        print(f"  [未知 TAG] {t}")

    # 注册表一致性：官方文件集须与合并脚本一致
    reg = doc_registry()
    want = {fn for _cat, fn in OFFICIAL_FILES}
    got = {k for k, v in reg.items() if v["kind"] == "official"}
    if want != got:
        problems.append(f"官方文件集与合并脚本不一致：缺 {want - got}，多 {got - want}")

    # 干跑（不落盘）：原文往返渲染须逐字节一致；插入一行后可解析且列数正确
    t0 = model["player_tags"][0]
    b0 = t0["blocks"][0]
    path0 = PARTS / b0["file"]
    before = path0.read_text(encoding="utf-8", newline="")
    if Doc(path0, "player").render() != before:
        problems.append(f"{b0['file']}：按行读写往返后与原文不一致（行尾处理有误）")
    probe = next((p for p in model["roster"] if p["name"] not in {r["op"] for r in b0["rows"]}), None)
    if probe:
        doc = Doc(path0, "player")
        got = insert_into(doc, b0, probe["name"], {"条件": "", "备注": "", "子 TAG": ""})
        text = doc.render()
        if got.get("skipped"):
            problems.append("干跑插入被误判为重复")
        if len(text.splitlines()) != len(before.splitlines()) + 1:
            problems.append("干跑插入后行数不符（应 +1）")
        if text.count("\r\n") != before.count("\r\n") + (1 if "\r\n" in before else 0):
            problems.append("干跑插入后 CRLF 计数不符")
        new_row = next((l for l in text.splitlines() if l.startswith("|") and probe["name"] in l), None)
        if not new_row or len(split_cells(new_row)) != len(b0["header"]):
            problems.append(f"干跑新行列数不符：{(new_row or '')[:50]}")
        dry = apply_ops({"ops": [{"kind": "insert", "op": probe["name"], "cond": "", "note": "",
                                  "targets": [{"id": b0["id"], "sig": b0["sig"]}]}], "automerge": False}, dry_run=True)
        if not dry["results"] or dry["results"][0]["targets"][0]["skipped"]:
            problems.append("干跑 /api/apply 插入被误判为重复")
        if path0.read_text(encoding="utf-8", newline="") != before:
            problems.append("干跑改动了文件（不应写盘）")
    else:
        print("  [跳过] 未找到可用于干跑的干员")

    # ---- 静态资源与页面契约 ----
    html_path, css_path, js_path = STATIC_DIR / "index.html", STATIC_DIR / "app.css", STATIC_DIR / "app.js"
    if not STATIC_DIR.is_dir():
        problems.append(f"缺少静态资源目录：{STATIC_DIR}")
    for p in (html_path, css_path, js_path):
        if not p.is_file() or p.stat().st_size == 0:
            problems.append(f"静态资源缺失或为空：{p}")
    if html_path.is_file() and js_path.is_file():
        html, css, js = html_path.read_text(encoding="utf-8"), css_path.read_text(encoding="utf-8"), js_path.read_text(encoding="utf-8")
        if html.count("__TOKEN__") != 1:
            problems.append(f"index.html 里的 __TOKEN__ 应恰好一次，实际 {html.count('__TOKEN__')} 次")
        if "__TOKEN__" in js:
            problems.append("app.js 里不应出现 __TOKEN__（令牌走 <meta name=x-token>）")
        if "<style" in html or "<script>" in html:
            problems.append("index.html 仍有内联 <style>/<script>，应外链静态资源")
        for need in ('href="/static/app.css"', 'src="/static/app.js"', 'name="x-token"'):
            if need not in html:
                problems.append(f"index.html 缺少 {need}")
        if "color-scheme: dark" not in css or "--ak-surface-canvas: #111315" not in css:
            problems.append("app.css 缺少 ak-ui 深色画布令牌")
        if "fonts.googleapis.com" not in js or "AbortController" not in js:
            problems.append("app.js 缺少带超时的字体加载（Noto Sans/Serif SC）")
        # DOM 契约：三个既有验收脚本依赖的 id/class/全局名（并集出现在 index.html ∪ app.js）
        contract = ("picklist pcnt oplist cnt tagtree stagelist stagetip ioplist icnt status search isearch "
                    "psearch tsearch menu modal toast resdot resfile resstats rtcnt rtags rmembers rpanel resbody "
                    "resrc rstext rserr btnew btload btmode btsort btcheck btview btback btformat btsave btmerge "
                    "btreload btclear automerge automergewrap mok mforce mnew mver mupd mbump mprob modal-card "
                    "row val editline tagline warnbar grouphdr blk stage-item kv dotid").split()
        merged = html + js
        missing = [name for name in contract if (f'id="{name}"' not in merged and f"#{name}" not in merged
                                                 and f'"{name}"' not in merged and f"'{name}'" not in merged)]
        if missing:
            problems.append("页面缺少验收脚本依赖的契约名：" + "、".join(missing))
        if "const RES" not in js:
            problems.append("app.js 里 RES 必须是顶层全局（验收脚本用 page.evaluate 读它）")

    # ---- 结果 JSON：文件名白名单 / 落盘格式 / 校验器自检 ----
    for bad in ("../x.json", "a/b.json", "a\\b.json", "x.txt", "con.json", "x.json ", ".hidden.json", "x", ""):
        try:
            safe_name(bad)
            problems.append(f"safe_name 应拒绝却通过了：{bad!r}")
        except UserError:
            pass
    for good in ("operator-tags.json", "测试 结果.json", "v2.json", "_tmp.json"):
        try:
            safe_name(good)
        except UserError as exc:
            problems.append(f"safe_name 应通过却拒绝了：{good!r}（{exc}）")
    sample = {
        "version": "v1", "updated": "2026-01-01",
        "operators": [
            {"name": "甲", "rarity": 6, "class": "术师", "branch": "中坚术师", "faction": "罗德岛",
             "releaseDate": "2024-01-01", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"},
            {"name": "乙", "rarity": 5, "class": "重装", "branch": "铁卫", "faction": "",
             "releaseDate": "2023-01-01", "prtsUrl": "https://prts.wiki/w/%E4%B9%99"}],
        "tags": [{"id": "P01", "name": "决战歼灭", "source": "player", "recommended": ["乙"], "members": [
            {"operator": "甲", "condition": "无", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"},
            {"operator": "甲", "condition": "", "prtsUrl": "https://prts.wiki/w/%E7%94%B2"}]}],
    }
    got, _stats = validate_results(sample)
    codes = {p["code"] for p in got}
    for want in ("M4", "M5", "R1"):
        if want not in codes:
            problems.append(f"校验器自检：样例应报出 {want}，实际只报出 {sorted(codes)}")
    text = render_results({"白铁": "OK"}, "crlf")
    if text.count("\r\n") != text.count("\n") or not text.endswith("\r\n") or "﻿" in text:
        problems.append("render_results 的 CRLF / BOM 处理有误")
    if json.loads(text) != {"白铁": "OK"} or '"白铁"' not in text:
        problems.append("render_results 往返解析不一致或未保持 ensure_ascii=False")
    target = RESULTS_DIR / "operator-tags.json"
    if target.exists():
        raw = target.read_text(encoding="utf-8-sig", newline="")
        try:
            probs, st = validate_results(json.loads(raw))
            n_err = sum(1 for p in probs if p["level"] == "error")
            print(f"结果 JSON：results/operator-tags.json（{len(raw)} 字符）→ {n_err} 错误 / {len(probs) - n_err} 提醒"
                  f"；operators {st['operators']} / tags {st['tags']} / 关系 {st['members']}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"results/operator-tags.json 解析失败：{exc}")
    else:
        print("[跳过] results/operator-tags.json 尚未生成（本工具只编辑，不生成）")

    if problems:
        print("发现问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("校验通过。")
    return 0

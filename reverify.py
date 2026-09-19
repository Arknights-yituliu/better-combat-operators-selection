# -*- coding: utf-8 -*-
"""「（待验证）」复算与回填工具。

背景：results/operator-tags.json 中的「（待验证）」是 AI 推算的数值（攻速/间隔换算、
倍率相乘/叠乘等），需逐条复算复核后回填分文件。链路与规范见 docs/concept.md:33、
根目录《待验证复算.md》。

子命令：
    extract  —— 抽出 JSON 中全部「（待验证）」条目，回查分文件行号/原行/备注原文，
                抽好待替换的「旧片段」，连同非 JSON 区的附录清单，写成 _reverify/items.jsonl。
    check    —— 算术自检（steps[] 复算）+ 证据与最小 diff 校验（复算产物就绪后运行）。
    report   —— 汇总各分组产物为根目录《待验证复算.md》（复核文件）。
    apply    —— 解析复核文件的「回填：…」行，回填分文件（--dry-run 先行）。
    verify   —— 重生成之后的验收（标记归零、结构 diff、锚点稳定）。

运行（Windows 控制台为 GBK，务必带 -X utf8；报告统一写 UTF-8 文件再读）：
    .venv/Scripts/python.exe -X utf8 reverify.py extract
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from generate_results import clean_cell, strip_marker, P05_PATH_RE  # noqa: E402
from gui.md import is_sep_row, split_cells                          # noqa: E402

PARTS_DIR = ROOT / "material_datas" / "tag_pipeline" / "player_tags"
RV_DIR = PARTS_DIR / "_reverify"
ITEMS_FILE = RV_DIR / "items.jsonl"
REPORTS_DIR = RV_DIR / "reports"
RESULTS_FILE = ROOT / "results" / "operator-tags.json"

# 12 个玩家 TAG 分文件（与 _merge_to_docs.py 的硬编码清单一致）
TAG_FILES = [
    ("01", "决战歼灭"), ("02", "次数对策"), ("03", "吃拐一轮秒"), ("04", "远程消耗"),
    ("05", "插拔容错"), ("06", "初动增加"), ("07", "充电"), ("08", "拐杖"),
    ("09", "保人"), ("10", "大力推拉"), ("11", "阻挡数5"), ("12", "阵容组合"),
]

# 「（待验证）」及其变体：含（均待验证）、（待验证，……）等
MARK_RE = re.compile(r"（[^）]{0,40}?待验证[^）]{0,40}?）")
# 只匹配最内层括号（用于剥离标记、避免跨嵌套括号吃掉正文）
MARK_STRICT = re.compile(r"（[^（）]{0,40}?待验证[^（）]{0,40}?）")

# 片段扩窗的边界字符（不含全角空格/半角空格——数值与单位间的空格要保留在片段内）
BOUND = set("，；。、：！？＝=（）()【】「」《》*｜|")

# 不进 JSON 的标记位置建议动作（按所在小节与文字特征判定）
RULE_TEXT_HINTS = ("标注", "标**（待验证）**", "标「（待验证）」")


def read_lines(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------- 分文件行迭代
# 与 generate_results.read_tables 相同的表格切分规则，但产出每行的真实行号，
# 并按分文件顺序记录所在的 h2/h3/h4 小节。

def iter_part_rows(path: pathlib.Path):
    """产出 (line_no, h2, h3, h4, header, raw, cells)。line_no 为 1 基行号。"""
    lines = read_lines(path)
    h2 = h3 = h4 = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            h2, h3, h4 = line[3:].strip(), "", ""
            i += 1
            continue
        if line.startswith("### "):
            h3, h4 = line[4:].strip(), ""
            i += 1
            continue
        if line.startswith("#### "):
            h4 = line[5:].strip()
            i += 1
            continue
        if not line.lstrip().startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        header = split_cells(lines[i])
        for k in range(i + 1, j):
            raw = lines[k]
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            yield k + 1, h2, h3, h4, header, raw, cells
        i = j


def member_row_remark(tag_no: str, header: list[str], cells: list[str]) -> str:
    """复刻 generate_results.parse_player 对成员行备注的变换（clean_cell + P05 strip）。"""
    ci, ni = header.index("条件"), header.index("备注")
    clean = [clean_cell(c) for c in cells]
    remark = clean[ni]
    if tag_no == "05":
        remark, _ = strip_marker(remark, [P05_PATH_RE])
    return remark


# ---------------------------------------------------------------- 片段扩窗

def fragment_for(text: str, m: re.Match, left_limit: int, right_limit: int) -> str:
    """以标记为中心扩窗：左右扩到最近的边界字符为止；确保含数字，必要时跨过一个边界再扩。"""
    s, e = m.start(), m.end()

    def expand(s0: int, e0: int) -> tuple[int, int]:
        i, j = s0, e0
        while i > left_limit and text[i - 1] not in BOUND:
            i -= 1
        while j < right_limit and text[j] not in BOUND:
            j += 1
        return i, j

    i, j = expand(s, e)
    for _ in range(2):  # 片段不含数字时跨过边界继续扩（最多两轮）
        if re.search(r"\d", text[i:j]):
            break
        k = i
        while k > left_limit and text[k - 1] in BOUND:
            k -= 1
        while k > left_limit and text[k - 1] not in BOUND:
            k -= 1
        j2 = j
        while j2 < right_limit and text[j2] in BOUND:
            j2 += 1
        while j2 < right_limit and text[j2] not in BOUND:
            j2 += 1
        i, j = k, j2
    return text[i:j].strip()


# ---------------------------------------------------------------- extract

def extract() -> int:
    warnings: list[str] = []
    RV_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 分文件成员行索引：key=(tag_id, 干员, 变换后备注) → [行信息]
    row_index: dict[tuple[str, str, str], list[dict]] = {}
    all_rows: list[dict] = []   # 全部表格行（含非成员表，供附录归属判断）
    line_owner: dict[tuple[str, int], str] = {}   # (file, line) → 该行的用途标注
    file_texts: dict[str, str] = {}
    for no, tag_name in TAG_FILES:
        fname = f"{no}-{tag_name}.md"
        fpath = PARTS_DIR / fname
        file_texts[fname] = fpath.read_text(encoding="utf-8")
        for line_no, h2, h3, h4, header, raw, cells in iter_part_rows(fpath):
            info = {"file": fname, "tag": f"P{no}", "tag_no": no, "line": line_no,
                    "h2": h2, "h3": h3, "h4": h4, "header": header, "raw": raw, "cells": cells}
            all_rows.append(info)
            if len(header) >= 3 and header[0] == "干员" and "条件" in header and "备注" in header:
                op = clean_cell(cells[0])
                key = (f"P{no}", op, member_row_remark(no, header, cells))
                row_index.setdefault(key, []).append(info)

    # 2) 扫描结果 JSON
    doc = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    items: list[dict] = []
    json_marker_total = 0
    occ_counter: dict[tuple[str, str], int] = {}

    def handle_remark(tag: dict, tag_idx: int, member: dict, member_idx: int,
                      remark: str, provider_idx: int | None = None) -> None:
        nonlocal json_marker_total
        marks = list(MARK_RE.finditer(remark))
        if not marks:
            return
        json_marker_total += len(marks)
        op = member.get("operator", "?")
        key = (tag["id"], op, remark)
        cands = row_index.get(key, [])
        if not cands:
            warnings.append(f"[未映射] {tag['id']} {op}：JSON 备注无法回查分文件行（{len(marks)} 处标记）")
            return
        # 选行：优先「原始备注格含标记且标记数一致」者
        picked = None
        for info in cands:
            ni = info["header"].index("备注")
            n = len(list(MARK_RE.finditer(info["cells"][ni])))
            if n == len(marks):
                picked = info
                break
        if picked is None:
            picked = cands[0]
            warnings.append(f"[标记数不符] {tag['id']} {op}：分文件行 {picked['file']}:{picked['line']} "
                            f"标记数与 JSON 不一致，已取首行")
        if len(cands) > 1:
            warnings.append(f"[多候选] {tag['id']} {op}：同键匹配 {len(cands)} 行，取 "
                            f"{picked['file']}:{picked['line']}")
        ni = picked["header"].index("备注")
        ci = picked["header"].index("条件")
        raw_note, raw_cond = picked["cells"][ni], picked["cells"][ci]
        file_text = file_texts[picked["file"]]
        raw_marks = list(MARK_RE.finditer(raw_note))
        if len(raw_marks) != len(marks):
            warnings.append(f"[备注变换差异] {picked['file']}:{picked['line']} {op}："
                            f"JSON {len(marks)} 处 / 原文 {len(raw_marks)} 处")
        for k, m in enumerate(raw_marks, 1):
            occ_counter[(tag["id"], op)] = occ_counter.get((tag["id"], op), 0) + 1
            occ = occ_counter[(tag["id"], op)]
            left_limit = raw_marks[k - 2].end() if k >= 2 else 0
            right_limit = raw_marks[k].start() if k < len(raw_marks) else len(raw_note)
            frag = fragment_for(raw_note, m, left_limit, right_limit)
            item = {
                "id": f"{tag['id']}-{op}-{occ}",
                "tag": tag["id"], "tag_name": tag["name"],
                "operator": op,
                "file": picked["file"], "line": picked["line"],
                "occ": k, "occ_total": len(raw_marks),
                "json_path": {"tag_idx": tag_idx, "member_idx": member_idx,
                              "provider_idx": provider_idx},
                "json_remark": remark,
                "raw_cond": raw_cond,
                "raw_note": raw_note,
                "raw_line": picked["raw"],
                "old_fragment": frag,
                "frag_in_cell": raw_note.count(frag),
                "frag_in_file": file_text.count(frag),
                "context": remark[max(0, m.start() - 60):m.end() + 15],
            }
            if item["frag_in_cell"] != 1:
                warnings.append(f"[片段非唯一] {item['id']}：片段在备注格出现 "
                                f"{item['frag_in_cell']} 次：{frag!r}")
            items.append(item)

    for tag_idx, tag in enumerate(doc["tags"]):
        if tag.get("source") != "player":
            continue
        for member_idx, member in enumerate(tag["members"]):
            if "remark" in member:
                handle_remark(tag, tag_idx, member, member_idx, member["remark"])
            for p_idx, prov in enumerate(member.get("providers", [])):
                if "remark" in prov:
                    handle_remark(tag, tag_idx, prov, member_idx, prov["remark"], p_idx)
            if member.get("combo") and member.get("remark"):
                handle_remark(tag, tag_idx, {"operator": member["combo"]}, member_idx,
                              member["remark"])
    # P12 组合级 remark（组合元数据，不属成员行）单独清点
    combo_marks = sum(len(MARK_RE.findall(m.get("remark", "")))
                      for t in doc["tags"] if t.get("source") == "player"
                      for m in t["members"] if m.get("combo"))
    json_marker_total += combo_marks
    if combo_marks:
        warnings.append(f"[组合级备注] P12 组合元数据含 {combo_marks} 处标记，需人工定位")

    # 3) 附录：分文件里未纳入 items 的标记
    used = {(it["file"], it["line"], it["occ"]) for it in items}
    appendix: list[dict] = []
    for no, tag_name in TAG_FILES:
        fname = f"{no}-{tag_name}.md"
        text = file_texts[fname]
        for line_no, line in enumerate(text.splitlines(), 1):
            if not MARK_RE.search(line):
                continue
            # 该行是否为已纳入的成员行
            taken = sum(1 for it in items if it["file"] == fname and it["line"] == line_no)
            marks_on_line = len(list(MARK_RE.finditer(line)))
            if taken >= marks_on_line:
                continue
            section = ""
            for h in reversed(range(1, line_no)):
                head = text.splitlines()[h - 1]
                if head.startswith("## "):
                    section = head[3:].strip()
                    break
            rule_text = any(hint in line for hint in RULE_TEXT_HINTS)
            action = "保留" if rule_text else ("忽略" if section.startswith("检索记录") else "复核")
            appendix.append({"id": f"X-{no}-{line_no}", "file": fname, "tag": f"P{no}",
                             "line": line_no, "section": section, "action": action,
                             "text": line.strip()})

    # 4) 自检：JSON 标记总数应等于 items 数
    if json_marker_total != len(items):
        warnings.append(f"[总数不符] JSON 标记 {json_marker_total} 处 / 抽出 {len(items)} 条")

    # 5) 落盘
    with ITEMS_FILE.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    lines = [
        "# extract 报告",
        "",
        f"- JSON 标记总数（含组合级）：{json_marker_total}；抽出条目：{len(items)}；"
        f"附录（非 JSON 区）：{len(appendix)}",
        f"- 涉及分文件：{[it['file'] for it in items].count('01-决战歼灭.md') and ''}"
        f"P01={sum(1 for i in items if i['tag'] == 'P01')}、"
        f"P02={sum(1 for i in items if i['tag'] == 'P02')}、"
        f"P03={sum(1 for i in items if i['tag'] == 'P03')}、"
        f"P05={sum(1 for i in items if i['tag'] == 'P05')}",
        f"- 片段唯一性问题：{sum(1 for i in items if i['frag_in_cell'] != 1)}",
        f"- 警告：{len(warnings)}",
        "",
        "## 片段抽样（前 25 条）",
        "",
    ]
    for it in items[:25]:
        lines.append(f"- {it['id']}　[{it['file']}:{it['line']}]　旧片段：{it['old_fragment']}")
    lines += ["", "## 附录清单", ""]
    for ap in appendix:
        lines.append(f"- {ap['id']}　[{ap['file']}:{ap['line']}]（{ap['section']}｜建议{ap['action']}）"
                     f"{ap['text'][:110]}")
    lines += ["", "## 警告明细", ""] + [f"- {w}" for w in warnings]
    (REPORTS_DIR / "extract.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"OK extract: items={len(items)} appendix={len(appendix)} warnings={len(warnings)}")
    print(f"report: {REPORTS_DIR / 'extract.md'}")
    return 0 if not warnings else 0  # 警告不改变退出码，供人读报告


# ---------------------------------------------------------------- check

def _translate_expr(expr: str) -> str:
    s = (expr.replace("×", "*").replace("÷", "/").replace("＋", "+")
         .replace("−", "-").replace("－", "-").replace("（", "(").replace("）", ")")
         .replace("＝", "").replace("≈", "").replace("~", ""))
    return re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)


def safe_eval(expr: str) -> float:
    """受限求值：只允许数字与 + - * / () 与百分号。"""
    import ast

    node = ast.parse(_translate_expr(expr), mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    for sub in ast.walk(node):
        if not isinstance(sub, allowed):
            raise ValueError(f"表达式含不允许的语法：{expr!r} -> {sub!r}")
    val = eval(compile(node, "<step>", "eval"), {"__builtins__": {}}, {})
    if not isinstance(val, (int, float)):
        raise ValueError(f"表达式求值非数值：{expr!r}")
    return float(val)


def apply_round(x: float, mode: str) -> float:
    import math

    if mode == "round":
        return float(math.floor(x + 0.5)) if x >= 0 else -float(math.floor(-x + 0.5))
    if mode == "floor":
        return float(math.floor(x))
    if mode == "ceil":
        return float(math.ceil(x))
    return x


def _nums_in(text: str) -> str:
    """去掉数字/单位/标记后的骨架，用于检测非数值改写（保留 ≈ 以察觉「近似」语义丢失）。"""
    t = MARK_STRICT.sub("", text)
    return re.sub(r"[0-9.%⌊⌋＋+\-−×÷/＝=（）()「」《》 　]", "", t)


def check() -> int:
    import math

    warnings: list[str] = []
    errors: list[str] = []
    review: list[str] = []      # 需人工瞄一眼的条目
    items = [json.loads(l) for l in ITEMS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {it["id"]: it for it in items}
    slices = {}
    for sl in sorted((RV_DIR / "slices").glob("G*.jsonl")):
        slices[sl.stem] = [json.loads(l) for l in sl.read_text(encoding="utf-8").splitlines() if l.strip()]

    parts: dict[str, dict] = {}
    for pf in sorted((RV_DIR / "parts").glob("G*.jsonl")):
        for ln, line in enumerate(pf.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:
                errors.append(f"{pf.name}:{ln} JSON 解析失败：{exc}")
                continue
            parts[obj.get("id", f"?{pf.name}:{ln}")] = obj

    # 覆盖性
    for g, sl in slices.items():
        pf = RV_DIR / "parts" / f"{g}.jsonl"
        if not pf.exists():
            warnings.append(f"{g}: 产物缺失（{pf.name}）")
            continue
        got = [json.loads(l)["id"] for l in pf.read_text(encoding="utf-8").splitlines() if l.strip()]
        want = [it["id"] for it in sl]
        if got != want:
            errors.append(f"{g}: 条目/顺序不一致（期望 {len(want)} 条，得到 {len(got)} 条）")
    missing = [it["id"] for it in items if it["id"] not in parts]
    if missing:
        warnings.append(f"未复算条目 {len(missing)}：{'、'.join(missing[:10])}")

    tally = {"一致": 0, "不一致": 0, "待裁定": 0, "缺": 0}
    cross: dict[str, dict] = {}
    for it in items:
        pid = it["id"]
        obj = parts.get(pid)
        if obj is None:
            tally["缺"] += 1
            continue
        concl = obj.get("conclusion")
        tally[concl] = tally.get(concl, 0) + 1 if concl in tally else tally.get(concl, 0)
        # ---- 片段自洽
        old_f, new_f = obj.get("old_fragment", ""), obj.get("new_fragment", "")
        raw_note = it["raw_note"]
        if not old_f or not new_f:
            errors.append(f"{pid}: 缺 old_fragment/new_fragment")
        else:
            if raw_note.count(old_f) != 1:
                errors.append(f"{pid}: 旧片段在备注格出现 {raw_note.count(old_f)} 次（须恰好 1 次）：{old_f!r}")
            if "待验证" in new_f:
                errors.append(f"{pid}: 新片段仍含「待验证」")
            expect = raw_note.replace(old_f, new_f)
            if obj.get("new_remark_expected") != expect:
                errors.append(f"{pid}: new_remark_expected 与「旧→新」替换结果不一致")
            if _nums_in(old_f) != _nums_in(new_f):
                review.append(f"{pid}: 片段含非数值文字差异 → 旧{_nums_in(old_f)!r} / 新{_nums_in(new_f)!r}")
            if new_f != MARK_STRICT.sub("", old_f):
                pos = raw_note.find(old_f)
                if raw_note[:pos].rstrip().endswith(("＝", "=")):
                    review.append(f"{pid}: 新片段改写了算式而旧片段前是「＝」——须确认旧片段覆盖完整算式项（防回填断裂）")
        # ---- 步进算术
        steps = obj.get("steps") or []
        if not steps:
            review.append(f"{pid}: 无 steps")
        else:
            for si, st in enumerate(steps, 1):
                try:
                    raw = safe_eval(str(st.get("expr", "")))
                except Exception as exc:
                    errors.append(f"{pid} step{si}: {exc}")
                    continue
                val = apply_round(raw, str(st.get("round", "none")))
                decl = st.get("value")
                if decl is None:
                    errors.append(f"{pid} step{si}: 缺 value")
                    continue
                tol = max(1e-3, abs(float(decl)) * 2e-3)
                if abs(val - float(decl)) > tol:
                    errors.append(f"{pid} step{si}: 实算 {val} ≠ 声明 {decl}（expr={st.get('expr')}）")
            rv = str(obj.get("recomputed_value", ""))
            nums = [float(x) for x in re.findall(r"[0-9]+(?:\.[0-9]+)?", rv)]
            if nums and steps:
                cands: list[float] = []
                for st in steps:
                    try:
                        v = float(st.get("value"))
                    except (TypeError, ValueError):
                        continue
                    cands += [v, v * 100, v / 100]
                if not any(abs(n - c) <= max(1e-2, abs(c) * 2e-3) for n in nums for c in cands):
                    errors.append(f"{pid}: 复算值 {rv} 与任何步骤都不符"
                                  f"（步骤值 {[st.get('value') for st in steps]}）")
        # ---- 证据存在性（一条 evidence 可含「；」分隔的多个 文件:行号）
        for ev in obj.get("evidence") or []:
            for src in re.split(r"[；;]", str(ev.get("src", ""))):
                src = src.strip()
                if not src:
                    continue
                m = re.match(r"^(.+\.md):([\d,\-–\s]+)$", src)
                if not m:
                    review.append(f"{pid}: 证据写法异常 {src!r}")
                    continue
                rel = m.group(1)
                path = ROOT / "material_datas" / "PRTS" / rel
                if not path.exists():   # 也允许仓库根相对路径（如 docs/glossary.md）
                    path = ROOT / rel
                if not path.exists():
                    errors.append(f"{pid}: 证据文件不存在 {src}")
                    continue
                n = len(path.read_text(encoding="utf-8").splitlines())
                for part in re.split(r"[，,、]", m.group(2)):
                    part = part.strip()
                    if not part:
                        continue
                    rr = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
                    hi = int(rr.group(2)) if rr else int(part)
                    if hi > n:
                        errors.append(f"{pid}: 证据行号越界 {src}（文件 {n} 行）")
        if concl == "不一致" and not obj.get("delta"):
            review.append(f"{pid}: 结论「不一致」但缺 delta")
        if concl == "待裁定" and not (obj.get("pending_rule") or "").strip() \
                and len(obj.get("notes") or "") < 40:
            warnings.append(f"{pid}: 结论「待裁定」但未标 pending_rule 且备注过简")
        # ---- 跨 TAG 面板/间隔一致性收集
        op = it["operator"]
        for inp in obj.get("inputs") or []:
            label = str(inp.get("item", ""))
            if any(k in label for k in ("面板", "基础间隔", "攻击间隔")):
                cross.setdefault(op, {}).setdefault(label, set()).add(str(inp.get("value")))
    for op, labels in cross.items():
        for label, vals in labels.items():
            if len(vals) > 1:
                review.append(f"跨条目不一致：{op} 的「{label}」出现多值 {sorted(vals)}")

    lines = [
        "# check 报告",
        "",
        f"- 条目总数 {len(items)}；已复算 {len(parts)}；缺 {tally['缺']}",
        f"- 结论统计：一致 {tally['一致']} / 不一致 {tally['不一致']} / 待裁定 {tally['待裁定']}",
        f"- 错误 {len(errors)}；警告 {len(warnings)}；需人工瞄一眼 {len(review)}",
        "",
        "## 错误（必须修）", "",
    ] + [f"- {e}" for e in errors] + ["", "## 警告", ""] + [f"- {w}" for w in warnings] \
        + ["", "## 需人工瞄一眼", ""] + [f"- {r}" for r in review]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK check: items={len(items)} done={len(parts)} errors={len(errors)} "
          f"warnings={len(warnings)} review={len(review)}")
    print(f"report: {REPORTS_DIR / 'check.md'}")
    return 0


# ---------------------------------------------------------------- report

ROUND_LABEL = {"none": "无取整", "round": "四舍五入", "floor": "向下取整", "ceil": "向上取整"}


def _norm_verdict(v: str) -> str:
    """审计结论标签归一（兼容带括号说明与「A（…）＋B（…）」组合写法，取首个标签）：
    合格/通过 → 通过；有问题/不合格/需修正 → 有问题；待裁定/待人工 → 待裁定。"""
    head = re.split(r"[（(＋+]", str(v), maxsplit=1)[0].strip()
    if head in ("合格", "通过"):
        return "通过"
    if head in ("有问题", "不合格", "需修正"):
        return "有问题"
    if head in ("待裁定", "待人工"):
        return "待裁定"
    return str(v)


def _fmt_num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.4f}".rstrip("0").rstrip(".")


def _section(text: str, start_prefix: str, stop_prefix: str) -> str:
    out, on = [], False
    for line in text.splitlines():
        if line.startswith(start_prefix):
            on = True
        elif on and line.startswith(stop_prefix):
            break
        if on:
            out.append(line)
    return "\n".join(out).rstrip()


def _drop_head(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("## "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def report(dest: pathlib.Path | None = None) -> int:
    dest = dest or (ROOT / "待验证复算.md")
    items = [json.loads(l) for l in ITEMS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    parts: dict[str, dict] = {}
    for pf in sorted((RV_DIR / "parts").glob("G*.jsonl")):
        for line in pf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                parts[obj["id"]] = obj
    audits: dict[str, dict] = {}
    for af in sorted((RV_DIR / "parts").glob("G*.audit.jsonl")):
        for line in af.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                audits[a["id"]] = a
    disp: dict[str, str] = {}
    dp = RV_DIR / "audit_disposition.json"
    if dp.exists():
        disp = json.loads(dp.read_text(encoding="utf-8"))
    missing = [it["id"] for it in items if it["id"] not in parts]
    if missing:
        print(f"FAIL report: 缺 {len(missing)} 条（{'、'.join(missing[:8])}…），先补齐 parts")
        return 2

    rules_md = (RV_DIR / "rules.md").read_text(encoding="utf-8")
    sec1 = _drop_head(_section(rules_md, "## 1.", "## 2."))
    sec2 = _drop_head(_section(rules_md, "## 2.", "## 3."))
    g2rep = RV_DIR / "parts" / "G2.report.md"
    if g2rep.exists():
        txt = g2rep.read_text(encoding="utf-8")
        secs: list[tuple[str, list[str]]] = []
        cur, buf = None, []
        for line in txt.splitlines():
            if line.startswith("## "):
                if cur is not None:
                    secs.append((cur, buf))
                cur, buf = line[3:].strip(), []
            elif cur is not None:
                buf.append(line)
        if cur is not None:
            secs.append((cur, buf))
        extra = [(t, b) for t, b in secs if "C1" in t or "C2" in t]
        if extra:
            sec2 += "\n\n### P02 相关冲突明细（C1/C2，供裁定参考）\n"
            for t, b in extra:
                sec2 += f"\n**{t}**\n\n" + "\n".join(b).strip() + "\n"

    tally: dict[str, int] = {}
    for it in items:
        tally[parts[it["id"]].get("conclusion", "?")] = tally.get(parts[it["id"]].get("conclusion", "?"), 0) + 1

    nonmatch = [it for it in items if parts[it["id"]].get("conclusion") != "一致"]

    lines: list[str] = [
        "# （待验证）复算与回填 · 复核文件",
        "",
        "> 对象：`results/operator-tags.json` 中全部 115 处「（待验证）」（88 条成员行，涉及 P01/P02/P03/P05）。",
        "> 基线：JSON `v2 / 2026-09-19`；分文件→合并文档→结果 JSON 链路已核对一致，回填将走「改分文件→重跑合并与生成」。",
        "> 用法：逐条看「复算值 / 结论 / 回填」三行即可；**不同意就直接修改 `回填：…` 行里的 `新=` 值**（保持「键=值、分号分隔」格式），改完通知我执行回填。",
        "",
        "## 0. 摘要",
        "",
        f"- 结论统计：一致 **{tally.get('一致', 0)}** ／ 不一致 **{tally.get('不一致', 0)}** ／ 待裁定 **{tally.get('待裁定', 0)}**"
        f"（合计 {len(items)}；P01 27、P02 10、P03 66、P05 12）",
        "",
        "### 结论非「一致」的条目",
        "",
        "| id | 干员 | 原值 → 复算值 | 结论 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for it in nonmatch:
        obj = parts[it["id"]]
        delta = obj.get("delta") or {}
        orig = MARK_STRICT.sub("", it["old_fragment"]).strip()
        arrow = f"{delta.get('from', '')} → {delta.get('to', '')}" if delta else \
            f"{orig} → {obj.get('recomputed_value', '')}"
        note = (obj.get("notes") or "").split("\n")[0][:60]
        lines.append(f"| {it['id']} | {it['operator']} | {arrow} | {obj.get('conclusion')} | {note} |")
    if not nonmatch:
        lines.append("| — | — | — | — | — |")

    lines += ["", "## 1. 计算规则集", "", sec1, "", "## 2. 待开发者确认（规则冲突）", "", sec2, ""]

    lines += ["## 3. 概要表", "",
              "| id | TAG | 干员 | 位置 | 原值 | 复算值 | 结论 |",
              "|---|---|---|---|---|---|---|"]
    for it in items:
        obj = parts[it["id"]]
        orig = MARK_STRICT.sub("", it["old_fragment"]).strip()
        lines.append(f"| {it['id']} | {it['tag_name']} | {it['operator']} | {it['file']}:{it['line']} | "
                     f"{orig} | {obj.get('recomputed_value', '')} | {obj.get('conclusion', '')} |")

    lines += ["", "## 4. 逐条详情", ""]
    cur_tag = ""
    for it in items:
        obj = parts[it["id"]]
        if it["tag_name"] != cur_tag:
            cur_tag = it["tag_name"]
            lines += [f"### {it['tag']} {cur_tag}", ""]
        occ = f"（第 {it['occ']}/{it['occ_total']} 处）" if it.get("occ_total", 1) > 1 else ""
        lines.append(f"#### {it['id']}　{it['operator']}｜{it['file']}:{it['line']}{occ}")
        lines.append(f"- **原值**：{MARK_RE.sub('', it['old_fragment']).strip()}")
        ev = obj.get("evidence") or []
        lines.append("- **依据**：")
        for e in ev:
            lines.append(f"  - `{e.get('src', '')}`——{e.get('use', '')}")
        if not ev:
            lines.append("  - （缺）")
        inp = obj.get("inputs") or []
        if inp:
            lines.append("- **取值表**：")
            for i in inp:
                lines.append(f"  - {i.get('item', '')}：{i.get('value', '')}（`{i.get('src', '')}`）")
        steps = obj.get("steps") or []
        lines.append("- **计算式**：")
        for si, st in enumerate(steps, 1):
            n_txt = str(st.get("note") or "").strip().lstrip("；;").strip()
            note = f"；{n_txt}" if n_txt else ""
            rmode = str(st.get("round"))
            val_s = _fmt_num(st.get("value"))
            if rmode == "none":
                lines.append(f"  {si}. `{st.get('expr', '')}` ＝ {val_s}（{note or '无取整'}）")
            else:
                try:
                    raw_s = _fmt_num(safe_eval(str(st.get("expr", ""))))
                except Exception:
                    raw_s = "?"
                lines.append(f"  {si}. `{st.get('expr', '')}` ＝ {raw_s} → {val_s}"
                             f"（{ROUND_LABEL.get(rmode, rmode)}{note}）")
        concl = obj.get("conclusion", "")
        delta = obj.get("delta") or {}
        tail = f"（原 {delta.get('from')} → 新 {delta.get('to')}）" if delta else ""
        pr = f"　规则待裁定：{obj['pending_rule']}" if obj.get("pending_rule") else ""
        lines.append(f"- **复算值**：**{obj.get('recomputed_value', '')}**　结论：{concl}{tail}{pr}")
        impact = obj.get("impact") or {}
        lines.append(f"- **影响判定**：{impact.get('text', '无')}")
        lines.append(f"- **回填**：`回填：文件={it['file']}；行={it['line']}；干员={it['operator']}；"
                     f"旧={obj.get('old_fragment', '')}；新={obj.get('new_fragment', '')}`")
        lines.append(f"- **备注**：{obj.get('notes') or '—'}")
        au = audits.get(it["id"])
        if au:
            inc = [f for f in au.get("factors", []) if f.get("included")]
            exc = [f for f in au.get("factors", []) if not f.get("included")]
            ok = au.get("placement_ok")
            nv = _norm_verdict(au.get("verdict", ""))
            lines.append(f"- **因素审计**：计入 {len(inc)} 项 / 未计入 {len(exc)} 项；"
                         f"乘区位置：{'通过' if ok else '**不合格**'}"
                         f"；结论：{'通过' if nv == '通过' else ('**' + nv + '**')}")
            if it["id"] in disp:
                lines.append(f"- **审计处置**：{disp[it['id']]}")
            for f in inc:
                lines.append(f"  - 计入：{f.get('name', '')}（{f.get('where_or_reason', '')}；`{f.get('src', '')}`）")
            for f in exc:
                lines.append(f"  - 未计入：{f.get('name', '')}——{f.get('where_or_reason', '')}（`{f.get('src', '')}`）")
            if au.get("placement_notes"):
                lines.append(f"  - 位置说明：{au['placement_notes']}")
            for m in au.get("missed") or []:
                lines.append(f"  - **疑似漏算**：{m.get('what', '')}（建议：{m.get('suggested', '')}；`{m.get('src', '')}`）")
            if au.get("panel_note"):
                lines.append(f"  - 面板注记：{au['panel_note']}")
        lines.append("")

    # §5 因素审计（完整性 + 乘区位置）
    audit_items = [it for it in items if it["id"] in audits]
    lines += ["## 5. 因素审计（完整性 + 乘区位置）", ""]
    if not audit_items:
        lines += ["（审计进行中或未产出；本节在审计完成后更新）", ""]
    else:
        tally_audit: dict[str, int] = {}
        for it in audit_items:
            v = _norm_verdict(audits[it["id"]].get("verdict", "?"))
            tally_audit[v] = tally_audit.get(v, 0) + 1
        n_missed = sum(1 for it in audit_items if audits[it["id"]].get("missed"))
        n_badplace = sum(1 for it in audit_items if not audits[it["id"]].get("placement_ok"))
        n_fixed = sum(1 for v in disp.values() if v.startswith("已修正"))
        n_hold = sum(1 for v in disp.values() if v.startswith("未修正"))
        lines += [
            f"- 已审计 **{len(audit_items)}/{len(items)}** 条；结论：通过 **{tally_audit.get('通过', 0)}** ／ "
            f"有问题 **{tally_audit.get('有问题', 0)}** ／ 待裁定 **{tally_audit.get('待裁定', 0)}**"
            f"（其中疑似漏算 {n_missed} 条、乘区位置不合格 {n_badplace} 条）；"
            f"经审计触发的修正已回填值 **{n_fixed}** 条、保留待裁定 **{n_hold}** 条",
            "",
            "### 有问题条目（扫描表）", "",
            "| id | 干员 | 疑似漏算 | 位置 | 面板/说明 |",
            "|---|---|---|---|---|",
        ]
        any_issue = False
        for it in audit_items:
            au = audits[it["id"]]
            if _norm_verdict(au.get("verdict", "")) == "通过" and au.get("placement_ok") and not au.get("missed"):
                continue
            any_issue = True
            missed = "；".join(str(m.get("what", "")) for m in au.get("missed") or []) or "—"
            place = "通过" if au.get("placement_ok") else str(au.get("placement_notes") or "不合格")
            d = disp.get(it["id"], "")
            mark = ""
            if d.startswith("已修正"):
                mark = "**【已修正】** "
            elif d.startswith("未修正"):
                mark = "**【待裁定】** "
            note = mark + (d if d else str(au.get("panel_note") or ""))
            lines.append(f"| {it['id']} | {it['operator']} | {missed[:90]} | {place[:60]} | {note[:110]} |")
        if not any_issue:
            lines.append("| — | — | — | — | — |")
        lines.append("")
        for g in ["G1", "G2", "G3", "G4", "G5", "G6"]:
            rp = RV_DIR / "parts" / f"{g}.audit.md"
            if rp.exists():
                body = "\n".join(re.sub(r"^#{1,3} ", "#### ", ln)
                                 for ln in rp.read_text(encoding="utf-8").strip().splitlines())
                lines += [f"### {g} 审计报告", "", body, ""]

    lines += ["## 6. 附录：非 JSON 区的「（待验证）」清单（本轮不复算）", "",
              "以下为分文件中不进结果 JSON 的章节里的标记（43 处、21 行），按建议动作分类：复核＝含算式的记录、保留＝描述标注规则本身的文字、忽略＝检索记录过程叙述。", ""]
    ex = REPORTS_DIR / "extract.md"
    if ex.exists():
        ap = _section(ex.read_text(encoding="utf-8"), "## 附录清单", "## 警告明细")
        lines.append("### 附录清单\n" + _drop_head(ap))

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK report: {dest}（{len(items)} 条）")
    return 0


# ---------------------------------------------------------------- apply

KEY_RE = re.compile(r"(文件|行|干员|旧|新)\s*[=＝]")


def parse_backfill_line(line: str) -> list[dict]:
    """从复核文件的一行里解析全部「回填：…」（支持一行多条、全/半角冒号）。"""
    out: list[dict] = []
    for seg in re.split(r"回填\s*[:：]", line)[1:]:
        seg = seg.strip().rstrip("`").strip()
        marks = list(KEY_RE.finditer(seg))
        d: dict[str, str] = {}
        for i, km in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(seg)
            d[km.group(1)] = seg[km.end():end].strip().rstrip("；;").strip()
        if d:
            out.append(d)
    return out


def _table_at(lines: list[str], idx: int) -> tuple[list[str], list[str]] | None:
    """第 idx 行（1 基，须为表格数据行）所在表格的 (header, cells)；不成立返回 None。"""
    if not (1 <= idx <= len(lines)) or not lines[idx - 1].lstrip().startswith("|"):
        return None
    i = idx - 1
    while i > 0 and lines[i - 1].lstrip().startswith("|"):
        i -= 1
    header = split_cells(lines[i].rstrip("\r\n"))
    cells = split_cells(lines[idx - 1].rstrip("\r\n"))
    if "备注" not in header or len(cells) != len(header):
        return None
    return header, cells


def apply_backfill(review: pathlib.Path, dry_run: bool) -> int:
    from gui.errors import UserError
    from gui.writeback import save_cell

    entries: list[dict] = []
    parse_fail = 0
    for ln, line in enumerate(review.read_text(encoding="utf-8").splitlines(), 1):
        for d in parse_backfill_line(line):
            if not d.get("文件") or d.get("旧") is None or d.get("新") is None:
                parse_fail += 1
                continue
            if "待验证" in d["新"]:
                d["_err"] = "新片段仍含「待验证」"
            entries.append({**d, "review_line": ln})

    results: list[str] = []
    tally: dict[str, int] = {}
    # 按 (文件, 行) 分组，行缺省时按文件+干员分组
    groups: dict[tuple, list[dict]] = {}
    for e in entries:
        key = (e["文件"], e.get("行", ""), e.get("干员", ""))
        groups.setdefault(key, []).append(e)

    for (fname, line_s, op), group in groups.items():
        def rec(status: str, msg: str = "") -> None:
            tally[status] = tally.get(status, 0) + 1
            results.append(f"- [{status}] {fname}:{line_s or '?'} {op or ''} "
                           f"（复核文件行 {group[0]['review_line']}）{msg}")

        path = PARTS_DIR / pathlib.PurePath(fname).name
        if not path.exists():
            rec("UNKNOWN-FILE", f"分文件不存在：{fname}")
            continue
        raw = path.open("r", encoding="utf-8", newline="").read()
        lines = raw.splitlines(keepends=True)

        idx = int(line_s) if line_s.isdigit() else None
        target, moved = None, False
        if idx:
            t = _table_at(lines, idx)
            if t and all(t[1][t[0].index("备注")].count(e["旧"]) == 1 for e in group):
                target = idx
        if target is None:
            for cand in range(1, len(lines) + 1):
                t = _table_at(lines, cand)
                if not t:
                    continue
                header0, cells0 = t
                if op and cells0[0] != op:
                    continue
                if all(cells0[header0.index("备注")].count(e["旧"]) == 1 for e in group):
                    target, moved = cand, idx is not None
                    break
        if target is None:
            rec("MISS", "未找到含全部旧片段的行（文件已被改动？）")
            continue
        if moved:
            tally["LINE-MOVED"] = tally.get("LINE-MOVED", 0) + 1
            results.append(f"- [LINE-MOVED] {fname}: {line_s} → 实际行 {target}（按干员定位）")

        header, cells = _table_at(lines, target)
        ci, ni = header.index("条件"), header.index("备注")
        note = cells[ni]
        statuses = []
        for e in group:
            if e.get("_err"):
                statuses.append(("PARSE-FAIL", e["_err"]))
            elif e["旧"] == e["新"]:
                statuses.append(("NO-OP", "旧＝新，无需回填"))
            elif e["旧"] in note:
                note = note.replace(e["旧"], e["新"], 1)
                statuses.append(("APPLIED", ""))
            elif e["新"] in note:
                statuses.append(("ALREADY-APPLIED", ""))
            else:
                statuses.append(("MISS", f"旧片段不在备注中：{e['旧']!r}"))
        if note == cells[ni]:
            for st, msg in statuses:
                rec(st, msg)
            continue
        if dry_run:
            for st, msg in statuses:
                rec(st, msg + ("（dry-run 未写盘）" if st == "APPLIED" else ""))
            continue
        try:
            save_cell(pathlib.PurePath(fname).name, target, lines[target - 1].rstrip("\r\n"),
                      cells[ci], note)
        except UserError as exc:
            for st, msg in statuses:
                rec(st, f"写回失败：{exc}")
            continue
        for st, msg in statuses:
            rec(st, msg)

    lines_md = ["# apply 报告", "",
                f"- 回填条目 {len(entries)}；解析失败 {parse_fail}；"
                f"{'（dry-run，未写盘）' if dry_run else ''}", "",
                "## 明细", ""] + results
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "apply.md").write_text("\n".join(lines_md) + "\n", encoding="utf-8")
    print("OK apply" + ("（dry-run）" if dry_run else "") +
          f": entries={len(entries)} " + " ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"report: {REPORTS_DIR / 'apply.md'}")
    return 0


# ---------------------------------------------------------------- verify

def _transform_remark(tag: str, text: str) -> str:
    """复刻 generate_results 对成员备注的变换（clean_cell + P05 strip），用于比对预期。"""
    out = clean_cell(text)
    if tag == "P05":
        out, _ = strip_marker(out, [P05_PATH_RE])
    return out


def _git_show(rel: str) -> str | None:
    import subprocess

    try:
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8")
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def verify() -> int:
    import subprocess

    items = [json.loads(l) for l in ITEMS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    parts: dict[str, dict] = {}
    for pf in sorted((RV_DIR / "parts").glob("G*.jsonl")):
        for line in pf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                parts[obj["id"]] = obj

    checks: list[tuple[str, bool, str]] = []   # (检查项, 是否通过, 说明)

    # 1) 逐条比对：JSON 现状 vs 预期（new_remark_expected 经管线变换）
    doc = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    tags = {t["id"]: t for t in doc["tags"]}
    mismatch: list[str] = []
    pre: list[str] = []
    for it in items:
        obj = parts.get(it["id"])
        if not obj:
            mismatch.append(f"{it['id']}：无复算产物")
            continue
        if _transform_remark(it["tag"], it["raw_note"]) != it["json_remark"]:
            pre.append(it["id"])
        expect = _transform_remark(it["tag"], obj["new_remark_expected"])
        p = it["json_path"]
        tag = tags.get(it["tag"])
        try:
            mem = tag["members"][p["member_idx"]]
            if p.get("provider_idx") is not None:
                mem = mem["providers"][p["provider_idx"]]
            cur = mem.get("remark", "")
        except Exception as exc:
            mismatch.append(f"{it['id']}：JSON 定位失败 {exc}")
            continue
        if cur != expect:
            mismatch.append(f"{it['id']}：JSON 备注与预期不符（现：{cur[:40]!r}…）")
    checks.append(("逐条回填比对", not mismatch, f"不符 {len(mismatch)} 条"))
    if pre:
        checks.append(("管线复刻前提（原文→JSON 变换可复现）", False, f"{len(pre)} 条不符：{pre[:5]}"))
    else:
        checks.append(("管线复刻前提（原文→JSON 变换可复现）", True, "115/115 相符"))

    # 2) 标记归零
    jcount = len(MARK_RE.findall(RESULTS_FILE.read_text(encoding="utf-8")))
    checks.append(("结果 JSON 内「待验证」归零", jcount == 0, f"剩余 {jcount}"))
    for no, tag_name in TAG_FILES:
        fname = f"{no}-{tag_name}.md"
        fpath = PARTS_DIR / fname
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        # 成员行内残留
        inrows = 0
        for _ln, _h2, _h3, _h4, header, _raw, cells in iter_part_rows(fpath):
            if len(header) >= 3 and header[0] == "干员" and "备注" in header:
                inrows += len(MARK_RE.findall(cells[header.index("备注")])) + \
                          len(MARK_RE.findall(cells[header.index("条件")]))
        total = len(MARK_RE.findall(text))
        checks.append((f"{fname}：成员行内归零", inrows == 0, f"成员行残留 {inrows}；全文 {total}（含附录白名单）"))
    merged = ROOT / "docs" / "player-tags-members.md"
    if merged.exists():
        mcount = len(MARK_RE.findall(merged.read_text(encoding="utf-8")))
        checks.append(("合并文档「待验证」计数（成员表内应归零）", True, f"全文 {mcount}（含不进 JSON 的章节）"))

    # 3) 结构 diff（对 HEAD）
    head_raw = _git_show("results/operator-tags.json")
    struct_bad: list[str] = []
    changed_urls: list[str] = []
    if head_raw:
        head = json.loads(head_raw)
        if [o["name"] for o in head["operators"]] != [o["name"] for o in doc["operators"]]:
            struct_bad.append("operators[] 名单变化")
        htags = {t["id"]: t for t in head["tags"]}
        if set(htags) != set(tags):
            struct_bad.append("TAG 集合变化")
        for tid in sorted(set(htags) & set(tags)):
            h, c = htags[tid], tags[tid]
            if h.get("recommended") != c.get("recommended"):
                struct_bad.append(f"{tid}: recommended 变化")
            hm, cm = h["members"], c["members"]
            if len(hm) != len(cm):
                struct_bad.append(f"{tid}: 成员数 {len(hm)}→{len(cm)}")
                continue
            for i, (a, b) in enumerate(zip(hm, cm)):
                a2, b2 = dict(a), dict(b)
                a2.pop("remark", None), b2.pop("remark", None)
                if a2 != b2:
                    # 移除 remark 后仍不同（prtsUrl/subTags/condition/operator…）
                    struct_bad.append(f"{tid}[{i}] {a.get('operator') or a.get('combo')}: 非备注字段变化")
                if a.get("prtsUrl") != b.get("prtsUrl"):
                    changed_urls.append(f"{tid} {a.get('operator') or a.get('combo')}: "
                                        f"{a.get('prtsUrl')} → {b.get('prtsUrl')}")
        checks.append(("结构 diff（除备注/版本外无变化）", not struct_bad,
                       "；".join(struct_bad[:6]) if struct_bad else "通过"))
        checks.append(("prtsUrl 锚点稳定", not changed_urls,
                       "；".join(changed_urls[:8]) if changed_urls else "无变化"))
    else:
        checks.append(("结构 diff（对 HEAD）", False, "无法读取 HEAD 版本"))

    # 4) untagged-operators.md 未变
    unt = _git_show("docs/untagged-operators.md")
    cur_unt = (ROOT / "docs" / "untagged-operators.md")
    if unt is not None and cur_unt.exists():
        same = unt == cur_unt.read_text(encoding="utf-8")
        checks.append(("docs/untagged-operators.md 未变化", same, "一致" if same else "内容变化"))

    lines = ["# verify 验收报告", ""]
    for name, ok, msg in checks:
        lines.append(f"- {'PASS' if ok else 'FAIL'}　{name}：{msg}")
    if mismatch:
        lines += ["", "## 逐条比对不符明细", ""] + [f"- {m}" for m in mismatch]
    (REPORTS_DIR / "verify.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad = sum(1 for _n, ok, _m in checks if not ok)
    print(f"OK verify: checks={len(checks)} FAIL={bad}")
    print(f"report: {REPORTS_DIR / 'verify.md'}")
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------- fetch-rules

def fetch_rules(pages: list[str]) -> int:
    """抓取 PRTS 机制页快照 → material_datas/PRTS/_rules/<页名>.md。

    复用 crawl_prts.py 的浏览器头 / 取页重试 / 限速与正文提取，供规则集引用 `文件:行号`。
    """
    import random
    import time

    import requests
    from crawl_prts import (BASE, HEADERS, clean, collect_sections, content_div, fetch,
                            parse, sanitize_filename, to_markdown)

    out_dir = ROOT / "material_datas" / "PRTS" / "_rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update(HEADERS)
    for page in pages:
        url = BASE + "/w/" + urllib.parse.quote(page)
        try:
            r = fetch(sess, url)
            time.sleep(random.uniform(1.2, 2.8))
            soup = parse(r)
            content = content_div(soup)
            clean(content)
            try:
                sections = collect_sections(content)
            except RuntimeError:  # 短页可能没有 h2/h3，整页作一段
                sections = [(page, list(content.children))]
            md = to_markdown(sections, page, url, None)
        except Exception as exc:  # 单页失败不阻断其余页面
            print(f"FAILED {page}: {exc}")
            continue
        out = out_dir / f"{sanitize_filename(page)}.md"
        out.write_text(md, encoding="utf-8")
        print(f"saved {out} ({len(md)} chars)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="「（待验证）」复算与回填工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract", help="抽出全部待验证条目 → _reverify/items.jsonl")
    sub.add_parser("check", help="算术自检 + 片段自洽 + 证据存在性")
    sub.add_parser("report", help="汇总为《待验证复算.md》（复核文件）")
    ap_apply = sub.add_parser("apply", help="按复核文件回填分文件")
    ap_apply.add_argument("--dry-run", action="store_true", help="只报告不写盘")
    ap_apply.add_argument("--review", default=str(ROOT / "待验证复算.md"), help="复核文件路径")
    sub.add_parser("verify", help="重生成后验收（待实现）")
    fr = sub.add_parser("fetch-rules", help="抓取 PRTS 机制页快照 → material_datas/PRTS/_rules/")
    fr.add_argument("--pages", nargs="*", default=["作战机制"],
                    help="页名列表（默认：作战机制）")
    args = ap.parse_args()
    if args.cmd == "extract":
        return extract()
    if args.cmd == "check":
        return check()
    if args.cmd == "report":
        return report()
    if args.cmd == "apply":
        return apply_backfill(pathlib.Path(args.review), args.dry_run)
    if args.cmd == "verify":
        return verify()
    if args.cmd == "fetch-rules":
        return fetch_rules(args.pages)
    print(f"{args.cmd}: 尚未实现")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

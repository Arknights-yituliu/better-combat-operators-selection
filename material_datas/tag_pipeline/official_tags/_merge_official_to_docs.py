# -*- coding: utf-8 -*-
"""把 official_tags/ 下的官方设定 TAG 分模块合入 docs/official-tags-members.md。

- §4 TAG 详情：由本目录 13 个分模块按序重建（定义行括号内「N 人 · 首现」自动重算）。
- §3 总览：各类别 TAG 数与关系数自动重算；正文两处总数（头部校验目标、§3 标题）同步。
- §5 时间线：按各 TAG 的「首现」日期重建。
- 其余章节（§1/§2/§6/§7/§8/§9 等）原样保留；成员表按实装时间倒序（同日期保持文件内相对序）。

用法：.venv/Scripts/python.exe -X utf8 _merge_official_to_docs.py [--check]
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DOC = os.path.join(ROOT, "docs", "official-tags-members.md")
DATES = json.load(open(os.path.join(ROOT, "material_datas", "tag_pipeline",
                                    "player_tags", "_launch_dates.json"), encoding="utf-8"))

FILES = [
    ("A 控制·异常（对敌施加）", ["A-控制异常-1.md", "A-控制异常-2.md", "A-控制异常-3.md"]),
    ("B 伤害类型", ["B-伤害类型.md"]),
    ("C 生存与增益（自身/友方/召唤物）", ["C-生存与增益-1.md", "C-生存与增益-2.md", "C-生存与增益-3.md"]),
    ("D 部署与编队", ["D-部署与编队.md"]),
    ("E 技力与技能资源", ["E-技力与技能资源.md"]),
    ("F 治疗与支援", ["F-治疗与支援.md"]),
    ("G 召唤物", ["G-召唤物.md"]),
    ("H 攻击行为特征", ["H-攻击行为特征.md"]),
    ("I 全场光环（全场持续效果）", ["I-全场光环.md"]),
]

DEF_RE = re.compile(r"^\*\*(?P<name>.+)\*\*（\d+ 人 · 首现 [\d-]+）：(?P<rest>.*)$")
DEF_FALLBACK = re.compile(r"^\*\*(?P<name>.+)\*\*（.*?）：(?P<rest>.*)$")
SEP_RE = re.compile(r"^\|[\s:|-]+\|$")

warnings = []


def date_of(name):
    name = name.strip()
    if name in DATES:
        return DATES[name]
    base = re.split(r"[（(]", name)[0].strip()
    return DATES.get(base)


def parse_file(fname):
    path = os.path.join(HERE, fname)
    lines = open(path, encoding="utf-8").read().splitlines()
    entries = []
    cur = None
    for ln in lines:
        s = ln.strip()
        m = DEF_RE.match(s) or DEF_FALLBACK.match(s)
        if m:
            cur = {"name": m.group("name"), "rest": m.group("rest"),
                   "notes": [], "rows": []}
            entries.append(cur)
        elif cur is not None and s.startswith(">"):
            if s:
                cur["notes"].append(s)
        elif cur is not None and s.startswith("|"):
            if SEP_RE.match(s) or s.startswith("| 干员"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) != 3:
                warnings.append(f"{fname}: 单元格数 {len(cells)} ≠ 3：{s[:60]}")
                continue
            cur["rows"].append(cells)
        # 其它行（标题/空行/说明）忽略
    return entries


def build_category(cat, fnames):
    entries = []
    for fn in fnames:
        entries.extend(parse_file(fn))
    out_lines = []
    stat = []
    for e in entries:
        rows = e["rows"]
        dated = []
        for i, (op, cond, rem) in enumerate(rows):
            d = date_of(op)
            if d is None:
                warnings.append(f"{cat}｜{e['name']}: 成员「{op}」无实装时间（保持原位）")
            dated.append((d, i, op, cond, rem))
        known = [t for t in dated if t[0] is not None]
        unknown = [t for t in dated if t[0] is None]
        known.sort(key=lambda t: t[0], reverse=True)  # 稳定排序：同日保持文件内相对序
        ordered = known + unknown
        first = min((t[0] for t in known), default=None)
        n = len(rows)
        out_lines.append(f"**{e['name']}**（{n} 人 · 首现 {first or '—'}）：{e['rest']}")
        out_lines.append("")
        for note in e["notes"]:
            out_lines.append(note)
        if e["notes"]:
            out_lines.append("")
        out_lines.append("| 干员 | 条件 | 备注 |")
        out_lines.append("|---|---|---|")
        for _, _, op, cond, rem in ordered:
            out_lines.append(f"| {op} | {cond} | {rem} |")
        out_lines.append("")
        stat.append((e["name"], n, first))
    return out_lines, stat


def main():
    check_only = "--check" in sys.argv
    text = open(DOC, encoding="utf-8").read()
    lines = text.splitlines()

    # ---- 生成 §4 ----
    sec4, stats = [], []
    for cat, fnames in FILES:
        body, stat = build_category(cat, fnames)
        sec4.append(f"### {cat}")
        sec4.append("")
        sec4.extend(body)
        stats.append((cat, stat))

    # ---- §4 替换 ----
    i4 = next(i for i, l in enumerate(lines) if l.startswith("## 4. TAG 详情"))
    i5 = next(i for i, l in enumerate(lines) if l.startswith("## 5. "))
    lines = lines[:i4 + 1] + [""] + sec4 + lines[i5:]

    # ---- 统计 ----
    n_tags = sum(len(s) for _, s in stats)
    n_rel = sum(n for _, s in stats for _, n, _ in s)

    # ---- §5 时间线重建 ----
    tl = {}
    for _, s in stats:
        for name, n, first in s:
            tl.setdefault(first or "—", []).append(name)
    tl_lines = ["| 首现 | TAG |", "|---|---|"]
    tl_dates = sorted([d for d in tl if d != "—"], reverse=True) + (["—"] if "—" in tl else [])
    for d in tl_dates:
        tl_lines.append(f"| {d} | {'、'.join(tl[d])} |")
    i5 = next(i for i, l in enumerate(lines) if l.startswith("## 5. "))
    i6 = next(i for i, l in enumerate(lines) if l.startswith("## 6. "))
    lines = lines[:i5 + 2] + tl_lines + [""] + lines[i6:]

    # ---- §3 总览表重建 ----
    i3 = next(i for i, l in enumerate(lines) if l.startswith("## 3. 总览"))
    i4 = next(i for i, l in enumerate(lines) if l.startswith("## 4. TAG 详情"))
    t3 = ["| 类别 | TAG 数 | TAG×干员关系数 |", "|---|---|---|"]
    for cat, s in stats:
        t3.append(f"| {cat} | {len(s)} | {sum(n for _, n, _ in s)} |")
    j = i3 + 2
    while j < len(lines) and lines[j].startswith("|"):
        j += 1
    lines = lines[:i3 + 2] + t3 + lines[j:i4] + lines[i4:]

    # ---- 两处总数 ----
    joined = "\n".join(lines)
    joined, k1 = re.subn(r"共 \d+ 个 TAG、\d+ 条 TAG×干员关系",
                         f"共 {n_tags} 个 TAG、{n_rel} 条 TAG×干员关系", joined)
    joined, k2 = re.subn(r"：\d+ 个 TAG，\d+ 条 TAG×干员关系",
                         f"：{n_tags} 个 TAG，{n_rel} 条 TAG×干员关系", joined)
    joined, k3 = re.subn(r"共 \d+ 条 TAG×干员关系",
                         f"共 {n_rel} 条 TAG×干员关系", joined)
    if k1 == 0:
        warnings.append("未找到头部总数句（共 X 个 TAG、Y 条…）")
    if k2 == 0:
        warnings.append("未找到 §3 标题总数（：X 个 TAG，Y 条…）")

    # ---- 无 TAG 干员名单收缩 ----
    all_names = set()
    for cat, fnames in FILES:
        for fn in fnames:
            for e in parse_file(fn):
                for op, _, _ in e["rows"]:
                    all_names.add(op)
    m = re.search(r"无 TAG 干员（\d+ 名，([^）]*)）：([^\n]+)", joined)
    if m:
        names = [x.strip() for x in m.group(2).split("、") if x.strip()]
        kept = [x for x in names if x not in all_names]
        moved = [x for x in names if x in all_names]
        joined = (joined[:m.start()] +
                  f"无 TAG 干员（{len(kept)} 名，{m.group(1)}）：" + "、".join(kept) +
                  joined[m.end():])
        if moved:
            print(f"  无 TAG 名单收缩 {len(names)}→{len(kept)}：移出 " + "、".join(moved))
    else:
        warnings.append("未找到「无 TAG 干员」段")

    print(f"TAG 数 {n_tags}，关系数 {n_rel}")
    for cat, s in stats:
        print(f"  {cat}: {len(s)} TAG / {sum(n for _, n, _ in s)} 关系")
    for w in warnings:
        print("  [warn]", w)
    if check_only:
        return 0
    open(DOC, "w", encoding="utf-8", newline="\r\n").write(joined + "\n")
    print("written", DOC)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""解析 `docs/temp.txt`（PRTS《模组》页表格快照），提取各模组效果格里的「※」条文（隐藏机制），
汇编成 `docs/module-hidden-mechanics.md`（含按干员、按类别两套索引）。

- 源文件是 HTML 片段（MediaWiki 表格 DOM），不是 Markdown——用 stdlib 的 HTMLParser 建一棵小 DOM 再取数。
- 本脚本是**生成物**的产出方：改格式请改本脚本后重跑；不要手改 `docs/module-hidden-mechanics.md`。
- 用法：
    `python -X utf8 tools/module_notes.py --list`     # 只打印统计与条文清单（核对用）
    `python -X utf8 tools/module_notes.py --emit`     # 写出 docs/module-hidden-mechanics.md
    `python -X utf8 tools/module_notes.py --check`    # 只校验（不写盘），输出统计
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from urllib.parse import unquote

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "temp.txt"
OUT = ROOT / "docs" / "module-hidden-mechanics.md"

VOID = {"br", "img", "hr", "meta", "link", "input"}

# 判定「通用注释」的阈值：在 ≥ 该数量的模组里出现、且不指向具体机制 → 单列一节
GENERIC_MIN_MODULES = 3

# 类别索引的关键词表（按序匹配，命中即归；仅供检索，正文为准）
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("距离与射程", ("距离", "格远", "射程")),
    ("寒冷·冻结", ("寒冷", "冻结")),
    ("损伤与爆发", ("损伤", "爆发", "凋亡", "灼燃", "侵蚀", "神经")),
    ("停顿·晕眩·束缚·战栗", ("停顿", "晕眩", "束缚", "战栗", "麻痹", "浮空")),
    ("抵抗与状态时长", ("抵抗", "状态", "持续")),
    ("攻击速度", ("攻击速度", "攻速", "间隔")),
    ("攻击力与伤害", ("攻击力", "伤害")),
    ("防御·法抗·承伤", ("防御", "法抗", "减伤", "受伤", "生命值")),
    ("治疗与回复", ("治疗", "回复", "恢复", "生命上限")),
    ("部署·费用·再部署", ("部署", "费用", "再部署", "技力")),
    ("阻挡与位移", ("阻挡", "推动", "拉动", "位移")),
    ("隐匿·反隐·索敌", ("隐匿", "反隐", "索敌", "嘲讽")),
    ("召唤物与装置", ("召唤物", "装置", "陷阱", "棋子")),
    ("概率与触发", ("概率", "触发", "几率")),
]


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str = "", attrs: dict | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent

    def find_all(self, tag: str | None = None, cls: str | None = None):
        out = []
        for ch in self.children:
            if isinstance(ch, str):
                continue
            if (tag is None or ch.tag == tag) and (cls is None or cls in (ch.attrs.get("class") or "")):
                out.append(ch)
            out.extend(ch.find_all(tag, cls))
        return out

    def text(self) -> str:
        """渲染为纯文本：`<br>` 换行、递归拼接；**跳过 `display:none` 的隐藏子树**（术语弹窗里的 glossary 释义）。"""
        parts = []
        for ch in self.children:
            if isinstance(ch, str):
                parts.append(ch)
            elif ch.tag == "br":
                parts.append("\n")
            elif "display:none" in (ch.attrs.get("style") or "").replace(" ", ""):
                continue
            else:
                parts.append(ch.text())
        return "".join(parts)


class Dom(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def _direct(node: Node, tag: str) -> list[Node]:
    return [c for c in node.children if not isinstance(c, str) and c.tag == tag]


def parse_modules(path: pathlib.Path) -> list[dict]:
    """→ [{op, name, code, levels: {1: [行…], 2: […], 3: […]}}]"""
    dom = Dom()
    dom.feed(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for table in dom.root.find_all("table", "modtable"):
        for tbody in _direct(table, "tbody") or [table]:
            for tr in _direct(tbody, "tr"):
                tds = _direct(tr, "td")
                if len(tds) < 4:
                    continue
                name = code = op = ""
                for img in tds[0].find_all("img"):
                    m = re.search(r"模组_(.+?)\.png", unquote(img.attrs.get("src", "")))
                    if m:
                        name = m.group(1)
                for a in tds[1].find_all("a"):
                    if a.attrs.get("title"):
                        op = a.attrs["title"]
                for img in tds[2].find_all("img"):
                    m = re.search(r"模组类型_([A-Z]{3}-[A-Z])_", unquote(img.attrs.get("src", "")))
                    if m:
                        code = m.group(1)
                levels: dict[int, list[str]] = {}
                for lv_tr in tds[3].find_all("tr"):
                    lv_tds = _direct(lv_tr, "td")
                    if len(lv_tds) < 3:
                        continue
                    lv = None
                    for img in lv_tds[0].find_all("img"):
                        m = re.search(r"模组等级_(\d)\.png", unquote(img.attrs.get("src", "")))
                        if m:
                            lv = int(m.group(1))
                    if lv is None:
                        continue
                    lines = [ln.strip() for ln in lv_tds[2].text().split("\n")]
                    levels[lv] = [ln for ln in lines if ln]
                if op:
                    out.append({"op": op, "name": name or "（未署名）", "code": code or "?", "levels": levels})
    return out


def notes_of(mod: dict, generic: set[str]) -> list[tuple[int, str]]:
    """某模组的 ※ 条文（含通用注释），返回 [(等级, 条文)]，同一模组内去重。"""
    seen, out = set(), []
    for lv in sorted(mod["levels"]):
        for ln in mod["levels"][lv]:
            if ln.startswith("※") and ln not in seen:
                seen.add(ln)
                out.append((lv, ln))
    return out


def classify(note: str) -> str:
    for name, keys in CATEGORIES:
        if any(k in note for k in keys):
            return name
    return "其它"


def main() -> int:
    ap = argparse.ArgumentParser(description="解析 temp.txt 的模组隐藏机制，汇编为 docs/module-hidden-mechanics.md")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="只打印统计与条文清单（核对用）")
    g.add_argument("--emit", action="store_true", help="写出 docs/module-hidden-mechanics.md")
    g.add_argument("--check", action="store_true", help="只统计（默认行为）")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"缺少快照文件：{SRC}")
        print("请从 PRTS《模组》页复制表格 HTML 存为 docs/temp.txt（本地快照，不进库）后重试。")
        return 2

    mods = parse_modules(SRC)
    if not mods:
        print(f"快照里没有解析到模组：{SRC}")
        print("docs/temp.txt 可能不是 PRTS《模组》页表格快照（或已被覆盖），请重新导出后重试。")
        return 2
    all_notes: Counter[str] = Counter()
    by_mod: dict[tuple[str, str], list[tuple[int, str]]] = {}
    mod_of_note: dict[str, set[str]] = defaultdict(set)
    for m in mods:
        ns = [(lv, t) for lv, t in notes_of(m, set()) if not t.startswith("※※")]
        if ns:
            by_mod[(m["op"], m["name"])] = ns
            for _, t in ns:
                all_notes[t] += 1
                mod_of_note[t].add(m["op"])
    generic = {t for t in all_notes if len(mod_of_note[t]) >= GENERIC_MIN_MODULES}

    print(f"模组 {len(mods)} 个 / 干员 {len({m['op'] for m in mods})} 名")
    print(f"含 ※ 的模组 {len(by_mod)} 个 / 干员 {len({k[0] for k in by_mod})} 名")
    print(f"※ 条文 {sum(all_notes.values())} 条 / 去重 {len(all_notes)} 条；通用注释 {len(generic)} 条")

    if args.list:
        print("\n--- 通用注释 ---")
        for t in sorted(generic, key=lambda x: -all_notes[x]):
            print(f"  [{len(mod_of_note[t])} 模组] {t[:120]}")
        print("\n--- 专属条文 ---")
        for t in sorted((x for x in all_notes if x not in generic), key=lambda x: (-all_notes[x], x)):
            print(f"  [{len(mod_of_note[t])}] {t[:130]}")
        return 0

    if not args.emit:
        return 0

    # ---- 生成文档 ----
    by_op: dict[str, list[tuple[str, str]]] = defaultdict(list)  # 干员 → [(模组名, 类型码)]
    for m in mods:
        by_op[m["op"]].append((m["name"], m["code"]))
    cat_index: dict[str, list[tuple[str, int]]] = defaultdict(list)  # 类别 → [(干员·模组, 条数)]
    for (op, name), ns in by_mod.items():
        per_cat: Counter[str] = Counter()
        for _, t in ns:
            if t not in generic:
                per_cat[classify(t)] += 1
        for cat, cnt in per_cat.items():
            cat_index[cat].append((f"{op}·{name}", cnt))

    L: list[str] = []
    L.append("# 模组隐藏机制汇编（各模组「※」条文）")
    L.append("")
    L.append("> 来源：`docs/temp.txt`（PRTS《模组》页表格快照）。**本档为生成物**——由 `tools/module_notes.py --emit` 写出，勿手改。")
    L.append(f"> 覆盖：{len(mods)} 个模组 / {len({m['op'] for m in mods})} 名干员；其中 {len(by_mod)} 个模组带「※」条文、去重后 {len(all_notes)} 条。"
             "**仅含该快照收录的普通模组线（X／Y）**——不含特限证章，也不含该快照缺失的线（如 提丰 的 Y 线）。")
    L.append("> 用法：查某干员的模组隐藏机制 → 「一、按干员索引」；查某类机制出现在哪些模组 → 「二、按类别索引」。"
             "通用术语（虚弱、寒冷、抵抗……）的定义在 `docs/glossary.md`；本档只收**模组效果格里的条文**。")
    L.append("")
    L.append("## 一、按干员索引")
    L.append("")
    L.append("| 干员 | 模组（类型码） | ※ 条数 |")
    L.append("|---|---|---|")
    for op in sorted(by_op):
        cells = []
        for name, code in by_op[op]:
            n = len(by_mod.get((op, name), []))
            cells.append(f"{name}（{code}）" + (f"　※{n}" if n else ""))
        L.append(f"| {op} | {'；'.join(cells)} | {sum(len(by_mod.get((op, nm), [])) for nm, _ in by_op[op])} |")
    L.append("")
    L.append("## 二、按类别索引")
    L.append("")
    L.append("> 类别由关键词自动归入（一条只归一类），**仅供检索**；条文原文以「三、模组条文」为准。")
    L.append("")
    for cat, _ in CATEGORIES:
        items = cat_index.get(cat, [])
        if not items:
            continue
        L.append(f"**{cat}**（{sum(c for _, c in items)} 条）："
                 + "；".join(f"{who}（{c}）" if c > 1 else who for who, c in items))
        L.append("")
    if cat_index.get("其它"):
        items = cat_index["其它"]
        L.append(f"**其它**（{sum(c for _, c in items)} 条）："
                 + "；".join(f"{who}（{c}）" if c > 1 else who for who, c in items))
        L.append("")
    L.append("## 三、模组条文")
    L.append("")
    for op in sorted(by_op):
        for name, code in by_op[op]:
            ns = by_mod.get((op, name))
            if not ns:
                continue
            L.append(f"### {op} · {name}（{code}）")
            L.append("")
            for lv, t in ns:
                L.append(f"- **{lv}级**｜{t}")
            L.append("")
    L.append("## 四、通用注释（跨模组重复出现，供排除误读）")
    L.append("")
    L.append(f"> 在 ≥{GENERIC_MIN_MODULES} 个模组里逐字重复的条文——多为跨模组的通用说明，**不指向某干员的专属机制**；"
             "仍在此列出，避免检索时把它们误当专属机制。")
    L.append("")
    for t in sorted(generic, key=lambda x: (-all_notes[x], x)):
        ops = sorted(mod_of_note[t])
        L.append(f"- **{t}**（{len(ops)} 个模组：{'、'.join(ops[:12])}{'…' if len(ops) > 12 else ''}）")
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}（{len(L)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""把 player_tags/ 下的 9 个分 TAG 产物合并为 docs/player-tags-members.md（v1）。

- 所有 markdown 表格：去掉「依据」列；「干员」列后插入「实装时间」列（PRTS 上线时间）。
- 评定标准 / 成员表 / 边界与排除记录：原文收录；待开发者确认统一收进末尾。
- 只有 09 的「数据结构建议」收录（对 results JSON 设计有用）；检索记录不入正文。
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PARTS = os.path.join(ROOT, "material_datas", "tag_pipeline", "player_tags")
OUT = os.path.join(ROOT, "docs", "player-tags-members.md")

TAGS = [
    ("01", "决战歼灭", "01-决战歼灭.md"),
    ("02", "次数对策", "02-次数对策.md"),
    ("03", "吃拐一轮秒", "03-吃拐一轮秒.md"),
    ("04", "远程消耗", "04-远程消耗.md"),
    ("05", "插拔容错", "05-插拔容错.md"),
    ("06", "初动", "06-初动.md"),
    ("07", "充电", "07-充电.md"),
    ("08", "拐杖", "08-拐杖.md"),
    ("09", "保人", "09-保人.md"),
    ("10", "抗削弱", "10-抗削弱.md"),
    ("11", "大力推拉", "11-大力推拉.md"),
    ("12", "阻挡数5", "12-阻挡数5.md"),
    ("13", "阵容组合", "13-阵容组合.md"),
]

dates = json.load(open(os.path.join(PARTS, "_launch_dates.json"), encoding="utf-8"))


def read(name):
    return open(os.path.join(PARTS, name), encoding="utf-8").read()


def section(text, start, stops):
    lines = text.splitlines()
    out, on = [], False
    for ln in lines:
        if not on and ln.startswith(start):
            on = True
            continue
        if on and any(ln.startswith(s) for s in stops):
            break
        if on:
            out.append(ln)
    return "\n".join(out).strip("\n")


def is_sep_row(cells):
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def date_of(name_cell):
    base = re.split(r"[（(]", name_cell.strip())[0].strip()
    if "、" in base or "，" in base or " " in base:
        return "—"
    return dates.get(base, "—")


def transform_table(rows, sort=False):
    """rows: list[list[str]]；返回处理后的 md 行。sort=True 时按实装时间倒序（无日期者置后）。"""
    header = [c.strip() for c in rows[0]]
    ev = [i for i, c in enumerate(header) if c == "依据"]
    if ev:
        k = ev[-1]
        header = header[:k] + header[k + 1:]
        rows = [r[:k] + r[k + 1:] for r in rows]
    date_col = header and header[0].strip() == "干员"
    if date_col:
        header = [header[0], "实装时间"] + header[1:]
    data = []
    for r in rows[1:]:
        r = [c.strip() for c in r]
        if len(r) > len(header) - (1 if date_col else 0):
            n = len(header) - (1 if date_col else 0)
            r = r[: n - 1] + [" | ".join(r[n - 1:])]
        if date_col:
            d = date_of(r[0])
            r = [r[0], d] + r[1:]
        while len(r) < len(header):
            r.append("—")
        data.append((r[1] if date_col else "", r))
    if sort and date_col:
        data.sort(key=lambda t: (t[0] == "—", t[0]), reverse=False)
        # 有日期者按日期倒序在前，无日期者保持原序置后
        dated = [t for t in data if t[0] != "—"]
        undated = [t for t in data if t[0] == "—"]
        dated.sort(key=lambda t: t[0], reverse=True)
        data = dated + undated
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out.extend("| " + " | ".join(r) + " |" for _, r in data)
    return out


def process(text, sort=False):
    """行级处理：连续表格行成块，转换后输出；其余原样。sort=True 时成员表按实装时间倒序。"""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            raw = [ln.strip().strip("|").split("|") for ln in lines[i:j]]
            if len(raw) >= 2:
                body = [r for k, r in enumerate(raw) if not (k == 1 and is_sep_row(r))]
                seps = [r for r in raw if is_sep_row(r)]
                if not seps:
                    body = raw
                out.extend(transform_table(body, sort=sort))
            else:
                out.extend(lines[i:j])
            i = j
        else:
            out.append(lines[i])
            i += 1
    # 折叠多余空行
    res, prev_blank = [], False
    for ln in out:
        if ln.strip() == "":
            if not prev_blank:
                res.append("")
            prev_blank = True
        else:
            res.append(ln)
            prev_blank = False
    return "\n".join(res)


def pending(text):
    return section(text, "## 待开发者确认", ["## 检索记录", "## 数据结构建议", "## 边界与排除记录"])


def count_members(text):
    seg = section(text, "## 成员表", ["## "])
    if not seg:
        seg = section(text, "## §A", ["## 交叉引用", "## 边界与排除记录"])
    lines = seg.splitlines()
    n, i = 0, 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            rows = [lines[k] for k in range(i, j)]
            data = [r for r in rows if not is_sep_row([c.strip() for c in r.strip().strip("|").split("|")])]
            n += max(0, len(data) - 1)
            i = j
        else:
            i += 1
    return n


def main():
    parts = {name: read(fn) for _, name, fn in TAGS}
    out = []
    out.append("# 玩家体感 TAG 干员名单（v1）")
    out.append("")
    out.append("> 编写：2026-09-10。数据基础：`material_datas/PRTS/`（431 名干员，2026-09-08 抓取，含召唤物页）。")
    out.append("> 本文件是 `docs/player-tags-specify.md`（13 个玩家体感 TAG 定义）的判定结果：每个 TAG 下的干员名单、条件与备注。")
    out.append("> 与 `docs/tags.md`（官方定义类 TAG）互补；逐条 `文件:行号` 证据见 `material_datas/tag_pipeline/player_tags/` 各分文件。")
    out.append("")
    out.append("## 0. 通用评定标准")
    out.append("")
    out.append("- **条件**＝硬性达成条件（精英化、技能、专精、模组及等级、模式限定、目标限制）；精零 1 级即具备者写「无」。")
    out.append("- **备注**＝信息加工后的内容（数值、持续时间、隐藏机制、特殊用法、战术帮助），不写游戏内一眼可见的内容。")
    out.append("- **召唤物/装置效果计入持有干员**；**模式限定模组（ISW-α / RA-α / SO-α 等）计入**，但必须在「条件」中写明、备注注明仅该模式可用（开发者 2026-09-10 评定标准）。")
    out.append("- 名单按**实装时间倒序**（同实装日按拼音序）；实装时间取自 PRTS `获得方式` 上线时间。打数/倍率等数值取专精 3（Rank Ⅲ）数值。**「阵容组合」的组合内成员与各「边界与排除记录」表按判定逻辑分组排列，不按时间序。**")
    out.append("- 判定均为机制层、时间无关（不收「新神/退环境」等当期强度结论）。")
    out.append("")
    out.append("## 总览")
    out.append("")
    out.append("| # | TAG | 主表行数 | 分文件（含证据行号） |")
    out.append("|---|---|---|---|")
    for num, name, fn in TAGS:
        out.append(f"| {num} | {name} | {count_members(parts[name])} | `{fn}` |")
    out.append("")

    for num, name, fn in TAGS:
        text = parts[name]
        out.append(f"## {num}｜{name}")
        out.append("")
        if name == "阵容组合":
            kou = section(text, "## 评定标准", ["## §A"])
            out.append("### 评定标准")
            out.append("")
            out.append(process(kou).strip())
            out.append("")
            body = section(text, "## §A", ["## 边界与排除记录"])
            out.append("### 成员表（按组合）")
            out.append("")
            out.append(process(body).strip())
            out.append("")
            body2 = section(text, "## §B", ["## 边界与排除记录"])
            if body2.strip():
                out.append("### 非阵营型编队联动（官方 D-编队 22 人锚名单补录）")
                out.append("")
                out.append(process(body2).strip())
                out.append("")
            bian = section(text, "## 边界与排除记录", ["## 待开发者确认", "## 检索记录", "## 数据结构建议"])
            out.append("### 边界与排除记录")
            out.append("")
            out.append(process(bian).strip())
            out.append("")
            ds = section(text, "## 数据结构建议", [])
            if ds.strip():
                out.append("### 数据结构建议（供 results JSON 设计参考）")
                out.append("")
                out.append(ds.strip())
                out.append("")
        else:
            kou = section(text, "## 评定标准", ["## "])
            tab = section(text, "## 成员表", ["## "])
            bian = section(text, "## 边界与排除记录", ["## 待开发者确认", "## 检索记录", "## 数据结构建议"])
            out.append("### 评定标准")
            out.append("")
            out.append(process(kou).strip())
            out.append("")
            out.append("### 成员表（按实装时间倒序）")
            out.append("")
            out.append(process(tab, sort=True).strip())
            out.append("")
            out.append("### 边界与排除记录")
            out.append("")
            out.append(process(bian).strip())
            out.append("")

    out.append("## 待开发者确认（按 TAG 汇总）")
    out.append("")
    for num, name, fn in TAGS:
        p = pending(parts[name])
        if p.strip():
            out.append(f"### {name}")
            out.append("")
            out.append(p.strip())
            out.append("")

    out.append("## 附录 A：文档勘误（判定中发现）")
    out.append("")
    out.append("1. `docs/tags.md` §6.4 写的「星熊/可颂 X 模组（阻挡数+1）」实为 **PRO-Y**（星熊.md:374/411、可颂.md:169/198；角峰、暴雨同理为 Y）；`docs/player-tags-specify.md` 的「年 2 技能 Y 模组」与 PRTS 一致。")
    out.append("2. `docs/player-tags-specify.md` 写「号角 **2 天赋**（仅限重装）」，但 PRTS 将「军事要塞」（在场时所有重装干员攻击力+20%）列为**第一天赋**，「血战」为第二天赋（号角/号角.md:56-59,63）。")
    out.append("3. `docs/player-tags.md`（v1 草案）§6.4 把「深海色」列入深海猎人组合，但 PRTS 中深海色所属势力为【阿戈尔】且无【深海猎人】联动文本（深海色/深海色.md:144,154,242），不应计入。")
    out.append("")
    out.append("## 附录 B：与官方定义类 TAG 的互链")
    out.append("")
    out.append("| 玩家体感 TAG | 官方类 TAG / 说明 |")
    out.append("|---|---|")
    out.append("| 远程消耗 | H-全图/全场攻击（蕾缪安、荒芜拉普兰德、澄闪、安比尔）；本 TAG 另含以「越界/全场」原文为依据者 |")
    out.append("| 大力推拉 | A-推拉位移（失衡位移，33 人）；本 TAG 为其力度 ≥ 大力 的子集 |")
    out.append("| 充电 | E-为他人回复技力（17 人）；本 TAG 另补归溟幽灵鲨、海蒂、异客等 |")
    out.append("| 初动 | 无对应官方 TAG（E-为他人回复技力 不含初始技力）；与「充电」互补：初动＝开局/部署时点，充电＝持续回复速度 |")
    out.append("| 抗削弱 | 无对应官方 TAG；保机制下限/提机制上限类（攻速下限、费用下限、弹药上限、技力上限等） |")
    out.append("| 全场光环 | **已转为官方设定 TAG**（见 docs/tags.md 类别 I），不再属玩家体感 TAG |")
    out.append("| 次数对策 | 无对应官方 TAG；与 B-施加中毒/灼烧/流血、H-帧级结算、I-全场光环部分重叠（多对多并存） |")
    out.append("| 阻挡数>=5 | H-阻挡数≥4（官方不设）；遗留第 4 条明确玩家侧以技能/召唤物条件判定 |")
    out.append("| 阵容组合 | D-编队/阵营联动增益（22 人）+ 各阵营实战组合 |")
    out.append("| 保人 | C-庇护/屏障/护盾/闪避/减伤/嘲讽/抵抗、F-元素损伤治疗等 |")
    out.append("")
    out.append("## 附录 C：产物与复现")
    out.append("")
    out.append("- 分 TAG 判定文件（含逐条 `文件:行号` 证据）：`material_datas/tag_pipeline/player_tags/01..09-*.md`。")
    out.append("- 共享作业评定标准：`material_datas/tag_pipeline/player_tags/_brief.md`；实装时间表：`_launch_dates.json`；合并脚本：`_merge_to_docs.py`。")
    out.append("- 官方类 TAG 数据：`docs/tags.md`、`material_datas/tag_pipeline/{final_lists.tsv,merged.json}`。")
    out.append("")

    open(OUT, "w", encoding="utf-8").write("\n".join(out))
    print("written", OUT)


if __name__ == "__main__":
    main()

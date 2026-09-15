# -*- coding: utf-8 -*-
"""生成 results/operator-tags.json（v1）：把两份名单文档合成为最终结果 JSON。

数据来源（docs/output-standard.md §7）：
- docs/official-tags-members.md       官方设定 TAG（81 个，成员表 干员｜编号｜条件｜备注）
- docs/player-tags-members.md        玩家体感 TAG（12 个，含 子 TAG／救急路径 等分组信息）
- material_datas/tag_pipeline/catalog.json                    官方 TAG 字典（名称 → id／类别）
- material_datas/tag_pipeline/char_ids.json                   干员名 → charId
- material_datas/tag_pipeline/player_tags/_launch_dates.json  干员名 → 实装时间
- material_datas/tag_pipeline/player_tags/_recommend.json     玩家 TAG 荐（可缺省）
- material_datas/PRTS/<干员>/<干员>.md                         基本信息（稀有度/职业/分支/势力）
- material_datas/PRTS/<干员>/*.md                              锚点判定用的天赋/技能/模组/召唤物名索引

用法：
    .venv/Scripts/python.exe -X utf8 generate_results.py            # 写 results/operator-tags.json
    .venv/Scripts/python.exe -X utf8 generate_results.py --check    # 只生成到内存并跑规范校验
    .venv/Scripts/python.exe -X utf8 generate_results.py --report   # 打印统计与逐 TAG 计数
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
from gui.md import is_sep_row, split_cells          # noqa: E402
from gui.roster import launch_date, parse_prts_brief  # noqa: E402
from gui import results_json as rj                   # noqa: E402

PRTS_DIR = ROOT / "material_datas" / "PRTS"
PIPE = ROOT / "material_datas" / "tag_pipeline"
OFFICIAL_DOC = ROOT / "docs" / "official-tags-members.md"
PLAYER_DOC = ROOT / "docs" / "player-tags-members.md"
OUT_FILE = ROOT / "results" / "operator-tags.json"

# 官方条目行：**施加恐惧**（5 人 · 首现 2024-07-09）：定义
DEF_RE = re.compile(r"^\*\*(?P<name>.+?)\*\*（(?P<n>\d+) 人 · 首现 (?P<d>[\d-]+)）：")
# 文档里残留的 文件:行号 证据（结果 JSON 不得携带）
EV_RE = re.compile(r"[；，、]?\s*[^（）()；。\s]*\.md:\d[\d,\-–\s]*")
PLAYER_H2_RE = re.compile(r"^## (\d\d)｜(.+)$")

# 锚点判定用的类别名
SRC_SKILL, SRC_TALENT, SRC_MODULE, SRC_TRAIT, SRC_SUMMON = "技能", "天赋", "模组", "特性", "召唤物"
ANCHOR = {SRC_SKILL: "#技能", SRC_TALENT: "#天赋", SRC_MODULE: "#模组",
          SRC_TRAIT: "#特性", SRC_SUMMON: "#召唤物信息"}


# ---------------------------------------------------------------- 基础工具

def clean_cell(text: str) -> str:
    """单元格 → JSON 文本：去 markdown 强调标记、文件:行号 证据与生产文档引用。"""
    text = text.replace("**", "").strip()
    text = EV_RE.sub("", text)
    text = re.sub(r"（\s*[；，、]\s*", "（", text)   # 引用被摘掉后留下的空语气
    text = re.sub(r"[；，、]\s*）", "）", text)
    text = re.sub(r"`([^`]*[./][^`]*)`", r"\1", text)   # 代码标记只用于文档引用 → 去反引号
    # 生产文档引用 → 产品可读表述（结果 JSON 不携带生产文档路径）
    text = re.sub(r"\d\d-([\w一-鿿]+)\.md", r"「\1」TAG", text)
    text = re.sub(r"docs/[\w\-]+\.md( ?§[\d.]+)?", "", text)
    text = re.sub(r"_brief\.md( ?§[\d.]+)?", "", text)
    text = re.sub(r"[，,]?(逐格)?见\s*[\w一-鿿]+/攻击范围\.md", "", text)
    text = re.sub(r"（按\s+", "（", text)
    text = re.sub(r"（\s+", "（", text)
    text = re.sub(r"\s+）", "）", text)
    text = text.replace("（）", "").replace("()", "")
    text = re.sub(r"[（(]\s*[；，]\s*([^）)])", r"（\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def url_of(name: str, anchor: str = "") -> str:
    return "https://prts.wiki/w/" + urllib.parse.quote(name) + anchor


# ---------------------------------------------------------------- 阵容组合（P12）组合级元数据

COMBO_NAME_RE = re.compile(r"A\d+\.\s*(.+)")
COMBO_BULLET_RE = re.compile(r"^- \*\*(触发条件|组合整体机制|可用受益干员)\*\*：(.*)$")


def parse_names(text: str) -> list[str]:
    """「可用受益干员」bullet → 名单数组；不可枚举（带说明文字/路径/超长词）时返回空。

    只认全角「（」与「。」作尾注分隔——干员名里的括号是半角（如 阿米娅(医疗)），不可当分隔符。
    """
    head = re.split(r"[（。]", text, maxsplit=1)[0]
    names = [x.strip() for x in head.split("、") if x.strip()]
    if len(names) < 2 or any(len(n) > 10 or re.search(r"[\s`／/]", n) for n in names):
        return []
    return names


def read_combo_meta(path: pathlib.Path) -> dict[str, dict]:
    """阵容组合：`### A<N>. 组合名` 段里固定三条 bullet → 组合级 condition/remark/beneficiaries。"""
    out: dict[str, dict] = {}
    cur = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            m = COMBO_NAME_RE.match(line[4:].strip())
            cur = m.group(1).strip() if m else ""
            if cur:
                out.setdefault(cur, {})
            continue
        if line.startswith("## "):
            cur = ""
            continue
        if not cur:
            continue
        m = COMBO_BULLET_RE.match(line.strip())
        if not m:
            continue
        label, text = m.group(1), m.group(2).strip()
        if label == "触发条件":
            out[cur]["condition"] = text
        elif label == "组合整体机制":
            out[cur]["remark"] = text
        else:
            names = parse_names(text)
            if names:
                out[cur]["beneficiaries"] = names
    return out


def read_tables(path: pathlib.Path):
    """顺序产出 (h2, h3, h4, header, rows, line_no)：以表头行分组、跳过空行分隔。"""
    lines = path.read_text(encoding="utf-8").splitlines()
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
        rows = []
        for raw in lines[i + 1:j]:
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            rows.append(cells)
        yield h2, h3, h4, header, rows, i + 1
        i = j


def is_member_table(header: list[str]) -> bool:
    return bool(header) and header[0] == "干员" and "条件" in header and "备注" in header


# ---------------------------------------------------------------- PRTS 名称索引（锚点判定用）

class PrtsIndex:
    """每名干员页面的「天赋名 / 技能名 / 模组名 / 召唤物名」，用于判断能力出自哪个章节。"""

    def __init__(self) -> None:
        self.cache: dict[str, dict[str, set[str]]] = {}

    def get(self, name: str) -> dict[str, set[str]]:
        if name in self.cache:
            return self.cache[name]
        talents, skills, modules, summons = set(), set(), set(), set()
        path = PRTS_DIR / name / f"{name}.md"
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            sec = ""
            for k, line in enumerate(lines):
                if line.startswith("## "):
                    sec = line[3:].strip()
                    continue
                if sec == "天赋" and line.lstrip().startswith("|"):
                    cells = split_cells(line)
                    if cells and cells[0] not in ("第一天赋", "第二天赋", "第三天赋", "备注", ""):
                        talents.add(cells[0])
                elif sec == "模组" and line.startswith("### "):
                    modules.add(line[4:].strip())
                elif sec == "技能" and line.lstrip().startswith("|"):
                    cells = split_cells(line)
                    if len(cells) > 1 and cells[1] and not cells[0] and not is_sep_row(cells) \
                            and not re.fullmatch(r"(等级|备注|Rank.*|\d+)", cells[1]):
                        skills.add(cells[1])
            for f in (PRTS_DIR / name).glob("*.md"):
                if f.stem not in (name, "攻击范围"):
                    summons.add(f.stem)
        # 召唤物文件带括号后缀（如「白铁™多功能平台(高效补给)」）时补上主名
        summons |= {re.split(r"[（(]", s)[0] for s in summons}
        self.cache[name] = {"talent": talents, "skill": skills, "module": modules, "summon": summons}
        return self.cache[name]

    @staticmethod
    def _hits(text: str, words: set[str]) -> bool:
        return any(len(w) >= 2 and w in text for w in words)

    def sources(self, op: str, cond: str, remark: str) -> set[str]:
        """依 docs/output-standard.md §5：从「条件／备注」文本判定能力来源章节。

        条件为主判据；条件给不出唯一来源时，再看备注主句（前两段）的名称/关键词。
        判出两类及以上即视为跨章节，交回「无锚点」。
        """
        idx = self.get(op)
        found: set[str] = set()
        # ---- 条件：硬性达成方式即来源
        if re.search(r"分支特性|分支[）)]", cond):
            found.add(SRC_TRAIT)
        if re.search(r"（第[一二三]天赋）|（天赋）", cond):
            found.add(SRC_TALENT)
        if re.search(r"[0-9一二三]技能", cond):
            found.add(SRC_SKILL)
        # 「更佳/可增幅/1级即可」等＝模组只做强化（模组本身不是能力来源）；
        # 精英0/1 即可达成、模组只是「追加/扩至」者同理。
        mod_weak = re.search(r"更佳|更优|可增幅|可选|为进阶|1级即可", cond) or (
            re.search(r"追加|扩至|起强化", cond) and re.search(r"精英[01]|^无", cond))
        if "模组" in cond and not mod_weak:
            # 能力由模组本身追加（模组段含更新后的天赋文本）：只锚模组，不再看备注
            if not found:
                return {SRC_MODULE}
            found.add(SRC_MODULE)
        if re.search(r"召唤物[「<“]|召唤物承载|由召唤物|由装置|装置型", cond):
            found.add(SRC_SUMMON)
        # ---- 备注主句：补充/校正（如「光环型（呵斥）」点名天赋）
        head = "；".join(remark.split("；")[:2])
        if "分支特性" in head:
            found.add(SRC_TRAIT)
        if re.search(r"第[一二三]天赋|天赋[「“]", head) or self._hits(head, idx["talent"]):
            found.add(SRC_TALENT)
        if re.search(r"[0-9一二三]技能|技能[「“]", head) or self._hits(head, idx["skill"]):
            found.add(SRC_SKILL)
        if self._hits(head, idx["module"]) or re.search(r"模组(新增|更新|追加)", head):
            found.add(SRC_MODULE)
        if re.search(r"召唤物承载", head) or self._hits(head, idx["summon"]):
            found.add(SRC_SUMMON)
        # ---- 合并：技能自带的装置/召唤物随技能（§5 表首行）
        if SRC_SKILL in found and SRC_SUMMON in found:
            found.discard(SRC_SUMMON)
        if SRC_MODULE in found and SRC_SUMMON in found:
            found.discard(SRC_SUMMON)
        return found

    def anchor_reason(self, op: str, cond: str, remark: str) -> tuple[str, str]:
        found = self.sources(op, cond, remark)
        if len(found) == 1:
            src = next(iter(found))
            return ANCHOR[src], src
        return "", ("跨章节：" + "/".join(sorted(found)) if found else "无来源信号")

    def anchor(self, op: str, cond: str, remark: str) -> str:
        return self.anchor_reason(op, cond, remark)[0]


# ---------------------------------------------------------------- 官方 TAG 解析

def strip_marker(text: str, patterns: list[re.Pattern]) -> tuple[str, list[str]]:
    """摘掉备注开头的结构性标记，返回 (剩余文本, 标记值列表)。"""
    values: list[str] = []
    changed = True
    while changed:
        changed = False
        for pat in patterns:
            m = pat.match(text)
            if m:
                values += [v.strip() for v in m.group(1).split("、") if v.strip()]
                text = text[m.end():].lstrip("；。")
                changed = True
    return text, values


def split_halo(value: str) -> list[str]:
    """全场光环组合值：「伤害+削弱+增益+治疗光环」→ 伤害光环/削弱光环/增益光环/治疗光环。"""
    out = []
    for part in value.split("+"):
        part = part.strip()
        if part:
            out.append(part if part.endswith("光环") else part + "光环")
    return out


def parse_official(catalog: dict, idx: PrtsIndex) -> tuple[list[dict], list[dict]]:
    name2id = {t["name"]: t for t in catalog["tags"]}
    tags, operators = [], {}
    lines = OFFICIAL_DOC.read_text(encoding="utf-8").splitlines()
    category = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            category = line[4:].strip()
            i += 1
            continue
        m = DEF_RE.match(line.strip())
        if not m:
            i += 1
            continue
        name = m.group("name")
        j = i + 1
        while j < len(lines) and not lines[j].lstrip().startswith("|"):
            j += 1
        k = j
        while k < len(lines) and lines[k].lstrip().startswith("|"):
            k += 1
        header = split_cells(lines[j]) if j < k else []
        assert is_member_table(header), f"官方条目 {name} 成员表列头异常：{header}"
        ci, ni = header.index("条件"), header.index("备注")
        entry = name2id.get(name)
        assert entry is not None, f"catalog.json 缺少官方 TAG：{name}"
        cat = re.sub(r"（.*?）$", "", category).strip()
        assert cat == entry["cat"], f"{name} 类别不一致：文档 {cat} / 字典 {entry['cat']}"
        members = []
        for raw in lines[j + 1:k]:
            cells = split_cells(raw)
            if is_sep_row(cells) or not cells or not cells[0] or len(cells) != len(header):
                continue
            op = cells[0].replace("**", "").strip()
            cond, remark = clean_cell(cells[ci]), clean_cell(cells[ni])
            sub_values: list[str] = []
            if name == "闪避":
                remark, vals = strip_marker(remark, [re.compile(r"^子 ?TAG[:：]([^。]*)。")])
                sub_values = vals
            elif name == "全场光环":
                remark, vals = strip_marker(remark, [re.compile(r"^子 ?TAG[:：]([^。]*)。")])
                sub_values = [v for val in vals for v in split_halo(val)]
            elif name == "抗削弱":
                remark, vals = strip_marker(remark, [re.compile(r"^子 ?TAG[:：]([^。]*)。")])
                sub_values = vals
            member = {"operator": op, "condition": cond}
            if remark:
                member["remark"] = remark
            if sub_values:
                group = "闪避类型" if name == "闪避" else "子 TAG"
                member["subTags"] = [{"group": group, "value": v} for v in dict.fromkeys(sub_values)]
            # 召唤物类 TAG：能力即「拥有/回收/绑定召唤物」，常驻者锚召唤物信息段（§5 表）
            if name in ("拥有召唤物", "召唤物退场返还/自动刷新", "技能-召唤物绑定"):
                anchor = "#技能" if re.search(r"[0-9一二三]技能", cond) else "#召唤物信息"
            else:
                anchor = idx.anchor(op, cond, remark)
            member["prtsUrl"] = url_of(op, anchor)
            members.append(member)
            operators.setdefault(op, None)
        tags.append({"id": entry["id"], "name": name, "source": "official",
                     "category": cat, "members": members})
        i = k
    return tags, list(operators)


# ---------------------------------------------------------------- 玩家 TAG 解析

P05_PATH_RE = re.compile(r"^救急路径[:：]([^；。]*)[；；]?")
P07_SUB_RE = re.compile(r"^\*{0,2}子 ?TAG[:：]([^。]*)。")

def player_subtags(tag_no: str, h3: str, h4: str, header: list[str], cells: list[str],
                   cond: str, remark: str) -> tuple[str, list[dict]]:
    """返回 (处理后的备注, subTags)。分组规则见 docs/output-standard.md §4.3。"""
    subs: list[dict] = []

    def add(group: str, value: str, detail: str = "") -> None:
        item = {"group": group, "value": value}
        if detail:
            item["detail"] = detail
        if item not in subs:
            subs.append(item)

    if tag_no == "02":
        for v in re.split(r"[、＋+]", h3):
            if v.strip():
                add("子 TAG", v.strip())
    elif tag_no == "03":
        for v in re.split(r"[、＋+]", cells[header.index("子 TAG")]):
            if v.strip():
                add("子 TAG", v.strip())
    elif tag_no == "04":
        m = re.match(r"表\s*\d+\s*·\s*([^（(]+)", h3)
        parent = m.group(1).strip() if m else ""
        if parent:
            add("子 TAG", parent)
        if h4 and parent:  # 「2A 召唤师 / 装置型召唤物」「2B 陷阱师（…）」＝子 TAG 之下的再分组
            child = re.sub(r"^\d[A-Z]\s*", "", h4).split("（")[0].strip()
            if child:
                add(parent, child)
    elif tag_no == "05":
        remark, vals = strip_marker(remark, [P05_PATH_RE])
        for v in vals:
            add("救急路径", re.sub(r"（[^）]*）$", "", v).strip())
        add("承载方式", "召唤物承载" if "承载" in remark else "本体")
    elif tag_no == "07":
        remark, vals = strip_marker(remark, [P07_SUB_RE])
        for v in vals:
            add("子 TAG", v)
    elif tag_no == "08":
        for item in cells[header.index("子 TAG")].split("、"):
            item = item.strip()
            if not item:
                continue
            group, _, value = item.partition("/")
            value, detail = value.strip(), ""
            if value.startswith("触发时"):  # 拐杖：仅「触发时」并记 detail（见 08-拐杖.md §子 TAG 定义）
                dm = re.match(r"^触发时\((.*)\)$", value)
                if dm:
                    value, detail = "触发时", dm.group(1).strip()
            add(group.strip(), value, detail)
    elif tag_no == "09":
        m = re.match(r"[一二三四五六七八九十]+、([^（(]+)", h3)
        if m:
            add("子 TAG", m.group(1).strip())
    return remark, subs or []


def parse_player(idx: PrtsIndex) -> tuple[list[dict], list[str]]:
    recommend = {}
    rec_file = PIPE / "player_tags" / "_recommend.json"
    if rec_file.exists():
        recommend = json.loads(rec_file.read_text(encoding="utf-8"))
    combo_meta = read_combo_meta(PLAYER_DOC)
    tags, seen_ops = [], []
    tag_no = last_h2 = ""
    per_tag: dict[str, list[dict]] = {}
    combos: dict[str, dict] = {}  # 阵容组合：组合名 → {combo, providers}
    tags_order: list[dict] = []
    for h2, h3, h4, header, rows, _ln in read_tables(PLAYER_DOC):
        m = PLAYER_H2_RE.match(f"## {h2}")
        if m and h2 != last_h2:  # 同一 TAG 的多张子表只建一次条目
            last_h2 = h2
            tag_no, tag_name = m.group(1), m.group(2)
            tags_order.append({"no": tag_no, "name": tag_name, "members": []})
            per_tag[tag_no] = []
        if not tags_order or not is_member_table(header):
            continue
        ci, ni = header.index("条件"), header.index("备注")
        for cells in rows:
            clean = [clean_cell(c) for c in cells]
            op = clean[0]
            cond, remark = clean[ci], clean[ni]
            if tag_no == "12":  # 阵容组合：成员行 = 组合的提供者（组合名取自子表标题）
                cm = COMBO_NAME_RE.match(h3.strip())
                combo = cm.group(1).strip() if cm else ""
                entry = combos.setdefault(combo, {"combo": combo, "providers": []})
                prov = {"operator": op, "condition": cond}
                if remark:
                    prov["remark"] = remark
                prov["prtsUrl"] = url_of(op, idx.anchor(op, cond, remark))
                entry["providers"].append(prov)
                seen_ops.append(op)
                continue
            remark, subs = player_subtags(tag_no, h3, h4, header, clean, cond, remark)
            member = {"operator": op, "condition": cond}
            if remark:
                member["remark"] = remark
            if subs:
                member["subTags"] = subs
            member["prtsUrl"] = url_of(op, idx.anchor(op, cond, remark))
            per_tag[tag_no].append(member)  # 一行成员表 = 一条成员；同一末端子 TAG 不重复即可重名
            seen_ops.append(op)
    for t in tags_order:
        if t["no"] == "12":  # 阵容组合：members = 组合条目（组合名/条件/备注/受益者/提供者明细）
            members = []
            for combo, entry in combos.items():
                meta = combo_meta.get(combo, {})
                item = {"combo": combo,
                        "condition": clean_cell(meta.get("condition", "")),
                        "remark": clean_cell(meta.get("remark", ""))}
                if meta.get("beneficiaries"):
                    item["beneficiaries"] = meta["beneficiaries"]
                item["providers"] = entry["providers"]
                members.append(item)
        else:
            members = per_tag[t["no"]]
            members.sort(key=lambda m: launch_date(m["operator"]) or "", reverse=True)
        tags.append({"id": f"P{t['no']}", "name": t["name"], "source": "player",
                     "recommended": [x for x in recommend.get(t["name"], [])],
                     "members": members})
    return tags, list(dict.fromkeys(seen_ops))


# ---------------------------------------------------------------- 干员表

def build_operators(names: list[str], extra: list[str]) -> list[dict]:
    ids = json.loads((PIPE / "char_ids.json").read_text(encoding="utf-8"))
    all_names = list(dict.fromkeys(names + extra))
    out = []
    for name in all_names:
        brief = parse_prts_brief(name)
        assert brief["star"] and brief["cls"], f"缺少 PRTS 基本信息：{name}"
        out.append({
            "name": name,
            "charId": ids.get(name, ""),
            "rarity": brief["star"],
            "class": brief["cls"],
            "branch": brief["branch"],
            "faction": brief["faction"],
            "releaseDate": launch_date(name) or "",
            "prtsUrl": url_of(name),
        })
    out.sort(key=lambda o: (o["releaseDate"] or "", o["name"]), reverse=True)
    return out


# ---------------------------------------------------------------- 未归 TAG 干员名单

def roster_names() -> list[str]:
    out = []
    for line in (ROOT / "docs" / "operators.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out.append(parts[0].strip())
    return out


def write_untagged_md(operators: list[dict]) -> int:
    """全量干员 − results 收录者 → docs/untagged-operators.md。"""
    ids = json.loads((PIPE / "char_ids.json").read_text(encoding="utf-8"))
    covered = {o["name"] for o in operators}
    rows = []
    for name in roster_names():
        if name in covered:
            continue
        brief = parse_prts_brief(name)
        rows.append({
            "name": name, "charId": ids.get(name, ""), "star": brief["star"] or "",
            "cls": brief["cls"], "branch": brief["branch"],
            "date": launch_date(name) or "", "url": url_of(name),
        })
    rows.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
    hist: dict[str, int] = {}
    for r in rows:
        hist[r["cls"]] = hist.get(r["cls"], 0) + 1
    hist_line = "、".join(f"{k} {v}" for k, v in sorted(hist.items(), key=lambda x: -x[1]))
    lines = [
        "# 未归入任何 TAG 的干员",
        "",
        "> 本文件自动生成，勿手改：由 `generate_results.py` 在生成 `results/operator-tags.json` 时同步写出"
        "（命令见 `docs/output-standard.md` §7）。",
        f"> 口径：全量干员（`docs/operators.txt`，{len(roster_names())} 名）− 结果 JSON `operators[]`（{len(operators)} 名）"
        f"＝ **{len(rows)} 名**未出现在任何官方设定 TAG／玩家体感 TAG 的成员表中。",
        "> 官方设定 TAG 的「无 TAG 干员」名单（`docs/official-tags-members.md` §3）中已有部分被玩家体感 TAG 收录，"
        "故本表与其不完全重合；某干员一旦进入任一成员表，重新生成时自动移出本表。",
        f"> 构成（按职业）：{hist_line}；名单按实装时间倒序。",
        "",
        "| 干员 | 编号 | 星级 | 职业·分支 | 实装时间 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| [{r['name']}]({r['url']}) | {r['charId']} | {r['star']} | {r['cls']}·{r['branch']} | {r['date']} |")
    lines.append("")
    (ROOT / "docs" / "untagged-operators.md").write_bytes("\n".join(lines).replace("\n", "\r\n").encode("utf-8"))
    return len(rows)


# ---------------------------------------------------------------- 主流程

def build() -> dict:
    catalog = json.loads((PIPE / "catalog.json").read_text(encoding="utf-8"))
    idx = PrtsIndex()
    official, ops_a = parse_official(catalog, idx)
    player, ops_b = parse_player(idx)
    operators = build_operators(ops_a, ops_b)
    return {
        "version": "v1",
        "updated": rj.today_str(),
        "operators": operators,
        "tags": official + player,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 results/operator-tags.json")
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    ap.add_argument("--report", action="store_true", help="打印逐 TAG 计数")
    args = ap.parse_args()

    doc = build()
    problems, stats = rj.validate_results(doc)
    if args.report:
        off = [t for t in doc["tags"] if t["source"] == "official"]
        ply = [t for t in doc["tags"] if t["source"] == "player"]
        print(f"官方 TAG {len(off)} 个 / 玩家 TAG {len(ply)} 个 / 干员 {len(doc['operators'])} 名")
        for t in doc["tags"]:
            anchored = sum(1 for m in t["members"] if "#" in m["prtsUrl"])
            subs = sum(1 for m in t["members"] if m.get("subTags"))
            print(f"  {t['id']:<12} {t['name']:<14} 成员 {len(t['members']):>3}  锚点 {anchored:>3}  子TAG {subs:>3}")
    if problems:
        errs = [p for p in problems if p["level"] == "error"]
        warns = [p for p in problems if p["level"] == "warn"]
        print(f"\n校验：{len(errs)} 错误 / {len(warns)} 警告")
        for p in (errs + warns)[:80]:
            print(f"  [{p['level']}] {p['code']} {p['path']}: {p['message']} {('[%s]' % p['label']) if p['label'] else ''}")
    else:
        print("\n校验：无问题")
    if args.check:
        return 1 if any(p["level"] == "error" for p in problems) else 0
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(rj.render_results(doc, eol="crlf").encode("utf-8"))  # 仓库落盘风格：CRLF
    print(f"已写出 {OUT_FILE.relative_to(ROOT)}（{OUT_FILE.stat().st_size} 字节）")
    untagged = write_untagged_md(doc["operators"])
    print(f"已写出 docs/untagged-operators.md（未归 TAG 干员 {untagged} 名）")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

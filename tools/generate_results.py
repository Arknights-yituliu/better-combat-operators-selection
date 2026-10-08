# -*- coding: utf-8 -*-
"""生成 results/operator-tags.json（v1）：把两份分文件（tag-part/1 JSON）合成为最终结果 JSON。

数据来源（docs/output-standard.md §7）：
- agent_workspace/tag_pipeline/official_tags/[A-I]-*.json       官方设定 TAG 分模块（tag-part/1，成员表 干员｜编号｜条件｜备注）
- agent_workspace/tag_pipeline/player_tags/NN-*.json            玩家体感 TAG 分文件（tag-part/1，含 子 TAG／救急路径 等分组信息）
- agent_workspace/tag_pipeline/catalog.json                    官方 TAG 字典（名称 → id／类别）
- agent_workspace/tag_pipeline/char_ids.json                   干员名 → charId
- agent_workspace/tag_pipeline/player_tags/_launch_dates.json  干员名 → 实装时间
- agent_workspace/tag_pipeline/player_tags/_recommend.json     玩家 TAG 荐（可缺省）
- material_datas/PRTS/<干员>/<干员>.md                         基本信息（稀有度/职业/分支/势力）
- material_datas/PRTS/<干员>/*.md                              锚点判定用的天赋/技能/模组/召唤物名索引

用法：
    python -X utf8 tools/generate_results.py            # 写 results/operator-tags.json
    python -X utf8 tools/generate_results.py --check    # 只生成到内存并跑规范校验
    python -X utf8 tools/generate_results.py --report   # 打印统计与逐 TAG 计数
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIPE = ROOT / "agent_workspace" / "tag_pipeline"
OFFICIAL_DIR = PIPE / "official_tags"
PLAYER_DIR = PIPE / "player_tags"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(OFFICIAL_DIR))
from gui.md import is_sep_row, split_cells          # noqa: E402
from gui.roster import launch_date, parse_prts_brief  # noqa: E402
from gui import results_json as rj                   # noqa: E402
import partdoc                                       # noqa: E402  （分文件 JSON 的唯一读写实现）
import _merge_official_to_docs as offm               # noqa: E402  （官方分模块清单 FILES 的唯一来源）

PRTS_DIR = ROOT / "material_datas" / "PRTS"
OUT_FILE = ROOT / "results" / "operator-tags.json"

# docs/output-standard.md §1：TAG 增删／改名／排序变化、成员变化、字段形状变化等须递增版本
VERSION = "v20"

# 文档里残留的 文件:行号 证据（结果 JSON 不得携带）
EV_RE = re.compile(r"[；，、]?\s*[^（）()；。\s]*\.md:\d[\d,\-–\s]*")

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


# ---------------------------------------------------------------- 备注分块（写法见 docs/concept.md「备注分块」）

BLOCK_SEP = "｜"                    # 块分隔：全角竖线（ASCII | 会破坏表格结构，撰写侧禁用）
ITEM_SEP = "；"                     # 条分隔
BLOCK_LABEL_MAX = 40                # 块标签字数上限，超长视为正文（避免整句被当标题）
BLOCK_LABEL_BAD = set("；。，")       # 块标签不得含句读与逗号（引文整句不是标签）
BLOCK_LABEL_FREE = ("成绩", "计算", "说明")  # 保留块类：标签不受字数上限约束（成绩情形名可带面板口径）
ITEM_LABEL_MAX = 12                 # 条标签字数上限
ITEM_LABEL_BAD = set("（）「」，。、")  # 条标签不得含标点（技能名带「」者按正文处理）
BRACKETS = {"（": "）", "(": ")", "「": "」", "【": "】"}   # 括号内不切分
CLOSERS = {"）", ")", "」", "】"}    # 闭括号宽窄混用（`（…）`）按闭合处理：宁可少切一刀，不可静默错切
# 块标签只能是能力名或保留块类，绝不会以引号开头（`「…」：` 是引文正文，不是标签）
BLOCK_HINT_RE = re.compile(r"^(?:成绩|计算|说明)[：\s]")
ABILITY_HEAD_RE = re.compile(r"^(?:第[一二三]天赋|[0-9一二三]技能|召唤物|装置|特性|模组)")


def _strip_brackets(s: str) -> str:
    """剥掉**配对**括号／引号内的内容（支持嵌套，如 `（Y模组3级（PUM-Y），潜能5）`）。

    块标签的句读判据只看括号外的部分——用正则会漏掉嵌套写法，导致标签被静默退回正文。
    """
    out, depth = [], 0
    for ch in s:
        if ch in "（(「【":
            depth += 1
        elif ch in "）)」】":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def block_hint(chunk: str) -> bool:
    """块首像能力名却不是标签？——`第一天赋「X」（…）：…` 这类带限定语的块名被退回正文时，
    lint 必须报出来（否则整块静默降级成一段正文）。引文式散文（`第一天赋「X」的额外伤害…`）
    没有紧跟的 `：`，不会误报。"""
    if BLOCK_HINT_RE.match(chunk):
        return True
    m = ABILITY_HEAD_RE.match(chunk)
    return bool(m) and chunk[len(m.group(0)):].startswith(("「", "（", "(")) and "：" in chunk[:48]
TEXT_PROBLEMS: list[str] = []       # 文本 lint 报告（只报告、不阻断；即存量待重排清单）


def split_top(text: str, sep: str) -> list[str]:
    """按 sep 切分，但**括号内不切**（`（）`／`「」`／`【】`／`()`）。

    括号里的 `；` 是括号内容的一部分（如「（最低可满足档 面板433×…；最高档 面板535×…）」），
    若照切会把一条拆成两条、后半条失去条标签。
    """
    out: list[str] = []
    buf: list[str] = []
    stack: list[str] = []
    for ch in text:
        if ch in BRACKETS:
            stack.append(BRACKETS[ch])
        elif stack and ch in CLOSERS:
            stack.pop()
        if ch == sep and not stack:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def balanced(text: str) -> bool:
    """括号／引号是否配对；不配对会让分隔符判据整体失效（`split_top` 的静默失效模式）。"""
    stack: list[str] = []
    for ch in text:
        if ch in BRACKETS:
            stack.append(BRACKETS[ch])
        elif stack and ch in CLOSERS:
            stack.pop()
        elif ch in CLOSERS:
            return False
    return not stack


def split_block_label(chunk: str) -> tuple[str, str]:
    """块的 `标签：正文` → (标签, 正文)；不合规的标签一律留作正文。"""
    i = chunk.find("：")
    if i <= 0:
        return "", chunk
    head = chunk[:i].strip()
    # 句读判据只看括号外的部分：`第二天赋「…」（精英2，潜能5）` 里的逗号是限定语的一部分，
    # 而整句引文（`「…，…」：…`）仍会被挡住。
    bare = _strip_brackets(head)
    if not head or head.startswith("「") or (set(bare) & BLOCK_LABEL_BAD):
        return "", chunk
    free = any(head == k or head.startswith(k + " ") for k in BLOCK_LABEL_FREE)
    if not free and len(head) > BLOCK_LABEL_MAX:
        return "", chunk
    return head, chunk[i + 1:].strip()


def split_item_label(text: str) -> tuple[str, str]:
    j = text.find("：")
    if j <= 0:
        return "", text
    head, tail = text[:j].strip(), text[j + 1:].strip()
    if tail and head and len(head) <= ITEM_LABEL_MAX and not (set(head) & ITEM_LABEL_BAD):
        return head, tail
    return "", text


def parse_blocks(text: str) -> list[dict]:
    """备注源文本 → 块数组（docs/output-standard.md §4.2）。

    `｜` 分块、`；` 分条（两者在括号内都不生效）；两个层级共用同一句法 `标签：正文`。
    不含分隔符的旧文本自然成为「单块 + 条按 `；` 拆分」。
    """
    blocks: list[dict] = []
    for raw_block in split_top(text, BLOCK_SEP):
        chunk = raw_block.strip()
        if not chunk:
            continue
        label, body = split_block_label(chunk)
        items: list[dict] = []
        for raw_item in split_top(body, ITEM_SEP):
            item_text = raw_item.strip()
            if not item_text:
                continue
            ilabel, itext = split_item_label(item_text)
            items.append({"label": ilabel, "text": itext} if ilabel else {"text": item_text})
        if not items:
            continue
        blocks.append({"label": label, "items": items} if label else {"items": items})
    return blocks


# 备注禁用项：正则 → 说明（docs/concept.md「备注分块」末节）
LINT_PATTERNS = (
    (r"(?<![0-9])★", "含 ★ 分类标记（★ 仅用于星级写法 N★）"),
    (r"备注[:：]", "含「备注：」字样"),
    (r"PRTS\s?(?:备注|注)[:：]", "含「PRTS 备注/注」字样"),
    (r"(?:天赋|技能)原文[:：]", "含「原文」字样"),
    (r"[（(]下详[）)]|见备注|同上|另见", "含指向别处的悬空引用（应自包含写全）"),
    (r"UI 建议|作为强条件提示", "含面向 UI 的指令文字"),
    (r"(?<![A-Za-z])S[123](?![0-9])", "用 S1/S2/S3 简写（应写「N技能「技能名」」）"),
)


def lint_text(tag: str, op: str, cond: str, remark: str) -> None:
    """按 docs/concept.md「备注分块」检查源文本。只报告、不阻断写出。

    结构类检查（括号配对、空块／空条、块标签是否被识别）与内容类检查（禁用字样、块序）并列——
    结构类问题是静默的（解析只会少切一刀），必须由 lint 兜住。
    """
    def rep(msg: str) -> None:
        TEXT_PROBLEMS.append(f"{tag}｜{op}：{msg}")

    for pattern, msg in LINT_PATTERNS:
        if re.search(pattern, remark):
            rep(msg)
    if not balanced(remark):
        rep("括号／引号不配对（分隔符判据会整体失效，先补全括号）")
    raw_blocks = [s for s in split_top(remark, BLOCK_SEP)]
    for raw in raw_blocks:
        chunk = raw.strip()
        if not chunk:
            continue
        label, body = split_block_label(chunk)
        if not label and block_hint(chunk):
            rep(f"块首疑似标签但未被识别：{chunk[:24]}…")
        if label and not any(label == k or label.startswith(k + " ") for k in BLOCK_LABEL_FREE) \
                and len(label) > BLOCK_LABEL_MAX:
            rep(f"块标签偏长（{len(label)} 字）：{label[:20]}…")
        segs = split_top(body, ITEM_SEP)
        if any(not s.strip() for s in segs[1:-1]):
            rep(f"块「{label or '（无标签）'}」内含空的条（`；` 连写）")
    labels = [b.get("label", "") for b in parse_blocks(remark)]
    for label in labels:
        if re.fullmatch(r"[0-9一二三]技能", label):
            rep(f"块标签「{label}」未点名技能（应写「{label}「技能名」」）")
    if any(l.startswith("成绩") for l in labels) and not labels[0].startswith("成绩"):
        rep("成绩块未排在首位（块序应为 成绩→能力→计算→说明）")
    tail = [i for i, l in enumerate(labels) if l in ("计算", "说明")]
    if tail:
        between = labels[tail[0]:]
        if any(l not in ("计算", "说明") for l in between):
            rep("「计算」／「说明」块之后还有能力块（块序应为 成绩→能力→计算→说明）")
        elif "计算" in between and "说明" in between and between.index("说明") < between.index("计算"):
            rep("「说明」块排在「计算」之前")
    # 条件不设字数上限（见 docs/rulings.md「条件不设字数上限」）：可读性由分条与句式保证，
    # 硬性前提与硬性条件一个都不能省；面板/计数口径句仍应写进「说明」块（那属职责分工，不按字数判）。


# ---------------------------------------------------------------- 阵容组合（P12）组合级元数据

COMBO_NAME_RE = re.compile(r"([AB])(\d+)\.\s*(.+)$")
COMBO_CATEGORY = {"A": "势力", "B": "用法"}
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


def read_combo_meta(doc: dict) -> dict[str, dict]:
    """阵容组合（12 的 tag-part/1）：`### A<N>. 组合名`（势力）/ `### B<N>. 组合名`（用法）段里
    固定三条 bullet → 组合级 condition/remark/beneficiaries，并记子 TAG 分类（A→势力、B→用法）。"""
    out: dict[str, dict] = {}
    cur = ""
    for it in doc["body"]:
        if it["t"] == "heading":
            if it["level"] == 2:
                cur = ""
            elif it["level"] == 3:
                m = COMBO_NAME_RE.match(partdoc.clean_heading(it["text"]))
                cur = m.group(3).strip() if m else ""
                if cur:
                    out.setdefault(cur, {})
                    if m:
                        out[cur]["subtag"] = COMBO_CATEGORY.get(m.group(1), "")
            continue
        if not cur or it["t"] != "p":
            continue
        for line in it["lines"]:
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


ARKDPS_SOURCE_URL = "https://ark-dps.com/zh/"

# 显示成绩采用了 ArkDPS 帧模型/用法分支的成员行（按「分文件编号＋干员名」显式登记）。
# 正文不再行内标注引用，来源字段据此写入；新增此类行时须在此登记（口径见 docs/calc-rules.md §4.10）。
ARKDPS_MEMBER_ROWS = {
    ("01", "斩业星熊"),
    ("01", "司霆惊蛰"),
    ("01", "荒芜拉普兰德"),
    ("01", "玛恩纳"),
    ("01", "卡涅利安"),
}

ARKDPS_DETAILS = {
    "帧模型与用法分支": ("可攻击时长、取整帧与帧级时点采用站点帧模型（按站点公式实际含有的项：动画帧、取整帧、阶段/有效时长等；"
                          "四舍五入(可攻击时长 ÷ 间隔)）；多情形成绩的情形名采用站点用法分支名；"
                          "间隔、面板、潜能与条件均按我方，评定标准与达标判定不引用站点。"),
    "组合公式与默认数据": ("组合数值按站点组合公式逐字代入；采用站点默认数据（默认面板、木桩敌人 0 防/0 抗、单目标），"
                            "不使用本项目其它 TAG 的取档口径。"),
    "算法框架与用法分支": "采用站点算法框架与用法分支；面板与判定仍按我方。",
}


def arkdps_source(remark: str, default_parts: str = "算法框架与用法分支") -> dict:
    """外部计算工具来源字段（口径见 docs/calc-rules.md §4.10、docs/output-standard.md §4.2）。

    model＝工具名；url＝官网；author＝作者（极夜星辰）；parts＝本条引用了站点的哪一部分；
    detail＝该引用部分的详细说明（消费端仅在详情卡片末尾展示）。
    """
    if "帧模型与用法分支" in remark:
        parts = "帧模型与用法分支"
    elif "组合公式" in remark:
        parts = "组合公式与默认数据"
    else:
        parts = default_parts
    return {"model": "ArkDPS", "url": ARKDPS_SOURCE_URL, "author": "极夜星辰",
            "parts": parts, "detail": ARKDPS_DETAILS.get(parts, ARKDPS_DETAILS["算法框架与用法分支"])}


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


# 官方 TAG 的取值闭集：TAG 名 → [(组名, 取值…)]。分模块成员行的备注列以「子 TAG：…。」
# 开头书写，可连续出现多个前缀、一次一组；组名不写在行内，由「取值 → 组名」反查，
# 故前缀先后顺序不影响解析（见 docs/output-standard.md §4.3）。
OFFICIAL_SUB_GROUPS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "闪避": [("闪避类型", ("物理闪避", "法术闪避", "全伤害闪避")),
             ("作用范围", ("仅自身", "可给予他人"))],
    "全场光环": [("子 TAG", ("伤害光环", "削弱光环", "增益光环", "治疗光环", "增伤光环"))],
    "抗削弱": [("子 TAG", ("下限保护", "上限提高"))],
    "帧级结算": [("子 TAG", ("帧级判定", "帧伤"))],
    "护盾（按层抵挡）": [("作用范围", ("仅自身", "可给予他人"))],
    "屏障（吸收值）": [("作用范围", ("仅自身", "可给予他人"))],
    "免死/复活/替身": [("作用范围", ("仅自身", "可给予他人"))],
    "伤害减免/减伤": [("作用范围", ("仅自身", "可给予他人"))],
    "庇护（物法减伤）": [("作用范围", ("仅自身", "可给予他人"))],
    "迷彩": [("作用范围", ("仅自身", "可给予他人"))],
    "抵抗": [("作用范围", ("仅自身", "可给予他人"))],
    "嘲讽/吸引攻击": [("作用范围", ("仅自身", "可给予他人"))],
    "降低被攻击优先级": [("作用范围", ("仅自身", "可给予他人"))],
}

# 组合写法的取值（全场光环「伤害+削弱光环」）先展开再查表
SUB_EXPANDERS = {"全场光环": split_halo}

SUB_PREFIX_RE = re.compile(r"^子 ?TAG[:：]([^。]*)。")
SUB_PROBLEMS: list[str] = []


def sub_group_of(tag: str, value: str) -> str:
    """按取值反查组名；未登记取值返回空串。"""
    for group, values in OFFICIAL_SUB_GROUPS.get(tag, ()):
        if value in values:
            return group
    return ""


def parse_sub_prefix(remark: str, tag: str) -> tuple[str, list[dict]]:
    """剥离备注开头连续出现的「子 TAG：…。」前缀，返回 (剩余备注, subTags)。"""
    subs: list[dict] = []
    while True:
        m = SUB_PREFIX_RE.match(remark)
        if not m:
            break
        expand = SUB_EXPANDERS.get(tag)
        values = [v.strip() for v in m.group(1).split("、") if v.strip()]
        for value in (x for v in values for x in (expand(v) if expand else [v])):
            group = sub_group_of(tag, value)
            if not group:
                if tag in OFFICIAL_SUB_GROUPS:
                    SUB_PROBLEMS.append(f"{tag}：子 TAG 取值「{value}」不在闭集内")
                group = "子 TAG"
            item = {"group": group, "value": value}
            if item not in subs:
                subs.append(item)
        remark = remark[m.end():].lstrip("；。")
    return remark, subs


def parse_official(catalog: dict, idx: PrtsIndex) -> tuple[list[dict], list[dict]]:
    name2id = {t["name"]: t for t in catalog["tags"]}
    unknown = [n for n in OFFICIAL_SUB_GROUPS if n not in name2id]
    assert not unknown, f"子 TAG 取值闭集表里的 TAG 不在 catalog.json：{unknown}"
    tags, operators = [], {}
    for category, flist in offm.FILES:
        cat = re.sub(r"（.*?）$", "", category).strip()
        for fname in flist:
            doc = partdoc.load(OFFICIAL_DIR / fname)
            for e in doc["entries"]:
                name = e["name"]
                rows = [list(r) for it in e["items"] if it["t"] == "table" for r in it["rows"]]
                # 原管道读的视图已按实装时间倒序排好；此处对源行做同一排序（共享助手，防两处漂移）
                rows, _undated = partdoc.order_official_rows(rows)
                entry = name2id.get(name)
                assert entry is not None, f"catalog.json 缺少官方 TAG：{name}"
                assert cat == entry["cat"], f"{name} 类别不一致：文档 {cat} / 字典 {entry['cat']}"
                members = []
                for cells in rows:
                    op = cells[0].replace("**", "").strip()
                    cond, remark = clean_cell(cells[2]), clean_cell(cells[3])  # 列序＝干员｜编号｜条件｜备注
                    remark, subs = parse_sub_prefix(remark, name)
                    if re.match(r"^子\s?TAG", remark):  # 前缀漏写「。」时正则失配、前缀会原样混入备注
                        SUB_PROBLEMS.append(f"{name}｜{op}：备注开头的子 TAG 前缀未以「。」收尾")
                    lint_text(name, op, cond, remark)
                    member = {"operator": op, "condition": cond}
                    blocks = parse_blocks(remark)
                    if blocks:
                        member["remark"] = blocks
                    if subs:
                        member["subTags"] = subs
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
    return tags, list(operators)


# ---------------------------------------------------------------- 玩家 TAG 解析

P05_PATH_RE = re.compile(r"^救急路径[:：]([^；。]*)[；；]?")

# 01 决战歼灭：子 TAG 排列顺序（范围轴＋伤害轴；与 tools/recommend.py 的 P01_SUB_ORDER 同步）
P01_SUB_ORDER = ["小范围", "大范围", "主物理伤害", "主法术伤害", "主真实伤害", "主弱点伤害",
                 "物法混伤", "物真混伤", "物元混伤", "法元混伤"]

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

    if tag_no == "01":
        # 子表标题＝伤害类型；「范围」列＝范围轴；每行恰两个值，按 P01_SUB_ORDER 排序
        for v in re.split(r"[、＋+]", h3):
            if v.strip():
                add("子 TAG", v.strip())
        if "范围" in header:
            v = cells[header.index("范围")].strip()
            if v:
                add("子 TAG", v)
        subs.sort(key=lambda s: P01_SUB_ORDER.index(s["value"]) if s["value"] in P01_SUB_ORDER else len(P01_SUB_ORDER))
    elif tag_no in ("02", "03", "06"):
        # 子表标题即子 TAG：02 多段·间隔／03 聚爆·连射·慢热／06 编入·部署
        for v in re.split(r"[、＋+]", h3):
            if v.strip():
                add("子 TAG", v.strip())
    elif tag_no == "13":          # 高档控制：子表标题即子 TAG（大力推拉／阻挡数5／长效控制／远距控制／硬控／软控）
        for v in re.split(r"[、＋+]", h3):
            if v.strip():
                add("子 TAG", v.strip())
        if h4 and h3.strip().startswith("远距控制"):  # 远距控制之下再分「独立达成／需配合」
            if h4.strip():
                add("远距控制", h4.strip())
    elif tag_no == "04":
        m = re.match(r"表\s*\d+\s*·\s*([^（(]+)", h3)
        parent = m.group(1).strip() if m else ""
        if parent:
            add("子 TAG", parent)
        if parent and h4.startswith("2A "):   # 「2A 召唤师 / 装置型召唤物」＝子 TAG 之下的再分组（陷阱部分并入本表、无再分组）
            child = re.sub(r"^\d[A-Z]\s*", "", h4).split("（")[0].strip()
            if child:
                add(parent, child)
    elif tag_no == "05":
        remark, vals = strip_marker(remark, [P05_PATH_RE])
        for v in vals:
            add("救急路径", re.sub(r"（[^）]*）$", "", v).strip())
        if "承载" in remark:          # 承载方式：只记「召唤物承载」（其余为干员本体承担、不设值）
            add("承载方式", "召唤物承载")
    elif tag_no == "07":          # 充电：子表标题即子 TAG（直接补充技力／技力回复速度加快／补弹）
        for v in re.split(r"[、＋+]", h3):
            if v.strip():
                add("子 TAG", v.strip())
    elif tag_no == "08":
        for item in cells[header.index("子 TAG")].split("、"):
            item = item.strip()
            if not item:
                continue
            group, _, value = item.partition("/")
            value, detail = value.strip(), ""
            if value.startswith("触发时"):  # 拐杖：仅「触发时」并记 detail（见 08-拐杖.json §子 TAG 定义）
                dm = re.match(r"^触发时\((.*)\)$", value)
                if dm:
                    value, detail = "触发时", dm.group(1).strip()
            add(group.strip(), value, detail)
    elif tag_no == "09":
        m = re.match(r"[一二三四五六七八九十]+、([^（(]+)", h3)
        if m:
            add("子 TAG", m.group(1).strip())
    return remark, subs or []


def collect_sub_scopes(members: list[dict]) -> list[tuple[str, str]]:
    """成员的 subTags → [(group, value)]（按出现顺序、value 去重）。"""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in members:
        for s in m.get("subTags", []):
            v = s.get("value")
            if v and v not in seen:
                seen.add(v)
                out.append((s.get("group") or "子 TAG", v))
    return out


def rec_fields(tag_name: str, members: list[dict],
               rec_map: dict[str, list[str]], fb_map: dict[str, list[str]]) -> dict:
    """荐字段：有子 TAG 的顶级 TAG → recommendedBySub（荐下沉到子 TAG）；
    无子 TAG 的维持 TAG 级 recommended/recommendedFallback。"""
    scopes = collect_sub_scopes(members)
    if tag_name == "决战歼灭":  # 范围轴＋伤害轴按 P01_SUB_ORDER 排列（见 docs/output-standard.md §4.3）
        scopes.sort(key=lambda gv: P01_SUB_ORDER.index(gv[1]) if gv[1] in P01_SUB_ORDER else len(P01_SUB_ORDER))
    out: dict = {}
    if not scopes:
        out["recommended"] = list(rec_map.get(tag_name, []))
        out["recommendedFallback"] = list(fb_map.get(tag_name, []))
        return out
    by: list[dict] = []
    fb: list[dict] = []
    for group, value in scopes:
        names = rec_map.get(f"{tag_name}/{value}", [])
        if names:
            by.append({"group": group, "value": value, "names": list(names)})
        fnames = fb_map.get(f"{tag_name}/{value}", [])
        if fnames:
            fb.append({"group": group, "value": value, "names": list(fnames)})
    out["recommended"] = list(rec_map.get(tag_name, []))  # 裸 TAG 键（如有）：兼容字段
    out["recommendedFallback"] = list(fb_map.get(tag_name, []))
    if by:
        out["recommendedBySub"] = by
    if fb:
        out["recommendedFallbackBySub"] = fb
    return out


def parse_player(idx: PrtsIndex) -> tuple[list[dict], list[str]]:
    recommend = {}
    rec_file = PIPE / "player_tags" / "_recommend.json"
    if rec_file.exists():
        recommend = json.loads(rec_file.read_text(encoding="utf-8"))
    recommend_fallback = {}
    rec_fb_file = PIPE / "player_tags" / "_recommend_fallback.json"
    if rec_fb_file.exists():
        recommend_fallback = json.loads(rec_fb_file.read_text(encoding="utf-8"))
    combo_meta = read_combo_meta(partdoc.load(PLAYER_DIR / "12-阵容组合.json"))
    tags, seen_ops = [], []
    per_tag: dict[str, list[dict]] = {}
    combos: dict[str, dict] = {}  # 阵容组合：组合名 → {combo, providers}
    tags_order: list[dict] = []
    for tag_no, tag_name, path in partdoc.player_files():
        doc = partdoc.load(path)
        tags_order.append({"no": tag_no, "name": tag_name, "members": []})  # 一文件 = 一个 TAG
        per_tag[tag_no] = []
        for h3, h4, header, rows, _bi in partdoc.member_tables(doc):
            ci, ni = header.index("条件"), header.index("备注")
            for cells in rows:
                clean = [clean_cell(c) for c in cells]
                op = clean[0]
                cond, remark = clean[ci], clean[ni]
                if tag_no == "12":  # 阵容组合：成员行 = 组合的提供者（组合名取自子表标题）
                    cm = COMBO_NAME_RE.match(h3.strip())
                    combo = cm.group(3).strip() if cm else ""
                    entry = combos.setdefault(combo, {"combo": combo, "providers": []})
                    lint_text("阵容组合/" + combo, op, cond, remark)
                    prov = {"operator": op, "condition": cond}
                    blocks = parse_blocks(remark)
                    if blocks:
                        prov["remark"] = blocks
                    prov["prtsUrl"] = url_of(op, idx.anchor(op, cond, remark))
                    entry["providers"].append(prov)
                    seen_ops.append(op)
                    continue
                remark, subs = player_subtags(tag_no, h3, h4, header, clean, cond, remark)
                lint_text(tag_name, op, cond, remark)
                member = {"operator": op, "condition": cond}
                blocks = parse_blocks(remark)
                if blocks:
                    member["remark"] = blocks
                if subs:
                    member["subTags"] = subs
                if "ArkDPS" in remark or (tag_no, op) in ARKDPS_MEMBER_ROWS:
                    # 显示成绩引用了外部帧模型/用法分支（口径见 docs/calc-rules.md §4.10）
                    member["source"] = arkdps_source(remark, default_parts="帧模型与用法分支")
                member["prtsUrl"] = url_of(op, idx.anchor(op, cond, remark))
                per_tag[tag_no].append(member)  # 一行成员表 = 一条成员；同一末端子 TAG 不重复即可重名
                seen_ops.append(op)
    for t in tags_order:
        if t["no"] == "12":  # 阵容组合：members = 组合条目（组合名/条件/备注/受益者/提供者明细）
            members = []
            for combo, entry in combos.items():
                meta = combo_meta.get(combo, {})
                cond = clean_cell(meta.get("condition", ""))
                remark = clean_cell(meta.get("remark", ""))
                lint_text("阵容组合/" + combo, combo, cond, remark)
                item = {"combo": combo, "condition": cond}
                blocks = parse_blocks(remark)
                if blocks:
                    item["remark"] = blocks
                if meta.get("beneficiaries"):
                    item["beneficiaries"] = meta["beneficiaries"]
                if meta.get("subtag"):
                    item["subTags"] = [{"group": "子 TAG", "value": meta["subtag"]}]
                if meta.get("subtag") == "用法":  # 「用法」组合均取自站点组合公式，卡片末尾统一标注来源
                    item["source"] = arkdps_source(remark, default_parts="组合公式与默认数据")
                item["providers"] = entry["providers"]
                members.append(item)
        else:
            members = per_tag[t["no"]]
            members.sort(key=lambda m: launch_date(m["operator"]) or "", reverse=True)
        rec = rec_fields(t["name"], members, recommend, recommend_fallback)
        item = {"id": f"P{t['no']}", "name": t["name"], "source": "player"}
        item.update(rec)
        item["members"] = members
        tags.append(item)
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
        "> 本文件自动生成，勿手改：由 `tools/generate_results.py` 在生成 `results/operator-tags.json` 时同步写出"
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
        "version": VERSION,
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
            anchored = sum(1 for m in t["members"] if "#" in m.get("prtsUrl", ""))  # 组合条目无 prtsUrl
            subs = sum(1 for m in t["members"] if m.get("subTags"))
            print(f"  {t['id']:<12} {t['name']:<14} 成员 {len(t['members']):>3}  锚点 {anchored:>3}  子TAG {subs:>3}")
    if SUB_PROBLEMS:
        print(f"\n子 TAG 解析问题：{len(SUB_PROBLEMS)} 条")
        for p in SUB_PROBLEMS[:40]:
            print("  " + p)
    if TEXT_PROBLEMS:
        by_tag: dict[str, int] = {}
        for p in TEXT_PROBLEMS:
            by_tag[p.split("｜", 1)[0]] = by_tag.get(p.split("｜", 1)[0], 0) + 1
        head = "、".join(f"{k} {v}" for k, v in sorted(by_tag.items(), key=lambda kv: -kv[1])[:12])
        print(f"\n文本 lint：{len(TEXT_PROBLEMS)} 条待重排（不阻断写出；按 TAG 分布：{head}）")
        if args.report:
            for p in TEXT_PROBLEMS:
                print("  " + p)
    if problems:
        errs = [p for p in problems if p["level"] == "error"]
        warns = [p for p in problems if p["level"] == "warn"]
        print(f"\n校验：{len(errs)} 错误 / {len(warns)} 警告")
        for p in (errs + warns)[:80]:
            print(f"  [{p['level']}] {p['code']} {p['path']}: {p['message']} {('[%s]' % p['label']) if p['label'] else ''}")
    else:
        print("\n校验：无问题")
    if args.check:
        return 1 if (any(p["level"] == "error" for p in problems) or SUB_PROBLEMS) else 0
    if SUB_PROBLEMS:
        return 1  # 解析问题未解决，不写出
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(rj.render_results(doc, eol="crlf").encode("utf-8"))  # 仓库落盘风格：CRLF
    print(f"已写出 {OUT_FILE.relative_to(ROOT)}（{OUT_FILE.stat().st_size} 字节）")
    untagged = write_untagged_md(doc["operators"])
    print(f"已写出 docs/untagged-operators.md（未归 TAG 干员 {untagged} 名）")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

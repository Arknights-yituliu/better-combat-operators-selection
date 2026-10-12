# -*- coding: utf-8 -*-
"""玩家体感 TAG 评定标准（严谨版）→ results/player-tags-criteria.json

源文件：docs/player-tags-criteria.md（结构与撰写要求见其文件头）。

行内标记：源文件用 md 书写（`**强调**`、`反引号代码`），写出前转写为 HTML 行内标签（`<strong>`／`<code>`）
——结果 JSON 不携带 md 语法，前端按白名单渲染（见 docs/ui-render-rules.md §5.5／§7）。

校验（默认全部运行，全部通过才写出）：
  1) 覆盖：与 results/operator-tags.json 双向核对——每个玩家 TAG、成员里出现的每个（组，值）都必须有条目，多、缺都报错；
  2) 术语：文末「术语表」的每个术语必须在正文里被引用（『·』拆分的各部分任一出现即算）；表内条目不得重复；
  3) 数字守卫：正文里带单位的数字必须能在对应分文件的「评定标准」节或 docs/glossary.md 中找到（防转述编造；例外登记在 NUM_EXEMPT）；
  4) 指纹：各分文件「评定标准」节的内容指纹记录在源文件注释中，源一变即提醒复核；--check 视为失败，--accept 更新记录；
  5) 行内标记：产物不得残留 md 行内语法（`**`、反引号）——漏转写会让前端显示字面标记。

用法：
    .venv/Scripts/python.exe -X utf8 tools/criteria_to_json.py            # 生成 + 校验（指纹漂移仅提醒）
    .venv/Scripts/python.exe -X utf8 tools/criteria_to_json.py --check    # 只校验（指纹漂移视为失败）
    .venv/Scripts/python.exe -X utf8 tools/criteria_to_json.py --accept   # 更新指纹记录并生成
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "player-tags-criteria.md"
GLOSSARY = ROOT / "docs" / "glossary.md"
RESULTS = ROOT / "results" / "operator-tags.json"
OUT = ROOT / "results" / "player-tags-criteria.json"
PARTS_DIR = ROOT / "agent_workspace" / "tag_pipeline" / "player_tags"

NOTE = "玩家体感 TAG 评定标准（前端「查看评定标准详情」抽屉文案）；源文件 docs/player-tags-criteria.md，生成脚本 tools/criteria_to_json.py"

# 数字守卫例外：{（TAG 名）：[允许出现但不在正本中的数字 token]}
NUM_EXEMPT: dict[str, list[str]] = {}

FP_RE = re.compile(r"<!--\s*源指纹：(.*?)\s*-->")
TOP_RE = re.compile(r"^##\s+(.+?)\s*$")
SUB_RE = re.compile(r"^###\s+(.+?)\s*$")
LABEL_RE = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")
TERM_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def norm_width(s: str) -> str:
    return s.translate(str.maketrans("０１２３４５６７８９％．＞＜", "0123456789%.><"))


# ---- 行内 md → HTML 行内标签（结果 JSON 不携带 md；前端白名单渲染，见 docs/ui-render-rules.md §7）----
MD_CODE_RE = re.compile(r"`([^`\n]+?)`")
MD_STRONG_RE = re.compile(r"\*\*(.+?)\*\*")


def md_inline(text: str) -> str:
    """源文件里写 `**强调**`、`反引号代码`，写出前转写为 `<strong>`／`<code>`。"""
    if not text:
        return text
    text = MD_CODE_RE.sub(r"<code>\1</code>", text)
    return MD_STRONG_RE.sub(r"<strong>\1</strong>", text)


def parse_sections(lines: list[str]):
    """返回 [(kind, key, body_lines)]；kind ∈ {'intro','tag','sub','terms'}，tag/sub 的 key 为名称。"""
    out = []
    cur = None
    for ln in lines:
        m_sub = SUB_RE.match(ln)
        m_top = TOP_RE.match(ln)
        if m_sub:
            cur = ("sub", m_sub.group(1), [])
            out.append(cur)
            continue
        if m_top:
            name = m_top.group(1)
            kind = "intro" if name == "导言" else ("terms" if name == "术语表" else "tag")
            cur = (kind, name, [])
            out.append(cur)
            continue
        if cur is not None:
            cur[2].append(ln)
    return out


def parse_body(body_lines: list[str]):
    """→ (intro, blocks, plain_items)。blocks＝[{'label','note','items'}]，items 元素为 str 或 {'text','items'}；
    plain_items＝首个标签之前出现的项目符号行（供「导言」用）。"""
    intro_lines: list[str] = []
    plain_items: list[str] = []
    blocks: list[dict] = []
    cur_block = None
    cur_item = None
    seen_label = False
    for ln in body_lines:
        m = LABEL_RE.match(ln)
        if m:
            seen_label = True
            cur_block = {"label": m.group(1).strip(), "note": m.group(2).strip(), "items": []}
            blocks.append(cur_block)
            cur_item = None
            continue
        if not seen_label:
            s = ln.strip()
            if not s:
                continue
            if re.match(r"^-\s+", s):
                plain_items.append(s.split("- ", 1)[1].strip())
            else:
                intro_lines.append(s)
            continue
        s = ln.rstrip("\n")
        if re.match(r"^\s*-\s+", s):
            text = s.split("- ", 1)[1].strip()
            if s.startswith("  - "):
                if cur_item is None:
                    continue
                cur_item.setdefault("items", []).append(text)
            else:
                cur_item = {"text": text}
                cur_block["items"].append(cur_item)
    intro = "".join(intro_lines)
    # 无块时也允许（导言等）：把初始行作为文本
    return intro, blocks, plain_items


def parse_terms(body_lines: list[str]):
    terms = []
    for ln in body_lines:
        m = TERM_RE.match(ln)
        if not m:
            continue
        name, text = m.group(1), m.group(2)
        if name in ("术语", "---") or set(name) <= set("-: "):
            continue
        terms.append({"name": name, "text": text})
    return terms


def clean_items(items):
    out = []
    for it in items:
        if isinstance(it, dict):
            entry = {"text": md_inline(it["text"])}
            if it.get("items"):
                entry["items"] = [md_inline(c) for c in it["items"]]
            out.append(entry)
        else:
            out.append(md_inline(it))
    return out


def part_file_of(tag_id: str) -> pathlib.Path | None:
    for p in sorted(PARTS_DIR.glob("[0-9][0-9]-*.json")):
        if p.name.startswith(tag_id[1:] + "-"):
            return p
    return None


def criteria_fingerprint(part: pathlib.Path) -> str:
    data = json.loads(part.read_text(encoding="utf-8"))
    texts = []
    in_std = False
    for b in data.get("body", []):
        if b.get("t") == "heading":
            t = b.get("text", "")
            if t.startswith("## "):
                in_std = "评定标准" in t
                continue
        if in_std and b.get("t") == "p":
            texts.extend(x.strip() for x in b.get("lines", []) if x.strip())
    raw = "\n".join(texts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def main() -> int:
    ap = argparse.ArgumentParser(description="评定标准源 → results/player-tags-criteria.json")
    ap.add_argument("--check", action="store_true", help="只校验、不写出；指纹漂移视为失败")
    ap.add_argument("--accept", action="store_true", help="更新源文件里的指纹记录")
    args = ap.parse_args()

    doc_text = DOC.read_text(encoding="utf-8")
    doc_lines = doc_text.splitlines()
    sections = parse_sections(doc_lines)

    # ---- 组装 JSON ----
    root_intro = {"text": "", "items": []}
    tags_out: list[dict] = []
    terms: list[dict] = []
    cur_tag: dict | None = None
    for kind, name, body in sections:
        if kind == "intro":
            intro, blocks, plain_items = parse_body(body)
            root_intro = {"text": md_inline(intro), "items": [md_inline(x) for x in plain_items]}
            continue
        if kind == "terms":
            terms = [{"name": t["name"], "text": md_inline(t["text"])} for t in parse_terms(body)]
            continue
        intro, blocks, plain_items = parse_body(body)
        entry = {"name": name, "intro": md_inline(intro), "sections": [{"label": b["label"], "note": md_inline(b["note"]), "items": clean_items(b["items"])} for b in blocks if b["note"] is not None]}
        # note 为空时省略
        for s in entry["sections"]:
            if not s["note"]:
                del s["note"]
        if kind == "tag":
            entry["subs"] = []
            tags_out.append(entry)
            cur_tag = entry
        else:
            head = name
            tag_name, sep, rest = head.partition(" · ")
            group, sep2, value = rest.partition(" / ")
            sub = {"group": group.strip(), "value": value.strip(), "intro": entry["intro"], "sections": entry["sections"]}
            if cur_tag is None or cur_tag["name"] != tag_name.strip():
                print(f"⚠ 子项标题的 TAG 名与当前节不符：{name}")
            else:
                cur_tag["subs"].append(sub)

    # ---- 对齐 id 与覆盖校验 ----
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    problems: list[str] = []
    tag_ids = {}
    expected_subs: dict[str, set] = {}
    for t in data.get("tags", []):
        if t.get("source") != "player":
            continue
        tag_ids[t["name"]] = t["id"]
        s = set()
        for m in t.get("members", []):
            for sub in m.get("subTags", []):
                s.add((sub.get("group", ""), sub.get("value", "")))
        expected_subs[t["name"]] = s

    for t in tags_out:
        if t["name"] not in tag_ids:
            problems.append(f"说明多于产物：{t['name']}")
        else:
            t["id"] = tag_ids[t["name"]]
    for name in tag_ids:
        if name not in [t["name"] for t in tags_out]:
            problems.append(f"缺少顶级说明：## {name}")
    for t in tags_out:
        name = t["name"]
        if name not in expected_subs:
            continue
        have = {(s["group"], s["value"]) for s in t["subs"]}
        for pair in sorted(expected_subs[name] - have):
            problems.append(f"缺少子项说明：{name} · {pair[0]} / {pair[1]}")
        for pair in sorted(have - expected_subs[name]):
            problems.append(f"子项说明多于产物：{name} · {pair[0]} / {pair[1]}")
    # id 排序保持文档顺序：文档顺序与 tag_ids 对齐后重排按 id 数字序
    tags_out.sort(key=lambda t: int(t["id"][1:]))

    # ---- 术语校验 ----
    body_text = doc_text
    for term in terms:
        parts = [p for p in term["name"].split("·") if p]
        if not any(p in body_text for p in parts):
            problems.append(f"术语未被引用：{term['name']}")
    names = [t["name"] for t in terms]
    dup = {n for n in names if names.count(n) > 1}
    for n in sorted(dup):
        problems.append(f"术语重复：{n}")

    # ---- 数字守卫 ----
    glossary = norm_width(GLOSSARY.read_text(encoding="utf-8"))
    doc_norm = norm_width(doc_text)
    term_sec_start = doc_norm.find("## 术语表")
    for t in tags_out:
        part = part_file_of(t.get("id", ""))
        if part is None:
            problems.append(f"找不到分文件：{t.get('id', '')} {t['name']}")
            continue
        src = norm_width(part.read_text(encoding="utf-8"))
        seg_start = doc_norm.find("## " + t["name"])
        seg_end = len(doc_norm)
        for t2 in tags_out:
            pos = doc_norm.find("## " + t2["name"], seg_start + 1)
            if pos != -1:
                seg_end = min(seg_end, pos)
        seg_end = min(seg_end, term_sec_start if term_sec_start != -1 else len(doc_norm))
        seg = doc_norm[seg_start:seg_end]
        tokens = sorted(set(re.findall(r"\d+(?:\.\d+)?(?= ?(?:%|格|秒|次|段|个|名|倍|级|点|发|帧|层))", seg)), key=float)
        missing = [x for x in tokens if x not in src and x not in glossary and x not in NUM_EXEMPT.get(t["name"], [])]
        if missing:
            problems.append(f"数字守卫 · {t['name']}：以下数字在正本与术语源中都找不到：{missing}")

    # ---- 指纹 ----
    fps = {}
    for t in tags_out:
        part = part_file_of(t.get("id", ""))
        if part is not None:
            fps[part.name[:2]] = criteria_fingerprint(part)
    recorded_raw = FP_RE.search(doc_text)
    recorded = {}
    if recorded_raw:
        for kv in recorded_raw.group(1).split():
            if "=" in kv:
                k, v = kv.split("=", 1)
                recorded[k] = v
    drift = [k for k, v in fps.items() if recorded.get(k) != v]
    if drift and recorded:
        names = "、".join(f"{k}" for k in sorted(drift))
        print(f"⚠ 正本指纹变化（{names}）——分文件「评定标准」节有改动，请复核本文件是否需要同步；复核后用 --accept 放行。")

    # ---- 输出 ----
    out = {"note": NOTE, "intro": root_intro, "tags": tags_out, "terms": terms}

    # ---- 行内标记：产物不得残留 md 行内语法（漏转写会让前端显示字面标记）----
    leftovers: list[str] = []

    def scan_md(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                scan_md(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan_md(v, f"{path}/[{i}]")
        elif isinstance(node, str) and ("**" in node or "`" in node):
            leftovers.append(path)

    scan_md({"intro": root_intro, "tags": tags_out, "terms": terms}, "$")
    for pth in leftovers:
        problems.append(f"行内标记 · {pth}：残留 md 语法（** 或反引号，应为 <strong>／<code>）")

    if problems:
        print("校验未通过：")
        for p in problems:
            print("  - " + p)
        return 1
    if drift and args.check and not args.accept:
        return 1
    if args.check:
        print(f"校验通过（{len(tags_out)} 个 TAG、{sum(len(t['subs']) for t in tags_out)} 个子项、{len(terms)} 条术语）。")
        return 0

    new_comment = "<!-- 源指纹：" + " ".join(f"{k}={fps[k]}" for k in sorted(fps)) + " -->"
    if recorded_raw:
        doc_text = FP_RE.sub(new_comment, doc_text, count=1)
    else:
        lines = doc_text.splitlines()
        lines.insert(1, "")
        lines.insert(2, new_comment)
        doc_text = "\n".join(lines) + "\n"
    if args.accept or not recorded_raw:
        DOC.write_text(doc_text, encoding="utf-8")
        print(f"已更新源文件指纹记录（{len(fps)} 个分文件）。")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}：{len(tags_out)} 个 TAG、{sum(len(t['subs']) for t in tags_out)} 个子项、{len(terms)} 条术语。")
    print("覆盖、术语、数字守卫校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

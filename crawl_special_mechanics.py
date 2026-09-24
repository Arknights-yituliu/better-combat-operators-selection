"""抓取 PRTS《特殊机制》页，产出术语表素材（docs/glossary.md 的追加章节）

用法：
  python -X utf8 crawl_special_mechanics.py            # 抓取 → 快照 + 规范化条目 JSON
  python -X utf8 crawl_special_mechanics.py --emit     # 另输出 glossary 章节文本到暂存文件
  python -X utf8 crawl_special_mechanics.py --apply    # 追加进 docs/glossary.md（去重；移除旧手写块）

产物：
  material_datas/PRTS/特殊机制/特殊机制.md            页面快照（逐条一行，可作证据引用）
  material_datas/tag_pipeline/_special_mechanics.json 规范化条目（名称/释义/备注/举例/章节/行号）
  material_datas/tag_pipeline/_special_mechanics.glossary.md（--emit 的暂存产物，供人工复核）

收录范围：与干员机制相关的条目（见 EXCLUDE）；元素损伤/元素伤害的重复结算归各元素 TAG，
移动创伤等已在术语表中的条目按已有文本处理（OVERRIDE）。请求带完整浏览器头并节流，
与 crawl_prts.py / crawl_ranges.py 同规。
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PAGE = "特殊机制"
BASE = "https://prts.wiki"
API = BASE + "/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE + "/w/%E9%A6%96%E9%A1%B5",
}
SNAPSHOT = ROOT / "material_datas" / "PRTS" / PAGE / f"{PAGE}.md"
ENTRIES = ROOT / "material_datas" / "tag_pipeline" / "_special_mechanics.json"
STAGING = ROOT / "material_datas" / "tag_pipeline" / "_special_mechanics.glossary.md"
DOC = ROOT / "docs" / "glossary.md"

# PRTS 页章节 → 术语表章节（只列收录的；引擎机制整节不收）
SECTION_MAP = {
    "常用的基础机制": "基础机制",
    "额外术语": "额外术语",
    "战场效果": "战场效果",
    "伤害机制": "伤害机制",
    "复用机制": "复用机制",
    "特殊计算方式": "特殊计算",
}
GLOSSARY_SECTIONS = ["基础机制", "额外术语", "战场效果", "伤害机制", "复用机制", "特殊计算"]

# 不收：纯引擎实现、关卡/活动/联动专属、纯敌方行为且干员侧无判定价值的条目
EXCLUDE = {
    # 引擎机制
    "静态刚体", "失衡移动阻尼",
    # 关卡/活动/联动专属
    "洋红蒸汽", "纯白水汽", "田地", "病害值", "稳固锁链", "兔子洞", "御龙",
    "伤害相性（P3R）",
    # 敌方出生/波次/行为
    "无害目标", "非首要目标", "被阻挡时使用相同攻击", "被阻挡时使用不同攻击", "空攻击",
    "可空降", "闪现", "闪现前进", "明晦属性", "载客", "“叠叠乐”", "附着", "弱点部位",
    "鉴定", "能量", "暴露", "直击", "交战", "搜捕", "固定弱点", "强制部署",
    "已损失生命值判定", "释放当前波次",
}
# 「干员」并入「无职业」的备注（术语名会致 UI 正文全量误标注）
SKIP = {"干员"}
MERGE_INTO = {
    "无职业": ("干员条：职业为先锋／近卫／狙击／重装／医疗／辅助／术师／特种之一；"
             "许多游戏机制写明“只能对干员生效”，其含义通常便是“职业为这八者之一”，有时还限定必须为角色类单位。"),
}
# 已在术语文档中的条目：沿用文档现有文本（此处按生成的条文覆盖，保证格式合法）
OVERRIDE = {
    "移动创伤": dict(
        definition=(
            "每个可移动单位自出现后便会每隔5帧记录自己当前位置并与上次位置计算直线距离，"
            "计入总移动距离中（单位为格）。移动创伤（Rupture）便是利用目标身上的总移动距离数值，"
            "根据每两次更新时检测到的数值之差创造伤害的机制。"
        ),
        notes=[
            "移动创伤Buff开始时，将记录目标当前的总移动距离；接下来每 0.067 秒（2 帧）更新一次，"
            "Buff结束时会额外更新一次，每次更新对Buff持有者造成 "
            "(当前数值-上次更新时数值)×每格伤害比例 的预计算的真实持续伤害；若两次更新间数值差>4格，则不会造成任何伤害。",
            "每次更新时，即使两次更新间数值差为0也会产生一次伤害，但会因为“攻击力”为0而在伤害计算后直接取消。",
        ],
    ),
}


def fetch_wikitext() -> str:
    r = requests.get(
        API,
        params={"action": "parse", "page": PAGE, "prop": "wikitext",
                "format": "json", "formatversion": "2"},
        headers=HEADERS, timeout=40,
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise SystemExit(f"API 错误：{data['error']}")
    return data["parse"]["wikitext"]


def split_params(s: str) -> list[str]:
    """按顶层 | 切分模板参数（跳过 {{}} 与 [[]] 内部）。"""
    out, buf, depth, i = [], [], 0, 0
    while i < len(s):
        if s.startswith("{{", i) or s.startswith("[[", i):
            depth += 1
            buf.append(s[i:i + 2])
            i += 2
            continue
        if s.startswith("}}", i) or s.startswith("]]", i):
            depth -= 1
            buf.append(s[i:i + 2])
            i += 2
            continue
        if s[i] == "|" and depth == 0:
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(s[i])
        i += 1
    out.append("".join(buf))
    return out


def render(text: str) -> str:
    """模板/链接/强调 → 纯文本；<br> → 换行。"""
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    t = re.sub(r"\{\{dot\}\}", "• ", t)
    t = re.sub(r"\{\{=\}\}", "=", t)
    t = re.sub(r"\{\{参考客户端版本\}\}", "", t)
    t = re.sub(r"\{\{攻击范围/兼容版\}\}", "", t)
    # 按最内层优先反复化掉模板
    for _ in range(6):
        t = re.sub(r"\{\{(?:异常效果|术语|color|color2|mdi|[^{}|]*)\|([^{}|]*)\|([^{}|]*)\}\}", r"\2", t)
        t = re.sub(r"\{\{(?:异常效果|术语|mdi|[^{}|]*)\|([^{}|]*)\}\}", r"\1", t)
        t = re.sub(r"\{\{[^{}|]*\}\}", "", t)
    t = re.sub(r"\[\[:?分类:([^|\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[/[^\s\]]+(?:\s+“[^”]*”)?\]", "", t)
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[\[文件:[^\]]*\]\]", "", t)
    t = re.sub(r"'''|''", "", t)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def example_names(raw: str) -> list[str]:
    """从举例列的图片链接里取示例单位名（link=干员名）。"""
    names: list[str] = []
    for m in re.finditer(r"link=([^|\]}]+)", raw):
        n = m.group(1).split("#")[0].strip()
        if n and n not in names:
            names.append(n)
    return names


def join_text(cur: str, seg: str) -> str:
    """续接片段：上一段以句读结尾时直接接，否则补句号。"""
    if cur and cur.rstrip()[-1] not in "。！？：；、”」）)":
        cur = cur.rstrip() + "。"
    return cur + seg


def parse_entries(wikitext: str) -> list[dict]:
    entries: list[dict] = []
    cur_section = ""
    section_sub = ""
    for lineno, ln in enumerate(wikitext.split("\n"), 1):
        m = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", ln)
        if m:
            level, title = len(m.group(1)) - 1, m.group(2)
            if level == 2:
                cur_section, section_sub = title, ""
            else:
                section_sub = title
            continue
        for tm in re.finditer(r"\{\{特殊机制表格\|", ln):
            body = ln[tm.end():]
            params = split_params(body)
            name = render(params[0]).strip()
            raw_example = params[2] if len(params) > 2 else ""
            extra = ""
            m_extra = re.match(r"\s*额外简介\s*=\s*(.*)$", raw_example, flags=re.S)
            if m_extra:
                extra = render(m_extra.group(1))
                raw_example = ""
            intro = render(params[1]) if len(params) > 1 else ""
            example = render(raw_example)
            names = example_names(ln)
            if not name or not intro:
                continue
            entries.append({
                "section": cur_section,
                "sub": section_sub,
                "name": name,
                "intro": intro,
                "extra": extra,
                "example": example,
                "example_names": names,
                "line": lineno,
            })
    return entries


def to_block(e: dict) -> list[str]:
    """条目 → glossary 块（术语名 / 释义 / ※备注…）。"""
    name = e["name"]
    if name in OVERRIDE:
        o = OVERRIDE[name]
        return [name, o["definition"]] + [f"※{n}" for n in o["notes"]]
    segments = [s for s in e["intro"].split("\n") if s]
    if not segments:
        return []
    definition = ""
    if segments[0].startswith("※"):
        definition = segments[0].lstrip("※").strip()
        segments = segments[1:]
    else:
        definition = segments[0]
        segments = segments[1:]
    notes: list[str] = []
    for seg in segments:
        if seg.startswith("※"):
            notes.append(seg.lstrip("※").strip())
        elif notes:
            notes[-1] += "\n" + seg
        else:
            definition = join_text(definition, seg)
    for seg in [s for s in e["extra"].split("\n") if s]:
        if seg.startswith("※") or not notes:
            notes.append(seg.lstrip("※").strip())
        else:
            notes[-1] += "\n" + seg
    merged = MERGE_INTO.get(name)
    if merged:
        notes.append(merged)
    example = re.sub(r"^※\s*", "", e["example"].strip()).strip()
    if example and example not in ("暂无", "—", "-") and not example.startswith("文件:"):
        notes.append(example)
    names = [n for n in e.get("example_names", []) if n]
    if names:
        notes.append("举例：" + "、".join(names))
    return [name, definition] + [f"※{n}" for n in notes]


def build_glossary(entries: list[dict]) -> str:
    by_section: dict[str, list[list[str]]] = {s: [] for s in GLOSSARY_SECTIONS}
    seen: set[str] = set()
    for e in entries:
        if e["name"] in EXCLUDE or e["name"] in seen or e["name"] in SKIP:
            continue
        sec = SECTION_MAP.get(e["section"])
        if sec is None:
            continue
        seen.add(e["name"])
        block = to_block(e)
        if block:
            by_section[sec].append(block)
    out: list[str] = []
    for sec in GLOSSARY_SECTIONS:
        blocks = by_section[sec]
        if not blocks:
            continue
        out.append(sec)
        out.append("")
        for block in blocks:
            out += block + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="输出 glossary 章节文本到暂存文件")
    ap.add_argument("--apply", action="store_true", help="追加进 docs/glossary.md")
    ap.add_argument("--input", help="改用本地 wikitext 快照（不联网）")
    args = ap.parse_args()

    if args.input:
        wikitext = Path(args.input).read_text(encoding="utf-8")
    else:
        wikitext = fetch_wikitext()
        time.sleep(1.2)
        (SNAPSHOT.parent / f"{PAGE}.wikitext").write_text(wikitext, encoding="utf-8")
    entries = parse_entries(wikitext)
    if len(entries) < 80:
        raise SystemExit(f"条目数异常：{len(entries)}")

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    snap = [f"# {PAGE}（PRTS 快照；{len(entries)} 条）", ""]
    cur = ""
    for e in entries:
        if e["section"] != cur:
            cur = e["section"]
            snap += ["", f"## {cur}", ""]
        snap.append(f"### {e['name']}（第 {e['line']} 行）")
        snap += e["intro"].split("\n")
        if e["example"]:
            snap.append(f"举例：{e['example']}")
        snap.append("")
    SNAPSHOT.write_text("\n".join(snap), encoding="utf-8")

    ENTRIES.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")

    text = build_glossary(entries)

    kept = [e["name"] for e in entries if e["name"] not in EXCLUDE]
    print(f"快照 {SNAPSHOT}（{len(entries)} 条）")
    print(f"规范化 {ENTRIES}")
    print(f"收录 {len(kept)} 条 / 排除 {len(entries) - len(kept)} 条（另：与现有术语重名者按文档处理）")
    if args.emit or args.apply:
        STAGING.write_text(text, encoding="utf-8")
        print(f"章节文本 {STAGING}（{len(text.splitlines())} 行）")
    if args.apply:
        # 移除工作区里未成形的手写块（缺术语名行的 移动创伤 段）
        doc = DOC.read_text(encoding="utf-8")
        doc2 = re.sub(
            r"\n每个可移动单位自出现后便会每隔5帧记录[^\n]*\n[^\n]*\n[^\n]*\n※每次更新时，即使两次更新间数值差为0[^\n]*\n?$",
            "\n", doc)
        doc2 = doc2.rstrip("\n") + "\n\n" + text
        DOC.write_text(doc2, encoding="utf-8")
        print(f"已追加进 {DOC}")


if __name__ == "__main__":
    main()

"""docs/glossary.md -> results/combat_glossary.json

术语文件的格式约定（块与块之间以空行分隔，块内每行代表一个术语）：

    战斗术语            <- 文档标题（仅第一行的这一处）
    状态                <- 章节名（SECTIONS 之一），可与术语同处一块
    停顿                <- 术语名
    移动速度降低80%      <- 释义（术语名的下一行）
    ※最终乘算，同名效果不叠加   <- 备注（以 ※ 开头；不以 ※ 开头的行是上一条备注的续行）

    例外：Fever 的术语名与释义写在同一行（"Fever Fever累计至450点时，…"），
    当术语名下一行不是释义时按首个半角空格拆分。

行内标记：释义与备注可按 md 写 `**强调**`、`反引号代码`，写出前转写为 HTML 行内标签
（`<strong>`／`<code>`）——结果 JSON 不携带 md 语法（前端按白名单渲染，见 docs/ui-render-rules.md §7）。

校验：章节名必须命中 SECTIONS；每个术语必须有非空释义；备注续行必须紧跟备注。
不满足则直接报错，绝不静默产出错的 JSON。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "glossary.md"
DST = ROOT / "results" / "combat_glossary.json"

TITLE = "战斗术语"
SECTIONS = ["状态", "技能相关", "元素相关", "干员分类", "杂项机制",
            "基础机制", "额外术语", "战场效果", "伤害机制", "复用机制", "特殊计算"]
NOTE_MARK = "※"


# 行内 md → HTML 行内标签（结果 JSON 不携带 md；前端白名单渲染，见 docs/ui-render-rules.md §7）
MD_CODE_RE = re.compile(r"`([^`\n]+?)`")
MD_STRONG_RE = re.compile(r"\*\*(.+?)\*\*")


def md_inline(text: str) -> str:
    """源文件里写 `**强调**`、`反引号代码`，写出前转写为 `<strong>`／`<code>`。"""
    if not text:
        return text
    text = MD_CODE_RE.sub(r"<code>\1</code>", text)
    return MD_STRONG_RE.sub(r"<strong>\1</strong>", text)


def split_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    cur: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line:
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def parse_term(lines: list[str]) -> dict:
    """lines 为去掉章节名后的块内容：术语名 [+ 释义] + 备注若干。"""
    if len(lines) >= 2 and not lines[1].startswith(NOTE_MARK):
        name, definition, rest = lines[0], lines[1], lines[2:]
    elif " " in lines[0]:  # 名与释义同行
        name, definition = lines[0].split(" ", 1)
        rest = lines[1:]
    else:
        raise SystemExit(f"术语 {lines[0]!r} 缺少释义行")

    if not definition or definition.startswith(NOTE_MARK):
        raise SystemExit(f"术语 {name!r} 的释义异常：{definition!r}")

    notes: list[str] = []
    for line in rest:
        if line.startswith(NOTE_MARK):
            notes.append(line[len(NOTE_MARK):].strip())
        elif notes:
            notes[-1] += "\n" + line
        else:
            raise SystemExit(f"术语 {name!r} 出现无归属的备注续行：{line!r}")
    if any(not n for n in notes):
        raise SystemExit(f"术语 {name!r} 存在空备注")

    term: dict = {"name": name, "definition": md_inline(definition)}
    if notes:
        term["notes"] = [md_inline(n) for n in notes]
    return term


def main() -> None:
    sections: list[dict] = []
    for block in split_blocks(SRC.read_text(encoding="utf-8")):
        for i, line in enumerate(block):
            if line == TITLE or line in SECTIONS:
                if line in SECTIONS:
                    sections.append({"name": line, "terms": []})
            else:
                if not sections:
                    raise SystemExit(f"术语 {line!r} 出现在章节之前")
                sections[-1]["terms"].append(parse_term(block[i:]))
                break

    found = [s["name"] for s in sections]
    if found != SECTIONS:
        raise SystemExit(f"章节与预期不符：{found}")

    data = {"title": TITLE, "sections": sections}
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    nterms = sum(len(s["terms"]) for s in sections)
    nnotes = sum(len(t.get("notes", [])) for s in sections for t in s["terms"])
    for s in sections:
        print(f"  {s['name']}: {len(s['terms'])} terms")
    print(f"wrote {DST.relative_to(ROOT)}: {len(sections)} sections, {nterms} terms, {nnotes} notes")


if __name__ == "__main__":
    sys.exit(main())

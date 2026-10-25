# -*- coding: utf-8 -*-
"""文档一致性校验：让「写死的约定」不会静默腐烂。

背景：`docs/version-update-quickstart.md`（快线）把版本更新类任务的阅读预算与流程写死了，
但它引用的文件名、检查项数量、节级锚点都由人维护——一旦 `tools/run_all_checks.py` 增删一项、
或 `docs/rulings.md` 改了节标题，文档就会静默失效（这类漂移真的发生过：「六项」实为九项、
「apply_tag_order 是第 8 步」实为第 5 项）。本工具把四类漂移变成红灯。

校验四类（只报告，不改任何文件）：

1. **检查项计数**：`tools/run_all_checks.py` 的 `CHECKS` 实际条数 vs 文档里写的「N 项一体／N 项校验／N 项全绿／十项」。
2. **nbsp 步序号**：文档里「run_all_checks 的第 N 项／第 N 步」与实际 `CHECKS` 顺序是否对得上。
3. **必读路径存在性**：快线 §1「阅读预算」必读表里反引号包住的仓库相对路径逐一 `exists()`。
4. **节级锚点**：文档里形如 `` `path`「标题」 `` 的引用，目标文件里必须存在同名 `## 标题` 或 `### 标题`。

用法：
    .venv/Scripts/python.exe -X utf8 tools/doc_consistency.py           # 校验
    .venv/Scripts/python.exe -X utf8 tools/doc_consistency.py --list    # 列出当前 CHECKS 清单
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]

CHECKS_PY = ROOT / "tools" / "run_all_checks.py"
QUICKSTART = ROOT / "docs" / "version-update-quickstart.md"

# 需要与 CHECKS 条数保持一致的文档
COUNT_DOCS = (
    ROOT / "docs" / "version-update-quickstart.md",
    ROOT / "docs" / "commands.md",
    ROOT / "docs" / "output-standard.md",
)

AGENTS = ROOT / "AGENTS.md"

# AGENTS.md 是「纯路线图」：行数有硬预算，且不得重新长出代码块或专文内容。
# 这两条是本次瘦身的落点——不写进校验，内容迟早回流。
AGENTS_MAX_LINES = 100
AGENTS_FORBIDDEN = {
    "```": "代码块（命令已移至 docs/commands.md）",
    "## Data flow": "数据流节（已移至 docs/architecture.md）",
    "## Commands": "命令节（已移至 docs/commands.md）",
    "## Classification conventions": "分类约定节（已移至 docs/classification-conventions.md）",
    "## What this repo is": "项目介绍节（已移至 docs/architecture.md）",
    "File authority map": "文件权属表（已移至 docs/architecture.md）",
}

# 全量中文化：这些手写文档不得出现英文散文行（代码围栏内跳过）
LANG_DOCS = [
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "gui/README.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/commands.md",
    "docs/classification-conventions.md",
    "docs/crawling-and-strip.md",
    "docs/history-notes.md",
    "docs/agent-primer.md",
    "docs/version-update-quickstart.md",
    "docs/scan-protocol.md",
    "docs/term-map.md",
    "docs/concept.md",
    ".claude/README.md",
    ".claude/agents/tag-rewrite.md",
]
LANG_DOCS += [f".claude/skills/{d}/SKILL.md" for d in (
    "add-new-operator", "add-player-tag", "crawl-prts-operator", "handoff",
    "reverify-numbers", "solidify-criteria", "tag-batch-rewrite", "update-version")]

CJK_RE = re.compile(r"[一-鿿]")
EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
PATH_TOKEN_RE = re.compile(r"\S*(?:/|\\|_[a-z0-9]+\.(?:py|json|md|tsv|txt))\S*")
URL_RE = re.compile(r"https?://\S+")
# frontmatter 里这些键的取值是标识符/工具名，本来就该是英文
EN_ALLOWED_FRONTMATTER = ("name:", "allowed-tools:")

PROBLEMS: list[str] = []


def problem(msg: str) -> None:
    PROBLEMS.append(msg)


# ---------------------------------------------------------------- 读 CHECKS

def load_checks() -> list[str]:
    """从 run_all_checks.py 的 CHECKS 字面量里取每项的名称（第一项字符串）。"""
    src = CHECKS_PY.read_text(encoding="utf-8")
    m = re.search(r"^CHECKS[^=]*=\s*\[(.*?)^\]", src, re.S | re.M)
    if not m:
        return []
    body = m.group(1)
    # 每项形如 ("名称", [命令…]),
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*\[', body)


# ---------------------------------------------------------------- 1&2 计数与步序

CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
             "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15}

# 「六项一体」「九项全绿」「十项」这类。前面是「第」的是步序（见 STEP_RE）；
# 「一项」「这一项」「多项」是量词短语、不是套件条数，一律不算。
COUNT_RE = re.compile(
    r"(?P<num>[0-9]+|[二三四五六七八九十][一二三四五六七八九十]?)\s*项(?:一体|校验|全绿|检查)?")


def count_hits(line: str):
    """一行的「N 项」计数命中 → [(原文, N)]。"""
    out = []
    for m in COUNT_RE.finditer(line):
        start = m.start()
        if start > 0 and line[start - 1] in "第这那每既统同":
            continue
        num = m.group("num")
        if num == "一":
            continue
        v = cn_to_int(num)
        if v is not None:
            out.append((m.group(0), v))
    return out


# 「run_all_checks 的第 5 项」「第 8 步」
STEP_RE = re.compile(r"run_all_checks\s*的\s*第\s*([0-9]+)\s*[项步]")


def cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    return CN_DIGITS.get(s)


def check_counts(n: int) -> None:
    for doc in COUNT_DOCS:
        if not doc.exists():
            problem(f"{rel(doc)}：文件不存在")
            continue
        text = doc.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for raw, v in count_hits(line):
                if v == n:
                    continue
                # 只对「N 项」且上下文是校验套件的行报错（避免误伤「三类子表」之类的其它计数）
                if "run_all_checks" not in line and "项校验" not in line and "项一体" not in line \
                        and "项全绿" not in line and "项通过" not in line:
                    continue
                problem(f"{rel(doc)}:{lineno}：写「{raw}」，实际 CHECKS 为 {n} 项")


def check_steps(checks: list[str]) -> None:
    for doc in COUNT_DOCS:
        if not doc.exists():
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            m = STEP_RE.search(line)
            if not m:
                continue
            idx = int(m.group(1))
            if not 1 <= idx <= len(checks):
                problem(f"{rel(doc)}:{lineno}：写「第 {idx} 项」，但 CHECKS 只有 {len(checks)} 项")
                continue
            actual = checks[idx - 1]
            # 该行提到的工具名应与该序号的实际检查项对得上
            tool = re.search(r"tools/(\w+)\.py", line)
            if tool and tool.group(1) not in actual:
                problem(f"{rel(doc)}:{lineno}：写「第 {idx} 项」配 `{tool.group(0)}`，"
                        f"但第 {idx} 项实际是「{actual}」")


# ---------------------------------------------------------------- 3 必读路径

def check_required_paths() -> None:
    if not QUICKSTART.exists():
        problem("docs/version-update-quickstart.md 不存在（快线是本工具的校验对象）")
        return
    text = QUICKSTART.read_text(encoding="utf-8")
    # 只取 §1「阅读预算」到下一个二级标题之前
    m = re.search(r"^## 1\. 阅读预算.*?(?=^## )", text, re.S | re.M)
    if not m:
        problem("快线缺少 §1「阅读预算」——阅读清单无处可校")
        return
    section = m.group(0)
    base = QUICKSTART.parent.parent  # 仓库根
    seen: set[str] = set()
    for raw in re.findall(r"`([^`\n]+)`", section):
        cand = raw.split()[0].strip()
        # 只校验像仓库相对路径的（含 / 且以已知扩展名或目录结尾），跳过命令与占位符
        if "/" not in cand or cand.startswith("-") or "<" in cand or " " in cand:
            continue
        if not re.search(r"\.(md|py|json)$|/$", cand):
            continue
        if cand.startswith("tools/") is False and cand.split("/")[0] not in (
                "docs", "tools", "crawlers", "agent_workspace", "material_datas", "gui", "results"):
            continue
        if cand in seen:
            continue
        seen.add(cand)
        # 含通配符/占位符的跳过
        if "*" in cand or "<" in cand:
            continue
        if not (base / cand).exists():
            problem(f"快线 §1 必读表引用了不存在的路径：{cand}")


# ---------------------------------------------------------------- 4 节级锚点

ANCHOR_RE = re.compile(r"`((?:docs|agent_workspace|\.claude)/[\w\-./]+\.md)`\s*[「『]([^」』]+)[」』]")


def _title_variants(title: str) -> list[str]:
    """同一小节的几种合法写法：`／` 与 `、` 在不同文件里互用（「条件分条／备注分块」对「条件分条」「备注分块」）。"""
    t = title.strip()
    out = [t]
    for a, b in (("／", "、"), ("、", "／"), ("／", "/"), ("/", "／")):
        if a in t:
            out.append(t.replace(a, b))
    return list(dict.fromkeys(out))


def _has_heading(body: str, title: str) -> bool:
    """该小节是否真实存在：`#`–`####` 标题（允许序号前缀），或行首加粗小标题 `**标题**：`。

    本仓库两种锚点风格并存：`## 条件分条`（concept）与 `**元素值（EP）与爆条节奏**（演算必读）：`
    （mechanism-understanding 的段内小标题）——两种都算解析成功。
    """
    for t in _title_variants(title):
        esc = re.escape(t)
        head = re.compile(r"^#{1,4}\s*(?:[零一二三四五六七八九十百]+、|[0-9]+[.、]?\s*)?" + esc + r"\s*$", re.M)
        if head.search(body):
            return True
        bold = re.compile(r"^\*\*" + esc + r"\*\*", re.M)
        if bold.search(body):
            return True
        # 组合式（多个小节名写在一起，如「条件分条／备注分块」）：各段都存在即可
        parts = [p for p in re.split(r"[／/、]", t) if p.strip()]
        if len(parts) > 1 and all(_has_heading(body, p) for p in parts):
            return True
    return False


def check_anchors() -> None:
    files = [
        ROOT / "docs" / "version-update-quickstart.md",
        ROOT / "AGENTS.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "commands.md",
        ROOT / "docs" / "classification-conventions.md",
        ROOT / "docs" / "crawling-and-strip.md",
        ROOT / "docs" / "README.md",
        ROOT / ".claude" / "skills" / "handoff" / "SKILL.md",
        ROOT / ".claude" / "skills" / "update-version" / "SKILL.md",
    ]
    for doc in files:
        if not doc.exists():
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for target, title in ANCHOR_RE.findall(line):
                path = ROOT / target
                if not path.exists():
                    problem(f"{rel(doc)}:{lineno}：锚点引用的文件不存在 `{target}`")
                    continue
                if not _has_heading(path.read_text(encoding="utf-8"), title):
                    problem(f"{rel(doc)}:{lineno}：`{target}` 里找不到小节「{title}」")


# ---------------------------------------------------------------- 5 AGENTS.md 边界

def check_agents_shape() -> None:
    """AGENTS.md 是「纯路线图」：行数有预算，且不得重新长出代码块与专文内容。"""
    if not AGENTS.exists():
        problem("AGENTS.md 不存在（它是任务分派入口）")
        return
    lines = AGENTS.read_text(encoding="utf-8").splitlines()
    if len(lines) > AGENTS_MAX_LINES:
        problem(f"AGENTS.md 已 {len(lines)} 行，超出纯路线图预算 {AGENTS_MAX_LINES} 行——"
                f"请把内容移入 docs/architecture.md／docs/commands.md 等专文")
    for lineno, line in enumerate(lines, 1):
        for token, why in AGENTS_FORBIDDEN.items():
            if token in line:
                problem(f"AGENTS.md:{lineno}：出现{why}——{token}")


# ---------------------------------------------------------------- 6 英文散文

def _is_prose_english(line: str) -> bool:
    """判定一行是否为英文散文：中文极少、且英文词占绝对多数。

    先剥掉**不算散文**的部分——反引号代码、路径／文件名、URL、以及 frontmatter 的
    `name:`／`allowed-tools:`——再要求「≥4 个英文词」且「英文词数 > 中文字数 × 2」。
    这样纯路径表格、命令清单、YAML 元数据都不会被误判。
    """
    s = CODE_SPAN_RE.sub(" ", line)
    s = URL_RE.sub(" ", s)
    s = PATH_TOKEN_RE.sub(" ", s)
    if s.lstrip().startswith(EN_ALLOWED_FRONTMATTER):
        return False
    en = len(EN_WORD_RE.findall(s))
    cjk = len(CJK_RE.findall(s))
    return en >= 4 and en > cjk * 2


def check_language() -> None:
    for relpath in LANG_DOCS:
        doc = ROOT / relpath
        if not doc.exists():
            problem(f"撰写语言清单里的文件不存在：{relpath}")
            continue
        in_fence = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if _is_prose_english(line):
                problem(f"{relpath}:{lineno}：英文散文行（正文应用中文）——{line.strip()[:60]}")


# ---------------------------------------------------------------- 汇总

def rel(p: pathlib.Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="文档一致性校验（阅读预算 / 检查项计数 / 节级锚点 / AGENTS 边界 / 撰写语言）")
    ap.add_argument("--list", action="store_true", help="列出当前 run_all_checks 的检查项")
    args = ap.parse_args()

    checks = load_checks()
    if not checks:
        print("✗ 读不到 tools/run_all_checks.py 的 CHECKS 清单")
        return 1
    if args.list:
        for i, name in enumerate(checks, 1):
            print(f"{i:>2}. {name}")
        return 0

    n = len(checks)
    check_counts(n)
    check_steps(checks)
    check_required_paths()
    check_anchors()
    check_agents_shape()
    check_language()

    if PROBLEMS:
        print(f"文档一致性：{len(PROBLEMS)} 条问题（CHECKS 共 {n} 项）")
        for p in PROBLEMS:
            print("  - " + p)
        return 1
    print(f"文档一致性：通过（CHECKS {n} 项、必读路径与节级锚点均可解析、AGENTS 边界与撰写语言合规）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

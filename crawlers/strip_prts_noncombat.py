# -*- coding: utf-8 -*-
"""One-off: strip non-combat content from material_datas/PRTS and re-anchor evidence.

The crawler now applies crawl_prts.strip_noncombat() to every page it writes, but
the corpus on disk predates it. This script backfills the same transform — the
plan/render logic is imported from crawl_prts, not reimplemented, so the two can
never drift apart.

Deleting lines shifts every 文件:行号 evidence pointer below them, and those
pointers are the project's evidence layer (~8k of them across the part files,
the official module files, docs/ and agent_workspace/workdocs/待验证复算.md). So the same pass records an
old→new line map per file and rewrites every pointer through it, asserting line
by line that the rewritten anchor still holds byte-identical text. A pointer that
would land on deleted content is reported as a collision and left untouched —
by design that should be an empty list, and a non-empty one needs a hand edit.

Usage:
  python -X utf8 crawlers/strip_prts_noncombat.py --dry-run    # report, write nothing
  python -X utf8 crawlers/strip_prts_noncombat.py              # strip + rewrite pointers
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from crawl_prts import plan_strip, render_strip

ROOT = Path(__file__).resolve().parents[1]
PRTS_DIR = ROOT / "material_datas" / "PRTS"
SKIP_DIRS = {"_rules", "特殊机制"}

# Files carrying 文件:行号 pointers. Enumerate by directory, not by guessing which
# ones matter: a file one level outside a listed glob (official-fullmap-aura.md
# sits beside official_tags/, not inside it) is skipped silently and keeps stale
# numbers, so every directory known to hold pointers is listed explicitly.
REF_GLOBS = [
    "agent_workspace/tag_pipeline/*.md",
    "agent_workspace/tag_pipeline/player_tags/*.md",
    "agent_workspace/tag_pipeline/player_tags/**/*.md",
    "agent_workspace/tag_pipeline/player_tags/**/*.jsonl",
    "agent_workspace/tag_pipeline/player_tags/**/*.json",
    "agent_workspace/tag_pipeline/official_tags/*.json",
    "docs/*.md",
    "agent_workspace/workdocs/*.md",
    "information_records/*.md",
    "*.md",
    "*.py",
    "**/*.py",
]

# Fully generated from the part files (_merge_to_docs.py writes the whole file),
# so it is regenerated after the strip rather than rewritten here.
REF_EXCLUDE = {"docs/player-tags-members.md"}

# Reviewed deviations from the mechanical line map: pointers moved by hand onto the
# line that actually supports the claim, rather than onto whatever line the map
# points at. Each is (source file, HEAD-side atom). --audit reports anything not
# listed here, so adding to this set is the deliberate act of accepting a deviation.
ACCEPTED = {
    # 元素损伤 EP（元素值）机制修正轮：03-吃拐一轮秒.json 的 折光 慢热行按裁定移出成员表，
    # 其依据中的两处引用随整行删除消失——属有意为之的整行移除（裁定见 docs/rulings.md §十六）。
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "84"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "124"),
    # tag-part/1 迁移：`_brief.md` §4 的产出模板由 md 表格示例改为 JSON 骨架，旧模板中的示例
    # 引用（`维什戴尔/维什戴尔.md:133`）随整块替换移除——属有意为之的文档改写。
    ("agent_workspace/tag_pipeline/player_tags/_brief.md", "133"),
    # `agent_workspace/workdocs/待裁定.md`每轮整体重写（其条目随裁定折入后移除），旧版里引用过的 11-阻挡数5 例证（`珊比.md:33`）随重写消失——属流程性的整文件替换。
    ("agent_workspace/workdocs/待裁定.md", "33"),
    # 第九批：13-高档控制.md 的边界记录在引用紧前方改写了散文（灵知由「另见待裁」改为「已纳入」），
    # 引用本身未变、仍指向同一处原文——属「键分词误报」，逐条放行；凛御银灰／灵知 的原「待裁」
    # 引用随该块移除、已转入成员表新行，同属有意为之的整块替换。
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "85"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "86"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "87"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "88"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "89"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "90"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "91"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "92"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "93"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "94"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "113"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "61"),
    # 根《待裁定.md》第九批整体重写：旧版号角行引用的 号角/号角.md:155 随重写消失。
    ("待裁定.md", "155"),
    # 11-阻挡数5.md 三行（珊比／酒神／余）的备注原内联了证据，按「证据只写进依据列」
    # 移到依据列后改用全路径写法（`珊比/珊比.md:…`），原短路径写法（`珊比.md:121`）随之消失——
    # 属有意为之的写法统一，非漏改。
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "121"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "122"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "120"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "121"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "122"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "21"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "26"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "28"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "101"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "102"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "103"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "104"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "105"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "106"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "107"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "108"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "109"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "110"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "55"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "56"),
    # 连射「可及距离 ≥3 格」门槛的成员调整：以下 9 行（祐天寺若麦、聆音、维娜·维多利亚、
    # 百炼嘉维尔、归溟幽灵鲨、龙舌兰、山、瑕光、傀影）由主进程移出 03-吃拐一轮秒.md，
    # 其被移除行所带的指针随行消失——属有意为之的成员变动，非漏改（见该文件「边界与排除记录」H）。
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "17"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "112"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "82"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "64"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "65"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "157"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "183"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "58"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "59"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "60"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "116"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "135"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "160"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "36"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "123"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "217"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "86"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "179"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "64"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "65"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "130"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "113"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "115"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "188"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "34"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "126"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "127"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "128"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "129"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "130"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "131"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "132"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "133"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "134"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "135"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "59"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "60"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "220"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "227"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "33"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "123"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "124"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "125"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "126"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "127"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "128"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "129"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "130"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "131"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "132"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "67"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "227"),
    # 深海色的原锚点是证章标题，并不支撑「所属势力【阿戈尔】、天赋为召唤物系」这句
    # 断言；改为指向属性表的所属势力行与「召唤触手」天赋行（现在写作 34,54-58）。
    ("agent_workspace/tag_pipeline/player_tags/12-阵容组合.json", "144"),
    ("agent_workspace/tag_pipeline/player_tags/12-阵容组合.json", "154"),
    ("agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py", "144"),
    ("agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py", "154"),
    # _brief.md 的示例行原本锚在一处空表格行上，改为锚 3 技能 Rank Ⅲ 行。
    ("agent_workspace/tag_pipeline/player_tags/_brief.md", "120"),
    # 异客行的备注正文里曾内联两处证据（`异客/异客.md:208`／`:209`）——按
    # docs/output-standard.md「证据只写进依据列」已从正文删除，同一组行号仍在依据列
    # （`异客/异客.md:59,60,62,208,209,216,223`）里保留。
    ("agent_workspace/tag_pipeline/player_tags/04-远程消耗.json", "208"),
    ("agent_workspace/tag_pipeline/player_tags/04-远程消耗.json", "209"),
    # 准入门槛读法收紧后移出的两行（死芒「对单 24 跳 <25」、洛洛「爬升均值 ≈244% <250%」）：
    # 成员行与其依据引用一同离开文件；两行各在「边界与排除记录」留下带行号的条目
    # （死芒 → :110、洛洛 → :15,101），故这三条 33／55／40 与 33 不再出现。
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "33"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "55"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "40"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "33"),
    # 排除⑦ 撤销：H 节「攻击型短间隔连射」判例条目整体删除，随它提供的四条技能行号引用
    # （能天使3／安洁莉娜2／可露希尔2／烛煌3）不再出现；这四条技能现已按新口径重判并各自入表。
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "115"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "108"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "132"),
    # 同上两行：其行号在「边界与排除记录」的新条目里重新出现，但已不在原位置——按位置比对的审计
    # 需要显式放行（引用本身仍指向同一处原文，未失效）。
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "110"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "15"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "101"),
    # 上拐门槛（台账「吃拐一轮秒：上拐单位数 ≤1」）：电弧、伺夜 两行因「召唤物按自身攻击力结算、
    # 须分别上拐」移出 03-吃拐一轮秒.md，其被移除行所带的指针随行消失——属有意为之的成员变动。
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "61"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "238"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "11"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "23"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "54"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "66"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "133"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "40"),
    # 11-阻挡数5.md 年行：原备注内联的 `年.md:…` 证据随重扫改写而删除（新备注不再内联证据，
    # 依据列保留指向 `年/年.md` 的引用）——属有意为之的写法统一，非漏改。
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "172"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "174"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "178"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "180"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "181"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "111"),
    ("agent_workspace/tag_pipeline/player_tags/11-阻挡数5.md", "112"),
    # 「模组代号进产物」全库补入：官方 A-控制异常-3.md 塑心行的键里插入了 `（RIT-Y）`，
    # 引用本身（`塑心/塑心.md:181`）未变、仍指向同一处原文——属有意为之的写法变更，非漏改。
    ("agent_workspace/tag_pipeline/official_tags/A-控制异常-3.json", "181"),# `agent_workspace/workdocs/待裁定.md`每轮整体重写（条目随裁定折入后移除）：旧版自带的  等
    # 引用随重写消失——属流程性的整文件替换，非漏改（与上方同类条目一致）。
    ("待裁定.md", "20"),
    ("待裁定.md", "23"),
    ("待裁定.md", "38"),
    ("待裁定.md", "58"),
    ("待裁定.md", "74"),
    ("待裁定.md", "109"),
    ("待裁定.md", "110"),
    ("待裁定.md", "111"),
    ("待裁定.md", "112"),
    ("待裁定.md", "130"),
    ("待裁定.md", "133"),
    ("待裁定.md", "175"),
    ("待裁定.md", "176"),
    ("待裁定.md", "177"),
    ("待裁定.md", "178"),
    ("待裁定.md", "179"),
    ("待裁定.md", "180"),
    ("待裁定.md", "181"),
    ("待裁定.md", "182"),
    ("待裁定.md", "183"),
    ("待裁定.md", "184"),
    ("待裁定.md", "185"),
    ("待裁定.md", "186"),
    ("待裁定.md", "187"),
    ("待裁定.md", "188"),
    ("待裁定.md", "189"),
    ("待裁定.md", "190"),
    ("待裁定.md", "191"),
    ("待裁定.md", "192"),
    ("待裁定.md", "193"),
    ("待裁定.md", "194"),
    ("待裁定.md", "195"),
    ("待裁定.md", "196"),
    ("待裁定.md", "197"),
    # 01-决战歼灭.md 号角「不可对空」排除行、02-次数对策.md 复奏/提丰「多段伤害」边界行：
    # 本轮在这三行的引用**紧前方**改写了文字（号角按「过载只覆盖后半程」订正窗口计法、
    # 复奏/提丰按「该动作的攻击间隔÷单动作段数≤0.667」补注）——引用本身（`号角/号角.md:17,96,…`、
    # `复奏/复奏.md:94,105`、`提丰/提丰.md:132,134`）未动、仍指向同一处原文。审计的键分词会把引用前的
    # 散文并入键名，键随文字改动而变、致误报「失效」——与下方「模组代号进产物」条目同类（引用未失效的显式放行）。
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "17"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "33"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "40"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "96"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "132"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "155"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "181"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "195"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "94"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "105"),
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "134"),
    # 第八批折入：13-高档控制.md 远距控制补扫——待裁块整块替换与多行行文改写使紧前方的
    # 引用「键分词」变化；引用本身未变、仍指向同一处原文（PRTS 语料未动，映射为恒等）。
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "26"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "28"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "38"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "39"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "40"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "54"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "55"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "58"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "59"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "63"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "65"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "66"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "67"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "68"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "69"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "100"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "101"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "102"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "103"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "104"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "105"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "106"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "107"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "108"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "109"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "110"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "114"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "115"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "116"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "117"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "118"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "119"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "120"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "121"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "122"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "123"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "124"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "125"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "126"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "127"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "129"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "130"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "131"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "132"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "133"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "134"),
    # DoT 跳数循环修复轮（2026-10-03／10-05）：02-次数对策.md 的望「棋子」条目在引用紧前方补写「首击」说明
    # （≈6.5 次 → ＝7 次（施加一击无伤害、另计 1 次首击）），引用本身未变、仍指向同一处原文——属「键分词误报」，放行。
    # （同轮早前登记的 白雪 15／103、谜图 107、归溟幽灵鲨 61／62／64／66／67 因口径回改已不再触发，一并移除。）
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "96"),
    # 决战歼灭 范围二档全库扫描轮（2026-10-07）：01-决战歼灭.md 的「边界与排除记录」按裁定整体改写
    # （旧条目行整体替换、旧引用随行移除或重排；旧引用位于括号内、键带「（」前缀，替换后该键不再存在
    # ——按整块替换显式放行；引用指向的原文仍在，新条目各带新引用）。
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "15"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "38"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "45"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "55"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "86"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "90"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "101"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "114"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "116"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "126"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "130"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "131"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "133"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "134"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "135"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "156"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "175"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "177"),
    # 决战歼灭 大范围范围条件调整轮（2026-10-07）：林3 按小范围线复核未达、成员行移出（转入「明确排除」条目），
    # 其引用随行改以括号式出现在边界条目、键并入引用前散文（「3480%）＜5000%。（林/林.md」）——
    # 旧键「林/林.md」在工作区的数字集合不再含 196（17/33/40/55/130/195 已在上面整批放行）；
    # 引用指向的原文仍在（PRTS 语料未动），属有意为之的整块替换，显式放行。
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "196"),
    # 砾行（台账「十二、数据勘误」）：精英2 第一天赋更名为「小个子支援」的字句改写使引用紧前方的
    # 散文并入「键分词」，键随文字改动而变、致误报「失效」；引用本身未变、仍指向同一处原文
    # （PRTS 语料未动，映射为恒等），放行。
    ("agent_workspace/tag_pipeline/player_tags/12-阵容组合.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/12-阵容组合.json", "57"),
    # 2026-10 版本更新（新干员 克莱门莎／旅骨／德·托莱多；乌尔比安 CRU-Y「“前路”」、黍 GUA-Y「好时节」）：
    # 重爬乌尔比安/黍 后，PRTS 天赋表新增「精英2 Y模组2级/3级」行（各 +2 行、插入于天赋小节中段），
    # 其后全部行号平移 +2；受影响引用已逐行人工比对原文并重锚到新行号（锚点仍指同一处原文，
    # 属重爬场景的必做重锚，非漏改）。按位置比对的审计以 HEAD 值为期望、需对旧值显式放行。
    ("agent_workspace/tag_pipeline/player_tags/04-远程消耗.json", "113"),
    ("agent_workspace/tag_pipeline/player_tags/04-远程消耗.json", "117"),
    ("agent_workspace/tag_pipeline/player_tags/04-远程消耗.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/05-插拔容错.json", "113"),
    ("agent_workspace/tag_pipeline/player_tags/05-插拔容错.json", "117"),
    ("agent_workspace/tag_pipeline/player_tags/05-插拔容错.json", "128"),
    ("agent_workspace/tag_pipeline/player_tags/07-充电.json", "66"),
    ("agent_workspace/tag_pipeline/player_tags/08-拐杖.json", "65"),
    ("agent_workspace/tag_pipeline/player_tags/08-拐杖.json", "131"),
    ("agent_workspace/tag_pipeline/player_tags/08-拐杖.json", "66"),
    # 09-保人 黍行同时修正「黍\黍.md」反斜杠与重锚 112→114（键内反斜杠已在 numbers_by_key 归一，
    # 56/58 不再触发；此处只需放行重锚消失的 112）。
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "112"),
    ("agent_workspace/tag_pipeline/player_tags/12-阵容组合.json", "65"),
    # 2026-10 版本更新续：13-高档控制「阻挡数5」排除行的乌尔比安/其余四家拆成两句（乌尔比安经
    # 2技能＋Y模组3级叠层加阻挡至 4、其余维持 3），引用紧前方的「→ 3（」变为「→ 4（」并新增
    # 「→ 3（」，键分词随之变形（旧键「3（乌尔比安/乌尔比安.md」不再存在）；引用本身已随重爬
    # 重锚指向同一处原文（33＝阻挡数行、102-111→104-113），属键分词误报，逐条放行。
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "33"),
    ("agent_workspace/tag_pipeline/player_tags/13-高档控制.json", "111"),
    # 《特殊机制》页快照重抓（免疫传送对齐三家）：页面漂移使「移动创伤每跳伤害机制」整句
    # 由 :373 移至 :399，02-次数对策 三行（歌蕾蒂娅/温蒂/夜魔）引用人工重锚至新行号——
    # 锚点仍指同一句原文，按位置比对的审计需对旧值显式放行。
    ("agent_workspace/tag_pipeline/player_tags/02-次数对策.json", "373"),
    # 司霆惊蛰 2技能 纳入轮（2026-10-10）：原「明确排除」条目（技能名误记「浩气长存」、按 10 格
    # 归小范围档）整条删除，其证据引用 35／36（两行本非该断言的支撑行）随条目移除——
    # 属有意为之的条目移除，引用指向的原文仍在（PRTS 语料未动、映射为恒等），显式放行。
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "35"),
    ("agent_workspace/tag_pipeline/player_tags/01-决战歼灭.json", "36"),
    # 降低敌方伤害（敌方向子 TAG）轮（2026-10-14）：09-保人 新增「敌方减攻」「敌方失能」两个子 TAG、
    # 08-拐杖 新增「减益类型」组，两者都要改写既有「边界与排除记录」里若干条 bullet 的散文（把
    # 「属对敌、不计入本 TAG」改为「归本 TAG 的子 TAG」、把已入表的干员从排除名单里移出、把
    # 「未计入」句改为指向新子 TAG）。这些 bullet 里的引用**本身未动、仍指向同一处原文**，但审计的
    # 键分词会把引用**紧前方的散文**并入键名，键随文字改动而变 → 误报「失效」——与本文件内前述
    # 「键分词误报」诸条同类（引用未失效的显式放行）。裁定见 docs/rulings.md §二十一。
    # 08：减防/削抗条里 丰川祥子 Y模组「颂乐音符」的忽视防御力/法术抗性部分（属「无视/穿透不收」的举例）。
    ("agent_workspace/tag_pipeline/player_tags/08-拐杖.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/08-拐杖.json", "58"),
    # 09：遥（浮空→敌方失能）、引星棘刺（敌攻速-→敌方减攻）、焰尾（晕眩→敌方失能）、
    # 可颂（晕眩→敌方失能）、缇缇（对敌沉睡→敌方失能）五条 bullet 的散文改写。
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "54"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "55"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "56"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "57"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "63"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "64"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "96"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "98"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "103"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "107"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "122"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "130"),
    ("agent_workspace/tag_pipeline/player_tags/09-保人.json", "132"),
    # 连射「等效每秒门槛」新增与成员复核轮：妮芙、鸿雪、迷迭香、刻俄柏、蓝毒 五行（及其余移出者
    # 仅存于此处的指针）由 03-吃拐一轮秒.md 的连射子表移出，被移除行所带的引用随行消失——属有意
    # 为之的成员变动，非漏改（裁定见 docs/rulings.md §二十四；移出记录见该文件「边界与排除记录」L）。
    # 「132」同时对应 妮芙/妮芙.md:132 与 刻俄柏/刻俄柏.md:132 两处（同原子值）。
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "132"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "63"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "127"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "181"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "197"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "34"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "162"),
    ("agent_workspace/tag_pipeline/player_tags/03-吃拐一轮秒.json", "105"),
}

# 文件:行号 — the number part is digits joined by , 、 or a -/– range.
# Parens are deliberately allowed in the path (阿米娅(近卫)、Mon3tr(凯尔希的召唤物)、
# 保护目标（冻结状态）); resolution below trims any prose that gets swept in.
# `:` is excluded from the path so a match cannot swallow a preceding citation in
# the same whitespace-free run (`…（星熊.md:173/179、可颂.md:124/130`).
CITE_RE = re.compile(r'([^\s|；;：:\[\]"]+\.md):(\d+(?:[，,、/]\d+|\s*[-–]\s*\d+)*)')
RANGE_RE = re.compile(r"^(\d+)\s*([-–])\s*(\d+)$")
SPLIT_RE = re.compile(r"([，,、/])")
# The one deliberate content rewrite: a module level icon line becomes this.
LEVEL_LINE = re.compile(r"^\*\*模组等级\d\*\*$")


def operator_files():
    for p in sorted(PRTS_DIR.glob("*/*.md")):
        if p.parent.name in SKIP_DIRS or p.parent.name.startswith("_"):
            continue
        yield p


def build_index():
    """Citation path → resolved file. Only unambiguous names are indexed."""
    by_name = {}
    index = {}
    for p in PRTS_DIR.rglob("*.md"):
        index[p.relative_to(PRTS_DIR).as_posix()] = p.resolve()
        by_name.setdefault(p.name, []).append(p.resolve())
    for p in ROOT.glob("*.md"):
        index.setdefault(p.name, p.resolve())
        by_name.setdefault(p.name, []).append(p.resolve())
    for name, hits in by_name.items():
        if len(hits) == 1:
            index.setdefault(name, hits[0])
    return index


def look_up(key, index):
    """Resolve a citation path, tolerating prose swept into the match.

    A path with no spaces can trail adjacent prose (`…每0.5秒受到…灵知/灵知.md`), some
    citations use Windows separators (`异客\异客.md`), and some name a file whose
    basename is not unique so only the full path resolves (`号角/攻击范围.md`, one of
    431). Normalising separators and walking every suffix longest-first handles all
    three: the real path is the longest suffix that is a known corpus path.
    """
    key = key.replace("\\", "/")
    for i in range(len(key)):
        cand = key[i:]
        if cand in index:
            return index[cand]
    return None


def rewrite_text(text, maps, index, src, collisions, stale_only=False):
    """Rewrite every PRTS pointer in `text` through the line maps.

    With stale_only, a token whose line already holds the text the map expects is
    left alone; only tokens still carrying their pre-strip number are remapped.
    That matters when one citation string mixes already-correct and never-rewritten
    numbers — remapping the whole list would double-map the correct ones.

    Returns (new_text, pointers_rewritten). Collisions are appended to
    `collisions` and leave the offending pointer untouched.
    """
    touched = [0]
    pre_of_cache = {}

    def already_correct(n, target):
        old_to_new, old, new = maps[target]
        if not 1 <= n <= len(new):
            return False
        if target not in pre_of_cache:
            pre_of_cache[target] = {v: i + 1
                                    for i, v in enumerate(old_to_new)
                                    if v is not None}
        orig = pre_of_cache[target].get(n)
        if orig is None:
            return False
        return old[orig - 1] == new[n - 1] or bool(LEVEL_LINE.match(new[n - 1]))

    def map_token(token, target, key):
        old_to_new = maps[target][0]
        m = RANGE_RE.match(token)
        if m:
            lo, dash, hi = int(m.group(1)), m.group(2), int(m.group(3))
            if stale_only and all(already_correct(n, target)
                                  for n in range(lo, hi + 1)):
                return token
            mapped = [old_to_new[L - 1] if 0 < L <= len(old_to_new) else None
                      for L in range(lo, hi + 1)]
            keep = [n for n in mapped if n is not None]
            if not keep:
                collisions.append(Collision(src, f"{key}:{token}", lo))
                return None
            contiguous = (len(keep) == len(mapped)
                          and keep == list(range(keep[0], keep[0] + len(keep))))
            return f"{keep[0]}{dash}{keep[-1]}" if contiguous else \
                "，".join(str(n) for n in keep)
        n = int(token)
        if stale_only and already_correct(n, target):
            return str(n)
        mapped = old_to_new[n - 1] if 0 < n <= len(old_to_new) else None
        if mapped is None:
            collisions.append(Collision(src, f"{key}:{token}", n))
            return None
        return str(mapped)

    def repl(match):
        key, nums = match.group(1), match.group(2)
        target = look_up(key, index)
        if target is None or target not in maps:
            return match.group(0)
        out = []
        for piece in SPLIT_RE.split(nums):
            if piece in ("，", ",", "、", "/"):
                out.append(piece)
                continue
            got = map_token(piece, target, key)
            if got is None:
                return match.group(0)          # leave the whole pointer alone
            out.append(got)
        touched[0] += 1
        return f"{key}:{''.join(out)}"

    return CITE_RE.sub(repl, text), touched[0]


class Collision:
    def __init__(self, src, cited, old_line):
        self.src, self.cited, self.old_line = src, cited, old_line

    def __str__(self):
        return (f"{self.src}: 引用 {self.cited} 落在被删内容上"
                f"（旧行 {self.old_line}）")


def check_identity(maps):
    """Every surviving anchor must land on the line the plan intended for it.

    Level-icon lines are the one deliberate rewrite (image → **模组等级N**), so
    the invariant is against the planned text, not the raw source line.
    """
    bad = []
    for target, (old_to_new, planned, new) in maps.items():
        rel = target.relative_to(ROOT).as_posix()
        for i, n in enumerate(old_to_new):
            if n is None:
                continue
            if n > len(new) or planned[i] != new[n - 1]:
                bad.append(Collision(rel, "行映射", i + 1))
    return bad


def git_head_text(rel):
    """The committed content of `rel`, or None if it does not exist at HEAD."""
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                       capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def head_maps(index):
    """Rebuild (old, new, old_to_new) per PRTS file from the committed corpus.

    The working tree is already stripped, so the map that explains the current
    line numbering can only be reconstructed from HEAD.
    """
    out = {}
    for target in set(index.values()):
        if PRTS_DIR not in target.parents or not target.is_file():
            continue
        if target.parent.name in SKIP_DIRS or target.parent.name.startswith("_"):
            continue        # not stripped, so its line numbering did not move
        rel = target.relative_to(ROOT).as_posix()
        text = git_head_text(rel)
        if text is None:
            continue
        old = text.splitlines()
        kept, old_to_new = render_strip(plan_strip(old))
        out[target] = (old, kept, old_to_new)
    return out


def map_atom(atom, old_to_new):
    """The post-strip numbers a HEAD-side atom should appear as; None if all deleted.

    Returns a list because a range whose middle was deleted expands into several
    numbers, and the caller compares against individual atoms, not a joined string.
    """
    rng = RANGE_RE.match(atom)
    span = (range(int(rng.group(1)), int(rng.group(3)) + 1)
            if rng else [int(atom)])
    keep = [old_to_new[L - 1] for L in span
            if 0 < L <= len(old_to_new) and old_to_new[L - 1] is not None]
    return keep or None


def numbers_by_key(text):
    """Every line number cited per key, ranges expanded.

    Comparing numbers rather than atom strings is what makes `:54-56` and
    `:54,55,56` equivalent — the rewriter keeps a contiguous range as a range, so a
    literal string comparison would flag every untouched range as stale.

    键内反斜杠先归一为斜杠：`look_up()` 解析时本就等价（历史写法 `黍\\黍.md` 与
    `黍/黍.md` 指向同一个语料文件），若在此不归一，依据列的斜杠写法统一会被误报为
    整键消失，每个行号原子各报一条。注意审计读的是**原始文件文本**（JSON 序列化后），
    字面反斜杠在文本中以「\\」两字符出现，故按两字符序列折叠为「/」。
    """
    out = {}
    for m in CITE_RE.finditer(text):
        key = m.group(1).strip().replace("\\\\", "/")
        got = out.setdefault(key, set())
        for piece in SPLIT_RE.split(m.group(2)):
            if piece in ("，", ",", "、", "/"):
                continue
            rng = RANGE_RE.match(piece)
            if rng:
                got.update(range(int(rng.group(1)), int(rng.group(3)) + 1))
            else:
                got.add(int(piece))
    return out


def audit(hmaps, index):
    """Compare the working tree's pointers against the ones HEAD actually carried.

    A content test cannot work here. The strip guarantees new[map(x)-1] == old[x-1],
    so for any in-range n the test `old[pre_of[n]-1] == new[n-1]` holds whichever
    side of the map n was written on — it is true for stale pointers too. An earlier
    version of this function did exactly that and reported "0 stale" while dozens of
    pointers still carried their pre-strip numbers; only out-of-range ones were ever
    caught.

    The sound test is against HEAD's own text: take each pointer as it stood at HEAD,
    map it, and require the working tree to carry the mapped value. Anything else is
    reported. Returns (checked, stale, dropped); `dropped` are HEAD pointers whose
    line the strip removed, which a human must review once per rule change.
    """
    stale, dropped, checked = [], [], 0
    seen = set()
    for pattern in REF_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if path in seen or rel in REF_EXCLUDE:
                continue
            seen.add(path)
            head = git_head_text(rel)
            if head is None:
                continue                      # new file: nothing at HEAD to compare
            try:
                work = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            present = numbers_by_key(work)
            for key, atoms in numbers_by_key(head).items():
                target = look_up(key, index)
                if target is None or target not in hmaps:
                    continue
                old_to_new = hmaps[target][2]
                here = present.get(key, set())
                for atom in sorted(atoms):
                    checked += 1
                    if (rel, str(atom)) in ACCEPTED:
                        continue
                    expected = map_atom(str(atom), old_to_new)
                    if expected is None:
                        old = hmaps[target][0]
                        text = old[atom - 1].strip() if 0 < atom <= len(old) else ""
                        dropped.append((rel, key, atom, text[:70]))
                    elif not set(expected) <= here:
                        stale.append((rel, key, atom,
                                      "，".join(str(n) for n in expected)))
    return checked, stale, dropped


def unresolved_keys(index):
    """Citation keys that fail to resolve but name a PRTS file.

    The rewriter and the audit both skip unresolvable keys. That is correct for
    genuinely foreign pointers (docs/glossary.md, part-file cross-refs), but it
    silently hides a PRTS path written in a shape look_up() cannot parse — the
    pointer then keeps its pre-strip number and nothing reports it. Such keys must
    be loud, so they are listed here rather than skipped.
    """
    names = {p.name for p in PRTS_DIR.rglob("*.md")}
    out, seen = [], set()
    for pattern in REF_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen or path.relative_to(ROOT).as_posix() in REF_EXCLUDE:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for m in CITE_RE.finditer(text):
                key = m.group(1).strip()
                if look_up(key, index) is not None:
                    continue
                if key.replace("\\", "/").split("/")[-1] in names:
                    out.append((path.relative_to(ROOT).as_posix(), key))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写任何文件")
    ap.add_argument("--audit", action="store_true",
                    help="按 HEAD 重建行映射，逐条核对现有引用是否仍指向原文")
    ap.add_argument("--fix-stale", action="store_true",
                    help="把审计发现的失效引用按 HEAD 行映射补正")
    args = ap.parse_args()

    if args.audit or args.fix_stale:
        index = build_index()
        hmaps = head_maps(index)
        checked, stale, dropped = audit(hmaps, index)
        unresolved = unresolved_keys(index)
        print(f"核对 HEAD 侧引用 {checked} 条：失效 {len(stale)} 条，指向已删行 {len(dropped)} 条")
        for rel, key, atom, expected in stale:
            print(f"  ! {rel}  {key}:{atom} → 应为 {expected}")
        print(f"无法解析但指向 PRTS 文件的引用 {len(unresolved)} 条")
        for path, key in unresolved:
            print(f"  ? {path}  {key}")
        print(f"指向已删行的引用 {len(dropped)} 条"
              f"（每次改动剥离规则后需人工过一遍其原文，确认删的不是作战内容）")
        for rel, key, atom, text in dropped:
            print(f"  · {rel}  {key}:{atom}  原文「{text}」")
        if not args.fix_stale:
            return 1 if (stale or unresolved) else 0

        if unresolved:
            print("\n存在无法解析的引用，未写入。请先处理。")
            return 1
        # A stale pointer still carries its HEAD-side number, so overwrite exactly
        # that atom with the value the HEAD map says it should hold.
        if not stale:
            print("\n无需校正。")
            return 0
        by_file = {}
        for rel, key, atom, expected in stale:
            by_file.setdefault(rel, []).append((key, str(atom), expected))
        files, edits = [], 0
        for rel, items in by_file.items():
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            before = text
            for key, atom, expected in items:
                pat = re.compile(re.escape(key) + r":([\d，,、/–-]+)")

                def sub(m, atom=atom, expected=expected, key=key):
                    parts = SPLIT_RE.split(m.group(1))
                    out = [expected if p == atom else p for p in parts]
                    return f"{key}:{''.join(out)}"
                text = pat.sub(sub, text)
            if text != before:
                files.append((path, text))
                edits += len(items)
        print(f"\n校正文件 {len(files)} 个，改写指针 {edits} 处")
        if not files:
            print("未能定位待校正的引用，未写入。")
            return 1
        for path, new in files:
            path.write_text(new, encoding="utf-8")
        print("已写入。请重跑 --audit 确认。")
        return 0

    index = build_index()
    maps = {}
    n_files = n_changed = 0
    old_lines = new_lines = old_chars = new_chars = 0

    for path in operator_files():
        n_files += 1
        text = path.read_text(encoding="utf-8")
        old = text.splitlines()
        planned = plan_strip(old)
        kept, old_to_new = render_strip(planned)
        old_lines += len(old)
        old_chars += len(text)
        new_lines += len(kept)
        new_chars += len("\n".join(kept)) + 1      # LF-based, like len(text)
        if old_to_new == list(range(1, len(old) + 1)):
            continue                                    # nothing to strip
        n_changed += 1
        maps[path.resolve()] = (old_to_new, planned, kept)

    collisions = check_identity(maps)
    ref_files, ref_edits = [], 0
    seen = set()
    for pattern in REF_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen or path.relative_to(ROOT).as_posix() in REF_EXCLUDE:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new, n = rewrite_text(
                text, maps, index, path.relative_to(ROOT).as_posix(), collisions)
            if new != text:
                ref_files.append((path, new))
                ref_edits += n

    print(f"扫描干员/召唤物 md: {n_files} 个，其中需改写 {n_changed} 个")
    print(f"行数 {old_lines} → {new_lines}"
          f"（−{old_lines - new_lines}，{(old_lines - new_lines) / old_lines * 100:.1f}%）")
    print(f"字符 {old_chars} → {new_chars}"
          f"（−{old_chars - new_chars}，{(old_chars - new_chars) / old_chars * 100:.1f}%）")
    print(f"引用文件待改 {len(ref_files)} 个，改写指针 {ref_edits} 处")
    print(f"行映射一致性: {'通过' if not collisions else '存在问题'}")
    print(f"冲突 {len(collisions)} 处")
    for c in collisions:
        print(f"  ! {c}")

    if args.dry_run:
        print("\n--dry-run：未写入任何文件")
        return 0
    if collisions:
        print("\n存在冲突，已中止，未写入任何文件。请先处理上述冲突。")
        return 1

    # newline="" keeps the CRLF we write verbatim; without it write_text would
    # expand the LF of every "\r\n" and produce \r\r\n.
    for path, (_m, _planned, kept) in maps.items():
        path.write_text("\r\n".join(kept) + "\r\n", encoding="utf-8", newline="")
    for path, new in ref_files:
        path.write_text(new, encoding="utf-8")
    broken = [p for p in maps if b"\r\r" in p.read_bytes()]
    if broken:
        print(f"\n写盘后检出 \\r\\r：{broken}")
        return 1
    print(f"\n已改写 {len(maps)} 个干员文件、{len(ref_files)} 个引用文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""One-off: strip non-combat content from material_datas/PRTS and re-anchor evidence.

The crawler now applies crawl_prts.strip_noncombat() to every page it writes, but
the corpus on disk predates it. This script backfills the same transform — the
plan/render logic is imported from crawl_prts, not reimplemented, so the two can
never drift apart.

Deleting lines shifts every 文件:行号 evidence pointer below them, and those
pointers are the project's evidence layer (~8k of them across the part files,
the official module files, docs/ and 待验证复算.md). So the same pass records an
old→new line map per file and rewrites every pointer through it, asserting line
by line that the rewritten anchor still holds byte-identical text. A pointer that
would land on deleted content is reported as a collision and left untouched —
by design that should be an empty list, and a non-empty one needs a hand edit.

Usage:
  python -X utf8 strip_prts_noncombat.py --dry-run    # report, write nothing
  python -X utf8 strip_prts_noncombat.py              # strip + rewrite pointers
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from crawl_prts import plan_strip, render_strip

ROOT = Path(__file__).resolve().parent
PRTS_DIR = ROOT / "material_datas" / "PRTS"
SKIP_DIRS = {"_rules", "特殊机制"}

# Files carrying 文件:行号 pointers. Enumerate by directory, not by guessing which
# ones matter: a file one level outside a listed glob (official-fullmap-aura.md
# sits beside official_tags/, not inside it) is skipped silently and keeps stale
# numbers, so every directory known to hold pointers is listed explicitly.
REF_GLOBS = [
    "material_datas/tag_pipeline/*.md",
    "material_datas/tag_pipeline/player_tags/*.md",
    "material_datas/tag_pipeline/player_tags/**/*.md",
    "material_datas/tag_pipeline/player_tags/**/*.jsonl",
    "material_datas/tag_pipeline/player_tags/**/*.json",
    "material_datas/tag_pipeline/official_tags/*.md",
    "docs/*.md",
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
    # 根目录《待裁定.md》每轮整体重写（其条目随裁定折入后移除），旧版里引用过的 11-阻挡数5 例证（`珊比.md:33`）随重写消失——属流程性的整文件替换。
    ("待裁定.md", "33"),
    # 11-阻挡数5.md 三行（珊比／酒神／余）的备注原内联了证据，按「证据只写进依据列」
    # 移到依据列后改用全路径写法（`珊比/珊比.md:…`），原短路径写法（`珊比.md:121`）随之消失——
    # 属有意为之的写法统一，非漏改。
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "121"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "122"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "120"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "121"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "122"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "21"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "26"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "28"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "101"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "102"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "103"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "104"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "105"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "106"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "107"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "108"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "109"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "110"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "55"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "56"),
    # 连射「可及距离 ≥3 格」门槛的成员调整：以下 9 行（祐天寺若麦、聆音、维娜·维多利亚、
    # 百炼嘉维尔、归溟幽灵鲨、龙舌兰、山、瑕光、傀影）由主进程移出 03-吃拐一轮秒.md，
    # 其被移除行所带的指针随行消失——属有意为之的成员变动，非漏改（见该文件「边界与排除记录」H）。
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "17"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "112"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "82"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "56"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "57"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "64"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "65"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "128"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "157"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "183"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "56"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "57"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "58"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "59"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "60"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "116"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "135"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "160"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "36"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "123"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "217"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "86"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "56"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "57"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "128"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "179"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "64"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "65"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "130"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "56"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "57"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "113"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "115"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "188"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "34"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "126"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "127"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "128"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "129"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "130"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "131"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "132"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "133"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "134"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "135"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "59"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "60"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "220"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "227"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "33"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "123"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "124"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "125"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "126"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "127"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "128"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "129"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "130"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "131"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "132"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "67"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "227"),
    # 深海色的原锚点是证章标题，并不支撑「所属势力【阿戈尔】、天赋为召唤物系」这句
    # 断言；改为指向属性表的所属势力行与「召唤触手」天赋行（现在写作 34,54-58）。
    ("material_datas/tag_pipeline/player_tags/12-阵容组合.md", "144"),
    ("material_datas/tag_pipeline/player_tags/12-阵容组合.md", "154"),
    ("material_datas/tag_pipeline/player_tags/_merge_to_docs.py", "144"),
    ("material_datas/tag_pipeline/player_tags/_merge_to_docs.py", "154"),
    # _brief.md 的示例行原本锚在一处空表格行上，改为锚 3 技能 Rank Ⅲ 行。
    ("material_datas/tag_pipeline/player_tags/_brief.md", "120"),
    # 异客行的备注正文里曾内联两处证据（`异客/异客.md:208`／`:209`）——按
    # docs/output-standard.md「证据只写进依据列」已从正文删除，同一组行号仍在依据列
    # （`异客/异客.md:59,60,62,208,209,216,223`）里保留。
    ("material_datas/tag_pipeline/player_tags/04-远程消耗.md", "208"),
    ("material_datas/tag_pipeline/player_tags/04-远程消耗.md", "209"),
    # 准入门槛读法收紧后移出的两行（死芒「对单 24 跳 <25」、洛洛「爬升均值 ≈244% <250%」）：
    # 成员行与其依据引用一同离开文件；两行各在「边界与排除记录」留下带行号的条目
    # （死芒 → :110、洛洛 → :15,101），故这三条 33／55／40 与 33 不再出现。
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "33"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "55"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "40"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "33"),
    # 排除⑦ 撤销：H 节「攻击型短间隔连射」判例条目整体删除，随它提供的四条技能行号引用
    # （能天使3／安洁莉娜2／可露希尔2／烛煌3）不再出现；这四条技能现已按新口径重判并各自入表。
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "128"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "115"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "108"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "132"),
    # 同上两行：其行号在「边界与排除记录」的新条目里重新出现，但已不在原位置——按位置比对的审计
    # 需要显式放行（引用本身仍指向同一处原文，未失效）。
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "110"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "15"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "101"),
    # 上拐门槛（台账「吃拐一轮秒：上拐单位数 ≤1」）：电弧、伺夜 两行因「召唤物按自身攻击力结算、
    # 须分别上拐」移出 03-吃拐一轮秒.md，其被移除行所带的指针随行消失——属有意为之的成员变动。
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "61"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "238"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "11"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "23"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "54"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "66"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "133"),
    ("material_datas/tag_pipeline/player_tags/03-吃拐一轮秒.md", "40"),
    # 11-阻挡数5.md 年行：原备注内联的 `年.md:…` 证据随重扫改写而删除（新备注不再内联证据，
    # 依据列保留指向 `年/年.md` 的引用）——属有意为之的写法统一，非漏改。
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "172"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "174"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "178"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "180"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "181"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "111"),
    ("material_datas/tag_pipeline/player_tags/11-阻挡数5.md", "112"),
    # 「模组代号进产物」全库补入：官方 A-控制异常-3.md 塑心行的键里插入了 `（RIT-Y）`，
    # 引用本身（`塑心/塑心.md:181`）未变、仍指向同一处原文——属有意为之的写法变更，非漏改。
    ("material_datas/tag_pipeline/official_tags/A-控制异常-3.md", "181"),# 根目录《待裁定.md》每轮整体重写（条目随裁定折入后移除）：旧版自带的  等
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
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "17"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "33"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "40"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "57"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "96"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "132"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "155"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "181"),
    ("material_datas/tag_pipeline/player_tags/01-决战歼灭.md", "195"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "94"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "105"),
    ("material_datas/tag_pipeline/player_tags/02-次数对策.md", "134"),
    # 第八批折入：13-高档控制.md 远距控制补扫——待裁块整块替换与多行行文改写使紧前方的
    # 引用「键分词」变化；引用本身未变、仍指向同一处原文（PRTS 语料未动，映射为恒等）。
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "26"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "28"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "38"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "39"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "40"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "54"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "55"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "56"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "57"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "58"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "59"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "63"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "65"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "66"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "67"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "68"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "69"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "100"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "101"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "102"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "103"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "104"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "105"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "106"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "107"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "108"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "109"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "110"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "114"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "115"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "116"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "117"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "118"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "119"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "120"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "121"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "122"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "123"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "124"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "125"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "126"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "127"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "128"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "129"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "130"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "131"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "132"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "133"),
    ("material_datas/tag_pipeline/player_tags/13-高档控制.md", "134"),
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
    """
    out = {}
    for m in CITE_RE.finditer(text):
        key = m.group(1).strip()
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

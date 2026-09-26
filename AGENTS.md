# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **data-production repository** (not an app) for an Arknights operator-filtering system. It crawls the PRTS wiki into local markdown, then classifies every operator under two TAG systems (official-defined + player-perception) and produces per-operator results consumed by a **separate UI project**. There is no build/lint/test tooling; the code is a handful of one-off Python data scripts. Working language is Chinese; all documents/outputs are Chinese.

The eventual product is two JSONs: `results/operator-tags.json` (main output; format spec: `docs/output-standard.md`) and `results/combat_glossary.json` (combat-term glossary, generated from `docs/glossary.md`). TAG definitions, membership lists, counts and open questions change frequently — this file describes stable structure and conventions only; treat `docs/` as the source of truth for content.

## Data flow / architecture

```
docs/operators.txt ──► crawl_prts.py ──► material_datas/PRTS/<干员>/<干员>.md (+ <召唤物>.md siblings)
crawl_ranges.py ──► material_datas/PRTS/<干员>/攻击范围.md（攻击范围网格：各精英化阶段 / 技能 / 召唤物；PRTS 用内联 SVG 绘制，主爬虫不抓）
                                              │
                                              │
        official TAGs:  material_datas/tag_pipeline/{catalog,merged,deterministic}.json + final_lists.tsv
                        material_datas/tag_pipeline/official_tags/[A-I]-*.md（分模块：干员 | 条件 | 备注）
                        └─► docs/official-tags-members.md（_merge_official_to_docs.py 重生成 §3/§4/§5）
        player TAGs:    docs/player-tags-specify.md（定义）
                        material_datas/tag_pipeline/player_tags/NN-*.md（分 TAG 判定文件，含逐条 文件:行号 证据）
                        _brief.md（共享评定标准）+ _launch_dates.json + _merge_to_docs.py + _recommend.json（荐，recommend.py 维护）
                        └─► docs/player-tags-members.md（自动生成，勿手改：改分文件后重新合并）
                        └─► results/operator-tags.json（最终输出，generate_results.py 生成，规范见 docs/output-standard.md）
                        └─► docs/untagged-operators.md（未归 TAG 干员，随生成一并写出）
```

- `material_datas/PRTS/` — one folder per operator; operator page plus one sibling `.md` per summon. `_manifest.json` is the crawler's resume record (per-operator status/files/summon links). 语料**只含作战信息**：章节级剧情（`干员档案`/`语音记录`/`干员密录`…）由 `STOP_SECTIONS` 整节丢弃，模组剧情、模组解锁任务、升级材料、`后勤技能` 由 `strip_noncombat()` 剥离（模组等级图标改写为 `**模组等级N**` 文本行，模组类型码保留为 `**ART-X**` 形式的文本行）。剥离压缩了行号，全仓库 `文件:行号` 引用随之整体平移，核对方式见下方 `strip_prts_noncombat.py --audit`。
- `material_datas/tag_pipeline/` — official-TAG machine-readable dicts (`catalog.json` = TAG dictionary — the only dict scripts read, `merged.json` = operator→TAG ids, `deterministic.json` = parsed base stats/summons — a snapshot that does not follow TAG changes; `merged.json` / `final_lists.tsv` rebuilt by `_merge_official_to_docs.py --sync-dicts`; `final_lists.tsv` = TAG→members)、`stats.json`（**机读属性层**：每干员的 E0–E2 满级攻击／信赖上限／潜能各档／模组各档固定属性，由 `prts_stats.py` 从 PRTS 语料抽取；面板与档位的唯一取数处）与 `player_tags/` for the player-TAG workflow.
- `information_records/` — pipeline/crawler notes and extraction decisions; `docs/mechanism-understanding.md` + `docs/verification-complaints.md` — mechanics primer and known judgment pitfalls (dated notes — their counts reflect the day they were written; current lists live in the member docs).
- `docs/concept.md` — project intent and the 条件/备注/结果 JSON rules that all classification work follows (the one place those writing rules live); `docs/output-standard.md` — final results JSON spec (version/date, operator cards, PRTS deep links, 荐); `docs/untagged-operators.md` — 未归入任何 TAG 的干员（auto-written by `generate_results.py`: full roster minus `operators[]`). `docs/player-tags-specify.md` — 玩家 TAG 定义（开发者手改）; `docs/calc-rules.md` — 计算规则正本（结算层位与总式、游戏文本→因素映射、演算流程、未定项索引），数值门槛与术语只作指针指向 `docs/player-tags-specify.md`／`docs/glossary.md`; `docs/ui-render-rules.md` — 消费端（前端项目）渲染规则记录，改 JSON 结构时对照之.
- `gui/` — the maintenance panel as a package: `config/errors/md` (leaf) → `tags/roster/recommends/merges/results_json` (data) → `writeback/model` (business) → `server/selfcheck/__main__`; page assets in `gui/static/` (`index.html` + `app.css` + `app.js`, styled with ak-ui dark tokens — see the CSS header for provenance and the density compromise). `recommend_gui.py` at the root is a thin entry point (`python -m gui` is equivalent). Usage guide (English): `gui/README.md`.
- The UI itself is **out of scope** for this repo (the panel above is a maintainer tool, not the product UI).

### File authority map (what to trust, what to edit)

Read only what the task needs; the two member docs and the two results JSONs are large — read them by §／target TAG, never whole.

**手写权威源（改这些）**: `docs/concept.md`（意图＋条件/备注规则）、`docs/output-standard.md`（产物规范）、`docs/player-tags-specify.md`（玩家 TAG 定义）、`docs/calc-rules.md`（计算规则正本：结算层位／文本→因素映射／演算流程；复算作业副本为 `player_tags/_reverify/rules.md`）、**`docs/rulings.md`（裁定台账：开发者对判断类问题的裁定逐条留痕——裁定／理由／适用范围／折入位置；判断类问题先查它，别再问第二遍）**、`docs/term-map.md`（代称映射表：一切自创代称／缩写／自编号的含义与查阅位置，改动或新增代称时同步）、`material_datas/tag_pipeline/official_tags/[A-I]-*.md`（官方 TAG 定义与成员，GUI 写回可改）、`material_datas/tag_pipeline/player_tags/NN-*.md`（玩家 TAG 判定＋证据；`_brief.md` 为作业规范）、`docs/glossary.md`（术语；前 5 节手写，后 6 节由 `crawl_special_mechanics.py --apply` 追加）、字典 `catalog.json`／`char_ids.json`／`_launch_dates.json`／`docs/operators.txt`。

**生成物（勿手改，改上列源文件后重生成）**: `docs/official-tags-members.md` §3/§4/§5 ← `_merge_official_to_docs.py`；`docs/player-tags-members.md` ← `player_tags/_merge_to_docs.py`；`results/operator-tags.json` ＋ `docs/untagged-operators.md` ← `generate_results.py`；`results/combat_glossary.json` ← `glossary_to_json.py`；`material_datas/PRTS/**`（含 `_manifest.json`、`_range_codes.json`、`特殊机制/`）← 三个爬虫；`merged.json`／`final_lists.tsv` ← `--sync-dicts`（无脚本读取）；`deterministic.json`＝基础属性快照（不随 TAG 变化）。

**属性与数值工具（非生成链路，按需运行）**: `prts_stats.py`（PRTS 语料 → `stats.json`，并提供 `panel_of()` 面板复算）与 `verify_numbers.py`（对着 `stats.json` 校准产物里的面板／档位／恒等式／内部代号／因子覆盖）。两者与 `stats.json` 一样是**生成物**：改 `stats.json` 要改爬虫侧或重跑 `prts_stats.py`，不手改。

**剥离工具（非生成链路，按需运行）**: `strip_prts_noncombat.py` —— 剥离逻辑本体在 `crawl_prts.py` 的 `plan_strip()`／`render_strip()`／`strip_noncombat()`，本脚本只 import 之，用于回填历史语料与审计。`--dry-run` 先看改动与冲突；`--fix-stale` 补正审计发现的失效引用。删除行会平移其后行号，任何再次剥离都必须同时跑改写与审计。

**回填工具（非生成链路，按需运行）**: `_apply_batch.py` —— 把 `_out/<批名>.json`（`tag-rewrite` 子代理的产出，键＝干员名，值＝`{condition, remark, why}`）写回分文件：**按表头定位列、以 HEAD 重建整行**，只替换「条件」「备注」两格，其余列原样取 HEAD（既防写错列，也能修复写错列的历史行）；行首机器协议前缀（插拔容错的 `救急路径：`、充电的 `子 TAG：`）用 `--keep-prefix` 保留，否则整批丢子 TAG。`_out/` 为临时批次目录（已 gitignore）。

`--audit` 报三类，判据是**与 HEAD 对比**——取每条引用在 HEAD 侧的行号，按行映射算出它应当变成什么，再要求工作区确实带着这个值：
- **失效**（应为 0）：工作区没带上应有的值，即漏改；
- **未解析**（应为 0）：解析不到目标、但文件名属于 PRTS 语料，属于"看不懂就当没问题"的静默跳过；
- **指向已删行**（每次改动剥离规则后需人工过一遍其原文）：原锚点所在行被剥离删除，逐条看删的是不是作战内容。

**不要**用"新行号处的文本 == 旧行号处的文本"做这个检查。剥离保证 `new[map(x)-1] == old[x-1]` 对任何在范围内的行号都成立，无论它是改写后的还是漏改的——那样的检查只会发现越界，正是本仓库踩过的坑。有意偏离机械映射的引用（改锚到真正支撑论点的行）登记在脚本内的 `ACCEPTED`，新增即视为一次显式裁定。

扫描范围按目录显式枚举（`REF_GLOBS`），新增目录时须同步——漏一个目录就是整批引用静默保留旧行号。

**只为背景、不作依据**: `information_records/*`、`docs/verification-complaints.md`、`player_tags/_mode-limited-module-audit.md`、`official-fullmap-aura.md`（历史转制稿）。`docs/mechanism-understanding.md` 是**机制常识正典**——判别原则以它为准（其中的计数与举例如有出入，以现行文件为准）。

## 开工前的必读清单（新会话与子代理）

派发或接手「TAG 改写／复算／数据修复」类任务前，**先读 `docs/agent-primer.md`**（作业记忆包）：游戏常识（技能按精英阶段开放、**专精需精英2＋技能 7 级**、模组解锁需精英2——这三条语料里查不到）、仓库作业常识、**反面清单**（真的发生过的错误类型）、以及派发子代理的必读清单与产出格式。派这类子代理一律用 `.claude/agents/tag-rewrite` 代理类型，别再手写 brief——记忆由结构保证，不靠每次重新嘱咐。

本文与 `docs/agent-primer.md` 的关系：本文讲仓库**结构**，primer 讲**常识与红线**；两者的内容如与 `docs/rulings.md` 的裁定冲突，以裁定为准并回改。

**接手既有工作时**：先跑 `.claude/skills/handoff/SKILL.md`（转交技能）——它含开工顺序、现场约定（踩过的坑）、校验套件、**当前状态快照**与未完成目标。该文件的状态节有时效，与仓库文件冲突时以文件为准；每轮交付前顺手更新它。

## Commands

```bash
# Crawl one (or several) operators, with summons; resumable + throttled
.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"
#   new operator? first add a line to docs/operators.txt:  干员名 https://prts.wiki/w/干员名
#   flags: --force (re-crawl ok entries), --delay-min/--delay-max, --operators-file, --out-dir
#   爬虫写出前会跑 strip_noncombat()，落盘语料不含剧情/养成内容

# 核对证据层：全仓库 文件:行号 是否仍指向剥离前的原文（剥离或改行号后必跑）
.venv/Scripts/python.exe -X utf8 strip_prts_noncombat.py --audit   # --fix-stale 补正

# 核对条件/备注重排：对比 HEAD，查重排行是否丢数字、丢依据、留禁用符号（改过分文件后必跑）
#   有意改动的数字登记在脚本内的 ACCEPTED（键＝文件名｜干员，值＝放行令牌＋理由）
.venv/Scripts/python.exe -X utf8 audit_text_migration.py           # --only 01 只审某文件

# 批次回填：把 _out/<批名>.json（tag-rewrite 子代理的产出，键＝干员名）写回分文件
#   按表头定位列、以 HEAD 重建整行，只替换「条件」「备注」两格；行首机器协议前缀用 --keep-prefix 保留
.venv/Scripts/python.exe -X utf8 _apply_batch.py --tag P03 --file 03-吃拐一轮秒.md --out _out/P03-A.json

# PRTS 语料 → 机读属性层（属性/信赖/潜能/模组档位固定属性）→ material_datas/tag_pipeline/stats.json
.venv/Scripts/python.exe -X utf8 prts_stats.py                     # --check 只报覆盖率；--panel 干员 --stage e2 --pot 4 --module Δ --tier 3
# 产物数值校准：面板是否与条件声明的档位相符、模组档位是否取满、恒等式、内部代号、因子覆盖
.venv/Scripts/python.exe -X utf8 verify_numbers.py                 # --only P01；--coverage 只看因子覆盖清单

# Regenerate the merged player-TAG document after editing part files
.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py

# Generate the final results JSON from both member docs (spec: docs/output-standard.md §7)
.venv/Scripts/python.exe -X utf8 generate_results.py          # --check / --report
#   writes results/operator-tags.json; --check validates against the spec without writing

# Maintain player-TAG 荐 (recommended operators); data file player_tags/_recommend.json
.venv/Scripts/python.exe -X utf8 recommend.py list|add|remove|check   # 例：recommend.py add 充电 白铁
# Local web panel, three tabs:
#   「荐」= 荐 add/remove (详情 = info card + read-only 条件/备注 in the right column);
#   「人工归纳」= pick operators out of a TAG (扩展/移动/移除) into a staging area, fold them into
#     target 子表, and edit 条件/备注 (writes back to player_tags/NN-*.md and official_tags/[A-I]-*.md;
#     recomputes official 条目头);
#   「结果 JSON」= load results/*.json into memory (or start from a spec-shaped skeleton), edit with
#     structured cards + a raw-source view, then save via 覆盖已有文件 / 新建自定义文件名 — nothing is
#     written until 保存, and validation against docs/output-standard.md only warns, never blocks.
.venv/Scripts/python.exe -X utf8 recommend_gui.py                    # --port / --no-browser / --check
.venv/Scripts/python.exe -X utf8 -m gui                              # 同上（实现都在 gui/ 包内）

# Crawl attack ranges (per elite phase / skill / summon) into each operator dir; resumable
.venv/Scripts/python.exe -X utf8 crawl_ranges.py            # --only 干员名 / --force

# Regenerate the combat-term glossary JSON from docs/glossary.md (mirror-checked inside)
.venv/Scripts/python.exe -X utf8 glossary_to_json.py

# Refresh the PRTS《特殊机制》snapshot + normalized entries (network; throttled)
.venv/Scripts/python.exe -X utf8 crawl_special_mechanics.py  # --emit / --apply（追加术语章节）/ --input

# After any official-TAG structural change (add/rename/merge TAGs, member edits): rebuild
# the machine-readable dicts merged.json / final_lists.tsv from the module files
.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/official_tags/_merge_official_to_docs.py --sync-dicts
```

- On Windows the console is GBK: always run Python with `-X utf8` / `PYTHONIOENCODING=utf-8`, or write CJK output to a UTF-8 file and read it with the Read tool — printing CJK directly yields mojibake.
- PRTS requires **full browser headers** (UA + Accept + Accept-Language + Referer) and throttling (default 1.2–2.8 s/request); never crawl in a tight loop. See `.claude/skills/crawl-prts-operator/SKILL.md` for crawler internals and cleanup gotchas (hidden-span passes, markdownify image loss, Windows `os.replace` retry).

## Classification conventions (apply when adding/editing TABs or members)

- **Evidence-based**: every judgment cites `文件:行号` under `material_datas/PRTS/`; never classify from model memory. Uncertain items are marked `[待考]` and routed to 待开发者确认.
- **条件 vs 备注**: 条件 = hard requirements, 备注 = processed info (numbers, durations, hidden mechanics, tactical use) — the full rules, 反例 and 正例 live in `docs/concept.md`「结果展示」; follow that instead of restating it here. 两者的**排布规范**同在该文件：「条件分条」（`；` 只切并列要求，「或」合并成一条、支内用 `／`）与「备注分块」（`｜` 分块、`；` 分条、两层都用 `标签：正文`；块序 成绩→能力→计算→说明；`★` 分类标记与 `备注：` 类前缀禁用）。源单元格里用 `｜` 写、生成器解析成结果 JSON 的块数组；不符规范的行由 `generate_results.py --check` 的文本 lint 逐条列出，改动过的行另跑 `audit_text_migration.py`（数字守恒／依据不丢）。
- **数值取自机读层、不手抄**: 面板（满信赖＋最高精英满级＋有效潜能最高档＋条件点名模组档位固定属性）、潜能与模组各档固定属性的**唯一取数处是** `material_datas/tag_pipeline/stats.json`（`prts_stats.py` 从 PRTS 语料抽取，`panel_of()` 给面板与组成式）；产物里的每个 `面板NNN` 由 `verify_numbers.py` 回头校准。模组／潜能取对本 TAG 有帮助的最高档并写进条件（**「有帮助」按绝对贡献判**——不得因更高档会拉低比值／稀释均值而改取低档；有特限证章者优先按其数值，无者默认模组增伤条件均满足、取更高者并把条件写进条件，见 `docs/rulings.md`）；成绩只允许「精英0/1 可满足的最低档＋最高档」与「特殊机制多情形」两种并列，其余取满配档；能力块必须自足（写清该能力本身）；未计入项逐条写进 `说明`；**内部代号（范围代号、`S1/S2/S3`、`表 2A`、`路径⑤`、英文模组码）不入产物**。演算默认敌人为**纯木桩**（0 防御／0 法抗／0 闪避免伤／无减伤）：作用于敌方防/抗数值的减益与穿透不计入，承伤倍率型增伤（脆弱、通缉）照计。
- **No dropped capabilities**: an operator's entry lists **every** capability meeting that TAG's 评定标准 — multiple qualifying features are all written (条件 covers each hard requirement, 备注 itemizes them); never omit one because it overlaps, is smaller, or a stronger one is already written.
- **Module tiers (模组档位)**: when a module enhances the capability a TAG judges, 条件 names the module + level (e.g. `Y模组3级`) and 备注 uses that tier's values; pick the highest tier whose **absolute** contribution to this TAG's judged capability is greatest — never a lower tier just because the higher one dilutes a ratio or margin; operators with a 特限证章 (mode-limited module) are computed from that module first, others assume every module's boost condition holds and take the higher line, writing the enabling condition into 条件. Different TAG rows may cite different modules. No vague "X模组更佳/可选" phrasing; modules irrelevant to the TAG are not mentioned.
- **Summons/devices count as the owner's capability.** **Mode-limited modules (ISW-α/RA-α etc.) count** for player TAGs — state the mode restriction in 条件 and note it in 备注.
- Direction matters (to allies vs self vs enemies); one operator may belong to **multiple TAGs**; player TAGs may have **sub-TAGs** (implementation/type/scope distinctions).
- Mechanism-level, time-independent only: no tier-list / current-meta claims.
- Member tables sort by release date descending (date from PRTS `## 获得方式`, cached in `player_tags/_launch_dates.json`); boundary/combo tables follow their own grouping.
- 开发者的裁定与开放问题落在各分文件自身的 `## 待开发者确认` 与评定标准/边界与排除记录里 — read the target file's 评定标准 and 边界与排除记录 before changing any player TAG.
- Player-TAG work uses parallel agents: one agent per TAG writes an evidence-bearing part file under `player_tags/`, following `_brief.md`; the merge script consolidates them into `docs/player-tags-members.md` (stripping the 依据 column). Keep evidence in the part files.
- Adding a new TAG: follow `.claude/skills/add-player-tag/SKILL.md` — make the 评定标准 fully unambiguous with the developer before any member work, unless they explicitly choose the "先创建此TAG，评定标准后续更新" stub option.
- New operator released (developer gives a PRTS link or description): follow `.claude/skills/add-new-operator/SKILL.md` — crawl into `material_datas/PRTS/`（含攻击范围）, judge every TAG (official + player), ask the developer about notable mechanics no TAG covers, then update the member docs (`docs/official-tags-members.md` + part files → merged doc) only — never generate `results/operator-tags.json`.
- Version update (new operator **plus** new modules on existing operators, incremental): follow `.claude/skills/update-version/SKILL.md` — refresh only the changed operators, fold new modules into the affected rows (模组档位), and run the cross-operator impact checklist (新阵营成员/使能者/对外挂点…); never a full-table rescan.

### TAG criteria: 评定标准 writing rules (official AND player TAGs)

- A TAG's evaluation standard is called **评定标准** — use that term everywhere: the section heading (`## 评定标准`), its sub-headings, and any prose that states, applies or records a standard. This applies to **both TAG systems**: the official entries (`docs/official-tags-members.md` §1/§4) and every player-TAG file (`material_datas/tag_pipeline/player_tags/NN-*.md`). Do not use 口径, 裁决 or any other synonym for the standard itself; sub-rules (how a count is computed, rounding, etc.) use plain words — 计数方式 / 计算方式 / 判定 / 门槛 — never 口径.
- When adding, revising or removing a standard, **never stamp dates or round labels** (`2026-09-11`, 本轮, 追加, 最新, 二次更新…) and never write the edit itself into the text (no "覆盖上一轮…", 已落实, 重新纳入, 移出改为…, 修正后, before/after phrasing). A reader must not be able to tell from the text which round a rule came from.
- Every TAG's 评定标准 must be **清晰、有序、整洁、风格一致**:
  - 清晰 — 纳入写「收什么」，排除写「不收什么」，判定阈值与算式给全；
  - 有序 — 固定顺序：规格原文（如有）→ 纳入 → 排除 → 与其它 TAG 的关系 → 通用约定（数值档位、召唤物/装置、模式限定模组）；有子 TAG 时每个子 TAG 独立成块、用同一套小标题；
  - 整洁 — 不重复、不夹叙旧账、不引用本文件其它小节编号之外的"第几条"；
  - 风格一致 — 统一用 `**纳入**：`、`**排除**：`、`**与其它 TAG 的关系**：`、`**约定**：` 等加粗标签起头。
- Fold each new standard into the existing structure — the path it belongs to, the member table, the boundary records — then re-read that TAG's whole 评定标准 section and tidy it: merge redundancies, renumber paths, re-word so it reads as one clean spec written in a single pass.
- Boundary, exclusion and 待开发者确认 records state rules/facts and their rationale only; they are not a changelog of how the list evolved (drop 本轮／日期／已落实-style labels there too). 检索记录 is the one place where dated process entries may remain.

## AI 协作铁律（工作流程）

1. **自创代称必须映射**：文档与本仓库 AI 输出中使用的任何代称、缩写、自编号（规则号 R1–R24、历史冲突号 C1–C10、TAG 代号 P01–P12、X模组/Y模组、公式符号等），一律登记在 `docs/term-map.md`（代称映射表）——逐条写明含义、用法与查阅位置。**创建任何新的代称／自创词时必须同步维护该表**；未登记的代称不得在交付文本中使用。
2. **裁定内容所见即所得、并且必须留痕**：所有待开发者裁定的内容集中于根目录单一文件 `待裁定.md`——每条自包含（背景、现状、候选值／选项、**支撑判断的计算式与来源**），开发者**仅需阅读该文件**即可完成全部裁定，无需查阅任何其它文件；文中出现的任何**自创词／简称必须当场解释该怎么理解**；涉及模组线（X／Y／Δ／特限证章等）、专有机制、道具、自编号与代称时，**必须给出完整描述**（名称、效果原文、数值、模式限定与达成条件）——**不得假设开发者的知识储备与自己对齐**。裁定后**四步缺一不可**：① 折入源文件（分文件／规则／复算产物）；② 在 `docs/rulings.md`（裁定台账）登记一条（**裁定／理由／适用范围／折入位置**）；③ 脚本侧逐条放行表（`ACCEPTED`／`REVIEWED_TIERS` 等）写明理由并指向台账；④ 整体移除 `待裁定.md`。**先查台账再提问**——同一个问题问第二遍就是流程失败。与《待验证复算.md》的分工：后者只保留数值复核职能（复算值与结论、回填行），一切需要开发者裁决的问题一律并入 `待裁定.md`。
3. **改动的授权边界**：**开发者明确要求修改的，必须动；AI 自行发现「可能需要修改」的，一律先写进《待裁定.md》问过开发者再决定**——不得自行改动、不得顺带修。自行放大工具权限同属越界（代理定义的 `allowed-tools` 一经收窄，放宽须经开发者明确同意）。

## Working notes

- Git branch `master`; `docs/player-tags-specify.md` is periodically hand-edited by the developer. Do not commit unless asked.
- The mechanics docs (`mechanism-understanding.md`, `verification-complaints.md`) exist because the same misjudgments recur (e.g. 灼烧 DoT ≠ 灼燃损伤; 屏障 vs 护盾 vs 闪避; "每帧检测" implementation notes vs real frame mechanics) — consult them before asserting a mechanism.
- Game-term definitions live in `docs/glossary.md` — check it before judging anything phrased as a term (e.g. 过载 = 技能进行到一半时触发额外效果、覆盖后半程；魔力、吟唱 同此).

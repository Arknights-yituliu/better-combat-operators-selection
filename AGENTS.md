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

- `material_datas/PRTS/` — one folder per operator; operator page plus one sibling `.md` per summon. `_manifest.json` is the crawler's resume record (per-operator status/files/summon links).
- `material_datas/tag_pipeline/` — official-TAG machine-readable dicts (`catalog.json` = TAG dictionary — the only dict scripts read, `merged.json` = operator→TAG ids, `deterministic.json` = parsed base stats/summons — a snapshot that does not follow TAG changes; `merged.json` / `final_lists.tsv` rebuilt by `_merge_official_to_docs.py --sync-dicts`; `final_lists.tsv` = TAG→members) and `player_tags/` for the player-TAG workflow.
- `information_records/` — pipeline/crawler notes and extraction decisions; `docs/mechanism-understanding.md` + `docs/verification-complaints.md` — mechanics primer and known judgment pitfalls (dated notes — their counts reflect the day they were written; current lists live in the member docs).
- `docs/concept.md` — project intent and the 条件/备注/结果 JSON rules that all classification work follows (the one place those writing rules live); `docs/output-standard.md` — final results JSON spec (version/date, operator cards, PRTS deep links, 荐); `docs/untagged-operators.md` — 未归入任何 TAG 的干员（auto-written by `generate_results.py`: full roster minus `operators[]`). `docs/player-tags-specify.md` — 玩家 TAG 定义（开发者手改）; `docs/calc-rules.md` — 计算规则正本（结算层位与总式、游戏文本→因素映射、演算流程、未定项索引），数值门槛与术语只作指针指向 `docs/player-tags-specify.md`／`docs/glossary.md`; `docs/ui-render-rules.md` — 消费端（前端项目）渲染规则记录，改 JSON 结构时对照之.
- `gui/` — the maintenance panel as a package: `config/errors/md` (leaf) → `tags/roster/recommends/merges/results_json` (data) → `writeback/model` (business) → `server/selfcheck/__main__`; page assets in `gui/static/` (`index.html` + `app.css` + `app.js`, styled with ak-ui dark tokens — see the CSS header for provenance and the density compromise). `recommend_gui.py` at the root is a thin entry point (`python -m gui` is equivalent). Usage guide (English): `gui/README.md`.
- The UI itself is **out of scope** for this repo (the panel above is a maintainer tool, not the product UI).

### File authority map (what to trust, what to edit)

Read only what the task needs; the two member docs and the two results JSONs are large — read them by §／target TAG, never whole.

**手写权威源（改这些）**: `docs/concept.md`（意图＋条件/备注规则）、`docs/output-standard.md`（产物规范）、`docs/player-tags-specify.md`（玩家 TAG 定义）、`docs/calc-rules.md`（计算规则正本：结算层位／文本→因素映射／演算流程；复算作业副本为 `player_tags/_reverify/rules.md`）、`docs/term-map.md`（代称映射表：一切自创代称／缩写／自编号的含义与查阅位置，改动或新增代称时同步）、`material_datas/tag_pipeline/official_tags/[A-I]-*.md`（官方 TAG 定义与成员，GUI 写回可改）、`material_datas/tag_pipeline/player_tags/NN-*.md`（玩家 TAG 判定＋证据；`_brief.md` 为作业规范）、`docs/glossary.md`（术语；前 5 节手写，后 6 节由 `crawl_special_mechanics.py --apply` 追加）、字典 `catalog.json`／`char_ids.json`／`_launch_dates.json`／`docs/operators.txt`。

**生成物（勿手改，改上列源文件后重生成）**: `docs/official-tags-members.md` §3/§4/§5 ← `_merge_official_to_docs.py`；`docs/player-tags-members.md` ← `player_tags/_merge_to_docs.py`；`results/operator-tags.json` ＋ `docs/untagged-operators.md` ← `generate_results.py`；`results/combat_glossary.json` ← `glossary_to_json.py`；`material_datas/PRTS/**`（含 `_manifest.json`、`_range_codes.json`、`特殊机制/`）← 三个爬虫；`merged.json`／`final_lists.tsv` ← `--sync-dicts`（无脚本读取）；`deterministic.json`＝基础属性快照（不随 TAG 变化）。

**只为背景、不作依据**: `information_records/*`、`docs/verification-complaints.md`、`docs/mechanism-understanding.md`（含整理当日的旧计数）、`player_tags/_mode-limited-module-audit.md`、`official-fullmap-aura.md`（历史转制稿）。

## Commands

```bash
# Crawl one (or several) operators, with summons; resumable + throttled
.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"
#   new operator? first add a line to docs/operators.txt:  干员名 https://prts.wiki/w/干员名
#   flags: --force (re-crawl ok entries), --delay-min/--delay-max, --operators-file, --out-dir

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
- **条件 vs 备注**: 条件 = hard requirements, 备注 = processed info (numbers, durations, hidden mechanics, tactical use) — the full rules, 反例 and 正例 live in `docs/concept.md`「结果展示」; follow that instead of restating it here.
- **No dropped capabilities**: an operator's entry lists **every** capability meeting that TAG's 评定标准 — multiple qualifying features are all written (条件 covers each hard requirement, 备注 itemizes them); never omit one because it overlaps, is smaller, or a stronger one is already written.
- **Module tiers (模组档位)**: when a module enhances the capability a TAG judges, 条件 names the module + level (e.g. `Y模组3级`) and 备注 uses that tier's values; with multiple modules pick the one that strengthens **this TAG's** capability — different TAG rows may cite different modules. No vague "X模组更佳/可选" phrasing; modules irrelevant to the TAG are not mentioned.
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
2. **裁定内容所见即所得**：所有待开发者裁定的内容集中于根目录单一文件 `待裁定.md`——每条自包含（背景、候选值／选项、需要你决定什么），开发者**仅需阅读该文件**即可完成全部裁定，无需查阅任何其它文件；裁定完成后折入源文件（分文件／规则／复算产物），并**整体移除该文件**。该流程用于降低认知负担、提升裁定效率；新增待裁定项一律先并入该文件再交付。与《待验证复算.md》的分工：后者只保留数值复核职能（复算值与结论、回填行），一切需要开发者裁决的问题一律并入 `待裁定.md`。

## Working notes

- Git branch `master`; `docs/player-tags-specify.md` is periodically hand-edited by the developer. Do not commit unless asked.
- The mechanics docs (`mechanism-understanding.md`, `verification-complaints.md`) exist because the same misjudgments recur (e.g. 灼烧 DoT ≠ 灼燃损伤; 屏障 vs 护盾 vs 闪避; "每帧检测" implementation notes vs real frame mechanics) — consult them before asserting a mechanism.
- Game-term definitions live in `docs/glossary.md` — check it before judging anything phrased as a term (e.g. 过载 = 技能进行到一半时触发额外效果、覆盖后半程；魔力、吟唱 同此).

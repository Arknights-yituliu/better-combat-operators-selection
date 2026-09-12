# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **data-production repository** (not an app) for an Arknights operator-filtering system. It crawls the PRTS wiki into local markdown, then classifies every operator under two TAG systems (official-defined + player-perception) and produces per-operator results consumed by a **separate UI project**. There is no build/lint/test tooling; the code is a handful of one-off Python data scripts. Working language is Chinese; all documents/outputs are Chinese.

The eventual product is a single results JSON (`results/operator-tags.json`; format spec: `docs/output-standard.md`). TAG definitions, membership lists, counts and open questions change frequently — this file describes stable structure and conventions only; treat `docs/` as the source of truth for content.

## Data flow / architecture

```
docs/operators.txt ──► crawl_prts.py ──► material_datas/PRTS/<干员>/<干员>.md (+ <召唤物>.md siblings)
crawl_ranges.py ──► material_datas/PRTS/<干员>/攻击范围.md（攻击范围网格：各精英化阶段 / 技能 / 召唤物；PRTS 用内联 SVG 绘制，主爬虫不抓）
                                              │
                                              │
        official TAGs:  material_datas/tag_pipeline/{catalog,merged,deterministic}.json + final_lists.tsv
                        └─► docs/official-tags-members.md
        player TAGs:    docs/player-tags-specify.md（定义）
                        material_datas/tag_pipeline/player_tags/NN-*.md（分 TAG 判定文件，含逐条 文件:行号 证据）
                        docs/judge-for-player-tags-members-1.md / -2.md（开发者评定标准，修改 TAG 前必读）
                        _brief.md（共享评定标准）+ _launch_dates.json + _merge_to_docs.py + _recommend.json（荐，recommend.py 维护）
                        └─► docs/player-tags-members.md（自动生成，勿手改：改分文件后重新合并）
                        └─► results/operator-tags.json（最终输出，规范见 docs/output-standard.md；尚未生成）
```

- `material_datas/PRTS/` — one folder per operator; operator page plus one sibling `.md` per summon. `_manifest.json` is the crawler's resume record (per-operator status/files/summon links).
- `material_datas/tag_pipeline/` — official-TAG pipeline artifacts (`catalog.json` = TAG dictionary, `merged.json` = operator→TAG ids, `deterministic.json` = parsed base stats/summons, `final_lists.tsv` = TAG→members) and `player_tags/` for the player-TAG workflow.
- `information_records/` — pipeline/crawler notes and extraction decisions; `docs/mechanism-understanding.md` + `docs/verification-complaints.md` — mechanics primer and known judgment pitfalls; `docs/player-tags.md` — v1 draft of player TAGs from the video corpus (leads only, not authoritative).
- `docs/concept.md` — project intent and the 条件/备注/结果 JSON rules that all classification work follows; `docs/output-standard.md` — final results JSON spec (version/date, operator cards, PRTS deep links, 荐).
- The UI itself is **out of scope** for this repo.

## Commands

```bash
# Crawl one (or several) operators, with summons; resumable + throttled
.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"
#   new operator? first add a line to docs/operators.txt:  干员名 https://prts.wiki/w/干员名
#   flags: --force (re-crawl ok entries), --delay-min/--delay-max, --operators-file, --out-dir

# Regenerate the merged player-TAG document after editing part files
.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py

# Maintain player-TAG 荐 (recommended operators); data file player_tags/_recommend.json
.venv/Scripts/python.exe -X utf8 recommend.py list|add|remove|check   # 例：recommend.py add 充电 白铁
# Local web panel for the same file + per-operator 条件/备注 editing (writes back to NN-*.md)
.venv/Scripts/python.exe -X utf8 recommend_gui.py                    # --port / --no-browser / --check

# Crawl attack ranges (per elite phase / skill / summon) into each operator dir; resumable
.venv/Scripts/python.exe -X utf8 crawl_ranges.py            # --only 干员名 / --force
```

- `main.py` is an unused PyCharm stub.
- On Windows the console is GBK: always run Python with `-X utf8` / `PYTHONIOENCODING=utf-8`, or write CJK output to a UTF-8 file and read it with the Read tool — printing CJK directly yields mojibake.
- PRTS requires **full browser headers** (UA + Accept + Accept-Language + Referer) and throttling (default 1.2–2.8 s/request); never crawl in a tight loop. See `.claude/skills/crawl-prts-operator/SKILL.md` for crawler internals and cleanup gotchas (hidden-span passes, markdownify image loss, Windows `os.replace` retry).

## Classification conventions (apply when adding/editing TABs or members)

- **Evidence-based**: every judgment cites `文件:行号` under `material_datas/PRTS/`; never classify from model memory. Uncertain items are marked `[待考]` and routed to 待开发者确认.
- **条件 vs 备注**: 条件 = hard requirements (精英化/技能/专精/模组与等级/模式限定/目标限制; "无" if available at E0L1). 备注 = processed info — numbers, durations, hidden mechanics, tactical use; do not restate what the in-game text already shows plainly.
- **Summons/devices count as the owner's capability.** **Mode-limited modules (ISW-α/RA-α etc.) count** for player TAGs — state the mode restriction in 条件 and note it in 备注.
- Direction matters (to allies vs self vs enemies); one operator may belong to **multiple TAGs**; player TAGs may have **sub-TAGs** (implementation/type/scope distinctions).
- Mechanism-level, time-independent only: no tier-list / current-meta claims.
- Member tables sort by release date descending (date from PRTS `## 获得方式`, cached in `player_tags/_launch_dates.json`); boundary/combo tables follow their own grouping.
- `docs/judge-for-player-tags-members-1.md` / `-2.md` hold the developer's feedback per open question — read them before changing any player TAG.
- Player-TAG work uses parallel agents: one agent per TAG writes an evidence-bearing part file under `player_tags/`, following `_brief.md`; the merge script consolidates them into `docs/player-tags-members.md` (stripping the 依据 column). Keep evidence in the part files.
- Adding a new TAG: follow `.claude/skills/add-player-tag/SKILL.md` — make the 评定标准 fully unambiguous with the developer before any member work, unless they explicitly choose the "先创建此TAG，评定标准后续更新" stub option.
- New operator released (developer gives a PRTS link or description): follow `.claude/skills/add-new-operator/SKILL.md` — crawl into `material_datas/PRTS/`（含攻击范围）, judge every TAG (official + player), ask the developer about notable mechanics no TAG covers, then update the member docs (`docs/official-tags-members.md` + part files → merged doc) only — never generate `results/operator-tags.json`.

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

## Working notes

- Git branch `master`; `docs/player-tags-specify.md` is periodically hand-edited by the developer. Do not commit unless asked.
- The mechanics docs (`mechanism-understanding.md`, `verification-complaints.md`) exist because the same misjudgments recur (e.g. 灼烧 DoT ≠ 灼燃损伤; 屏障 vs 护盾 vs 闪避; "每帧检测" implementation notes vs real frame mechanics) — consult them before asserting a mechanism.

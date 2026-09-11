# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **data-production repository** (not an app) for an Arknights operator-filtering system. It crawls the PRTS wiki into local markdown, then classifies every operator under two TAG systems (official-defined + player-perception) and produces per-operator results consumed by a **separate UI project**. There is no build/lint/test tooling; the code is a handful of one-off Python data scripts. Working language is Chinese; all documents/outputs are Chinese.

The eventual product is a results JSON per operator. TAG definitions, membership lists, counts and open questions change frequently — this file describes stable structure and conventions only; treat `docs/` as the source of truth for content.

## Data flow / architecture

```
docs/operators.txt ──► crawl_prts.py ──► material_datas/PRTS/<干员>/<干员>.md (+ <召唤物>.md siblings)
                                              │
                                              │
        official TAGs:  material_datas/tag_pipeline/{catalog,merged,deterministic}.json + final_lists.tsv
                        └─► docs/tags.md
        player TAGs:    docs/player-tags-specify.md（定义）
                        material_datas/tag_pipeline/player_tags/NN-*.md（分 TAG 判定文件，含逐条 文件:行号 证据）
                        docs/judge-for-player-tags-members-1.md / -2.md（开发者评定标准，修改 TAG 前必读）
                        _brief.md（共享评定标准）+ _launch_dates.json + _merge_to_docs.py
                        └─► docs/player-tags-members.md（自动生成，勿手改：改分文件后重新合并）
```

- `material_datas/PRTS/` — one folder per operator; operator page plus one sibling `.md` per summon. `_manifest.json` is the crawler's resume record (per-operator status/files/summon links).
- `material_datas/tag_pipeline/` — official-TAG pipeline artifacts (`catalog.json` = TAG dictionary, `merged.json` = operator→TAG ids, `deterministic.json` = parsed base stats/summons, `final_lists.tsv` = TAG→members) and `player_tags/` for the player-TAG workflow.
- `information_records/` — pipeline/crawler notes and extraction decisions; `docs/mechanism-understanding.md` + `docs/verification-complaints.md` — mechanics primer and known judgment pitfalls; `docs/player-tags.md` — v1 draft of player TAGs from the video corpus (leads only, not authoritative).
- `docs/concept.md` — project intent and the 条件/备注/结果 JSON rules that all classification work follows.
- The UI itself is **out of scope** for this repo.

## Commands

```bash
# Crawl one (or several) operators, with summons; resumable + throttled
.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"
#   new operator? first add a line to docs/operators.txt:  干员名 https://prts.wiki/w/干员名
#   flags: --force (re-crawl ok entries), --delay-min/--delay-max, --operators-file, --out-dir

# Regenerate the merged player-TAG document after editing part files
.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py
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

### Player-TAG criteria: 评定标准 writing rules

- A TAG's evaluation standard is called **评定标准** — use that term everywhere: the section heading (`## 评定标准`), its sub-headings, and any prose that states, applies or records a standard. Do not use 口径 or 裁决.
- When adding or revising a standard, **never stamp dates or round labels** (`2026-09-11`, 本轮, 追加…) and never write the edit itself into the text (no "覆盖上一轮…", 收紧, 补充, before/after phrasing).
- Fold each new standard into the existing structure — the path it belongs to, the member table, the boundary records — then re-read that TAG's whole 评定标准 section and tidy it: merge redundancies, renumber paths, re-word so it reads as one clean spec written in a single pass.
- Boundary and exclusion records state facts and rationale only; they are not a changelog of how the list evolved.

## Working notes

- Git branch `master`; `docs/player-tags-specify.md` is periodically hand-edited by the developer. Do not commit unless asked.
- The mechanics docs (`mechanism-understanding.md`, `verification-complaints.md`) exist because the same misjudgments recur (e.g. 灼烧 DoT ≠ 灼燃损伤; 屏障 vs 护盾 vs 闪避; "每帧检测" implementation notes vs real frame mechanics) — consult them before asserting a mechanism.

---
name: add-player-tag
description: Add a new TAG (玩家体感 TAG) to this project. Use whenever the developer says they want to 新增/添加 a TAG, create a new player-perception TAG, or extend the TAG system. The first job is always to make the evaluation criteria (评定标准) unambiguous by asking the developer — or, if they choose so, to create the TAG as a stub whose criteria are updated later.
---

# Add a new TAG

## Rule 0 — the 评定标准 must be unambiguous before any member work

A TAG's 评定标准 drives every later judgment: the member scan, the evidence, the UI filter.
A vague definition ("像 XX 那样的干员") is not a 评定标准. **Never guess it and never start scanning members until it is clear** — ask the developer and keep asking until every point below is answered.

1. **纳入标准** — which mechanisms/behaviors qualify; if several paths count, name them.
2. **排除边界** — near-miss cases the developer does *not* want in (have them name 2–3 borderline operators).
3. **条件 vs 备注** — what is a hard requirement (精英化 / 技能 / 专精 / 模组与等级 / 模式限定 / 目标限制) vs processed info (numerics, durations, hidden mechanics, tactical use).
4. **方向与对象** — to allies / self / enemies; single-target vs group; any source restrictions.
5. **子 TAG** — whether the TAG needs implementation/type/scope sub-TAGs.
6. **时间无关性** — confirm the standard is mechanism-level (no tier-list or current-meta claims).

Ask with the AskUserQuestion tool when the question is choice-shaped, plain text otherwise. One round of questions is the minimum; if an answer is still vague, say exactly which part is unclear and ask again.

## Offer the stub option

Every time the criteria are not yet clear, offer this as an explicit choice:

> **先创建此TAG，评定标准后续更新** — create the TAG now and update the 评定标准 later.

If the developer picks it:

- Create `material_datas/tag_pipeline/player_tags/NN-<TAG名>.md` (NN = next free index) with the raw definition under `## 评定标准`, marked `[待考]`, an empty 成员表, and a `## 待开发者确认` item listing precisely what is still unclear.
- Register the TAG: add it to the `TAGS` list in `player_tags/_merge_to_docs.py` and add a section to `docs/judge-for-player-tags-members-2.md`.
- `docs/player-tags-specify.md` is hand-edited by the developer — ask them to add the definition sentence rather than editing it yourself.
- Run the merge script so the stub appears in `docs/player-tags-members.md`.

## Once the 评定标准 is clear

1. **Pick the index/name**: `NN-<TAG名>.md` (existing part files are `01-…`–`12-…`).
2. **Register**: `_merge_to_docs.py` TAGS list, `docs/player-tags-specify.md`, `docs/judge-for-player-tags-members-2.md`.
3. **Write `## 评定标准`** following the 评定标准 writing rules in CLAUDE.md: use the term 评定标准 (never 口径 or 裁决), no dates, no edit traces; numbered paths when there are several; state boundaries and exclusions.
4. **Member scan**: drive full-corpus searches from the criteria keywords (PRTS pages under `material_datas/PRTS/` + `deterministic.json`); every inclusion and exclusion cites `文件:行号`; summons/devices count as the owner; mode-limited modules (ISW-α/RA-α/SO-α…) count, with the mode written into 条件.
5. **Boundary records**: 纳入存疑 / 明确排除 with rationale + evidence; unresolved items go to `## 待开发者确认`.
6. **Cross-TAG check**: compare with every other TAG main table, update the 多 TAG 并存 notes on both sides.
7. **Merge and verify**: run `.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py`, check the 总览 row count and the diff.

## Do not

- Do not invent or silently narrow/widen the 评定标准; do not classify from model memory.
- Do not write dates, round labels ("本轮新增"), or "覆盖上一轮…" phrasings into the criteria section.
- Do not edit `docs/player-tags-specify.md` on your own — it belongs to the developer.

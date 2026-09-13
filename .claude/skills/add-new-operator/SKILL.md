---
name: add-new-operator
description: Evaluate a newly released operator against every TAG (官方设定 TAG + 玩家体感 TAG) and update the member lists. Use when the developer provides a new operator's PRTS link (or a manual description), says a new 干员 has been released / needs to be classified, or asks to fold fresh PRTS data into the TAG system. Pipeline - crawl into material_datas/PRTS, judge every TAG, ask the developer about special mechanics no TAG covers, then update docs/*-members.md only (never generate results/operator-tags.json).
---

# Add a new operator (新干员评定流程)

Fixed pipeline: **crawl → judge every TAG → ask about uncovered mechanics → update member lists only.**

## 0. Inputs

- The developer gives one or more PRTS links (`https://prts.wiki/w/白铁`). A manual description is acceptable when PRTS has no page yet (announced-but-not-live operators) — judge only what the description states and mark the rest `[待考]`.
- A brand-new page may be incomplete (模组/数值 rows still filling in). Judge what exists; gaps → `[待考]` → `## 待开发者确认`.
- Batches: run steps 1–4 per operator, and batch all developer questions into **one** AskUserQuestion round at the end.

## 1. Crawl (per operator)

1. If missing, append to `docs/operators.txt` in the existing format: `<干员名> https://prts.wiki/w/<干员名>` (use the PRTS page name, e.g. `阿米娅(近卫)`).
2. `.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"` — summons are crawled automatically next to the main file; the run is resumable.
3. `.venv/Scripts/python.exe -X utf8 crawl_ranges.py --only "干员名"` — attack-range grids per elite phase / skill / summon.
4. Add the operator's 上线时间 to `material_datas/tag_pipeline/player_tags/_launch_dates.json` (format `"干员名": "YYYY-MM-DD"`, from the crawled `## 获得方式`) — the merge script reads it for the 实装时间 column.
5. Verify per `.claude/skills/crawl-prts-operator/SKILL.md` → "Verify after crawling": folder + `<干员名>.md` + one file per summon + `## 特性/天赋/技能/模组` + `攻击范围.md`; the 属性 table (稀有度/职业/所属势力/攻击间隔) must be present — the judgments need it. For judgments that need the range grid, read `攻击范围.md`.

## 2. Judge every TAG (single pass)

Read the new operator's md in full (summons included), then screen all TAGs. Efficient order:

1. **机制词表粗筛** — list the operator's mechanisms in plain words (控制/位移/召唤/伤害类型/资源回复/生存/部署/攻击行为…), then open only the plausible TAG entries.
2. **官方设定 TAG** — `docs/official-tags-members.md`: apply §1 判定铁律 (免疫≠持有、名称≠机制、数值减益不设 TAG…) and each §4 entry's definition + 备注. Summons/devices count as the owner; mode-limited modules count (write the mode into the eventual 条件). Collect the TAGs whose 成员 line gains the new operator.
3. **玩家体感 TAG** — `material_datas/tag_pipeline/player_tags/NN-*.md` (13 files): read each file's `## 评定标准` **and its 边界与排除记录** before deciding. Prepare the member row in the file's format:
   - `| 干员 | [子 TAG] | 条件 | 备注 | 依据 |` — 条件 = hard requirements (精英化/技能/专精/模组与等级/模式限定/目标限制; `无` if available at E0·1), 备注 = processed info (numbers, durations, hidden mechanics, tactical use), 依据 = `文件:行号`.
   - Judge the sub-TAGs too: 拐杖 子 TAG 列 / 次数对策 两张子表 / 吃拐一轮秒 聚爆·连射 / 保人 七个分部 / 阵容组合 组合名 等。
   - Near-misses go to the file's 边界与排除记录 with rationale + evidence, not into the member table.
4. **Multi-TAG** —多数新干员会同时落多个 TAG；TAG 之间不互斥（写明关系的除外，如 吃拐一轮秒 与 决战歼灭 不互斥）。顺手在两端的「多 TAG 并存」记录里互链。
5. **Batches ≥3 operators**: split the TAG families across parallel read-only agents (official 80 is mechanical/keyword-driven; player 13 is judgment-driven), then verify their findings against PRTS原文 before writing.

## 3. Special mechanics with no TAG → ask the developer

After the pass, list every **值得在意的机制** that no existing TAG covers — new 异常/状态关键词、新的结算方式、新的资源机制、超出既有阈值的设计。For each, prepare the evidence (`文件:行号` + 原文) and ask the developer with AskUserQuestion (batch all items):

1. **创建新 TAG** → follow `.claude/skills/add-player-tag/SKILL.md` (make the 评定标准 unambiguous first; offer the "先创建此TAG，评定标准后续更新" stub).
2. **归入现有 TAG** 的备注/边界（指明哪个 TAG、哪一类）.
3. **仅记录不建 TAG**（写入该干员的边界记录或 `_brief.md`）.

Never create a TAG from your own judgment; never silently drop a notable mechanic. Pure numeric differences (数值筛选维度) and 泛在机制 (普通治疗、普攻伤害) need no TAG and no question.

## 4. Update the member lists (the only output)

1. **官方** — edit the split modules under `material_datas/tag_pipeline/official_tags/`（`official_tags/*.md` 各分模块），然后运行合并脚本重生成文档：
   - 在每个命中的 TAG 的成员表（`| 干员 | 条件 | 备注 |`）中按**实装时间倒序**插入一行：条件＝硬性要求（精英化／技能／模组与等级／模式限定；天生即具备写「无」），备注＝游戏内原文引用；
   - run `.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/official_tags/_merge_official_to_docs.py` — 脚本自动重算各 TAG「N 人 · 首现」、§3 总览与 §5 时间线，并合入 `docs/official-tags-members.md`；
   - the pipeline artifacts (`material_datas/tag_pipeline/{merged.json,final_lists.tsv,…}`) are **not** maintained entry-by-entry — see `docs/output-standard.md` §7.
2. **玩家** — edit the part files (`成员表` + 边界/多 TAG 并存 as needed), then run:
   `.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py`
   and verify the 总览 rows in `docs/player-tags-members.md` (each affected TAG 行数 +N).
3. **体检** — `git diff --stat` shows only the expected files; 评定标准 sections must be untouched (this pipeline updates *member lists*; needing a criteria change is a separate task for the developer). Then verify a couple of new rows render correctly in the merged doc.
4. **Do NOT generate `results/operator-tags.json`** — the final JSON is produced separately per `docs/output-standard.md`. Do not commit unless asked.

## Do not

- Do not classify from model memory — every judgment cites `文件:行号` under `material_datas/PRTS/`; unknown items are `[待考]` → `## 待开发者确认`.
- Do not write dates, round labels or edit traces into any 评定标准 section (CLAUDE.md rules), and do not renumber/rewrite criteria while adding members.
- Do not edit `docs/player-tags-specify.md` (developer-owned).
- Do not create new TAGs unilaterally; do not touch `docs/judge-for-player-tags-members-*.md` unless a ruling changed (待确认 items live in the part files).
- Do not skip the crawl verification or judge ranges from memory — `攻击范围.md` is the authority for 范围类 TAG（决战歼灭、远程消耗等）.

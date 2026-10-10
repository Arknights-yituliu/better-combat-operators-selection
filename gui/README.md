# TAG Maintenance Panel — Developer Guide

A local, single-user web panel for maintaining the operator TAG data of this repository:
the 荐 lists, the member tables of every TAG (both TAG systems), and the final
`results/*.json` deliverable. It is a plain Python `http.server` on `127.0.0.1`
(stdlib only, no build step) serving three screens from `gui/static/`.

> The UI itself is in Chinese. This guide names every control in Chinese with an English gloss.

---

## 1. At a glance

| Tab | Chinese | What you do there | Writes to disk |
|---|---|---|---|
| Recommendations | 荐 | Add / remove the recommended operators (荐) of a player TAG; 详情 shows an info card in the right column | `agent_workspace/tag_pipeline/player_tags/_recommend.json` (immediately) |
| Manual induction | 人工归纳 | Pick operators out of a TAG (or the full roster), stage them, fold them into target sub-tables, edit 条件 / 备注 | the markdown part files, immediately (see §5) |
| Results JSON | 结果 JSON | Load `results/*.json` into memory, edit it (structured cards + raw source), save with two options; saving recomputes each player TAG's 荐 fields from `_recommend.json` | only when you press **保存…** |

Data conventions (what belongs in 条件 vs 备注, TAG criteria, the output schema) live in
`docs/concept.md`, `docs/output-standard.md`, `docs/player-tags-specify.md` and the per-TAG part
files — this guide only explains the tool.

---

## 2. Requirements and running

```bash
# from the repository root
start_gui.bat                 # Windows: double-click or run; uses .venv when present
./start_gui.sh                # macOS/Linux equivalent
.venv/Scripts/python.exe -X utf8 recommend_gui.py                 # start + open the browser
.venv/Scripts/python.exe -X utf8 recommend_gui.py --port 8520 --no-browser
.venv/Scripts/python.exe -X utf8 recommend_gui.py --check         # read-only self-test, no server
.venv/Scripts/python.exe -X utf8 -m gui                           # identical (implementation lives in gui/)
```

* Python 3.11+. The panel itself needs **no** third-party packages; the crawlers' dependencies are in `requirements.txt`.
* `start_gui.bat` / `start_gui.sh` pick the interpreter for you (`.venv` first, then system Python).
* `-X utf8` matters on Windows: without it the console mangles CJK output.
* The server binds `127.0.0.1` only (never exposed to the network) and picks an ephemeral port if
  the requested one is busy — the actual URL is printed at startup.
* Every mutating request carries a per-session token, so a random page in your browser cannot
  drive the panel.
* `--check` parses everything (12 player files, 14 official files, 431 roster operators) and asserts
  the invariants below. Run it after any change to the data files or to the tool itself.

---

## 3. Global chrome

| Control | Meaning |
|---|---|
| `荐 / 人工归纳 / 结果 JSON` | Tab strip. Switching away from 结果 JSON asks for confirmation if it has unsaved edits. |
| `保存后自动重新生成名单文档` (checkbox, on by default) | After a write, run the affected merge script(s) so `docs/*-members.md` matches the part files. Turn it off to batch many edits and press the button yourself at the end. |
| `重新生成名单文档` | Runs both merge scripts now (player + official). |
| `刷新数据` | Re-fetches `/api/data`, re-parsing the markdown files and forcing the PRTS basic-info cache to rebuild. |
| Status text (top right) | One-line result of the last action (`已保存并重新生成名单文档` / failures). |
| Toasts (bottom right) | Per-action feedback; red-bordered ones are errors and stay longer. |

**Keyboard.** `Enter` / `✓` commits an edit, `Esc` / `×` cancels it, `Ctrl+Enter` commits a
multi-line field. `Esc` closes the topmost layer (dialog → context menu → open card). In the save
dialog `Ctrl+Enter` saves from anywhere.

The three controls `保存后自动重新生成名单文档`, `重新生成名单文档`, `刷新数据` are hidden on the
结果 JSON tab — that screen has its own load/save semantics and never touches the markdown files.

---

## 4. Tab「荐」 — recommended operators

Purpose: mark which operators are recommended under a player TAG. 荐 exists only for the 12 player
TAGs (P01–P12); official TAGs have no such field. 荐 carries **no display priority** — the array
order in `_recommend.json` has no meaning.

1. Pick a TAG in the left column (`全部干员` = the union of every member table).
2. **Left-click** an operator row → adds it to that TAG's 荐 list.
   **Right-click** → removes it. Both act immediately and are written to `_recommend.json`.
3. The list shows two groups — 荐（N 人） first, then 其余成员（N 人） — each sorted by release date
   descending (same-day entries by pinyin). 荐 rows carry a 荐 badge and the amber highlight.
   With a sub-TAG in the scope bar selected, both groups list **only that sub-TAG's members**
   (the count line is `N / N 人`), so a 荐 cannot be given to an operator whose record under this
   TAG belongs to another sub-TAG. 荐 already stored under the selected scope stay listed even if
   they no longer qualify, so you can right-click them away.
4. Every row has a `详情` (Details) button: it renders that operator's info card (name / charId /
   rarity / class·branch / faction / release date / PRTS link) plus read-only 条件 / 备注 record
   cards — the selected TAG's records, or every player TAG's records under `全部干员` — in the
   right column. The right column shows a hint until you click a 详情.
5. The search box filters by name (substring, same behaviour as the other tabs).

Notes and failure modes:

* Only members of the TAG's main tables can become 荐 (the panel refuses otherwise) — that is what
  keeps `tools/recommend.py check` clean. Inside a sub-TAG scope the bar is higher: the operator
  must be a member **of that sub-TAG**, otherwise the add is refused with
  `「X」不在「TAG／子值」这个子 TAG 的成员中…`.
* Sub-TAG membership is read from the **part files** with the generator's own rule
  (`player_subtags()` in `tools/generate_results.py` — sub-table heading, 范围／子 TAG cell, or the
  备注 prefix, see `docs/output-standard.md` §4.3), the same code that fills `subTags` in
  `results/operator-tags.json`. A row added on 人工归纳 can therefore be recommended right away;
  no regeneration needed.
* If a 荐 later stops being a member (you removed the row, or moved it to another TAG), the panel
  prunes it and tells you with a toast. Re-adding the member does **not** restore the 荐. A 荐 that
  stays a TAG member but is no longer inside its sub-TAG is reported as `荐不在该子作用域内`
  (toast on load, listed by `--check`); it keeps showing in that scope's list so you can remove it.
* 阵容组合 (P12) is edited **per category (势力／用法)**: the scope bar switches the view; the combo header carries the combo-level 荐 (left-click = recommend the combo, right-click = remove), while the provider rows keep their own per-operator 荐. The two are independent and may be mixed (`docs/output-standard.md` §6). Providers within a combo by release date.
* 荐 scoping: for player TAGs **with sub-TAGs**, the scope bar switches between the sub-TAG lists only — there is **no TAG-level scope** (TAG level cannot hold 薦; the panel refuses TAG-level adds and defaults to a sub-scope). The operator list is confined to the selected sub-TAG's members, and so is every 荐 you can give there. Entries are stored under `TAG/子值` keys and the results JSON carries them as `recommendedBySub`／`recommendedFallbackBySub`.
* 条件 / 备注 are edited on the 人工归纳 tab; the 荐 tab itself cannot edit them.
* The CLI equivalent is `tools/recommend.py list|add|remove|check`; both write the same `_recommend.json`. The CLI validates TAG-level membership and the scope *value*; the stricter sub-TAG membership check lives in the panel (and in its `--check` report).

---

## 5. Tab「人工归纳」 — staging and folding

Purpose: pull operators out of one TAG and fold them into another (or add brand-new members to a
TAG), carrying their 条件 / 备注 where that makes sense.

### 5.1 Layout

```
┌ TAG tree ──────────┬ operator list ────────────────┬ full-roster picker ─┐
│ 玩家体感 TAG (12)   │ rows of the selected scope     │ search + 431 people │
│ 官方设定 TAG        │ click = expand the card        │ left-click = stage   │
├─────────────────────┴───────────────────────────────┤ (expand mode only)  │
│ staging area (临时区) — click an item to fold it in │                     │
└─────────────────────────────────────────────────────┴─────────────────────┘
```

### 5.2 Selecting targets

* The TAG tree groups **玩家体感 TAG** (P01–P12) and **官方设定 TAG** (A–I, one category per row).
* A TAG whose member table is split (决战歼灭, 次数对策, 吃拐一轮秒, 远程消耗, 充电, 初动增加, 保人,
  高档控制, 阵容组合) shows a caret: click the TAG row
  to browse all of its members, click a **sub-table row** (表 1 / 2A / 2B / …) to select it. The
  sub-table — not the TAG — is the unit that receives new rows, because each sub-table means
  something different.
* Click a sub-table = single selection. `Ctrl`/`Cmd`+click = multi-selection; every staged item is
  then folded into **all** selected sub-tables (except 移动, which allows exactly one).
* The selected scope is also what the operator list shows, and what the expanded cards edit.
  An operator that appears in two sub-tables of one TAG is legal (e.g. 机械师 in 02) — duplication
  is only rejected **within one sub-table**.

### 5.3 Staging (临时区)

| Action | Result |
|---|---|
| Left-click a picker row (right column) | Stages it in **扩展 / extend** mode. Nothing else is possible from the picker. |
| Right-click an operator row → `扩展` | Same, from the operator list. |
| `×` on a staged item | Drop it from staging (no file is touched). |
| `清空` | Empty the staging area (confirmation; no file is touched). |

Staged items are kept in `localStorage`, so a reload does not lose them. If the source row of a
`移动` item changed meanwhile, the item turns red and asks you to stage it again.

### 5.4 Folding a staged item into the selected sub-table(s)

Click a staged item. What happens depends on its mode:

* **扩展 (extend)** — inserts a new member row with **empty 条件 and 备注** (plus an empty 依据) so you
  can write them yourself; its 编号 is filled in from `char_ids.json` by operator name. The staged
  item stays, so you can fan the same operator out to several sub-tables.
* **移动 (move)** — inserts a new row carrying the source row's **编号 / 条件 / 备注 / 子 TAG / 依据**,
  then deletes the source row. Exactly one target sub-table is allowed. After a successful move the
  staged item is consumed. Columns the target table does not have are dropped and reported.
* Nothing is written if every target is skipped (e.g. the operator is already in that sub-table).

New rows are placed by release date (newest first) using `player_tags/_launch_dates.json`;
阵容组合 always appends to the end of the combo table, because that TAG groups by combo rather than
by date.

### 5.5 Right-click menu on an operator row

| Item | Meaning |
|---|---|
| `扩展（放入临时区）` | stage in extend mode |
| `移动（带走条件/备注，删除源行）` | stage in move mode, remembering the exact source row |
| `移除（删除该行）` | delete that row from the source table after a confirmation (the dialog names the file; `git` is the undo) |

When the operator has several records in the current scope, each 移动/移除 entry names the
sub-table it applies to.

### 5.6 Cards — viewing and editing one operator

Click an operator row to expand it. The card shows the operator's basic info from the PRTS crawl
(rarity, class·branch, faction, release date, PRTS link — read only) followed by one card per
record **within the currently selected scope**:

* `编号` — read-only charId (`char_1035_wisdel`), shown next to the operator's basic info. It is the
  member row's 编号 cell, falling back to `agent_workspace/tag_pipeline/char_ids.json` while a table
  has not been given the column yet; inserts fill it in automatically, and there is no editor.
* 条件 / 备注 — click to edit. Clearing 备注 deletes the key; an empty 条件 is flagged in amber
  until you fill it in.
* `依据` — read-only evidence pointer (player TAGs only).
* `子 TAG` — for member tables that carry a `子 TAG` column (拐杖 and the like), click the cell to edit it: values are written as `组/值`, multiple values joined with `、` (e.g. `增益类型/攻击力(加算)、生效方式/在场`; the `触发时` value keeps its detail in parentheses). TAGs whose sub-TAGs are stored as sub-tables are managed by moving rows between sub-tables instead.
* `prtsUrl` — free text plus four anchor buttons (`无锚点 / #技能 / #天赋 / #模组 / #召唤物信息`) and
  `按干员名重建`. Choosing the anchor is a human judgement (see `docs/output-standard.md` §5).
* `↑ 上移` / `↓ 下移` / `删除成员` — reorder or remove the member row.

Editing a cell writes just that row's `条件`/`备注` **field** (every other cell is left untouched) and
optionally re-runs the merge. A cell must not contain a pipe (`|` — the generated member doc is still
a markdown table) and must stay on one line: pasted newlines are collapsed to spaces with a warning.
Rows are addressed **structurally** (block id + row index + the row's current 条件/备注/子 TAG values);
if the row changed under you, the server rejects the write with `drift` and the panel asks you to
refresh instead of overwriting someone else's edit.

### 5.7 What the tab writes

| File | When |
|---|---|
| `agent_workspace/tag_pipeline/player_tags/NN-*.json` | member inserted / deleted / moved, or a cell edited |
| `agent_workspace/tag_pipeline/official_tags/[A-I]-*.json` | same; the entry header `（N 人 · 首现 日期）` is derived at render time, never stored |
| `agent_workspace/tag_pipeline/player_tags/_recommend.json` | a 荐 became invalid because its member row left the TAG |
| `docs/player-tags-members.md`, `docs/official-tags-members.md` | regenerated by the merge scripts (never edit these by hand) |

Inserting into an official table builds the row from that table's columns (`干员｜编号｜条件｜备注`;
编号 comes from `char_ids.json` by operator name); the part files are validated on load, so a
malformed row cannot be produced.

---

## 6. Tab「结果 JSON」 — editing the deliverable

Purpose: edit `results/*.json` (canonically `results/operator-tags.json`, spec:
`docs/output-standard.md`) by hand. The whole screen is **in-memory**: reading, editing and
validating never touch the disk. Only **保存…** writes.

### 6.1 Loading

* `加载…` lists the `results/` directory (nothing else can be opened or overwritten).
  A file that is not valid JSON still opens, in the source view, so you can repair it.
* `新建骨架` starts an empty document shaped like the spec
  (`{"version":"v1","updated":<today>,"operators":[],"tags":[]}`).
* Opening a non-results JSON (e.g. `combat_glossary.json`) puts the screen in read-only summary
  mode with a warning; nothing can be edited structurally.
* If a previous session left an unsaved draft in `localStorage`, a banner offers to restore or
  discard it — it is never restored automatically.
* If the file's 荐 fields differ from `_recommend.json` / `_recommend_fallback.json`, a toast warns
  on load that saving will recompute them (see §6.4).

### 6.2 Editing

Two views of one document; switching re-serializes / re-parses, so neither side can silently lose
the other's edits. If the source text is not valid JSON, switching back to the structured view is
refused (you stay in the source view, with the error shown).

* **Structured** — `按干员` / `按 TAG` toggles the mode.
  * TAG mode: left = `tags[]`, middle = its members, right = the TAG panel (`id` and `source` are
    read-only; `name` editable; `category` dropdown for official TAGs; a **read-only 荐 view** for
    player TAGs — per sub-TAG names, fallback entries marked, with a note that the source of truth
    is `_recommend.json` and saving recomputes it) plus the selected member's card
    (condition / remark / subTags / prtsUrl, add & remove members, reorder).
  * 阵容组合 (P12) members are **combo entries**: the card edits `combo` / `condition` / `remark` /
    `beneficiaries` and the nested provider rows (`operator` / `condition` / `remark` / `prtsUrl`);
    buttons: `＋ 加组合`, `＋ 提供者`, `删除组合` (format: `docs/output-standard.md` §4.2).
    Each combo card shows read-only whether the combo is currently in a 荐 list (荐 is maintained
    on the 荐 tab; saving recomputes it).
  * Operator mode: a searchable, paginated `operators[]` list; the card edits all seven fields;
    `从全量干员表补全` fills them from the crawled PRTS data; renaming cascades through members and
    荐; `新增干员条目` picks from the full roster; `删除条目` warns when references remain.
* **Source** — the whole document as JSON text, with `格式化` and the parse error underneath.

### 6.3 Checking and tidying

* `校验` runs the `docs/output-standard.md` rules on the server and reports errors / warnings as a
  toast. It never edits anything.
* `按规范整理` applies the mechanical rules after showing a summary of what it will change: sort
  `tags[]` (official by category A→I, then players by `P01…P12`), sort `operators[]` by release date,
  drop empty `remark` / `subTags`, add missing `recommended` arrays. It deliberately does **not**
  reorder the members of 阵容组合 (that TAG is grouped by combo). Undo = reload the file.

### 6.4 Saving

`保存…` opens the save dialog:

* **Target** — `覆盖已有文件` (a dropdown of `results/*.json`, defaulting to the file you loaded) or
  `新建文件` (a name; duplicate names are flagged). When nothing is loaded yet the dialog preselects
  **新建**, so you cannot overwrite another artifact by accident. Overwriting a file **other than the
  one you loaded** additionally requires ticking a confirmation checkbox.
* **Version** — if the content changed (ignoring `version`/`updated`), the dialog offers to set
  `updated` to today and bump `version` (`v1` → `v2`, any number of digits; unparsable values are
  left for you to type). Ticking the box off is allowed and only shows a warning. A pending 荐
  recompute counts as a content change too.
* **荐 fields** — before writing, every player TAG's `recommended` / `recommendedFallback` /
  `recommendedBySub` / `recommendedFallbackBySub` is recomputed from `_recommend.json` /
  `_recommend_fallback.json` with the generator's own rule (`rec_fields()` in
  `tools/generate_results.py`) — that is why a 覆盖保存 picks up 荐 added on the 荐 tab. The dialog
  lists the differences up front (as `R8` warnings, click to jump), the post-save toast reports what
  was recomputed, and the in-memory document adopts the written version.
* **Problems** — the same validation list, each entry clickable to jump to the offending card.
  Warnings and spec errors never block saving; the one hard refusal is text that is not valid JSON
  (you would be writing a broken deliverable).
* **`强制覆盖`** — only needed when the file changed on disk since you loaded it (see §7).
* After a successful save the in-memory document becomes the new baseline, the draft copy is
  dropped, and the screen's current file switches to the file you wrote.

Files are written as UTF-8 without BOM, `ensure_ascii=False`, two-space indent, CRLF line endings
(the style of the existing `results/` files); an LF file stays LF.

---

## 7. Why writes are safe (and when they are refused)

Every write path uses optimistic concurrency against the state you actually saw:

| Guard | Message you may see | What to do |
|---|---|---|
| Part files: the exact line you edited must still be on disk | `这一行已被外部改动（或行号已偏移），请点「刷新数据」后重试` | press `刷新数据` and redo the edit |
| Part files: the sub-table's heading + header row must match (a fingerprint) | `目标子表已被外部改动（标题或表头变化）…` | same |
| Results JSON: the file's content digest must match what you loaded | `文件已被外部改动，请重新载入，或确认后强制覆盖` | reload it, or tick `强制覆盖` if your version is the good one |
| Filenames | `文件名只能含中文/字母/数字/空格/._-，且必须以 .json 结尾` | only `results/<name>.json`, no separators |

Writes are atomic (temp file + `os.replace` with retries for Windows file locks) and the server
serialises every request behind one lock, so two browser tabs cannot interleave a read-modify-write.
Unsaved work is protected three ways: a `beforeunload` prompt, a confirmation when switching tabs or
loading another file, and a `localStorage` draft of the results document.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `有 N 条荐已不在成员表中，请核对` toast on load | a 荐 whose member row was removed outside the panel. Re-add the row, then the 荐, or edit `_recommend.json`. |
| A merge script fails after a save | the edit is already written; fix the reported problem and press `重新生成名单文档`. |
| `服务端异常：…` toast | an unexpected error; the file on disk is unchanged for that request. Check the console you started the server from. |
| Fonts look like the system default | the panel fetches Noto Sans/Serif SC from Google Fonts after load with a 2.5 s timeout; offline it silently falls back to the local stack. Nothing is broken. |
| The port is busy | the panel prints the port it actually bound — copy that URL. |
| Missing `gui/static` | the server refuses to start with the path in the message. |

`git diff` is the source of truth for what changed; every destructive action (移除, overwrite) names
the file it will touch, and the repository is the undo history.

---

## 9. Maintainer notes

```
gui/
  config.py      paths + sys.path bootstrap (imports the sibling tools/recommend.py / merge script),
                 CHAR_IDS (char_ids.json → 「编号」列取值)
  errors.py      UserError(msg, code) — anything raised here is shown to the user as-is
  md.py          cell helpers, atomic write, and the line-addressed Doc model
  tags.py        markdown parsers (player blocks, official entries)
  roster.py      PRTS basic-info parsing + mtime-keyed cache
  recommends.py  荐 store helpers, apply_recommend, prune_recommend
  merges.py      subprocess wrappers for the two merge scripts
  results_json.py  filename whitelist, load/render/validate/check/save for results/*.json
  rec_sync.py    recompute a results doc's 荐 fields from the 荐 files (generator-identical;
                 called on save; load/check use it for the drift notice)
  writeback.py   doc_registry, block resolution, apply_ops, save_cell
  model.py       the /api/data model
  server.py      Handler, routes, token, LOCK, static assets
  selfcheck.py   --check assertions
  static/        index.html + app.css + app.js (a plain classic script; RES must stay global)
```

Dependency direction is one-way: `config/errors/md` → data modules → `writeback/model` → `server`.
`selfcheck.py` must not import `server.py` (it is meant to run without a port).

Things to keep in sync when you change the UI:

1. **The DOM contract.** `--check` asserts that the ids/classes the acceptance scripts use still
   exist and that `RES` is a top-level global. Renaming one without updating the scripts breaks the
   harness silently.
2. **The skin.** `static/app.css` transcribes ak-ui's `--ak-*` tokens (MIT, © 2019 云游君 — the
   header comment records provenance). Keep components to one cut corner **or** one signal bar, and
   use the tokens rather than new hard-coded colours. The density compromise (44 / 36 / 32 px) is
   documented at the top of the same file.
3. **Static serving.** Only `index.html`, `app.css`, `app.js` are served, and `index.html` must
   contain exactly one `__TOKEN__` placeholder (the server substitutes the session token into
   `<meta name="x-token">`).
4. **New tab checklist.** Add the `<main id="page-…" hidden>` block, a `.tab[data-tab]` button, a
   branch in `setTab()`, a `render…()` call and (if it needs data) an endpoint in `server.py` plus a
   contract entry in `selfcheck.py`.
5. **Sub-TAG structure or representation changes.** After touching how a TAG stores its sub-TAGs
   (sub-tables ↔ `子 TAG` column ↔ remark prefix), walk all three tabs once: 荐 (scope bar, add /
   remove), 人工归纳 (pick a sub-table → 并入 / move / remove; edit 条件 / 备注 / 子 TAG cells),
   结果 JSON (load → 校验 → leave without saving). Then run `tools/run_all_checks.py`.

Run `--check` and click through all three tabs after any change; the end-to-end Playwright scripts
used during development live outside the repo (in the OS temp directory) and drive the same DOM
contract.

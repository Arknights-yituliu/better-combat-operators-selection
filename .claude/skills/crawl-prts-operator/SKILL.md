---
name: crawl-prts-operator
description: Crawl one or more Arknights operators (plus their summons, if any) from the PRTS wiki into material_datas/PRTS as markdown. Use when asked to grab/fetch/crawl an operator's data from PRTS, update or re-crawl existing operator data, or debug/extend the PRTS crawler.
---

# Crawl an operator from PRTS

## Quick path

The project crawler `crawl_prts.py` (run it with the project venv) does everything:

```bash
.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"
```

- If the operator is missing from `docs/operators.txt`, add a line first: `干员名 https://prts.wiki/w/干员名`.
- Output goes to `material_datas/PRTS/<干员名>/`:
  - `<干员名>.md` — the operator's gameplay body (干员信息 through 模组).
  - `<召唤物名>.md` — one sibling file per summon, crawled automatically from the 召唤物信息 section links. An operator with no summons gets only the main file.
- Operators already recorded as ok in `material_datas/PRTS/_manifest.json` (with files on disk) are skipped; pass `--force` to re-crawl. Failures are retried on the next run.
- Useful flags: `--only "A,B,C"` (subset), `--force`, `--delay-min/--delay-max` (per-request throttle).

## Verify after crawling

1. The folder exists and contains `<干员名>.md` (plus summon files if the wiki page has a 召唤物信息 section — check the page if unsure).
2. The header block shows `> 稀有度: N | 职业: X` and there is a `## 干员信息` block with those two lines.
3. The gameplay sections are present: `## 特性`, `## 天赋`, `## 技能`, `## 模组` (older/low-rarity operators may legitimately lack some).
4. Summon files contain the stat table (`## 召唤物信息`) and the owner name resolves (持有者 cell shows the operator's name, not empty).
5. No leaked tooltip text in data rows: body text should not contain `术语:` or `异常效果:` definitions inline.
6. No non-combat content survived: `## 精英化材料`, `## 技能升级材料`, `## 后勤技能` must be **absent**, and `## 模组` must contain no prose story, no `**模组解锁任务**`/`**解锁需求与材料消耗**`, and no image lines. Module tiers appear as `**模组等级1/2/3**` text lines and the type code as a `**ART-X**`-style text line.

## 非作战内容剥离

`crawl_page()` writes `strip_noncombat(to_markdown(...))`, so the corpus holds only combat information: section-level lore is dropped by `STOP_SECTIONS`, and module story (which PRTS emits twice — a `全文阅读` and a byte-identical `关闭全文` copy), unlock tasks, upgrade-material blocks, and 后勤技能 are stripped line-wise by `plan_strip()`/`render_strip()` in `crawl_prts.py`. Level icons become `**模组等级N**`; type icons are dropped because the same code sits on the next line as plain text.

Anything cited as `文件:行号` is a **post-strip** line number. Changing what gets stripped shifts every pointer below the edit, so after any change to the strip rules run `strip_prts_noncombat.py --audit`. It takes each pointer as it stood at HEAD, maps it, and requires the working tree to carry the mapped value; it reports 失效 (missed rewrite — must be 0), 未解析 (resolves to no file yet names a PRTS one, i.e. silently skipped — must be 0), and 指向已删行 (the anchor's line was stripped; review each one's original text to confirm it was not combat content). `--fix-stale` repairs 失效 pointers; `--dry-run` previews a backfill.

Do **not** try to detect a stale pointer with a content test — `new[map(x)-1] == old[x-1]` holds for every in-range number whichever side of the map it was written on, so such a check only ever catches out-of-range ones. Deliberate departures from the mechanical map (re-anchoring onto the line that actually supports the claim) live in the script's `ACCEPTED` set. Coverage comes from `REF_GLOBS`, enumerated by directory — a file one level outside a listed glob is never scanned, so add new citation-bearing directories there.

## What the crawler does (for context when debugging)

1. Fetches `https://prts.wiki/w/<name>` with full browser headers.
2. Splits `#mw-content-text > div.mw-content-ltr.mw-parser-output` into sections, keeping 干员信息 → 模组 and stopping at the first lore section (相关道具/干员档案/语音记录/干员密录/悖论模拟/干员模型/注释与链接).
3. Reads the 召唤物信息 section, follows its `/w/` links (deduped), and crawls each summon page the same way (stop at 召唤物模型).
4. Gets 稀有度/职业 for all operators via one batched Semantic MediaWiki `action=ask` query.
5. Cleans wiki noise, converts to markdown, strips non-combat content, writes files, updates `_manifest.json` after every operator (crash-safe resume).

## Notes / gotchas

### Access
- **Browser headers are mandatory.** The CDN (Vary: User-Agent) returns 403 to non-browser User-Agents — plain `curl`/`requests` with a custom UA fails. Send User-Agent + Accept + Accept-Language + Referer; `api.php` accepts the same headers.
- **Throttle requests** (default 1.2–2.8s random delay) to avoid the wiki's rate limiting; never crawl in tight loops.
- 403/429/5xx and network errors are retried with exponential backoff; 404 and other codes are not.

### Page structure
- Section headings are wrapped in `<div class="mw-heading">` — iterate `content.children` and unwrap, don't look for bare `h2`/`h3`.
- The `干员信息` section is **JS-only** (empty `charinfo-container` divs). Rarity and class cannot be scraped from static HTML; they come from the SMW API: `action=ask&query=[[分类:干员]]|?稀有度|?职业|limit=600`. Only these two properties exist in SMW — branch/faction/release date must come from page tables (特性/属性/获得方式 sections).
- Summon pages vary in section sets: at minimum `召唤物信息`, optionally `召唤物天赋`/`召唤物技能`, always ending with `召唤物模型` (stop marker). Summon names can contain parentheses (`Mon3tr(凯尔希的召唤物)`), curly quotes (`“清平”`), and dots (`龙腾.F`).
- Info boxes are emitted twice (desktop + `.nodesktop` mobile copies) — removing `.nodesktop` dedupes them.

### Hidden-span cleanup (the main noise source)
The wiki renders number variants as hidden `style="display:none"` spans:
- `*_算法_2` spans — algorithm-annotation view of the numbers (e.g. "直接乘算…+60%") → **drop**.
- `*_潜能_2` spans in data cells (`td`) — potential-upgraded numbers → **keep** as `〔潜能提升后：…〕`. The same class inside `th` cells is a checkbox toggle label → drop.
- Tooltip definition bodies (inside `.mc-tooltips`) → drop, keeping only the visible term text.
- Order matters: drop non-potential hidden spans **first**, then convert potential spans — otherwise `get_text()` leaks tooltip text into the kept variant.
- Nested hidden spans: after `decompose()`ing a parent, later entries from the same `select()` list are stale (`el.attrs` is None) — check `el.decomposed` before touching each.
- Also removed: `.charinfo-container`, `.charimg-m`, `table#calc` (stat calculator), checkbox toggles `span[style*="float:right"]` (remove **before** the `input` selector pass eats their inputs, or the label text survives), `#toc`, `.navbox`, scripts/styles.

### Markdown conversion
- markdownify **drops images inside table cells entirely**. Image-only links (e.g. the summon 持有者 cell, which is just the owner's avatar) lose the owner name — inject the link's `title` attribute as text before converting.

### Windows / persistence
- `os.replace` on `_manifest.json` can hit transient `PermissionError` (antivirus/indexer lock) — retry with backoff; this once crashed a long run at operator 254.
- `_manifest.json` is the resume record: per-operator status (ok/partial/error), files, and summon links. Re-running skips ok operators whose files still exist.

### Filenames
- Windows-invalid characters in names (`/ : * ? " < > | \`) are mapped to fullwidth equivalents by `sanitize_filename`; folder/file names come from the sanitized page name.

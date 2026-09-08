# PRTS Operator Crawler — Gotchas & Solutions

**Date:** 2026-09-08
**Task:** Build `crawl_prts.py` and crawl all 431 operators (plus 70 summon pages, 60 operators with summons) from PRTS into `material_datas/PRTS/` as markdown, one folder per operator with operator and summon files side by side.

**Outcome:** 501 files, 431/431 operators ok, zero failures on the completed run. The process hit 9 distinct gotchas, all recorded below. Project skill version lives at `.claude/skills/crawl-prts-operator/SKILL.md`.

---

## Gotcha 1: CDN returns 403 to any non-browser client

### Symptom
`curl`/`requests` with a plain or minimal User-Agent got `403` on every URL — page, `api.php`, even `index.php?action=raw`.

### Cause
PRTS sits behind an Alibaba/Tengine CDN whose responses carry `vary: Accept-Encoding, Cookie, User-Agent` (visible in the response headers the user pasted when debugging). It actively rejects non-browser User-Agents; a browser UA alone was still not enough.

### Fix
Send a **full browser header set**, not just the UA: `User-Agent` + `Accept` + `Accept-Language` + `Referer`. With all four, both `/w/` pages and `api.php` return 200. This is baked into `HEADERS` in `crawl_prts.py`.

### Lesson
When a site 403s you, don't conclude "API is blocked" from one endpoint. Test the same URL with progressively fuller header sets — `vary: User-Agent` in the response headers is the tell that UA-based filtering is in play.

---

## Gotcha 2: The 干员信息 (operator info) box is JS-only — rarity/class don't exist in the HTML

### Symptom
The 干员信息 section converted to ~70 lines of viewer-button noise ("全屏查看 / 下载立绘 / 试听语音…") with no rarity, class, or branch anywhere. Zero occurrences of `星级`/`稀有度` in the whole page source.

### Cause
The modern PRTS operator infobox is a `charinfo-container` whose divs (`charname`, `charstar`, `branch-text`, …) are populated entirely client-side by scripts. There is no static data to scrape.

### Fix
PRTS runs Semantic MediaWiki, so rarity and class come from one batched API call:
`api.php?action=ask&query=[[分类:干员]]|?稀有度|?职业|limit=600` (also needs browser headers). All 460 pages answered in one request; the crawler injects them as a generated `## 干员信息` block plus a `> 稀有度: N | 职业: X` header line.

Caveat: only 稀有度 and 职业 exist as SMW properties. Branch, faction, and release date are **not** in SMW — they come from the page's own tables (特性 → branch, 属性 → faction, 获得方式 → release date), which the crawler keeps.

### Lesson
"Not in the HTML" ≠ "not available". Before scraping JS-rendered content, check whether the wiki exposes it through an API — MediaWiki/SMW sites usually do.

---

## Gotcha 3: Section headings are wrapped in `<div class="mw-heading">`

### Symptom
First section-splitting attempt walked `content.children` looking for bare `h2`/`h3` tags and found nothing — the 召唤物信息 section parsed as empty.

### Cause
Current MediaWiki wraps every heading in `<div class="mw-heading mw-heading2"><h2>…</h2></div>`, so headings are never direct `h2` children of the parser-output div.

### Fix
`heading_of()` checks each direct child: if it's a `div.mw-heading`, unwrap to its inner `h2`/`h3`. Bare heading tags are still handled as a fallback.

---

## Gotcha 4: Hidden `display:none` spans duplicate every number variant — and which ones to keep differs

### Symptom
Talent/skill descriptions came out garbled: "防御力直接乘算里属于叠加，并非叠乘**60%**+60%" and entire tooltip definitions inlined ("晕眩**术语: 晕眩** 无法移动、阻挡、攻击及使用技能3秒"). There were ~716 `display:none` elements on one page.

### Cause
The wiki renders three kinds of variants as hidden spans, toggled by checkboxes:
- `*_算法_2` — the "显示算法" view of a buff (annotation of how the number is computed)
- `*_潜能_2` — the potential-upgraded numbers (only meaningful in data cells)
- `.mc-tooltips` definition bodies — hover-popup text after the visible term

All three `get_text()` into the same soup if you just convert the HTML.

### Fix — a two-pass cleanup with ordering that matters
1. **Pass 1:** decompose all hidden spans **except** `潜能`-classed ones inside `td` (their time comes later). This removes the algorithm views and tooltip bodies first.
2. **Pass 2:** for the remaining `潜能` spans in data cells, `get_text()` is now clean (no leaked tooltip text) — replace with a visible `〔潜能提升后：…〕` marker. The same class inside `th` is just the checkbox label and stays dropped.

Pass order is load-bearing: converting potential spans first would bake tooltip-definition text into the kept output (verified — that's exactly what the first one-pass attempt produced).

### Lesson
When a page packs several "views" into hidden elements, classify them by class/location before deciding keep-vs-drop, and do removal passes in an order that keeps `get_text()` clean for the parts you keep.

---

## Gotcha 5: Nested decompose() corrupts later elements in a bs4 select() list

### Symptom
Whole batch failed with `AttributeError: 'NoneType' object has no attribute 'get'` inside the hidden-span loop — every operator, 100% reproducible.

### Cause
A hidden span can contain another hidden span. Both are in the same `content.select(...)` result list. After `decompose()`ing the parent, the child's `.attrs` is `None`, but iterating the pre-computed list still touches it.

### Fix
bs4 exposes an `el.decomposed` flag — check `if el.decomposed: continue` before touching each element in the loop.

### Lesson
A `select()` result is a snapshot, not a live query. Any mutation loop over it must tolerate elements destroyed by earlier iterations.

---

## Gotcha 6: markdownify silently drops images inside table cells

### Symptom
The summon page's 持有者 (owner) cell rendered as empty — the one cell that says which operator owns the summon was lost. (Mon3tr's owner cell had shown junk earlier for the same underlying reason.)

### Cause
Isolated with a minimal repro: markdownify converts `img` fine in `<p>`, fine inside links in `<p>`, but **inside a `<td>` it drops images entirely** — no error, just gone. The owner cell is an image-only link (owner avatar with rarity/branch icon overlays, no text node).

### Fix
Before conversion, find image-only links and inject the link's `title` attribute as a text node: `if not a.get_text(strip=True) and a.find("img") and a.get("title"): a.append(NavigableString(a["title"]))`. The 持有者 cell now shows `[麦哲伦](/w/麦哲伦 "麦哲伦")`.

### Lesson
Converter libraries fail silently on structures they don't model. Verify conversion of *every* content-critical cell type with a minimal case before trusting a full-page run.

---

## Gotcha 7: Checkbox toggles must be removed before the selector that eats their inputs

### Symptom
After adding `input` to the decompose selectors, the toggle label text "显示算法" kept appearing in skill table headers ("| 等级 | 描述 显示算法 | …").

### Cause
The toggle is `<span style="float:right">显示算法<input …/></span>`. The cleanup checked `if el.find(["input"])` to identify toggles, but by then the generic `input` selector had already decomposed the inputs, so the check failed and the span survived.

### Fix
Reorder: match `span[style*="float:right"]` **before** the broad selector pass, and additionally accept the known label texts (`显示算法`/`算法`/`潜能`) as an OR condition.

### Lesson
When two cleanup rules interact (one destroys the marker the other detects), order them so detection happens before destruction — or key detection off properties that survive.

---

## Gotcha 8: Windows `os.replace` fails transiently on the manifest file (crashed a 431-operator run at #254)

### Symptom
The full crawl died at operator 254 with `PermissionError: [WinError 5] 拒绝访问` on `os.replace(_manifest.json.tmp, _manifest.json)` — nothing in the code held the file.

### Cause
Windows-specific: antivirus or the search indexer briefly locks freshly-written files; an atomic rename over the destination trips over that lock. Intermittent, machine-dependent, invisible on the 8-operator test runs.

### Fix
Wrap the replace in a retry loop (10 attempts, 1s + increasing backoff). Also, because the manifest is rewritten **after every operator**, the crash cost nothing: re-running the script skipped the 253 completed operators and resumed at 254.

### Lesson
On Windows, treat `os.replace` over a just-written destination as flaky. More generally: make long batch jobs idempotent with a per-item checkpoint *before* you need it — the crash turned into a 30-second resume instead of a restart.

---

## Gotcha 9: Info boxes are emitted twice (desktop + mobile)

### Symptom
Every "如需了解该持有者的召唤物…" notice and several tables appeared twice in early output.

### Cause
PRTS templates render a desktop copy plus a `.nodesktop` mobile copy of the same box; both are in the static HTML.

### Fix
Add `.nodesktop` (and `.navbox`, `#toc`) to the decompose selectors.

---

## Environment gotchas (same session, quick reference)

| Problem | Symptom | Fix |
|---|---|---|
| Windows console mojibake on CJK output | Probe scripts printed `�ٻ���` | Run with `-X utf8`; prefer writing probe output to a UTF-8 file and reading it, as in the earlier note |
| Editing long Python via `bash -c "python -c '…'"` | Three consecutive trivial bugs (typo'd dict key, reassigned variable, quote escaping) | Write probe/one-off scripts to a file first (`_probe.py`), run it, delete after — inline `-c` strings are not maintainable |
| First curl occasionally empty | Transient empty response, retry fine | Fetch helper already retries with exponential backoff — reuse it for everything |

---

## Reusable recipe: crawl one operator (with summons)

1. `crawl_prts.py --only "干员名"` — resumable, throttled, auto-follows 召唤物信息 links.
2. Verify: header `> 稀有度: N | 职业: X` present; sections 特性/天赋/技能/模组 present; summon 持有者 cell shows the owner name; no `术语:`/`异常效果:` text leaked into data rows.
3. If the operator is new: add the line to `docs/operators.txt` first; `--force` re-crawls an already-ok operator.
4. Summon page names can contain parens (`Mon3tr(凯尔希的召唤物)`), curly quotes (`“清平”`), and dots (`龙腾.F`) — `sanitize_filename()` maps Windows-invalid chars to fullwidth equivalents.

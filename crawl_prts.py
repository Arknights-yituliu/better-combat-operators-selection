# -*- coding: utf-8 -*-
"""Crawl PRTS wiki operator pages into material_datas/PRTS as markdown.

Each operator gets a folder under material_datas/PRTS/. Inside it:
  - <operator>.md   : the operator page's gameplay body
                      (干员信息 ... 模组, stopping before lore/voice/model sections)
  - <summon>.md     : one file per summon linked from the 召唤物信息 section
                      (召唤物信息/天赋/技能, stopping before 召唤物模型)

Rarity (稀有度) and class (职业) are not in the static HTML (the 干员信息
box is JS-only), so they are fetched once via the Semantic MediaWiki ask API
and injected as a generated 干员信息 block.

Noise from the wiki markup is removed before conversion:
  - hidden <span style="display:none"> variants: *_算法_2 (algorithm
    annotations) and tooltip definition bodies are dropped; *_潜能_2
    (potential-upgraded numbers) are kept as 〔潜能提升后：…〕
  - charinfo viewer, stat calculator table, checkbox toggles, scripts/styles,
    mobile duplicates (.nodesktop), TOC, navboxes

Resumable: operators recorded as ok in _manifest.json (with their files
still on disk) are skipped unless --force is passed. The manifest is
rewritten after every operator so an interrupted run can be restarted.

Requests are throttled (default 1.2-2.8s between requests) per the concept
doc's warning about the wiki's rate limiting. The CDN rejects non-browser
User-Agents, so full browser headers are required.
"""
import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from markdownify import MarkdownConverter

BASE = "https://prts.wiki"
API = BASE + "/api.php"
CONTENT_SELECTOR = "#mw-content-text > div.mw-content-ltr.mw-parser-output"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE + "/w/%E9%A6%96%E9%A1%B5",
}
# Sections that end the gameplay body (first match wins).
STOP_SECTIONS = {
    "相关道具", "干员档案", "语音记录", "干员密录", "悖论模拟",
    "干员模型", "召唤物模型", "注释与链接",
}
# Gameplay sections always kept even if they end up text-empty after
# cleaning (e.g. 攻击范围 is an inline SVG — no text; see crawl_ranges.py).
# Unknown sections that are empty after cleaning are dropped instead.
KEEP_EMPTY_SECTIONS = {
    "干员信息", "特性", "获得方式", "属性", "攻击范围", "天赋", "潜能提升",
    "技能", "后勤技能", "召唤物信息", "精英化材料", "技能升级材料", "模组",
    "召唤物天赋", "召唤物技能",
}
CLEAN_SELECTORS = (
    "script", "style", "link", "noscript", "input", "button", "canvas",
    ".mw-editsection", ".nodesktop", ".navbox", "#toc", ".mw-empty-elt",
    ".charinfo-container", ".charimg-m", "table#calc",
)
INVALID_FS_CHARS = {
    "\\": "＼", "/": "／", ":": "：", "*": "＊", "?": "？",
    '"': "＂", "<": "＜", ">": "＞", "|": "｜",
}


def sanitize_filename(name: str) -> str:
    name = "".join(INVALID_FS_CHARS.get(ch, ch) for ch in name)
    return name.strip(" .") or "_"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch(session: requests.Session, url: str, params=None, retries: int = 5):
    """GET with retries and exponential backoff on 403/429/5xx and network errors."""
    last_exc = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=(10, 60))
            if r.status_code == 200:
                return r
            last_exc = RuntimeError(f"HTTP {r.status_code}")
            if r.status_code not in (403, 429, 500, 502, 503, 504):
                break  # non-retryable (404 etc.)
        except requests.RequestException as exc:
            last_exc = exc
        time.sleep(min(120, 5 * (2 ** attempt)) + random.uniform(0, 3))
    raise RuntimeError(f"fetch failed after {retries} attempts: {url}: {last_exc}")


def parse(r: requests.Response) -> BeautifulSoup:
    return BeautifulSoup(r.content, "html.parser")


def content_div(soup: BeautifulSoup) -> Tag:
    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        raise RuntimeError(f"content div not found ({CONTENT_SELECTOR})")
    return content


def page_title(soup: BeautifulSoup) -> str:
    h = soup.select_one("#firstHeading")
    return h.get_text(strip=True) if h else ""


def heading_of(el):
    """Return the h2/h3 inside a mw-heading wrapper, or the bare h2/h3 itself."""
    if not isinstance(el, Tag):
        return None
    if el.name in ("h2", "h3"):
        return el
    if el.name == "div" and "mw-heading" in (el.get("class") or []):
        return el.find(["h2", "h3"])
    return None


def heading_text(h: Tag) -> str:
    return h.get_text(" ", strip=True).replace("[编辑]", "").strip()


def collect_sections(content: Tag) -> list:
    """Split content into [(title, [elements])], from the first heading to the
    first STOP section (exclusive). Headings are unwrapped from their
    mw-heading divs."""
    sections = []
    cur_title, cur_els = None, []
    for el in content.children:
        h = heading_of(el)
        if h is not None:
            title = heading_text(h)
            if title in STOP_SECTIONS:
                break
            if cur_title is not None:
                sections.append((cur_title, cur_els))
            cur_title, cur_els = title, [h]
        elif cur_title is not None and isinstance(el, Tag):
            cur_els.append(el)
    if cur_title is not None:
        sections.append((cur_title, cur_els))
    if not sections:
        raise RuntimeError("no gameplay sections found on page")
    return sections


def summon_links(content: Tag) -> list:
    """Ordered, deduped [/w/...] links inside the 召唤物信息 section."""
    els, cur = [], None
    for el in content.children:
        h = heading_of(el)
        if h is not None:
            cur = heading_text(h)
        elif cur == "召唤物信息" and isinstance(el, Tag):
            els.append(el)
    links, seen = [], set()
    for el in els:
        for a in el.find_all("a", href=True):
            if not a["href"].startswith("/w/"):
                continue
            url = urljoin(BASE, a["href"])
            if url in seen:
                continue
            seen.add(url)
            title = (a.get("title") or a.get_text(strip=True)).strip()
            links.append({"title": title, "url": url})
    return links


def clean(content: Tag) -> None:
    # "显示算法/潜能" checkbox toggles (checked before CLEAN_SELECTORS removes
    # the inputs these labels wrap)
    for el in content.select('span[style*="float:right"]'):
        if el.find(["input", "button"]) or \
                el.get_text(strip=True) in ("显示算法", "算法", "潜能"):
            el.decompose()
    for selector in CLEAN_SELECTORS:
        for el in content.select(selector):
            el.decompose()
    # hidden inline variants (algorithm views, tooltip bodies, potential views).
    # Pass 1 drops *_算法_2 annotations and tooltip definition bodies first so
    # their text doesn't leak into pass 2's get_text(). A span already
    # destroyed as part of an earlier decompose() is skipped.
    hidden = content.select('[style*="display:none"], [style*="display: none"]')
    for el in hidden:
        if not isinstance(el, Tag) or el.decomposed:
            continue
        cls = " ".join(el.get("class") or [])
        if "潜能" in cls and el.find_parent("th") is None:
            continue  # potential-upgraded data variant, handled in pass 2
        el.decompose()
    # Pass 2: potential-upgraded variants in data cells become visible as
    # 〔潜能提升后：…〕. Inside th they are header-toggle labels (dropped above).
    for el in hidden:
        if not isinstance(el, Tag) or el.decomposed:
            continue
        text = el.get_text(" ", strip=True)
        if text:
            el.replace_with(NavigableString(f"〔潜能提升后：{text}〕"))
        else:
            el.decompose()
    for img in content.find_all("img"):
        src = img.get("src", "")
        if not src:
            img.decompose()
        elif src.startswith("//"):
            img["src"] = "https:" + src
    # markdownify drops images inside tables; image-only links (e.g. the
    # summon owner cell) would lose their name entirely — inject the title.
    for a in content.find_all("a"):
        if not a.get_text(strip=True) and a.find("img") and a.get("title"):
            a.append(NavigableString(a["title"]))


def section_has_content(els: list) -> bool:
    for el in els:
        if el.name in ("h2", "h3"):
            continue
        if el.find("img"):
            return True
        if el.get_text(" ", strip=True):
            return True
    return False


def to_markdown(sections: list, title: str, url: str, smw: dict | None) -> str:
    parts = [f"# {title}\n",
             f"> 来源: {url}\n",
             f"> 抓取时间: {now_iso()}\n"]
    if smw:
        line = " | ".join(x for x in smw if x)
        if line:
            parts.append(f"> {line}\n")
    parts.append("\n")
    for sec_title, els in sections:
        if sec_title == "干员信息" and not section_has_content(els):
            # JS-only charinfo viewer; replaced by the generated info block
            if smw:
                parts.append("## 干员信息\n\n" +
                             "\n".join(f"- {x}" for x in smw if x) + "\n\n")
            continue
        if sec_title not in KEEP_EMPTY_SECTIONS and not section_has_content(els):
            continue
        parts.append(MarkdownConverter(
            heading_style="ATX", base_url=BASE, convert_as_tables=True
        ).convert("".join(str(el) for el in els)).strip() + "\n\n")
    return re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip() + "\n"


# ---------------------------------------------------------------- 非作战内容剥离
# The wiki's module sections interleave lore with mechanics: every module carries
# its story twice (an expanded 全文阅读 copy and a byte-identical collapsed
# 关闭全文 copy), plus unlock conditions and upgrade-material tables. None of it is
# combat information, and none of it is ever cited as evidence.
MODULE_LEVEL_ICON = re.compile(r"%E6%A8%A1%E7%BB%84%E7%AD%89%E7%BA%A7_(\d)\.png")
MODULE_ART = re.compile(
    r"uniequip_img|uniequip_type"
    r"|%E8%81%8C%E4%B8%9A%E5%88%86%E6%94%AF%E5%9B%BE%E6%A0%87"   # 职业分支图标
    r"|%E6%A8%A1%E7%BB%84_%E8%AF%81%E7%AB%A0"                    # 模组_证章
    r"|%E6%A8%A1%E7%BB%84%E7%B1%BB%E5%9E%8B"                     # 模组类型_基础
)
DROP_SECTIONS = {"精英化材料", "技能升级材料", "后勤技能"}


def plan_strip(lines: list) -> list:
    """Decide each line's fate: None to drop, else the text to keep.

    The 模组 section is a small state machine. Its story blocks end at the next
    level icon (the icon is itself level 1's marker) or the next heading; the
    material block ends at the first line that is neither blank nor an image,
    which keeps trailing footnotes that carry real mechanics notes.
    Module type codes stay: every uniequip_type icon is followed by the same
    code as plain text, so dropping the image loses nothing.
    """
    out = []
    section = None
    state = None
    for line in lines:
        stripped = line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            state = None
        elif line.startswith("### "):
            state = None
        if line.startswith("## ") or line.startswith("### "):
            out.append(None if section in DROP_SECTIONS else line)
            continue
        if section in DROP_SECTIONS:
            out.append(None)
            continue
        if section != "模组":
            out.append(line)
            continue
        if "#cite_ref" in line:
            # Wiki footnotes carry real mechanics notes on some operators
            # (e.g. 涤火杰西卡) and sit right after a story block, so they must
            # end any drop state rather than be swallowed by it.
            state = None
            out.append(line)
            continue
        if stripped.startswith("**基础信息**"):
            state = "story"
            out.append(None)
            continue
        if stripped.startswith("**模组解锁任务**"):
            state = "task"
            out.append(None)
            continue
        if stripped.startswith("**解锁需求与材料消耗**"):
            state = "cost"
            out.append(None)
            continue
        if state == "task":
            out.append(None)
            continue
        if state == "story":
            level = MODULE_LEVEL_ICON.search(line)
            if level:                      # story ends here; this icon is level 1
                state = None
                out.append(f"**模组等级{level.group(1)}**")
            else:
                out.append(None)
            continue
        if state == "cost" and (not stripped or "![](" in line):
            out.append(None)
            continue
        state = None                       # material block ended on real content
        level = MODULE_LEVEL_ICON.search(line)
        if level:
            out.append(f"**模组等级{level.group(1)}**")
            continue
        out.append(None if MODULE_ART.search(line) else line)
    return out


def render_strip(planned: list) -> tuple:
    """Apply a plan: collapse blank runs, drop trailing blanks.

    Returns (kept_lines, old_to_new) where old_to_new[i] is the 1-based new line
    number of source line i+1, or None if that line was dropped. Callers that
    rewrite 文件:行号 evidence pointers need the map; strip_noncombat discards it.
    """
    kept = []
    old_to_new = []
    blanks = 0
    for item in planned:
        if item is None:
            old_to_new.append(None)
            continue
        if not item.strip():
            blanks += 1
            if blanks > 1:
                old_to_new.append(None)
                continue
        else:
            blanks = 0
        kept.append(item)
        old_to_new.append(len(kept))
    while kept and not kept[-1].strip():
        kept.pop()
    old_to_new = [n if n is None or n <= len(kept) else None for n in old_to_new]
    return kept, old_to_new


def strip_noncombat(text: str) -> str:
    """Drop lore and upgrade-economy content from one operator markdown page.

    Returns the same plain-LF convention to_markdown() uses; the CRLF translation
    happens in Path.write_text on write, so callers must not pre-expand newlines.
    """
    kept, _ = render_strip(plan_strip(text.splitlines()))
    return "\n".join(kept) + "\n"


def fetch_smw_rarity_class(session: requests.Session) -> dict:
    """Batched SMW query: rarity and class for every page in 分类:干员."""
    r = fetch(session, API, params={
        "action": "ask", "format": "json",
        "query": "[[分类:干员]]|?稀有度|?职业|limit=600",
    })
    results = r.json().get("query", {}).get("results", {})
    out = {}
    for name, rec in results.items():
        po = rec.get("printouts", {})
        rarity = po.get("稀有度") or []
        klass = po.get("职业") or []
        out[name] = {"rarity": rarity[0] if rarity else "",
                     "class": klass[0] if klass else ""}
    return out


def smw_lines(smw_entry: dict | None) -> list:
    if not smw_entry:
        return []
    lines = []
    if smw_entry.get("rarity"):
        lines.append(f"稀有度: {smw_entry['rarity']}")
    if smw_entry.get("class"):
        lines.append(f"职业: {smw_entry['class']}")
    return lines


def crawl_page(session: requests.Session, url: str, out_dir: Path, filename: str,
               delay: tuple, smw_entry: dict | None) -> dict:
    """Fetch one page and write its markdown. Returns {title, path, summons}."""
    r = fetch(session, url)
    time.sleep(random.uniform(*delay))
    soup = parse(r)
    content = content_div(soup)
    title = page_title(soup)
    if not title:
        raise RuntimeError("firstHeading missing")
    summons = summon_links(content)  # before clean() removes nothing relevant
    clean(content)
    sections = collect_sections(content)
    out_path = out_dir / filename
    out_path.write_text(
        strip_noncombat(to_markdown(sections, title, url, smw_lines(smw_entry))),
        encoding="utf-8")
    return {"title": title, "path": out_path, "summons": summons}


def read_operators(path: Path) -> list:
    operators = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        operators.append((parts[0], parts[1] if len(parts) > 1
                          else urljoin(BASE, "/w/" + parts[0])))
    return operators


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--operators-file", default="docs/operators.txt")
    ap.add_argument("--out-dir", default="material_datas/PRTS")
    ap.add_argument("--only", help="comma-separated operator names to crawl (testing)")
    ap.add_argument("--force", action="store_true", help="recrawl even if already ok")
    ap.add_argument("--delay-min", type=float, default=1.2)
    ap.add_argument("--delay-max", type=float, default=2.8)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    root = Path(__file__).resolve().parent
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "_manifest.json"

    operators = read_operators(root / args.operators_file)
    if args.only:
        wanted = {n.strip() for n in args.only.split(",")}
        operators = [(n, u) for n, u in operators if n in wanted]
        missing = wanted - {n for n, _ in operators}
        if missing:
            print(f"WARNING: not in operators file: {sorted(missing)}")
    if not operators:
        print("no operators to crawl")
        return 1

    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers.update(HEADERS)
    delay = (args.delay_min, args.delay_max)

    smw = {}
    try:
        smw = fetch_smw_rarity_class(session)
        print(f"SMW rarity/class loaded: {len(smw)} pages", flush=True)
    except Exception as exc:
        print(f"WARNING: SMW query failed ({exc}); continuing without it", flush=True)

    def save_manifest():
        tmp = manifest_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        # os.replace can fail transiently on Windows (antivirus/indexer lock)
        for attempt in range(10):
            try:
                tmp.replace(manifest_path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(1 + attempt)

    results = {}
    total = len(operators)

    for i, (name, url) in enumerate(operators, 1):
        entry = manifest.get(name, {})
        expected = [sanitize_filename(name) + ".md"]
        for s in entry.get("summons", []):
            if s.get("status") == "ok":
                expected.append(sanitize_filename(s["title"]) + ".md")
        if (not args.force and entry.get("status") == "ok"
                and all((out_dir / sanitize_filename(name) / f).exists()
                        for f in expected)):
            print(f"[{i}/{total}] {name}: skipped (already crawled)", flush=True)
            results[name] = entry
            continue

        op_dir = out_dir / sanitize_filename(name)
        op_dir.mkdir(parents=True, exist_ok=True)
        smw_entry = smw.get(name) or smw.get(entry.get("title", ""), None)
        record = {"url": url, "crawled_at": now_iso(), "status": "error",
                  "files": [], "summons": []}
        if smw_entry:
            record["rarity"] = smw_entry["rarity"]
            record["class"] = smw_entry["class"]
        try:
            page = crawl_page(session, url, op_dir,
                              sanitize_filename(name) + ".md", delay, smw_entry)
            record.update(status="ok", title=page["title"],
                          files=[page["path"].name])
            print(f"[{i}/{total}] {name}: ok "
                  f"({len(page['summons'])} summon link(s))", flush=True)
            for link in page["summons"]:
                s_rec = {"title": link["title"], "url": link["url"],
                         "status": "error"}
                try:
                    s_page = crawl_page(session, link["url"], op_dir,
                                        sanitize_filename(link["title"]) + ".md",
                                        delay, smw.get(link["title"]))
                    s_rec.update(status="ok", title=s_page["title"],
                                 file=s_page["path"].name)
                    record["files"].append(s_page["path"].name)
                    print(f"    + summon {link['title']}: ok", flush=True)
                except Exception as exc:
                    s_rec["error"] = str(exc)
                    print(f"    + summon {link['title']}: ERROR {exc}", flush=True)
                record["summons"].append(s_rec)
            if any(s["status"] != "ok" for s in record["summons"]):
                record["status"] = "partial"
        except Exception as exc:
            record["error"] = str(exc)
            print(f"[{i}/{total}] {name}: ERROR {exc}", flush=True)
        manifest[name] = record
        results[name] = record
        save_manifest()

    bad = [n for n, r in results.items() if r.get("status") != "ok"]
    print(f"\nDone: {len(results) - len(bad)}/{len(results)} ok")
    if bad:
        print(f"Failed/partial: {bad}")
        print("Re-run to retry failures (successful operators are skipped).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

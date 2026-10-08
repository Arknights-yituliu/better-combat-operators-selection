# -*- coding: utf-8 -*-
"""抓取每个干员（含召唤物）的攻击范围，写入 material_datas/PRTS/<干员>/攻击范围.md。

数据来源：PRTS 页面 wikitext 里的攻击范围代号，而不是渲染后的 SVG——
  {{干员攻击范围|精英0范围=4-4|精英1范围=4-3|...}}   默认范围（按精英化）
  {{技能|技能名=…|技能范围=3-12|...}}                技能范围（与默认不同时才写）
  {{能力生效范围|名称=有特性加成的范围|范围=1-3}}     特性/模组影响的范围
  召唤物页：|攻击范围=1-1
代号到网格的展开：Widget:Range/<代号>（缓存于 material_datas/PRTS/_range_codes.json）。

图例： # 自身所在格；x 攻击范围；o PRTS 以虚线绘制的格（多位于自身与范围之间的近身段，
      随分支/技能含义不同，如攻城手/要塞的近身不可攻击段、技能指定的中继格）；. 范围外。
版面右侧为干员面朝方向（PRTS 约定）。

用法：
  python -X utf8 crawlers/crawl_ranges.py            # 全部（可断点续跑）
  python -X utf8 crawlers/crawl_ranges.py --only 赤刃明霄陈
  python -X utf8 crawlers/crawl_ranges.py --force    # 已抓过的也重抓
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import crawl_prts as C

ROOT = Path(__file__).resolve().parents[1]
PRTS_DIR = ROOT / "material_datas" / "PRTS"
MANIFEST = PRTS_DIR / "_manifest.json"
CODE_CACHE = PRTS_DIR / "_range_codes.json"
OUT_NAME = "攻击范围.md"
MARKER = "攻击范围代号（Widget:Range）"

LEGEND = (
    "> 图例：`#` 自身所在格；`x` 攻击范围；`o` PRTS 以虚线绘制的格（位于自身与范围之间的"
    "近身段，含义随分支/技能而定）；`.` 范围外（PRTS 未绘制）。版面右侧为干员面朝方向。"
)


def fetch_wikitext(session: requests.Session, title: str) -> str | None:
    r = session.get(
        C.API,
        params={"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                "titles": title, "format": "json", "formatversion": "2"},
        timeout=(10, 60),
    )
    page = r.json().get("query", {}).get("pages", [{}])[0]
    if "missing" in page or "revisions" not in page:
        return None
    return page["revisions"][0]["slots"]["main"]["content"]


def fetch_widget(session: requests.Session, code: str) -> dict | None:
    c = fetch_wikitext(session, "Widget:Range/" + code)
    if c is None:
        return None
    m = re.search(r"<svg.*?</svg>", c, re.S)
    if not m:
        return None
    svg = m.group(0)
    vbm = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    if not vbm:
        return None
    cols, rows = int(vbm.group(1)) // 26, int(vbm.group(2)) // 26
    self_t, rng, dash = set(), set(), set()

    def tile(x, y):
        return int(y // 26), int(x // 26)

    for mm in re.finditer(r'<use xlink:href="#(\d)" x="([\d.]+)" y="([\d.]+)"', svg):
        rid, x, y = mm.group(1), float(mm.group(2)), float(mm.group(3))
        (self_t if rid == "1" else rng).add(tile(x, y))
    for tag in re.findall(r"<path[^>]*?>", svg):
        sm = re.search(r'style="([^"]*)"', tag)
        dm = re.search(r'(?<![-\w])d="([^"]*)"', tag)
        if not sm or not dm:
            continue
        fm = re.search(r"fill:(#[0-9a-fA-F]{6})", sm.group(1))
        if not fm:
            continue
        tr = re.search(r'transform="translate\(([-\d.]+),[-\s]*([\d.]+)\)"', tag)
        dx, dy = (float(tr.group(1)), float(tr.group(2))) if tr else (0.0, 0.0)
        fill = fm.group(1).lower()
        if fill == "#27a6f3":
            mm = re.match(r"\s*M\s*([\d.]+)[,\s]+([\d.]+)", dm.group(1))
            if mm:
                self_t.add(tile(float(mm.group(1)) + dx, float(mm.group(2)) + dy))
        elif fill == "#808080":
            # 虚线区域由许多小段拼成：取绝对坐标（M/L/H/V）的包围盒，再映射到格子，
            # ±2px 容差避免描边压在格线上时串格。
            xs, ys = [], []
            for m2 in re.finditer(r"([MLHV])\s*(-?[\d.]+)(?:[,\s]+(-?[\d.]+))?", dm.group(1)):
                cmd, a, b = m2.group(1), float(m2.group(2)), m2.group(3)
                if cmd in ("M", "L") and b is not None:
                    xs.append(a + dx); ys.append(float(b) + dy)
                elif cmd == "H":
                    xs.append(a + dx)
                elif cmd == "V":
                    ys.append(a + dy)
            if xs and ys:
                c0 = int((min(xs) + 2) // 26); c1 = int((max(xs) - 2) // 26)
                r0 = int((min(ys) + 2) // 26); r1 = int((max(ys) - 2) // 26)
                for r in range(max(0, r0), max(0, r1) + 1):
                    for c in range(max(0, c0), max(0, c1) + 1):
                        dash.add((r, c))
    return {"cols": cols, "rows": rows, "self": sorted(self_t),
            "range": sorted(rng), "dash": sorted(dash - rng - self_t)}


def grid_of(code_def: dict) -> list[str]:
    cols, rows = code_def["cols"], code_def["rows"]
    g = [["."] * cols for _ in range(rows)]
    for r, c in code_def["range"]:
        if 0 <= r < rows and 0 <= c < cols:
            g[r][c] = "x"
    for r, c in code_def["dash"]:
        if 0 <= r < rows and 0 <= c < cols:
            g[r][c] = "o"
    for r, c in code_def["self"]:
        if 0 <= r < rows and 0 <= c < cols:
            g[r][c] = "#"
    return ["".join(row) for row in g]


CODE_CACHE_DATA: dict = {}


def code_def(session: requests.Session, code: str) -> dict | None:
    if code in CODE_CACHE_DATA:
        return CODE_CACHE_DATA[code]
    d = fetch_widget(session, code)
    if d is not None:
        CODE_CACHE_DATA[code] = d
    return d


def parse_operator(wt: str) -> list[tuple[str, str]]:
    out = []
    m = re.search(r"\{\{干员攻击范围(.*?)\n\s*\}\}", wt, re.S)
    if m:
        for mm in re.finditer(r"\|精英(\d)范围\s*=\s*([^|\n}]*)", m.group(1)):
            code = mm.group(2).strip()
            if code:
                out.append((f"默认（精英{mm.group(1)}）", code))
    # 技能模板有两套：{{技能|…}} 与 {{技能2|…}}/{{技能3|…}}；按出现顺序把
    # 「技能范围」归到最近的前一个「技能名」。
    names = [(mm.start(), mm.group(1).strip())
             for mm in re.finditer(r"\|\s*技能名\s*=\s*([^|\n}]*)", wt)]
    for mm in re.finditer(r"\|\s*技能范围\s*=\s*([^|\n}]*)", wt):
        code = mm.group(1).strip()
        if not code:
            continue
        label = "技能"
        for pos, nm in names:
            if pos < mm.start():
                label = f"技能「{nm}」"
            else:
                break
        out.append((label, code))
    for mm in re.finditer(r"\{\{能力生效范围(.*?)\}\}", wt, re.S):
        block = mm.group(1)
        name = re.search(r"\|名称\s*=\s*([^|\n}]*)", block)
        code = re.search(r"\|范围\s*=\s*([^|\n}]*)", block)
        if code and code.group(1).strip():
            out.append((f"{name.group(1).strip()}" if name else "能力生效范围", code.group(1).strip()))
    # 模组/特性里的行内范围（如 夕 的特性「攻击范围扩大 {{攻击范围|3-1}}」），
    # 标签取就近的 ===模组名=== 小节标题。
    heads = [(mm.start(), mm.group(1).strip())
             for mm in re.finditer(r"===\s*([^=\n]+?)\s*===", wt)]
    for mm in re.finditer(r"\{\{攻击范围\s*\|\s*([A-Za-z0-9-]+)\s*[}|]", wt):
        code = mm.group(1).strip()
        label = "特性/模组范围"
        for pos, h in heads:
            if pos < mm.start():
                label = f"特性/模组「{h}」范围"
            else:
                break
        out.append((label, code))
    return out


def parse_summon(wt: str) -> list[tuple[str, str]]:
    m = re.search(r"\|攻击范围\s*=\s*([^|\n}]*)", wt)
    if m and m.group(1).strip():
        return [("攻击范围", m.group(1).strip())]
    return []


def render_block(label: str, code: str, session: requests.Session) -> list[str]:
    lines = [f"**{label}**（代号 {code}）", ""]
    d = code_def(session, code)
    if not d:
        lines += ["（未找到该代号的图形定义）", ""]
        return lines
    lines += ["```"] + grid_of(d) + ["```", ""]
    return lines


def render_page(name, url, ranges, summons) -> str:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [f"# {name} · 攻击范围", "", f"> 来源：PRTS {url}", f"> 抓取：{now}",
             f"> 数据来源：PRTS {MARKER} 与页面 wikitext", LEGEND, ""]
    if not ranges:
        lines += ["（该页 wikitext 未给出攻击范围代号）", ""]
    else:
        lines += ["## 默认与技能攻击范围", ""]
        for label, code, block in ranges:
            lines += render_block(label, code, block)
    for sname, surl, sranges in summons:
        lines += [f"## 召唤物「{sname}」", "", f"> 来源：PRTS {surl}", ""]
        if not sranges:
            lines += ["（该页 wikitext 未给出攻击范围代号）", ""]
        for label, code, block in sranges:
            lines += render_block(label, code, block)
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只抓这些干员（逗号分隔）")
    ap.add_argument("--force", action="store_true", help="已存在新版 攻击范围.md 的也重抓")
    ap.add_argument("--delay-min", type=float, default=0.8)
    ap.add_argument("--delay-max", type=float, default=1.8)
    args = ap.parse_args()

    global CODE_CACHE_DATA
    if CODE_CACHE.exists():
        CODE_CACHE_DATA = json.loads(CODE_CACHE.read_text(encoding="utf-8"))

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    session = requests.Session()
    session.headers.update(C.HEADERS)
    delay = (args.delay_min, args.delay_max)

    done = skipped = failed = 0
    for name, entry in manifest.items():
        if only and name not in only:
            continue
        out_dir = PRTS_DIR / C.sanitize_filename(name)
        if not out_dir.is_dir():
            continue
        out_path = out_dir / OUT_NAME
        if out_path.exists() and MARKER in out_path.read_text(encoding="utf-8") and not args.force:
            skipped += 1
            continue
        try:
            time.sleep(random.uniform(*delay))
            wt = fetch_wikitext(session, name) or ""
            raw = [(lab, code) for lab, code in parse_operator(wt)]
            ranges = [(lab, code, session) for lab, code in raw]
            summons = []
            for s in entry.get("summons") or []:
                time.sleep(random.uniform(*delay))
                swt = fetch_wikitext(session, s.get("title") or "") or ""
                sranges = [(lab, code, session) for lab, code in parse_summon(swt)]
                summons.append((s.get("title") or s.get("file", "召唤物"), s["url"], sranges))
            out_path.write_text(render_page(name, entry["url"], ranges, summons), encoding="utf-8", newline="\n")
            print(f"[ok] {name}: {len(ranges)} blocks + {sum(len(x[2]) for x in summons)} summon blocks")
            done += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[fail] {name}: {exc}")
            failed += 1
    CODE_CACHE.write_text(json.dumps(CODE_CACHE_DATA, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done={done} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

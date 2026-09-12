# -*- coding: utf-8 -*-
"""玩家体感 TAG「荐」+ 条件/备注 维护面板（本地网页版）。

在本机起一个只监听 127.0.0.1 的小服务，用浏览器操作：

    左键干员卡片 = 把该干员设为当前 TAG 的荐（追加到名单末尾）
    右键干员卡片 = 取消该干员在当前 TAG 的荐
    「编辑」按钮 / 双击 = 打开编辑面板，逐个 TAG 修改该干员的「条件」「备注」
    （深链：地址后加 #op=干员名 可直接打开该干员的编辑面板）

写入的文件：
    material_datas/tag_pipeline/player_tags/_recommend.json   （荐，TAG 编号序）
    material_datas/tag_pipeline/player_tags/NN-*.md           （只改成员表该行的
                                                               条件/备注两格，依据与其他行不动）
    保存单元格后可选自动执行 _merge_to_docs.py 重新生成 docs/player-tags-members.md

用法：
    .venv/Scripts/python.exe -X utf8 recommend_gui.py                  # 启动并打开浏览器
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --port 8520 --no-browser
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --check          # 只解析自检，不起服务
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import recommend as rec  # noqa: E402  （复用 TAG 扫描 / 成员表解析 / 荐读写）

PARTS = rec.PARTS
MERGE_SCRIPT = PARTS / "_merge_to_docs.py"

# 成员表区间：与 recommend.py 保持一致
H2_START = rec.START_MARKS
H2_STOP = rec.STOP_MARKS

TOKEN = secrets.token_urlsafe(18)


class UserError(Exception):
    """可以直接展示给使用者的错误。"""


# ---------------------------------------------------------------- 解析


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def parse_members(path: pathlib.Path) -> list[dict]:
    """解析一个分 TAG 文件的成员表，返回逐行条目。

    只认「## 成员表 / ## §A」区间内、表头首列为「干员」且含「条件」「备注」列的表。
    每条记录 file/line/raw/条件/备注/依据/子表标题/子 TAG 列，供前端渲染与行级写回。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    h2 = h3 = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            h2, h3 = line, ""
            i += 1
            continue
        if line.startswith("### "):
            h3 = line
            i += 1
            continue
        if not line.lstrip().startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        block, start = lines[i:j], i
        i = j
        if not (h2.startswith(H2_START) and not h2.startswith(H2_STOP)):
            continue
        header = split_cells(block[0])
        if not header or header[0] != "干员" or "条件" not in header or "备注" not in header:
            continue
        ci, ni = header.index("条件"), header.index("备注")
        sub_col = header.index("子 TAG") if "子 TAG" in header else None
        section = h3[4:].strip() if h3 else h2[3:].strip()
        for k, raw in enumerate(block):
            cells = split_cells(raw)
            if k == 0 or is_sep_row(cells) or not cells or not cells[0]:
                continue
            if len(cells) != len(header) or ni >= len(cells):
                continue  # 结构异常的行不参与编辑，也不当成员
            out.append(
                {
                    "file": path.name,
                    "line": start + k + 1,
                    "raw": lines[start + k],
                    "op": cells[0].replace("**", "").strip(),
                    "cond": cells[ci],
                    "note": cells[ni],
                    "src": cells[len(header) - 1] if len(header) > ni else "",
                    "sub": cells[sub_col] if sub_col is not None else "",
                    "section": section,
                }
            )
    return out


def build_model() -> dict:
    tags = rec.load_tags()
    recommend = rec.load_recommend()
    out_tags = []
    for name, path in tags:
        members = parse_members(path)
        out_tags.append(
            {
                "num": path.name[:2],
                "name": name,
                "file": path.name,
                "members": members,
                "sections": len({m["section"] for m in members}),
                "recommend": recommend.get(name, []),
            }
        )
    known = {t["name"] for t in out_tags}
    stale = [
        {"tag": tag, "op": op}
        for tag, ops in recommend.items()
        if tag in known
        for op in ops
        if op not in {m["op"] for m in next(t for t in out_tags if t["name"] == tag)["members"]}
    ]
    return {
        "tags": out_tags,
        "recommend": recommend,
        "stale": stale,
        "unknown_tags": [t for t in recommend if t not in known],
    }


# ---------------------------------------------------------------- 写回


def write_atomic(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    os.replace(tmp, path)


def save_cell(file: str, line_no: int, original: str, cond: str, note: str) -> dict:
    """只替换成员表该行的条件/备注两格；行尾、依据列、其它行原样保留。"""
    tags = rec.load_tags()
    paths = {p.name: p for _, p in tags}
    if file not in paths:
        raise UserError(f"未知文件：{file}")
    path = paths[file]
    text = path.read_text(encoding="utf-8", newline="")  # 保留原 CRLF
    lines = text.splitlines(keepends=True)
    if not 1 <= line_no <= len(lines):
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")
    cur = lines[line_no - 1].rstrip("\r\n")
    if cur != original:
        raise UserError("这一行已被外部改动（或行号已偏移），请点「刷新数据」后重试")

    warn = ""
    new_cond, new_note = cond, note
    for label, value in (("条件", cond), ("备注", note)):
        if "|" in value:
            raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if "\n" in cond or "\r" in cond or "\n" in note or "\r" in note:
        new_cond = re.sub(r"\s*[\r\n]+\s*", " ", cond)
        new_note = re.sub(r"\s*[\r\n]+\s*", " ", note)
        warn = "换行已转为空格（表格单元格必须单行）"
    new_cond, new_note = new_cond.strip(), new_note.strip()

    i = line_no - 1
    while i > 0 and lines[i - 1].lstrip().startswith("|"):
        i -= 1
    header = split_cells(lines[i].rstrip("\r\n"))
    cells = split_cells(cur)
    if len(cells) != len(header) or "条件" not in header or "备注" not in header:
        raise UserError("该行所在表格结构异常，无法安全写回（条件/备注列未识别）")
    parts = cur.split("|")  # 首尾为空串，第 k 格 = parts[k+1]（含原有空白）
    for idx, value in ((header.index("条件"), new_cond), (header.index("备注"), new_note)):
        parts[idx + 1] = f" {value} "
    new_line = "|".join(parts)
    lines[line_no - 1] = new_line + lines[line_no - 1][len(cur):]
    write_atomic(path, "".join(lines))
    return {"ok": True, "line": line_no, "raw": new_line, "cond": new_cond, "note": new_note, "warn": warn}


def run_merge() -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(MERGE_SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    ok = proc.returncode == 0
    return {"ok": ok, "returncode": proc.returncode, "out": (proc.stdout or "").strip(), "err": (proc.stderr or "").strip()}


def apply_recommend(payload: dict) -> dict:
    action = payload.get("action")
    tags = rec.load_tags()
    names = [t for t, _ in tags]
    tag = payload.get("tag", "")
    if tag not in names:
        raise UserError(f"未知 TAG：{tag}")
    data = rec.load_recommend()
    ops = data.setdefault(tag, [])
    op = payload.get("op", "")

    if action in ("add", "first", "remove", "move"):
        members = rec.main_table_members(dict(tags)[tag])
        if action != "remove" and op not in members:
            raise UserError(f"「{op}」不是「{tag}」成员表内的干员，不能设为荐")
        if action == "add":
            if op in ops:
                return {"ok": True, "noop": "已是荐", "recommend": data}
            ops.append(op)
        elif action == "first":
            if op in ops:
                ops.remove(op)
            ops.insert(0, op)
        elif action == "remove":
            if op not in ops:
                return {"ok": True, "noop": "本就不是荐", "recommend": data}
            ops.remove(op)
        elif action == "move":
            if op not in ops:
                raise UserError(f"「{op}」不在「{tag}」的荐名单中")
            k = ops.index(op)
            nk = min(max(k + int(payload.get("delta", 0)), 0), len(ops) - 1)
            ops.pop(k)
            ops.insert(nk, op)
    elif action == "clear":
        ops.clear()
    else:
        raise UserError(f"未知操作：{action}")

    rec.save_recommend(data, names)
    return {"ok": True, "recommend": {k: v for k, v in data.items() if v}}


# ---------------------------------------------------------------- HTTP

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>玩家体感 TAG 名单维护</title>
<style>
:root{--bg:#f5f6f8;--panel:#fff;--line:#e4e7ec;--txt:#1f2430;--dim:#6b7280;--acc:#2f6fed;--rec:#d98a00;--ok:#12805c;--err:#c0392b}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:flex;flex-direction:column;font:14px/1.55 "Microsoft YaHei","PingFang SC","Noto Sans SC",system-ui,sans-serif;color:var(--txt);background:var(--bg)}
header{display:flex;align-items:center;gap:12px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:15px;margin:0;font-weight:600}
header .hint{font-size:12px;color:var(--dim)}
header .sp{flex:1}
button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
button:hover{border-color:var(--acc);color:var(--acc)}
button.mini{padding:0 6px;line-height:1.5;font-size:12px}
#status{font-size:12px;color:var(--dim);min-width:120px;text-align:right}
#status.ok{color:var(--ok)}#status.err{color:var(--err)}
main{flex:1;display:grid;grid-template-columns:200px minmax(0,1fr) 440px;min-height:0}
main>*{min-height:0;overflow:auto;background:var(--panel)}
#tagcol{border-right:1px solid var(--line);padding:8px}
#editcol{border-left:1px solid var(--line);padding:10px}
.tag{padding:7px 9px;border-radius:8px;cursor:pointer;display:flex;align-items:baseline;gap:6px}
.tag:hover{background:#f0f3f8}
.tag.on{background:#e8effd;color:var(--acc);font-weight:600}
.tag .n{font-size:11px;color:var(--dim);margin-left:auto;font-weight:400}
.tag .num{font-size:11px;color:#9aa3af}
#opcol{display:flex;flex-direction:column}
.toolbar{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding:8px 12px;display:flex;gap:10px;align-items:center;z-index:2}
.toolbar input{flex:1;font:inherit;padding:5px 9px;border:1px solid var(--line);border-radius:6px}
.toolbar .cnt{font-size:12px;color:var(--dim);white-space:nowrap}
#oplist{padding:8px 12px 24px}
.card{display:flex;align-items:center;gap:8px;padding:6px 9px;border:1px solid transparent;border-radius:8px;cursor:pointer;user-select:none}
.card:hover{background:#f0f3f8}
.card.rec{background:#fff8e8;border-color:#f2ddb0}
.card.rec .name{font-weight:600}
.card .name{min-width:4em}
.card .rank{width:18px;text-align:center;color:var(--rec);font-weight:700;font-size:12px}
.card .chips{display:flex;gap:5px;flex-wrap:wrap;min-width:0}
.chip{font-size:11px;color:var(--dim);background:#f1f3f6;border-radius:9px;padding:0 7px;white-space:nowrap;max-width:22em;overflow:hidden;text-overflow:ellipsis}
.card .edit{margin-left:auto;opacity:.3;font-size:12px;padding:0 7px}
.card:hover .edit{opacity:1}
.split{margin:10px 2px 6px;font-size:12px;color:var(--dim);border-top:1px dashed var(--line);padding-top:8px}
h3.sec{font-size:13px;margin:2px 0 8px;color:var(--dim);font-weight:600}
#recbox{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-bottom:12px;background:#fcfcfd}
#recbox h3{margin:0 0 6px;font-size:13px}
#recbox ol{margin:0;padding-left:20px}
#recbox li{margin:2px 0;display:flex;align-items:center;gap:4px}
#recbox li span.op{flex:1}
#recbox .empty{color:var(--dim);font-size:12px}
#recbox .note{color:var(--dim);font-size:11px;margin-top:6px}
.guide{font-size:12px;color:var(--dim);background:#f7f9fc;border:1px solid var(--line);border-radius:8px;padding:7px 9px;margin-bottom:12px;line-height:1.65}
.guide code{background:#eef1f6;border-radius:4px;padding:0 4px}
.row{border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-bottom:12px}
.row .head{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.row .head b{font-size:13px}
.row .loc{font-size:11px;color:#9aa3af;margin-left:auto}
.row label{display:block;font-size:12px;color:var(--dim);margin:6px 0 2px}
.row textarea{width:100%;font:inherit;font-size:13px;padding:5px 7px;border:1px solid var(--line);border-radius:6px;resize:vertical;overflow:hidden;min-height:32px}
.row .src{font-size:11px;color:#9aa3af;margin-top:6px;word-break:break-all}
.row .acts{display:flex;align-items:center;gap:8px;margin-top:8px}
.row .st{font-size:12px;color:var(--dim)}
.row .st.ok{color:var(--ok)}.row .st.err{color:var(--err)}
.row.dirty{border-color:#f0c674}
#editor .empty{color:var(--dim);font-size:13px}
#toast{position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:6px;z-index:9}
.tmsg{background:#1f2430;color:#fff;font-size:13px;padding:6px 12px;border-radius:8px;opacity:.94}
.tmsg.err{background:#a5281b}
</style>
</head>
<body>
<header>
  <h1>玩家体感 TAG 名单维护</h1>
  <span class="hint">左键 = 加荐 · 右键 = 取消荐 · 「编辑」按钮 / 双击 = 编辑条件与备注</span>
  <span class="sp"></span>
  <label class="hint"><input type="checkbox" id="automerge" checked> 保存后自动重新生成名单文档</label>
  <button id="btmerge">重新生成名单文档</button>
  <button id="btreload">刷新数据</button>
  <span id="status"></span>
</header>
<main>
  <aside id="tagcol"></aside>
  <section id="opcol">
    <div class="toolbar"><input id="search" placeholder="搜索干员名…"><span class="cnt" id="cnt"></span></div>
    <div id="oplist"></div>
  </section>
  <aside id="editcol">
    <div id="recbox"></div>
    <div class="guide">条件＝硬性达成条件（精英化／技能／专精／模组与等级／模式限定／目标限制），精零 1 级即具备写「无」；备注＝加工后的信息（数值、持续时间、隐藏机制、用法），不写游戏内一眼可见的内容；备注中由计算得出的数值带「（待验证）」（PRTS 原文数值不标）。单元格须单行、不含竖线 |；保存后并入 <code>docs/player-tags-members.md</code>，即最终 JSON 的 condition / remark。</div>
    <div id="editor"></div>
  </aside>
</main>
<div id="toast"></div>
<script>
const TOKEN = "__TOKEN__";
let DATA = null, curTag = null, editOp = null, query = "";

function toast(msg, isErr) {
  const d = document.createElement("div");
  d.className = "tmsg" + (isErr ? " err" : "");
  d.textContent = msg;
  document.getElementById("toast").appendChild(d);
  setTimeout(() => d.remove(), isErr ? 4200 : 1800);
}
function status(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.className = kind || "";
}
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Token": TOKEN},
    body: JSON.stringify(body),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { j = {error: "服务返回异常（HTTP " + r.status + "）"}; }
  if (!r.ok || j.ok === false) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
async function load() {
  DATA = await (await fetch("/api/data")).json();
  if (!curTag || !DATA.tags.some(t => t.name === curTag)) curTag = DATA.tags[0].name;
  if (DATA.stale.length) toast("有 " + DATA.stale.length + " 条荐已不在成员表中，请核对", true);
  const m = location.hash.match(/^#op=(.+)$/);  // 深链：#op=干员名 直接打开编辑面板
  if (m) { const op = decodeURIComponent(m[1]); if (rowsOf(op).length) editOp = op; }
  renderAll();
}
function tagOf(name) { return DATA.tags.find(t => t.name === name); }
function isTagView() { return curTag !== "__all__"; }
function rowsOf(name) {
  const out = [];
  for (const t of DATA.tags) for (const m of t.members) if (m.op === name) out.push({tag: t.name, m});
  return out;
}

function renderTags() {
  const col = document.getElementById("tagcol");
  col.innerHTML = "";
  const all = document.createElement("div");
  all.className = "tag" + (curTag === "__all__" ? " on" : "");
  all.innerHTML = '<span>全部干员</span><span class="n">' + new Set(DATA.tags.flatMap(t => t.members.map(m => m.op))).size + "</span>";
  all.onclick = () => { curTag = "__all__"; renderAll(); };
  col.appendChild(all);
  for (const t of DATA.tags) {
    const el = document.createElement("div");
    el.className = "tag" + (curTag === t.name ? " on" : "");
    const n = t.recommend.length;
    const cnt = new Set(t.members.map(m => m.op)).size;
    el.innerHTML = '<span class="num">' + t.num + '</span><span>' + t.name + '</span><span class="n">' +
      cnt + (n ? ' · 荐' + n : "") + "</span>";
    el.onclick = () => { curTag = t.name; renderAll(); };
    col.appendChild(el);
  }
}

function viewOps() {
  if (!isTagView()) {
    const names = [...new Set(DATA.tags.flatMap(t => t.members.map(m => m.op)))];
    names.sort((a, b) => a.localeCompare(b, "zh"));
    return names.map(op => ({op, rec: -1, rows: rowsOf(op)}));
  }
  const t = tagOf(curTag);
  const byOp = new Map();
  for (const m of t.members) {
    if (!byOp.has(m.op)) byOp.set(m.op, []);
    byOp.get(m.op).push(m);
  }
  const recs = t.recommend.map((op, i) => ({op, rec: i, rows: byOp.get(op) || []}));
  const rest = [...byOp.keys()].filter(op => !t.recommend.includes(op)).map(op => ({op, rec: -1, rows: byOp.get(op)}));
  return recs.concat(rest);
}
function showSection() { return isTagView() && tagOf(curTag).sections > 1; }

let clickTimer = null;
function renderOps() {
  const list = document.getElementById("oplist");
  list.innerHTML = "";
  const all = viewOps();
  const items = all.filter(it => !query || it.op.toLowerCase().includes(query));
  document.getElementById("cnt").textContent = items.length + " / " + all.length + " 人";
  let recDone = false;
  for (const it of items) {
    if (isTagView() && it.rec < 0 && !recDone && items.some(x => x.rec >= 0)) {
      recDone = true;
      const d = document.createElement("div");
      d.className = "split";
      d.textContent = "其余成员（成员表顺序）";
      list.appendChild(d);
    }
    const el = document.createElement("div");
    el.className = "card" + (it.rec >= 0 ? " rec" : "");
    const sec = showSection();
    const chips = it.rows.map(r => {
      const txt = r.sub || (sec ? r.section : "");
      return txt ? '<span class="chip">' + esc(txt) + "</span>" : "";
    }).join("");
    el.innerHTML = '<span class="rank">' + (it.rec >= 0 ? it.rec + 1 : "") + "</span>" +
      '<span class="name">' + esc(it.op) + "</span><span class=\"chips\">" + chips + "</span>" +
      '<button class="edit" title="编辑条件与备注">编辑</button>';
    el.onclick = e => {
      if (e.target.closest(".edit")) { openEditor(it.op); return; }
      clearTimeout(clickTimer);  // 双击＝编辑，故单击延迟片刻再落荐
      clickTimer = setTimeout(() => addRec(it.op), 220);
    };
    el.oncontextmenu = e => {
      e.preventDefault();
      if (e.target.closest(".edit")) return;
      removeRec(it.op);
    };
    el.ondblclick = e => { clearTimeout(clickTimer); if (!e.target.closest(".edit")) openEditor(it.op); };
    list.appendChild(el);
  }
}
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderRec() {
  const box = document.getElementById("recbox");
  if (!isTagView()) {
    box.innerHTML = "<h3>荐</h3><div class='empty'>在左侧选中一个 TAG 后，左键 / 右键干员即可增删荐。</div>";
    return;
  }
  const t = tagOf(curTag);
  let html = "<h3>「" + esc(t.name) + "」荐（" + t.recommend.length + " 人，按展示优先级）</h3>" +
    "<div class='note'>荐只能加在玩家体感 TAG（P01–P13）上；官方设定 TAG 无荐字段。</div>";
  if (!t.recommend.length) html += "<div class='empty'>暂无。左键下方任一干员即可加入。</div>";
  else {
    html += "<ol>";
    t.recommend.forEach((op, i) => {
      html += "<li><span class='op'>" + esc(op) + "</span>" +
        "<button class='mini' data-act='up' data-op='" + esc(op) + "' title='上移'>↑</button>" +
        "<button class='mini' data-act='down' data-op='" + esc(op) + "' title='下移'>↓</button>" +
        "<button class='mini' data-act='first' data-op='" + esc(op) + "' title='置顶'>⤒</button>" +
        "<button class='mini' data-act='remove' data-op='" + esc(op) + "' title='取消荐'>×</button></li>";
    });
    html += "</ol>";
  }
  box.innerHTML = html;
  box.querySelectorAll("button[data-act]").forEach(b => {
    b.onclick = async () => {
      const act = b.dataset.act, op = b.dataset.op;
      try {
        if (act === "up" || act === "down") await api("/api/recommend", {tag: curTag, action: "move", op, delta: act === "up" ? -1 : 1});
        else if (act === "first") await api("/api/recommend", {tag: curTag, action: "first", op});
        else await api("/api/recommend", {tag: curTag, action: "remove", op});
        await load();
      } catch (e) { toast(e.message, true); }
    };
  });
}

async function addRec(op) {
  if (!isTagView()) { toast("请先在左侧选择一个 TAG，再加荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: curTag, action: "add", op});
    DATA.recommend = j.recommend;
    tagOf(curTag).recommend = j.recommend[curTag] || [];
    toast(j.noop ? ("「" + curTag + "」已是荐：" + op) : ("已设荐：" + op + " →「" + curTag + "」"));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}
async function removeRec(op) {
  if (!isTagView()) { toast("请先在左侧选择一个 TAG，再取消荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: curTag, action: "remove", op});
    DATA.recommend = j.recommend;
    tagOf(curTag).recommend = j.recommend[curTag] || [];
    toast(j.noop ? ("「" + curTag + "」本就没有荐：" + op) : ("已取消荐：" + op));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}

function openEditor(op) {
  editOp = op;
  location.hash = "#op=" + encodeURIComponent(op);
  renderEditor();
}
function renderEditor() {
  const box = document.getElementById("editor");
  if (!editOp) {
    box.innerHTML = "<h3 class='sec'>编辑条件与备注</h3><div class='empty'>点干员卡片右侧的「编辑」（或双击卡片）打开。</div>";
    return;
  }
  const rows = rowsOf(editOp);
  let html = "<h3 class='sec'>编辑：" + esc(editOp) + "（" + rows.length + " 条记录）</h3>";
  for (const {tag, m} of rows) {
    html += "<div class='row' data-file='" + esc(m.file) + "' data-line='" + m.line + "'>" +
      "<div class='head'><b>" + esc(tag) + "</b>" +
      (m.section ? "<span class='chip'>" + esc(m.section) + "</span>" : "") +
      (m.sub ? "<span class='chip'>子TAG：" + esc(m.sub) + "</span>" : "") +
      "<span class='loc'>" + esc(m.file) + ":" + m.line + "</span></div>" +
      "<label>条件</label><textarea data-k='cond'>" + esc(m.cond) + "</textarea>" +
      "<label>备注</label><textarea data-k='note'>" + esc(m.note) + "</textarea>" +
      "<div class='src'>依据：" + esc(m.src) + "</div>" +
      "<div class='acts'><button class='save'>保存本行</button><button class='undo'>撤销</button><span class='st'></span></div>" +
      "</div>";
  }
  box.innerHTML = html;
  box.querySelectorAll(".row").forEach(r => {
    const m = rows.find(x => x.m.file === r.dataset.file && String(x.m.line) === r.dataset.line).m;
    const ta = {cond: r.querySelector("textarea[data-k=cond]"), note: r.querySelector("textarea[data-k=note]")};
    const fit = el => { el.style.height = "auto"; el.style.height = Math.max(el.scrollHeight, 30) + "px"; };
    for (const k in ta) {
      fit(ta[k]);
      ta[k].addEventListener("input", () => { fit(ta[k]); r.classList.toggle("dirty", ta.cond.value !== m.cond || ta.note.value !== m.note); });
    }
    r.querySelector(".undo").onclick = () => { ta.cond.value = m.cond; ta.note.value = m.note; fit(ta.cond); fit(ta.note); r.classList.remove("dirty"); st("");
      r.querySelector(".st").textContent = ""; };
    const st = (msg, kind) => { const s = r.querySelector(".st"); s.textContent = msg || ""; s.className = "st " + (kind || ""); };
    r.querySelector(".save").onclick = async () => {
      if (ta.cond.value === m.cond && ta.note.value === m.note) { st("无改动"); return; }
      st("保存中…");
      try {
        const j = await api("/api/cell", {file: m.file, line: m.line, original: m.raw, cond: ta.cond.value, note: ta.note.value});
        m.cond = j.cond; m.note = j.note; m.raw = j.raw;
        ta.cond.value = j.cond; ta.note.value = j.note; fit(ta.cond); fit(ta.note);
        r.classList.remove("dirty");
        st("已保存" + (j.warn ? "（" + j.warn + "）" : ""), j.warn ? "" : "ok");
        if (document.getElementById("automerge").checked) {
          const mr = await api("/api/merge", {});
          st(mr.ok ? "已保存，并重新生成 docs/player-tags-members.md" : "已保存，但重新生成名单文档失败", mr.ok ? "ok" : "err");
        } else {
          status("有未合并的单元格改动");
        }
      } catch (e) { st(e.message, "err"); }
    };
  });
}

function renderAll() { renderTags(); renderOps(); renderRec(); renderEditor(); }

document.getElementById("search").addEventListener("input", e => { query = e.target.value.trim().toLowerCase(); renderOps(); });
document.getElementById("btreload").onclick = () => load().then(() => status("数据已刷新", "ok")).catch(e => toast(e.message, true));
document.getElementById("btmerge").onclick = async () => {
  status("正在重新生成…");
  try {
    const j = await api("/api/merge", {});
    status(j.ok ? "名单文档已重新生成" : "重新生成失败", j.ok ? "ok" : "err");
    if (!j.ok) toast(j.err || j.out || "重新生成失败", true);
    else toast("docs/player-tags-members.md 已更新");
  } catch (e) { status("重新生成失败", "err"); toast(e.message, true); }
};
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (location.hash) history.replaceState(null, "", location.pathname);
    editOp = null;
    renderEditor();
  }
});
load().catch(e => toast("加载失败：" + e.message, true));
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "RecommendGui"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 静默，不打访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._send(200, HTML.replace("__TOKEN__", TOKEN).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/data":
                self._json(build_model())
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if self.headers.get("X-Token") != TOKEN:
            self._json({"ok": False, "error": "令牌无效，请刷新页面"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/recommend":
                self._json(apply_recommend(payload))
            elif path == "/api/cell":
                self._json(save_cell(payload["file"], int(payload["line"]), payload["original"], payload["cond"], payload["note"]))
            elif path == "/api/merge":
                self._json(run_merge())
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except UserError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except KeyError as exc:
            self._json({"ok": False, "error": f"请求缺少字段：{exc}"}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="玩家体感 TAG「荐」+ 条件/备注 维护面板（本地网页版）")
    parser.add_argument("--port", type=int, default=8520, help="监听端口（默认 8520，被占用时自动换一个）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="只解析自检一次，不起服务")
    args = parser.parse_args()

    if args.check:
        model = build_model()
        total = sum(len(t["members"]) for t in model["tags"])
        print(f"TAG {len(model['tags'])} 个，成员行 {total} 条；荐 {sum(len(v) for v in model['recommend'].values())} 条")
        for t in model["tags"]:
            print(f"  {t['num']} {t['name']}：成员 {len(t['members'])} 行 / 子表 {t['sections']} 个 / 荐 {len(t['recommend'])}")
        for s in model["stale"]:
            print(f"  [悬空荐] {s['tag']} -> {s['op']}")
        for t in model["unknown_tags"]:
            print(f"  [未知 TAG] {t}")
        return 0

    port = args.port
    for candidate in (port, 0):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = srv.server_address[1]
            break
        except OSError:
            continue
    else:
        print("无法绑定本地端口", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}/"
    print(f"「荐」维护面板已启动：{url}")
    print("   左键 = 加荐 · 右键 = 取消荐 · ✎/双击 = 编辑条件与备注；Ctrl+C 退出")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

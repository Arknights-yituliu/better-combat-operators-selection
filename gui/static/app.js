const TOKEN = (document.querySelector('meta[name="x-token"]') || {}).content || "";
// ak-ui 文档站用的字体（Noto Sans/Serif SC）。在 load 之后带超时地取一次 CSS：
// 取到才内联，取不到就安静地保持本机字体回退——绝不让字体 CDN 拖住页面（离线/被墙时
// 挂起的样式表会阻塞脚本与 document.fonts.ready）。
window.addEventListener("load", () => {
  const url = "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900"
    + "&family=Noto+Serif+SC:wght@700;900&display=swap";
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 2500);
  fetch(url, {mode: "cors", signal: ac.signal})
    .then(r => (r.ok ? r.text() : Promise.reject(new Error("HTTP " + r.status))))
    .then(css => {
      const s = document.createElement("style");
      s.textContent = css;
      document.head.appendChild(s);
    })
    .catch(() => {})
    .finally(() => clearTimeout(timer));
}, {once: true});
let DATA = null;
const IDX = {byId:new Map(), tagBlocks:new Map(), tree:[]};
const ST = {
  tab: "zhen",
  zhen: {tag: "__all__", q: ""},
  ind: {targets: [], browse: null, browseOpen: {}, openOp: null, q: "", pq: "", tq: "",
        collapsed: {}, stage: [], busy: false},
};

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function toast(msg, isErr) {
  const d = document.createElement("div");
  d.className = "tmsg" + (isErr ? " err" : "");
  d.textContent = msg;
  document.getElementById("toast").appendChild(d);
  setTimeout(() => d.remove(), isErr ? 4200 : 2000);
}
function status(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.className = kind || "";
}
function automergeOn() { return document.getElementById("automerge").checked; }
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Token": TOKEN},
    body: JSON.stringify(body),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { j = {error: "服务返回异常（HTTP " + r.status + "）"}; }
  if (!r.ok || j.ok === false) { const e = new Error(j.error || ("HTTP " + r.status)); e.code = j.code || ""; throw e; }
  return j;
}
function matches(name, q) { return !q || name.toLowerCase().includes(q); }

// ---------------------------------------------------------------- 加载 / 派生索引

async function load(fresh) {
  DATA = await (await fetch("/api/data" + (fresh ? "?fresh=1" : ""))).json();
  hydrate();
  if (DATA.stale.length) toast("有 " + DATA.stale.length + " 条荐已不在成员表中，请核对", true);
  renderAll();
}
function hydrate() {
  IDX.byId.clear(); IDX.tagBlocks.clear(); IDX.tree = [];
  const tagTree = [];
  for (const t of DATA.player_tags) {
    const blocks = t.blocks.map(b => b.id);
    IDX.tagBlocks.set("p:" + t.name, blocks);
    for (const b of t.blocks) IDX.byId.set(b.id, {...b, source: "player", tagKey: "p:" + t.name, tagName: t.name, multi: t.blocks.length > 1, tagNum: t.num});
    tagTree.push({key: "p:" + t.name, name: t.name, num: t.num, blocks, ops: new Set(t.blocks.flatMap(b => b.rows.map(r => r.op))).size});
  }
  IDX.tree.push({title: "玩家体感 TAG", tags: tagTree});
  const byCat = new Map();
  for (const e of DATA.official_entries) {
    const b = e.blocks[0];
    IDX.byId.set(b.id, {...b, source: "official", tagKey: "o:" + e.id, tagName: e.name, multi: false});
    IDX.tagBlocks.set("o:" + e.id, [b.id]);
    if (!byCat.has(e.category)) byCat.set(e.category, []);
    byCat.get(e.category).push({key: "o:" + e.id, name: e.name, blocks: [b.id], ops: new Set(b.rows.map(r => r.op)).size});
  }
  IDX.tree.push({title: "官方设定 TAG", cats: [...byCat.entries()].map(([title, tags]) => ({title, tags}))});
}
function tagOf(name) { return DATA.player_tags.find(t => t.name === name); }
function blockById(bid) { return IDX.byId.get(bid); }
function scopeBlocks() {
  if (ST.ind.targets.length) return ST.ind.targets.map(t => blockById(t.id)).filter(Boolean);
  if (ST.ind.browse) return (IDX.tagBlocks.get(ST.ind.browse) || []).map(blockById).filter(Boolean);
  return [];
}
function scopeRows() {
  const out = [];
  for (const b of scopeBlocks()) for (const r of b.rows) out.push({b, r});
  return out;
}
function inTargets(bid) { return ST.ind.targets.some(t => t.id === bid); }
function blkLabel(b) {  // 单子表 TAG 的区块标题就是「成员表…」，不再显示
  return (IDX.tagBlocks.get(b.tagKey) || []).length > 1 ? b.label : "";
}
function blkFull(b) { const l = blkLabel(b); return b.tagName + (l ? " · " + l : ""); }

// ---------------------------------------------------------------- 荐 页

function viewOps() {
  if (ST.zhen.tag === "__all__") {
    const names = [...new Set(DATA.player_tags.flatMap(t => t.blocks.flatMap(b => b.rows.map(r => r.op))))];
    names.sort((a, b) => a.localeCompare(b, "zh"));
    return names.map(op => ({op, rec: -1, rows: allRowsOf(op)}));
  }
  const t = tagOf(ST.zhen.tag);
  const recs = t.recommend.map((op, i) => ({op, rec: i, rows: allRowsOf(op)}));
  const members = [...new Set(t.blocks.flatMap(b => b.rows.map(r => r.op)))].filter(op => !t.recommend.includes(op));
  return recs.concat(members.map(op => ({op, rec: -1, rows: allRowsOf(op)})));
}
function allRowsOf(op) {
  const out = [];
  for (const t of DATA.player_tags) for (const b of t.blocks) for (const r of b.rows) if (r.op === op) out.push({b, r});
  return out;
}
function renderTags() {
  const col = document.getElementById("tagcol");
  col.innerHTML = "";
  const mk = (label, on, fn, badge) => {
    const el = document.createElement("div");
    el.className = "tag" + (on ? " on" : "");
    el.innerHTML = label + '<span class="n">' + badge + "</span>";
    el.onclick = fn;
    col.appendChild(el);
  };
  const total = new Set(DATA.player_tags.flatMap(t => t.blocks.flatMap(b => b.rows.map(r => r.op)))).size;
  mk('<span>全部干员</span>', ST.zhen.tag === "__all__", () => { ST.zhen.tag = "__all__"; renderAll(); }, total);
  for (const t of DATA.player_tags) {
    const n = new Set(t.blocks.flatMap(b => b.rows.map(r => r.op))).size;
    mk('<span class="num">' + t.num + '</span><span>' + esc(t.name) + "</span>",
       ST.zhen.tag === t.name, () => { ST.zhen.tag = t.name; renderAll(); },
       n + (t.recommend.length ? " · 荐" + t.recommend.length : ""));
  }
}
function renderOps() {
  const list = document.getElementById("oplist");
  list.innerHTML = "";
  const all = viewOps();
  const items = all.filter(it => matches(it.op, ST.zhen.q));
  document.getElementById("cnt").textContent = items.length + " / " + all.length + " 人";
  let recDone = false;
  for (const it of items) {
    if (ST.zhen.tag !== "__all__" && it.rec < 0 && !recDone && items.some(x => x.rec >= 0)) {
      recDone = true;
      const d = document.createElement("div");
      d.className = "split";
      d.textContent = "其余成员（成员表顺序）";
      list.appendChild(d);
    }
    const el = opRow(it, {
      rank: it.rec >= 0 ? it.rec + 1 : "",
      chips: [],
      buttons: [{label: "详情", title: "到「人工归纳」页查看条件与备注", fn: () => gotoInduce(it.op, ST.zhen.tag)}],
      onClick: () => addRec(it.op),
      onContext: () => removeRec(it.op),
    });
    list.appendChild(el);
  }
}
function renderRec() {
  const box = document.getElementById("recbox");
  if (ST.zhen.tag === "__all__") {
    box.innerHTML = "<h3>荐</h3><div class='empty'>在左侧选中一个 TAG 后，左键 / 右键干员即可增删荐。</div>";
    return;
  }
  const t = tagOf(ST.zhen.tag);
  let html = "<h3>「" + esc(t.name) + "」荐（" + t.recommend.length + " 人，按展示优先级）</h3>" +
    "<div class='note'>荐只能加在玩家体感 TAG（P01–P12）上；官方设定 TAG 无荐字段。</div>";
  if (!t.recommend.length) html += "<div class='empty'>暂无。左键下方任一干员即可加入。</div>";
  else {
    html += "<ol>";
    t.recommend.forEach(op => {
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
        if (act === "up" || act === "down") await api("/api/recommend", {tag: ST.zhen.tag, action: "move", op, delta: act === "up" ? -1 : 1});
        else if (act === "first") await api("/api/recommend", {tag: ST.zhen.tag, action: "first", op});
        else await api("/api/recommend", {tag: ST.zhen.tag, action: "remove", op});
        await load();
      } catch (e) { toast(e.message, true); }
    };
  });
}
async function addRec(op) {
  if (ST.zhen.tag === "__all__") { toast("请先在左侧选择一个 TAG，再加荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: ST.zhen.tag, action: "add", op});
    DATA.recommend = j.recommend;
    tagOf(ST.zhen.tag).recommend = j.recommend[ST.zhen.tag] || [];
    toast(j.noop ? ("「" + ST.zhen.tag + "」已是荐：" + op) : ("已设荐：" + op + " →「" + ST.zhen.tag + "」"));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}
async function removeRec(op) {
  if (ST.zhen.tag === "__all__") { toast("请先在左侧选择一个 TAG，再取消荐"); return; }
  try {
    const j = await api("/api/recommend", {tag: ST.zhen.tag, action: "remove", op});
    DATA.recommend = j.recommend;
    tagOf(ST.zhen.tag).recommend = j.recommend[ST.zhen.tag] || [];
    toast(j.noop ? ("「" + ST.zhen.tag + "」本就没有荐：" + op) : ("已取消荐：" + op));
    renderTags(); renderOps(); renderRec();
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- 共用行组件

function opRow(rec, o) {
  const el = document.createElement("div");
  el.className = "card" + (o.cls ? " " + o.cls : "");
  el.innerHTML = '<span class="rank">' + esc(o.rank || "") + "</span>" +
    '<span class="name">' + esc(rec.op) + "</span>" +
    '<span class="chips">' + (o.chips || []).map(c => '<span class="chip' + (c && c.cls ? " " + c.cls : "") + '">' + esc(c && c.t !== undefined ? c.t : c) + "</span>").join("") + "</span>" +
    '<span class="tail">' + (o.buttons || []).map((b, i) => '<button class="mini" data-i="' + i + '" title="' + esc(b.title || "") + '">' + esc(b.label) + "</button>").join("") + "</span>";
  el.onclick = e => {
    const b = e.target.closest("button[data-i]");
    if (b) { e.stopPropagation(); o.buttons[+b.dataset.i].fn(); return; }
    (o.onClick || (() => {}))();
  };
  if (o.onContext) el.oncontextmenu = e => { e.preventDefault(); o.onContext(e); };
  return el;
}
function bindSearch(id, get, set, render) {
  const el = document.getElementById(id);
  el.value = get();
  el.addEventListener("input", () => { set(el.value.trim().toLowerCase()); render(); });
}

// ---------------------------------------------------------------- 人工归纳：TAG 树

function renderTree() {
  const col = document.getElementById("tagtree");
  col.innerHTML = "";
  const q = ST.ind.tq;
  for (const group of IDX.tree) {
    const isOfficial = !!group.cats;
    const collapsed = !q && ST.ind.collapsed["g:" + group.title];
    const hdr = document.createElement("div");
    hdr.className = "grouphdr";
    hdr.innerHTML = '<span class="caret">' + (collapsed ? "▸" : "▾") + "</span><span>" + esc(group.title) + "</span>";
    hdr.onclick = () => { ST.ind.collapsed["g:" + group.title] = !collapsed; renderTree(); };
    col.appendChild(hdr);
    if (collapsed) continue;
    const cats = isOfficial ? group.cats : [{title: "", tags: group.tags}];
    for (const cat of cats) {
      if (cat.title) {
        const ck = "c:" + cat.title;
        const ccol = !q && ST.ind.collapsed[ck];
        const cel = document.createElement("div");
        cel.className = "catrow";
        cel.innerHTML = '<span class="caret">' + (ccol ? "▸" : "▾") + "</span><span>" + esc(cat.title) + "</span>";
        cel.onclick = () => { ST.ind.collapsed[ck] = !ccol; renderTree(); };
        col.appendChild(cel);
        if (ccol) continue;
      }
      for (const tag of cat.tags) {
        if (q && !tag.name.toLowerCase().includes(q) && !tag.blocks.some(b => ((blockById(b) || {}).label || "").toLowerCase().includes(q))) continue;
        const multi = tag.blocks.length > 1;
        if (multi) {
          const open = !!ST.ind.browseOpen[tag.key] || !!q;
          const el = document.createElement("div");
          el.className = "tag" + (ST.ind.browse === tag.key ? " on" : "");
          el.innerHTML = '<span class="caret">' + (open ? "▾" : "▸") + '</span><span class="lbl">' + esc(tag.name) + '</span><span class="n">' + tag.ops + "</span>";
          el.onclick = () => {
            ST.ind.browseOpen[tag.key] = !open;
            ST.ind.browse = tag.key;
            ST.ind.targets = [];
            renderInd();
          };
          col.appendChild(el);
          if (open) for (const bid of tag.blocks) col.appendChild(blockRow(blockById(bid), true));
        } else {
          col.appendChild(blockRow(blockById(tag.blocks[0]), false, tag.name));
        }
      }
    }
  }
}
function blockRow(b, indented, nameOverride) {
  const el = document.createElement("div");
  el.className = "blk" + (inTargets(b.id) ? " on" : "");
  const label = nameOverride || b.label;
  el.innerHTML = (indented ? '<span class="caret"></span>' : "") + '<span class="lbl">' + esc(label) + '</span><span class="n">' + b.rows.length + "</span>";
  el.title = (b.source === "official" ? "[官方] " : "[玩家] ") + blkFull(b);
  el.onclick = e => {
    if (e.ctrlKey || e.metaKey) {
      const k = ST.ind.targets.findIndex(t => t.id === b.id);
      if (k >= 0) ST.ind.targets.splice(k, 1);
      else ST.ind.targets.push({id: b.id, sig: b.sig});
      ST.ind.browse = null;
    } else {
      ST.ind.targets = [{id: b.id, sig: b.sig}];
      ST.ind.browse = null;
    }
    renderInd();
  };
  return el;
}

// ---------------------------------------------------------------- 人工归纳：干员列表

function renderInd() {
  renderTree(); renderIndList(); renderStage();
  const tip = document.getElementById("stagetip");
  const sel = ST.ind.targets.map(t => blockById(t.id)).filter(Boolean);
  tip.textContent = sel.length
    ? "目标：" + sel.map(blkFull).join("；") + (sel.length > 1 ? "（" + sel.length + " 个，移动只能落到一个）" : "")
    : (ST.ind.browse ? "浏览中（只读范围，点具体子表才能并入）" : "先在左侧选中目标子表");
}
function renderIndList() {
  const list = document.getElementById("ioplist");
  list.innerHTML = "";
  const rows = scopeRows();
  const byOp = new Map();
  for (const x of rows) {
    if (!byOp.has(x.r.op)) byOp.set(x.r.op, []);
    byOp.get(x.r.op).push(x);
  }
  const names = [...byOp.keys()];
  const items = names.filter(n => matches(n, ST.ind.q));
  document.getElementById("icnt").textContent = items.length + " / " + names.length + " 人";
  if (!scopeBlocks().length) {
    list.innerHTML = "<div class='split'>" + (ST.ind.openOp
      ? "「" + esc(ST.ind.openOp) + "」不在当前范围：请在左侧选中它所属的 TAG（含官方设定 TAG）后查看。"
      : "点左侧 TAG 查看其下干员；多子表 TAG 展开后点具体子表即可并入。") + "</div>";
    return;
  }
  const multi = scopeBlocks().length > 1;
  for (const op of items) {
    const recs = byOp.get(op);
    const open = ST.ind.openOp === op;
    const chips = recs.map(x => (x.r.sub || (multi ? x.b.label : ""))).filter(Boolean);
    const el = opRow({op}, {
      cls: open ? "open" : "",
      chips,
      buttons: [],
      onClick: () => { ST.ind.openOp = open ? null : op; renderIndList(); },
      onContext: e => rowMenu(e, op, recs),
    });
    list.appendChild(el);
    if (open) list.appendChild(detailEl(op, recs));
  }
}
function briefHtml(name, cid) {
  // 编号 = charId：只读展示，来自成员行的「编号」列（缺列时由服务端回查 char_ids.json）
  const idHtml = cid ? "<span class='cid' title='charId（只读；插入新行时按干员名自动填充）'>" + esc(cid) + "</span>" : "";
  const p = (DATA.roster || []).find(x => x.name === name);
  if (!p) return "<div class='brief'><b>" + esc(name) + "</b>" + idHtml + "<span>（未在全量干员表中找到）</span></div>";
  return "<div class='brief'><b>" + esc(p.name) + "</b>" + idHtml +
    "<span>" + (p.star ? "★".repeat(p.star) : "—") + "</span>" +
    "<span>" + esc([p.cls, p.branch].filter(Boolean).join("·")) + "</span>" +
    "<span>" + esc(p.faction || "—") + "</span>" +
    "<span>" + esc(p.date || "—") + "</span>" +
    "<span><a href='" + esc(p.url) + "' target='_blank' rel='noreferrer'>PRTS↗</a></span></div>";
}
function firstCid(recs) {
  for (const x of recs) if (x.r.cid) return x.r.cid;
  return "";
}
function detailEl(op, recs) {
  const box = document.createElement("div");
  box.className = "detail";
  box.innerHTML = briefHtml(op, firstCid(recs));
  for (const x of recs) box.appendChild(recordCard(x));
  return box;
}
function recordCard(x) {
  const b = x.b, r = x.r;
  const el = document.createElement("div");
  el.className = "row";
  const badge = b.source === "player" ? "<span class='badge p'>玩家</span>" : "<span class='badge o'>官方</span>";
  el.innerHTML = "<div class='head'>" + badge + "<b>" + esc(b.tagName) + "</b>" +
    (blkLabel(b) ? "<span class='chip'>" + esc(b.label) + "</span>" : "") +
    "<span class='loc'>" + esc(b.file) + ":" + r.line + "</span></div>" +
    "<div class='vlabel'>条件</div><div class='val" + (r.cond ? "" : " empty") + "' data-k='cond'>" + esc(r.cond || "（待填）") + "</div>" +
    "<div class='vlabel'>备注</div><div class='val" + (r.note ? "" : " empty") + "' data-k='note'>" + esc(r.note || "（待填）") + "</div>" +
    (b.source === "player" ? "<div class='src'>依据：" + esc(r.src || "—") + "</div>" : "");
  el.querySelectorAll(".val").forEach(v => { v.onclick = () => startEdit(v, x); });
  return el;
}
function startEdit(el, x) {
  const key = el.dataset.k;
  const old = x.r[key];
  const line = document.createElement("div");
  line.className = "editline";
  const input = document.createElement("input");
  input.value = old;
  const ok = document.createElement("button"); ok.textContent = "✓"; ok.title = "保存（Enter）";
  const no = document.createElement("button"); no.textContent = "×"; no.title = "取消（Esc）";
  line.append(input, ok, no);
  el.replaceWith(line);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  let done = false;
  const cancel = () => { if (!done) { done = true; paintVal(el, old); line.replaceWith(el); } };
  const commit = async () => {
    if (done) return;
    done = true;
    const v = input.value;
    const cond = key === "cond" ? v : x.r.cond;
    const note = key === "note" ? v : x.r.note;
    if (v === old) { line.replaceWith(el); return; }
    try {
      const j = await api("/api/cell", {file: x.b.file, line: x.r.line, original: x.r.raw, cond, note});
      x.r.cond = j.cond; x.r.note = j.note; x.r.raw = j.raw;
      paintVal(el, x.r[key]);
      line.replaceWith(el);
      toast("已保存" + (j.warn ? "（" + j.warn + "）" : ""));
      if (automergeOn()) {
        const mr = await api("/api/merge", {which: x.b.source === "official" ? "official" : "player"});
        status(mr.ok ? "已保存并重新生成名单文档" : "已保存，但重新生成名单文档失败", mr.ok ? "ok" : "err");
      } else status("有未合并的单元格改动");
    } catch (e) {
      done = false;
      toast(e.message, true);
      status("保存失败", "err");
    }
  };
  ok.onclick = commit;
  no.onclick = cancel;
  input.onkeydown = e => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
  };
}
function paintVal(el, v) {
  el.textContent = v || "（待填）";
  el.classList.toggle("empty", !v);
}

// ---------------------------------------------------------------- 人工归纳：右键菜单 / 移除

function closeMenu() { const m = document.getElementById("menu"); if (m) m.remove(); }
function openMenu(x, y, items) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu"; m.id = "menu";
  for (const it of items) {
    if (it.sep) { const s = document.createElement("div"); s.className = "sep"; m.appendChild(s); continue; }
    const b = document.createElement("button");
    b.textContent = it.label;
    b.onclick = () => { closeMenu(); it.fn(); };
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const rect = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - rect.width - 8) + "px";
  m.style.top = Math.min(y, innerHeight - rect.height - 8) + "px";
}
function rowMenu(e, op, recs) {
  const items = [{label: "扩展（放入临时区）", fn: () => stageOp(op, "extend", null)}];
  if (recs.length === 1) {
    items.push({label: "移动（带走条件/备注，删除源行）", fn: () => stageOp(op, "move", recs[0])});
    items.push({label: "移除（删除该行）", fn: () => removeRow(recs[0])});
  } else {
    for (const x of recs) {
      items.push({sep: true});
      items.push({label: "移动：原行在「" + blkFull(x.b) + "」", fn: () => stageOp(op, "move", x)});
      items.push({label: "移除：原行在「" + blkFull(x.b) + "」", fn: () => removeRow(x)});
    }
  }
  openMenu(e.clientX, e.clientY, items);
}
async function removeRow(x) {
  if (!confirm("从「" + blkFull(x.b) + "」删除「" + x.r.op + "」的整行记录？\n（含条件/备注/依据，源文件 " + x.b.file + ":" + x.r.line + "，可用 git 恢复）")) return;
  try {
    const j = await api("/api/apply", {automerge: automergeOn(), ops: [{kind: "delete", op: x.r.op,
      from: {block: {id: x.b.id, sig: x.b.sig}, line: x.r.line, raw: x.r.raw}}]});
    afterApply(j, "已移除：" + x.r.op);
  } catch (e) { toast(e.message, true); if (e.code === "drift") load(true); }
}
function afterApply(j, prefix) {
  const msgs = [];
  for (const r of j.results || []) {
    if (r.targets) {
      const bad = r.targets.filter(t => t.skipped);
      msgs.push((prefix ? prefix + "：" : "") + r.op + " → 已并入 " + (r.targets.length - bad.length) + " 个子表" +
        (bad.length ? "，跳过 " + bad.map(t => t.label + "（已在表内）").join("、") : ""));
    } else if (r.skipped) msgs.push(r.op + "：" + r.reason);
    else if (r.kind === "move") msgs.push("已移动：" + r.op + " → " + (r.to ? r.to.file : "") +
      (r.dropped && Object.keys(r.dropped).length ? "（" + Object.keys(r.dropped).join("、") + " 列目标表没有，未随行）" : ""));
    else msgs.push(prefix || "已完成");
  }
  const pruned = Object.entries(j.pruned_recommend || {});
  if (pruned.length) msgs.push("同步取消了荐：" + pruned.map(([t, ops]) => "「" + t + "」" + ops.join("、")).join("；"));
  for (const m of msgs) toast(m);
  for (const w of j.warnings || []) toast(w, true);
  const mg = j.merge || {};
  const bad = Object.entries(mg).filter(([, v]) => !v.ok);
  if (bad.length) toast("重新生成名单文档失败：" + bad.map(([k, v]) => k + " " + (v.err || v.out || "")).join("；"), true);
  return load(true);
}

// ---------------------------------------------------------------- 人工归纳：临时区

function stageSave() {
  try {
    localStorage.setItem("induct.v1", JSON.stringify({targets: ST.ind.targets, stage: ST.ind.stage}));
  } catch (e) {}
}
function stageOp(op, mode, rec) {
  const k = ST.ind.stage.findIndex(s => s.op === op);
  if (k >= 0) {
    const cur = ST.ind.stage[k];
    const sameSrc = mode === "move" && cur.mode === "move" && rec && cur.src
      && cur.src.blockId === rec.b.id && cur.src.line === rec.r.line;
    if (mode !== "move" || sameSrc) {
      toast("「" + op + "」已在临时区" + (cur.mode === "move" ? "（移动）" : ""));
      return;
    }
    ST.ind.stage.splice(k, 1);  // 已暂存为「扩展」或来自别的行时，按新来源覆盖（移动会带上条件/备注）
    toast("临时区中「" + op + "」的来源已更新");
  }
  ST.ind.stage.push({
    sid: "st-" + Date.now() + "-" + Math.floor(Math.random() * 1000),
    op, mode,
    src: rec ? {blockId: rec.b.id, blockSig: rec.b.sig, file: rec.b.file, line: rec.r.line, raw: rec.r.raw,
                tagName: rec.b.tagName, label: blkLabel(rec.b), full: blkFull(rec.b), src: rec.r.src} : null,
    preview: rec ? {cond: rec.r.cond, note: rec.r.note} : null,
    stale: false,
  });
  stageSave();
  toast((mode === "move" ? "已放入临时区（移动）：" : "已放入临时区（扩展）：") + op);
  renderStage();
}
function renderStage() {
  const list = document.getElementById("stagelist");
  list.innerHTML = "";
  if (!ST.ind.stage.length) {
    list.innerHTML = "<span class='empty'>空。右侧摘选区左键、或干员行右键「扩展 / 移动」把干员放进来；选中目标子表后点这里的干员即可并入。</span>";
    return;
  }
  for (const it of ST.ind.stage) {
    const el = document.createElement("div");
    el.className = "stage-item" + (it.mode === "move" ? " mv" : "") + (it.stale ? " stale" : "");
    const tag = it.mode === "move" && it.src ? "移动·自 " + (it.src.full || it.src.tagName) : "扩展";
    el.innerHTML = "<b>" + esc(it.op) + '</b><span class="badge">' + esc(tag) + "</span>" +
      (it.stale ? "<span class='chip'>源行已变化，请重新摘取</span>" : "") +
      "<button class='x' title='移出临时区'>×</button>";
    el.title = it.mode === "move" && it.preview
      ? "将带走：条件＝" + (it.preview.cond || "（空）") + "\n备注＝" + (it.preview.note || "（空）")
      : "并入后新行的条件/备注为空，需自行填写";
    el.onclick = e => { if (e.target.closest(".x")) return; dropStage(it); };
    el.querySelector(".x").onclick = e => {
      e.stopPropagation();
      ST.ind.stage = ST.ind.stage.filter(s => s.sid !== it.sid);
      stageSave(); renderStage();
    };
    list.appendChild(el);
  }
}
async function dropStage(it) {
  if (ST.ind.busy) return;
  const targets = ST.ind.targets;
  if (!targets.length) { toast("请先在左侧选中目标子表", true); return; }
  if (it.stale) { toast("该条目所记的源行已变化，请重新摘取", true); return; }
  if (it.mode === "move" && targets.length !== 1) { toast("移动只能指定一个目标子表", true); return; }
  ST.ind.busy = true;
  try {
    const ops = it.mode === "move"
      ? [{kind: "move", op_id: it.sid, from: {block: {id: it.src.blockId, sig: it.src.blockSig}, line: it.src.line, raw: it.src.raw}, targets: targets.map(t => ({id: t.id, sig: t.sig}))}]
      : [{kind: "insert", op_id: it.sid, op: it.op, cond: "", note: "", sub: "", targets: targets.map(t => ({id: t.id, sig: t.sig}))}];
    const j = await api("/api/apply", {automerge: automergeOn(), ops});
    if (it.mode === "move") ST.ind.stage = ST.ind.stage.filter(s => s.sid !== it.sid);
    stageSave();
    await afterApply(j, "");
  } catch (e) {
    toast(e.message, true);
    if (e.code === "drift") { await load(true); markStageStale(); }
  } finally { ST.ind.busy = false; }
}
function markStageStale() {
  for (const it of ST.ind.stage) {
    if (it.mode !== "move" || !it.src) continue;
    const b = blockById(it.src.blockId);
    const r = b ? b.rows.find(r => r.raw === it.src.raw) : null;
    if (!b || !r) it.stale = true;
    else { it.src.line = r.line; it.src.raw = r.raw; it.stale = false; }
  }
  stageSave(); renderStage();
}

// ---------------------------------------------------------------- 人工归纳：摘选区

function renderPicker() {
  const list = document.getElementById("picklist");
  list.innerHTML = "";
  const all = (DATA.roster || []).slice().sort((a, b) => a.name.localeCompare(b.name, "zh"));
  const items = all.filter(p => matches(p.name, ST.ind.pq));
  document.getElementById("pcnt").textContent = items.length + " / " + all.length + " 人";
  for (const p of items) {
    const staged = ST.ind.stage.some(s => s.op === p.name);
    const el = opRow({op: p.name}, {
      rank: "",
      chips: [p.star ? {t: "★".repeat(p.star), cls: "rar" + p.star} : null,
              [p.cls, p.branch].filter(Boolean).join("·"), p.date].filter(Boolean),
      cls: staged ? "open" : "",
      buttons: [],
      onClick: () => stageOp(p.name, "extend", null),
    });
    list.appendChild(el);
  }
}

// ---------------------------------------------------------------- 结果 JSON：状态与视图同步

const RES = {
  file: null, eol: "crlf", doc: null, base: "", expect: null, today: "",
  view: "card", mode: "tag", shape: "none", dirty: false, busy: false,
  src: "", srcParsed: true, srcErr: "", list: null, problems: null, stats: null,
  sel: {tag: -1, mi: -1, op: -1}, q: {t: "", m: "", o: ""}, opage: 1,
};
const RES_CLASSES = ["先锋", "近卫", "狙击", "重装", "医疗", "辅助", "术师", "特种"];
const RES_CATS = ["A 控制·异常", "B 伤害类型", "C 生存与增益", "D 部署与编队", "E 技力与技能资源",
  "F 治疗与支援", "G 召唤物", "H 攻击行为特征", "I 全场光环"];
const RES_ANCHORS = ["", "#技能", "#天赋", "#模组", "#召唤物信息"];

const serialize = d => JSON.stringify(d, null, 2);
function resShape(d) {
  if (d === null || typeof d !== "object" || Array.isArray(d)) return "notobject";
  if (!Array.isArray(d.tags) || !Array.isArray(d.operators)) return "foreign";
  return "ok";
}
function curText() { return RES.view === "src" ? RES.src : serialize(RES.doc); }
function resDirtyNow() { return RES.doc !== null && serialize(RES.doc) !== RES.base; }
function rootUrl(name) { return "https://prts.wiki/w/" + encodeURIComponent(name); }
function resTag() { return RES.doc && RES.doc.tags ? RES.doc.tags[RES.sel.tag] : null; }
function resMember() {
  const t = resTag();
  return t && t.members && RES.sel.mi >= 0 ? t.members[RES.sel.mi] : null;
}
let resDraftTimer = null;
function resDraft() {
  clearTimeout(resDraftTimer);
  resDraftTimer = setTimeout(() => {
    try {
      const text = curText();
      if (text.length > 1500000) return;  // 接近 localStorage 配额，放弃草稿
      localStorage.setItem("res.v1", JSON.stringify({file: RES.file, eol: RES.eol, text, savedAt: Date.now()}));
    } catch (e) {}
  }, 1000);
}
function resMark() { RES.dirty = true; resDraft(); renderResBar(); }
function resSet(doc, meta) {
  RES.doc = doc;
  RES.file = meta.file || null;
  RES.eol = meta.eol || "crlf";
  RES.expect = meta.digest ? {digest: meta.digest, mtime_ns: meta.mtime_ns, size: meta.size} : null;
  RES.base = serialize(doc);
  RES.dirty = false;
  RES.shape = resShape(doc);
  RES.problems = null; RES.stats = null;
  RES.view = "card";  // 非结果 JSON 在结构化区显示只读摘要，可手动切源码视图
  RES.mode = "tag";
  RES.sel = {tag: RES.shape === "ok" && doc.tags.length ? 0 : -1, mi: -1,
             op: RES.shape === "ok" && doc.operators.length ? 0 : -1};
  RES.opage = 1;
  RES.src = serialize(doc);
  RES.srcParsed = true; RES.srcErr = "";
  localStorage.removeItem("res.v1");
}
function resEnsure() {  // 把源码视图的文本提交进 doc
  if (RES.view !== "src") return true;
  try {
    RES.doc = JSON.parse(RES.src);
    RES.shape = resShape(RES.doc);
    RES.srcParsed = true; RES.srcErr = "";
    return true;
  } catch (e) { RES.srcParsed = false; RES.srcErr = String(e && e.message || e); return false; }
}
function resGuard(what) {
  if (!RES.doc) return true;
  if (RES.view === "src" && !resEnsure()) { toast("源码不是合法 JSON，请先修正：" + RES.srcErr, true); return false; }
  if (!resDirtyNow()) return true;
  return confirm("「结果 JSON」有未保存的改动，" + what + "会丢弃它们（浏览器草稿仍保留）。继续？");
}
function switchView(next) {
  if (!RES.doc || next === RES.view) return;
  if (next === "src") {
    RES.src = serialize(RES.doc);           // 结构化改动优先，无条件重写源码缓冲
    RES.srcParsed = true; RES.srcErr = "";
    RES.view = "src";
  } else {
    if (!resEnsure()) { renderResSrcErr(); toast("源码不是合法 JSON，已留在源码视图：" + RES.srcErr, true); return; }
    RES.view = "card";
  }
  renderResults();
}
function resSkeleton() {
  const today = RES.today || (RES.list && RES.list.today) || new Date().toISOString().slice(0, 10);
  return {version: "v1", updated: today, operators: [], tags: []};
}

async function resLoadDialog() {
  try {
    const list = await api("/api/results/list", {});
    RES.list = list; RES.today = list.today;
    const rows = list.files.map(f =>
      '<div class="mprob" data-f="' + esc(f.name) + '"><b>' + esc(f.name) + '</b>' +
      '<span class="hint">' + Math.round(f.size / 1024) + " KB</span></div>").join("") ||
      '<div class="mprob"><span class="hint">results/ 下还没有 json 文件，可先「新建骨架」</span></div>';
    openModal(
      '<h3>加载结果 JSON</h3><div class="hint">只列出 results/ 目录下的 json；加载后所有编辑只在内存中。</div>' +
      '<div class="mprobs">' + rows + '</div>' +
      '<div class="mfoot"><span class="sp"></span><button data-act="cancel">取消</button></div>',
      card => {
        card.querySelector('[data-act=cancel]').onclick = closeModal;
        card.querySelectorAll(".mprob[data-f]").forEach(el => {
          el.onclick = async () => {
            const name = el.dataset.f;
            closeModal();
            if (!resGuard("加载其他文件")) return;
            try {
              const j = await api("/api/results/load", {file: name});
              let doc;
              try { doc = JSON.parse(j.text); }
              catch (e) { doc = null; }
              if (doc === null) {
                RES.doc = null; RES.file = j.file; RES.eol = j.eol;
                RES.expect = j.digest ? {digest: j.digest, mtime_ns: j.mtime_ns, size: j.size} : null;
                RES.src = j.text; RES.view = "src"; RES.shape = "notobject"; RES.srcParsed = false; RES.srcErr = j.error || "解析失败";
                RES.base = j.text; RES.dirty = false;
                renderResults();
                toast("文件不是合法 JSON，已用源码视图打开，可修正后保存", true);
                return;
              }
              resSet(doc, j);
              renderResults();
              toast("已载入 results/" + j.file + "（" + (j.eol === "crlf" ? "CRLF" : "LF") + "）");
              if (RES.shape !== "ok") toast("该文件不是结果 JSON（缺 tags/operators），已切到源码视图", true);
            } catch (e) { toast(e.message, true); }
          };
        });
      });
  } catch (e) { toast(e.message, true); }
}

// ---- 渲染

function renderResBar() {
  const f = document.getElementById("resfile");
  if (f) f.textContent = RES.file ? "results/" + RES.file : (RES.doc ? "未命名（内存）" : "未载入");
  const dot = document.getElementById("resdot");
  if (dot) dot.classList.toggle("on", !!RES.dirty);
  const st = document.getElementById("resstats");
  if (st) {
    if (RES.shape === "ok" && RES.doc) {
      const members = RES.doc.tags.reduce((a, t) => a + ((t.members || []).length), 0);
      st.textContent = "operators " + RES.doc.operators.length + " · tags " + RES.doc.tags.length + " · 关系 " + members;
    } else st.textContent = RES.doc ? "非结果 JSON（只读浏览，可改源码）" : "";
  }
}
function renderResEmpty() {
  document.getElementById("resbody").hidden = false;
  document.getElementById("resrc").hidden = true;
  let draft = null;
  try { draft = JSON.parse(localStorage.getItem("res.v1") || "null"); } catch (e) {}
  const banner = draft
    ? '<div class="warnbar">发现未保存的浏览器草稿（' + esc(draft.file || "未命名") + " · " +
      new Date(draft.savedAt || Date.now()).toLocaleString() + "）<br>" +
      "<button id='btdraft'>恢复草稿</button> <button id='btdrop'>丢弃</button></div>"
    : "";
  document.getElementById("rtags").innerHTML = banner + "<div class='split'>尚未载入任何 JSON。</div>";
  document.getElementById("rmembers").innerHTML = "";
  document.getElementById("rpanel").innerHTML = "<div class='guide'>点上方「加载…」选择 results/ 下的 json，或「新建骨架」开始一份符合 <code>docs/output-standard.md</code> 的空文档。<br>所有编辑只发生在内存里，点「保存…」才会写盘（可覆盖已有文件，也可另存为新名字）。</div>";
  const btd = document.getElementById("btdraft");
  if (btd) btd.onclick = () => {
    RES.doc = null;
    try { RES.doc = JSON.parse(draft.text); } catch (e) { return toast("草稿不是合法 JSON，无法恢复", true); }
    RES.file = draft.file || null;
    RES.eol = draft.eol || "crlf";
    RES.expect = null;
    RES.base = "";
    RES.dirty = true;
    RES.shape = resShape(RES.doc);
    RES.view = RES.shape === "ok" ? "card" : "src";
    RES.src = draft.text;
    RES.sel = {tag: RES.shape === "ok" && RES.doc.tags.length ? 0 : -1, mi: -1, op: 0};
    renderResults();
    toast("已恢复草稿（注意：它可能比磁盘上的文件旧）");
  };
  const btx = document.getElementById("btdrop");
  if (btx) btx.onclick = () => { localStorage.removeItem("res.v1"); renderResEmpty(); };
  renderResBar();
}
function renderResults() {
  if (!RES.doc && !RES.file) return renderResEmpty();
  document.getElementById("btview").textContent = RES.view === "src" ? "结构化视图" : "源码视图";
  document.getElementById("resbody").hidden = RES.view === "src";
  document.getElementById("resrc").hidden = RES.view !== "src";
  document.getElementById("btmode").hidden = RES.view === "src" || RES.shape !== "ok";
  document.getElementById("btmode").textContent = RES.mode === "tag" ? "按干员" : "按 TAG";
  renderResBar();
  if (RES.view === "src") { renderResSrc(); return; }
  if (RES.shape !== "ok") { renderResForeign(); return; }  // 非结果 JSON：只读摘要，可切源码视图
  renderResLeft(); renderResMem(); renderResPanel();
}
function renderResForeign() {
  const keys = RES.doc && typeof RES.doc === "object" ? Object.keys(RES.doc).slice(0, 12) : [];
  document.getElementById("rtags").innerHTML =
    "<div class='warnbar'>该文件不是结果 JSON（缺 <code>tags</code> / <code>operators</code>），结构化编辑已停用。</div>" +
    "<div class='split'>顶层键：" + esc(keys.join("、") || "（无）") + "</div>" +
    "<button id='btgosrc'>到源码视图</button>";
  document.getElementById("rmembers").innerHTML = "";
  document.getElementById("rpanel").innerHTML = "<div class='guide'>可以点「新建骨架」开始一份符合规范的空文档，或用源码视图只读查看此文件。</div>";
  const b = document.getElementById("btgosrc");
  if (b) b.onclick = () => switchView("src");
}
function renderResSrc() {
  document.getElementById("rstext").value = RES.src;
  renderResSrcErr();
}
function renderResSrcErr() {
  const el = document.getElementById("rserr");
  el.textContent = RES.srcParsed ? "" : "JSON 解析失败：" + RES.srcErr;
}
function renderResLeft() {
  const box = document.getElementById("rtags");
  box.innerHTML = "";
  const search = document.getElementById("rtsearch");
  if (RES.mode === "op") {
    search.placeholder = "搜索干员…";
    const q = RES.q.o;
    const all = RES.doc.operators;
    const items = all.map((o, i) => ({o, i})).filter(x => matches(String(x.o.name || ""), q));
    document.getElementById("rtcnt").textContent = items.length + " / " + all.length;
    const per = 80, pages = Math.max(1, Math.ceil(items.length / per));
    RES.opage = Math.min(Math.max(1, RES.opage), pages);
    const slice = items.slice((RES.opage - 1) * per, RES.opage * per);
    slice.forEach(x => box.appendChild(opLine(x.i, x.o)));
    if (pages > 1) {
      const d = document.createElement("div");
      d.className = "split";
      d.textContent = "第 " + RES.opage + " / " + pages + " 页";
      box.appendChild(d);
      const nav = document.createElement("div");
      nav.style.cssText = "display:flex;gap:6px;padding:0 2px";
      nav.append(miniBtn("上一页", "", () => { RES.opage--; renderResLeft(); }, RES.opage <= 1),
                 miniBtn("下一页", "", () => { RES.opage++; renderResLeft(); }, RES.opage >= pages));
      box.appendChild(nav);
    }
    const addOp = document.createElement("div");
    addOp.style.cssText = "padding:8px 2px";
    addOp.appendChild(miniBtn("＋ 新增干员条目", "从全量干员表挑一个，字段自动带出", addOperatorDialog));
    box.appendChild(addOp);
    return;
  }
  search.placeholder = "搜索 TAG / id…";
  const q = RES.q.t;
  const tags = RES.doc.tags;
  const hit = tags.map((t, i) => ({t, i})).filter(x =>
    !q || String(x.t.name || "").toLowerCase().includes(q) || String(x.t.id || "").toLowerCase().includes(q));
  document.getElementById("rtcnt").textContent = hit.length + " / " + tags.length;
  let lastSrc = null;
  for (const x of hit) {
    if (x.t.source !== lastSrc) {
      lastSrc = x.t.source;
      const h = document.createElement("div");
      h.className = "rsec";
      h.textContent = x.t.source === "official" ? "官方设定 TAG" : (x.t.source === "player" ? "玩家体感 TAG" : String(x.t.source || "未知 source"));
      box.appendChild(h);
    }
    const el = document.createElement("div");
    el.className = "tagline" + (RES.sel.tag === x.i ? " on" : "");
    el.innerHTML = '<span class="dotid">' + esc(x.t.id || "—") + '</span><span>' + esc(x.t.name || "（无名）") +
      '</span><span class="n">' + ((x.t.members || []).length) + "</span>";
    el.onclick = () => { RES.sel.tag = x.i; RES.sel.mi = -1; renderResMem(); renderResPanel(); renderResLeft(); };
    box.appendChild(el);
  }
}
function opLine(i, o) {
  const el = document.createElement("div");
  el.className = "tagline" + (RES.sel.op === i ? " on" : "");
  el.innerHTML = "<span>" + esc(o.name || "（无名）") + "</span>" +
    '<span class="n">' + esc([o.rarity ? o.rarity + "★" : "", o.class || ""].filter(Boolean).join(" · ")) + "</span>";
  el.onclick = () => { RES.sel.op = i; renderResMem(); renderResPanel(); renderResLeft(); };
  return el;
}
function renderResMem() {
  const box = document.getElementById("rmembers");
  box.innerHTML = "";
  if (RES.mode === "op") return renderResRefs(box);
  const t = resTag();
  if (!t) { box.innerHTML = "<div class='split'>左侧选一个 TAG。</div>"; document.getElementById("rmcnt").textContent = ""; return; }
  const q = RES.q.m;
  const members = t.members || [];
  const items = members.map((m, j) => ({m, j})).filter(x => matches(String(x.m.operator || ""), q));
  document.getElementById("rmcnt").textContent = items.length + " / " + members.length + " 人";
  const head = document.createElement("div");
  head.className = "split";
  head.innerHTML = esc(t.name || "") + " · <span class='dotid'>" + esc(t.id || "") + "</span>";
  box.appendChild(head);
  for (const x of items) {
    const el = document.createElement("div");
    el.className = "card" + (RES.sel.mi === x.j ? " open" : "");
    el.innerHTML = '<span class="rank"></span><span class="name">' + esc(x.m.operator || "（缺 operator）") + "</span>" +
      '<span class="chips">' + (x.m.condition ? '<span class="chip">' + esc(String(x.m.condition).slice(0, 40)) + "</span>" : '<span class="chip todo">条件待填</span>') +
      ((x.m.subTags || []).length ? '<span class="chip">' + (x.m.subTags || []).length + " 个子 TAG</span>" : "") + "</span>";
    el.onclick = () => { RES.sel.mi = RES.sel.mi === x.j ? -1 : x.j; renderResMem(); renderResPanel(); };
    box.appendChild(el);
  }
  const add = document.createElement("div");
  add.style.cssText = "padding:8px 2px";
  add.innerHTML = "<button id='btaddmem'>＋ 加成员</button>";
  box.appendChild(add);
  const btn = document.getElementById("btaddmem");
  if (btn) btn.onclick = () => addMemberDialog(RES.sel.tag);
}
function renderResRefs(box) {
  const o = RES.doc.operators[RES.sel.op];
  document.getElementById("rmcnt").textContent = "";
  if (!o) { box.innerHTML = "<div class='split'>左侧选一个干员。</div>"; return; }
  const head = document.createElement("div");
  head.className = "split";
  head.textContent = "「" + (o.name || "（无名）") + "」被以下 TAG 引用";
  box.appendChild(head);
  let n = 0;
  RES.doc.tags.forEach((t, i) => (t.members || []).forEach((m, j) => {
    if (m.operator !== o.name) return;
    n++;
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = '<span class="rank"></span><span class="name">' + esc(t.name || "") + "</span>" +
      '<span class="chips"><span class="chip">' + esc(t.id || "") + '</span><span class="chip">members[' + j + "]</span></span>";
    el.onclick = () => { RES.mode = "tag"; RES.sel.tag = i; RES.sel.mi = j; renderResults(); };
    box.appendChild(el);
  }));
  if (!n) box.innerHTML += "<div class='split'>没有任何 TAG 引用（规范要求 operators 只收录进过成员表的干员）。</div>";
}

// ---------------------------------------------------------------- 结果 JSON：编辑面板与操作

function field(el, get, set, opts) {
  el.classList.add("val");
  const paint = () => {
    const v = get() == null ? "" : String(get());
    el.textContent = v || (opts && opts.empty) || "（空）";
    el.classList.toggle("empty", !v);
  };
  paint();
  el.onclick = () => {
    const wrap = document.createElement("div");
    wrap.className = "editline";
    const inp = document.createElement(opts && opts.multi ? "textarea" : "input");
    if (!(opts && opts.multi)) inp.type = "text";
    if (opts && opts.multi) inp.rows = 2;
    inp.value = get() == null ? "" : String(get());
    const ok = document.createElement("button"); ok.textContent = "✓"; ok.title = "保存（Enter / Ctrl+Enter）";
    const no = document.createElement("button"); no.textContent = "×"; no.title = "取消（Esc）";
    wrap.append(inp, ok, no);
    el.replaceWith(wrap);
    inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
    const finish = commit => {
      wrap.replaceWith(el);
      if (commit) { set(inp.value); resMark(); renderResults(); } else paint();
    };
    ok.onclick = () => finish(true);
    no.onclick = () => finish(false);
    inp.onkeydown = e => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); }
      else if (e.key === "Enter" && (!(opts && opts.multi) || e.ctrlKey)) { e.preventDefault(); finish(true); }
    };
  };
  return el;
}
function kv(label, valueEl, note) {
  const d = document.createElement("div");
  d.className = "kv";
  d.innerHTML = "<b>" + esc(label) + "</b>";
  d.appendChild(valueEl);
  if (note) { const s = document.createElement("span"); s.className = "ro"; s.textContent = note; d.appendChild(s); }
  return d;
}
function roText(text) { const s = document.createElement("span"); s.className = "ro"; s.textContent = text; return s; }
function selectEl(value, options, onPick) {
  const sel = document.createElement("select");
  const opts = options.slice();
  if (value != null && value !== "" && !opts.includes(value)) opts.unshift(value);
  for (const o of opts) { const e = document.createElement("option"); e.value = o; e.textContent = o || "（空）"; sel.appendChild(e); }
  sel.value = value == null ? "" : value;
  sel.onchange = () => { onPick(sel.value); resMark(); renderResults(); };
  return sel;
}
function miniBtn(label, title, fn, dis) {
  const b = document.createElement("button");
  b.className = "mini"; b.textContent = label; b.title = title || ""; b.disabled = !!dis; b.onclick = fn;
  return b;
}

function renderResPanel() {
  const box = document.getElementById("rpanel");
  box.innerHTML = "";
  if (RES.mode === "op") return renderOpCard(box);
  const t = resTag();
  if (!t) { box.innerHTML = "<div class='guide'>左侧选一个 TAG。</div>"; return; }
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>TAG</h4>";
  g.appendChild(kv("id", roText(String(t.id || "—")), "规范：一经发布不得更改"));
  const nameEl = document.createElement("span");
  field(nameEl, () => t.name, v => { t.name = v; }, {});
  g.appendChild(kv("name", nameEl));
  g.appendChild(kv("source", roText(String(t.source || "—"))));
  if (t.source === "official") g.appendChild(kv("category", selectEl(t.category, RES_CATS, v => { t.category = v; })));
  else if (t.source === "player") g.appendChild(kv("recommended", roText(Array.isArray(t.recommended) ? t.recommended.length + " 人" : "（缺字段）")));
  g.appendChild(kv("members", roText(String((t.members || []).length) + " 人")));
  box.appendChild(g);

  if (t.source === "player") {
    const g2 = document.createElement("div");
    g2.className = "pgroup";
    g2.innerHTML = "<h4>荐（按展示优先级）</h4>";
    const rec = Array.isArray(t.recommended) ? t.recommended : null;
    if (!rec) g2.innerHTML += "<div class='hint'>缺 recommended 字段（点「按规范整理」可补空数组）。</div>";
    else if (!rec.length) g2.innerHTML += "<div class='hint'>暂无。</div>";
    else rec.forEach((name, k) => {
      const row = document.createElement("div");
      row.className = "subrow";
      const s = document.createElement("span"); s.style.flex = "1"; s.textContent = (k + 1) + ". " + name;
      row.appendChild(s);
      row.appendChild(miniBtn("↑", "上移", () => { rec.splice(k - 1, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === 0));
      row.appendChild(miniBtn("↓", "下移", () => { rec.splice(k + 1, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === rec.length - 1));
      row.appendChild(miniBtn("⤒", "置顶", () => { rec.splice(0, 0, rec.splice(k, 1)[0]); resMark(); renderResults(); }, k === 0));
      row.appendChild(miniBtn("×", "取消荐", () => { rec.splice(k, 1); resMark(); renderResults(); }));
      g2.appendChild(row);
    });
    const add = document.createElement("div");
    add.style.marginTop = "6px";
    add.appendChild(miniBtn("＋ 加荐", "只能从本 TAG 的成员里选", () => recAddDialog(RES.sel.tag)));
    g2.appendChild(add);
    box.appendChild(g2);
  }

  const m = resMember();
  if (!m) {
    const hint = document.createElement("div");
    hint.className = "guide";
    hint.textContent = "点中间任一成员行即可编辑它的 条件 / 备注 / 子 TAG / prtsUrl。";
    box.appendChild(hint);
    return;
  }
  box.appendChild(memberCard(t, m));
}

function memberCard(t, m) {
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>成员：" + esc(String(m.operator || "（缺 operator）")) + "</h4>";
  const condEl = document.createElement("span");
  field(condEl, () => m.condition, v => { m.condition = v; }, {multi: true, empty: "（待填）"});
  g.appendChild(kv("条件", condEl));
  const noteEl = document.createElement("span");
  field(noteEl, () => m.remark, v => { if (v.trim()) m.remark = v; else delete m.remark; }, {multi: true, empty: "（空，保存时省略该字段）"});
  g.appendChild(kv("备注", noteEl));

  const sg = document.createElement("div");
  sg.style.marginTop = "8px";
  const h = document.createElement("div");
  h.innerHTML = "<b style='font-size:12px'>子 TAG</b>";
  sg.appendChild(h);
  const subs = m.subTags || [];
  subs.forEach((s, k) => {
    const row = document.createElement("div");
    row.className = "subrow";
    const ge = document.createElement("span"); field(ge, () => s.group, v => { s.group = v; }, {empty: "组"});
    const ve = document.createElement("span"); field(ve, () => s.value, v => { s.value = v; }, {empty: "值"});
    const de = document.createElement("span"); field(de, () => s.detail, v => { if (v.trim()) s.detail = v; else delete s.detail; }, {empty: "detail"});
    row.append(ge, ve, de);
    row.appendChild(miniBtn("×", "删除该子 TAG", () => {
      subs.splice(k, 1);
      if (!subs.length) delete m.subTags;
      resMark(); renderResults();
    }));
    sg.appendChild(row);
  });
  sg.appendChild(miniBtn("＋ 子 TAG", "", () => {
    m.subTags = Array.isArray(m.subTags) ? m.subTags : [];
    m.subTags.push({group: "", value: ""});
    resMark(); renderResults();
  }));
  g.appendChild(sg);

  const urlEl = document.createElement("span");
  field(urlEl, () => m.prtsUrl, v => { m.prtsUrl = v; }, {});
  g.appendChild(kv("prtsUrl", urlEl));
  const anch = document.createElement("div");
  anch.className = "subrow";
  RES_ANCHORS.forEach(a => anch.appendChild(miniBtn(a || "无锚点", "改用该锚点", () => {
    m.prtsUrl = String(m.prtsUrl || "").split("#")[0] + a;
    resMark(); renderResults();
  })));
  anch.appendChild(miniBtn("按干员名重建", "", () => {
    const tail = String(m.prtsUrl || "").includes("#") ? "#" + String(m.prtsUrl).split("#")[1] : "";
    m.prtsUrl = rootUrl(String(m.operator || "")) + tail;
    resMark(); renderResults();
  }));
  g.appendChild(anch);

  const acts = document.createElement("div");
  acts.className = "subrow";
  acts.style.marginTop = "8px";
  const move = (label, d, dis) => miniBtn(label, "", () => {
    const arr = t.members;
    const j = RES.sel.mi;
    const nk = Math.min(Math.max(j + d, 0), arr.length - 1);
    if (nk === j) return;
    arr.splice(nk, 0, arr.splice(j, 1)[0]);
    RES.sel.mi = nk;
    resMark(); renderResults();
  }, dis);
  acts.append(move("↑ 上移", -1, RES.sel.mi <= 0), move("↓ 下移", 1, RES.sel.mi >= (t.members || []).length - 1));
  acts.appendChild(miniBtn("删除成员", "", () => {
    if (!confirm("删除「" + String(m.operator || "") + "」在「" + String(t.name || "") + "」下的这条记录？\n（只改内存，保存前不会写盘）")) return;
    t.members.splice(RES.sel.mi, 1);
    RES.sel.mi = -1;
    resMark(); renderResults();
  }));
  g.appendChild(acts);
  return g;
}

function renderOpCard(box) {
  const i = RES.sel.op;
  const o = RES.doc.operators[i];
  if (!o) { box.innerHTML = "<div class='guide'>左侧选一个干员。</div>"; return; }
  const g = document.createElement("div");
  g.className = "pgroup";
  g.innerHTML = "<h4>干员基本信息</h4>";
  const nameEl = document.createElement("span");
  field(nameEl, () => o.name, v => renameOperator(i, v), {});
  g.appendChild(kv("name", nameEl, "改名会级联更新成员与荐"));
  const rin = document.createElement("input");
  rin.type = "number"; rin.min = "1"; rin.max = "6";
  rin.value = o.rarity == null ? "" : o.rarity;
  rin.style.cssText = "width:4.5em;font:inherit;font-size:13px;padding:2px 5px;border:1px solid var(--line);border-radius:6px";
  rin.onchange = () => { const v = parseInt(rin.value, 10); if (!Number.isNaN(v)) { o.rarity = v; resMark(); renderResults(); } };
  g.appendChild(kv("rarity", rin));
  g.appendChild(kv("class", selectEl(o.class, RES_CLASSES, v => { o.class = v; })));
  for (const [label, key] of [["branch", "branch"], ["faction", "faction"], ["releaseDate", "releaseDate"], ["prtsUrl", "prtsUrl"]]) {
    const el = document.createElement("span");
    field(el, () => o[key], v => { o[key] = v; }, {});
    g.appendChild(kv(label, el));
  }
  const acts = document.createElement("div");
  acts.className = "subrow";
  acts.style.marginTop = "8px";
  acts.appendChild(miniBtn("从全量干员表补全", "", () => opFill(i)));
  acts.appendChild(miniBtn("删除条目", "", () => opDel(i)));
  g.appendChild(acts);
  box.appendChild(g);
}

function pickDialog(title, names, onPick) {
  openModal('<h3>' + esc(title) + '</h3>' +
    '<div class="mradio"><input id="mkq" type="text" placeholder="搜索干员名…" style="flex:1;font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px"></div>' +
    '<div class="mprobs" id="mklist"></div>' +
    '<div class="mfoot"><span class="sp"></span><button data-act="cancel">取消</button></div>',
    card => {
      const list = card.querySelector("#mklist");
      const inp = card.querySelector("#mkq");
      const draw = () => {
        const q = inp.value.trim().toLowerCase();
        const hit = names.filter(n => matches(n, q)).slice(0, 200);
        list.innerHTML = hit.map(n => '<div class="mprob" data-n="' + esc(n) + '">' + esc(n) + "</div>").join("") ||
          '<div class="mprob"><span class="hint">无匹配</span></div>';
        list.querySelectorAll(".mprob[data-n]").forEach(el => {
          el.onclick = () => { closeModal(); onPick(el.dataset.n); };
        });
      };
      inp.oninput = draw;
      draw();
      inp.focus();
      card.querySelector("[data-act=cancel]").onclick = closeModal;
    });
}
function addMemberDialog(ti) {
  const t = RES.doc.tags[ti];
  const names = RES.doc.operators.map(o => String(o.name || "")).filter(Boolean);
  if (!names.length) return toast("operators[] 还是空的：先到「按干员」视图新增干员条目", true);
  pickDialog("给「" + String(t.name || "") + "」加成员", names, name => {
    t.members = Array.isArray(t.members) ? t.members : [];
    t.members.push({operator: name, condition: "", prtsUrl: rootUrl(name)});
    RES.sel.mi = t.members.length - 1;
    resMark(); renderResults();
    toast("已加成员（条件留空，保存前请补上）");
  });
}
function recAddDialog(ti) {
  const t = RES.doc.tags[ti];
  const rec = Array.isArray(t.recommended) ? t.recommended : [];
  const names = (t.members || []).map(m => String(m.operator || "")).filter(n => n && !rec.includes(n));
  pickDialog("给「" + String(t.name || "") + "」加荐", names, name => {
    t.recommended = Array.isArray(t.recommended) ? t.recommended : [];
    t.recommended.push(name);
    resMark(); renderResults();
  });
}
function addOperatorDialog() {
  const names = (DATA.roster || []).map(p => p.name);
  pickDialog("新增干员条目", names, name => {
    const p = (DATA.roster || []).find(x => x.name === name) || {};
    RES.doc.operators.push({name, rarity: p.star || 1, class: p.cls || "", branch: p.branch || "",
      faction: p.faction || "", releaseDate: p.date || "", prtsUrl: p.url || rootUrl(name)});
    RES.sel.op = RES.doc.operators.length - 1;
    RES.opage = Math.ceil(RES.doc.operators.length / 80);
    resMark(); renderResults();
  });
}
function opFill(i) {
  const o = RES.doc.operators[i];
  const p = (DATA.roster || []).find(x => x.name === o.name);
  if (!p) return toast("全量干员表里没有「" + String(o.name || "") + "」", true);
  o.rarity = p.star || o.rarity;
  o.class = p.cls || o.class;
  o.branch = p.branch || o.branch;
  o.faction = p.faction || "";
  o.releaseDate = p.date || o.releaseDate;
  o.prtsUrl = p.url || rootUrl(String(o.name || ""));
  resMark(); renderResults();
  toast("已按全量干员表补全");
}
function opDel(i) {
  const o = RES.doc.operators[i];
  let refs = 0;
  RES.doc.tags.forEach(t => (t.members || []).forEach(m => { if (m.operator === o.name) refs++; }));
  if (!confirm("删除干员条目「" + String(o.name || "") + "」？" + (refs ? "仍有 " + refs + " 处成员引用，删除会产生悬空引用（校验会报错）。" : "（当前无引用）"))) return;
  RES.doc.operators.splice(i, 1);
  RES.sel.op = Math.min(i, RES.doc.operators.length - 1);
  resMark(); renderResults();
}
function renameOperator(i, value) {
  const o = RES.doc.operators[i];
  const old = String(o.name || "");
  const next = String(value || "").trim();
  if (!next || next === old) return;
  let n = 0;
  RES.doc.tags.forEach(t => {
    (t.members || []).forEach(m => { if (m.operator === old) { m.operator = next; n++; } });
    if (Array.isArray(t.recommended)) t.recommended = t.recommended.map(x => (x === old ? next : x));
  });
  o.name = next;
  resMark(); renderResults();
  toast("已改名（级联 " + n + " 处成员引用）");
}

// ---- 文档级整理 / 校验

function resSortAll() {
  const doc = RES.doc;
  const rank = t => (t.source === "official" ? 0 : 1) * 10000 +
    (t.source === "official" ? Math.max(0, RES_CATS.indexOf(t.category)) : (parseInt(String(t.id || "").replace(/\D/g, ""), 10) || 99));
  const ordered = doc.tags.map((t, i) => ({t, i})).sort((a, b) => rank(a.t) - rank(b.t));
  const tagOrder = ordered.filter((x, k) => x.i !== k).length;
  const opsSorted = doc.operators.slice().sort((a, b) => String(b.releaseDate || "").localeCompare(String(a.releaseDate || "")));
  const opOrder = opsSorted.filter((o, k) => doc.operators[k] !== o).length;
  let emptyRemark = 0, emptySub = 0, missingRec = 0;
  doc.tags.forEach(t => {
    (t.members || []).forEach(m => {
      if ("remark" in m && !String(m.remark || "").trim()) emptyRemark++;
      if ("subTags" in m && (!Array.isArray(m.subTags) || !m.subTags.length)) emptySub++;
    });
    if (t.source === "player" && !Array.isArray(t.recommended)) missingRec++;
  });
  const total = tagOrder + opOrder + emptyRemark + emptySub + missingRec;
  if (!total) return toast("已经符合规范，无需整理");
  if (!confirm("将调整：TAG 顺序 " + tagOrder + " 处、干员顺序 " + opOrder + " 处、删除空备注 " + emptyRemark +
      " 处、删除空子 TAG " + emptySub + " 处、补 recommended " + missingRec + " 处。\n（只改内存，保存前不写盘；阵容组合 P12 的成员顺序不动）继续？")) return;
  const keepId = resTag() ? resTag().id : null;
  doc.tags = ordered.map(x => x.t);
  doc.operators = opsSorted;
  doc.tags.forEach(t => {
    (t.members || []).forEach(m => {
      if ("remark" in m && !String(m.remark || "").trim()) delete m.remark;
      if ("subTags" in m && (!Array.isArray(m.subTags) || !m.subTags.length)) delete m.subTags;
    });
    if (t.source === "player" && !Array.isArray(t.recommended)) t.recommended = [];
  });
  RES.sel.tag = keepId ? Math.max(0, doc.tags.findIndex(t => t.id === keepId)) : 0;
  RES.sel.mi = -1;
  resMark(); renderResults();
  toast("已按规范整理（共 " + total + " 处）");
}
async function resDoCheck() {
  const text = curText();
  try {
    const j = await api("/api/results/check", {text});
    RES.problems = j.problems;
    RES.stats = j.stats;
    const errs = j.problems.filter(p => p.level === "error").length;
    if (!j.parsed) toast("JSON 解析失败：" + j.problems[0].message, true);
    else toast("校验：" + errs + " 个错误 / " + (j.problems.length - errs) + " 个提醒", errs > 0);
    return j;
  } catch (e) { toast(e.message, true); return null; }
}
function problemsHtml(problems, limit) {
  if (!problems) return '<div class="mprob"><span class="hint">正在校验…</span></div>';
  if (!problems.length) return '<div class="mprob"><span class="lv" style="color:var(--ok)">通过</span><span>没有发现问题</span></div>';
  const show = problems.slice(0, limit || 8);
  return show.map((p, k) => '<div class="mprob ' + esc(p.level) + '" data-k="' + k + '"><span class="lv">' +
      (p.level === "error" ? "错误" : "提醒") + "</span><span>" + esc(p.label ? p.label + " — " : "") + esc(p.message) +
      '</span><span class="pth">' + esc(p.path || "") + "</span></div>").join("") +
    (problems.length > show.length ? '<div class="mprob"><span class="hint">另有 ' + (problems.length - show.length) + " 条未列出</span></div>" : "");
}
function jumpTo(loc) {
  if (!Array.isArray(loc) || !loc.length || RES.shape !== "ok") return;
  if (loc[0] === "tags" && typeof loc[1] === "number") {
    RES.mode = "tag";
    RES.view = "card";
    RES.sel.tag = loc[1];
    RES.sel.mi = (loc[2] === "members" && typeof loc[3] === "number") ? loc[3] : -1;
  } else if (loc[0] === "operators" && typeof loc[1] === "number") {
    RES.mode = "op";
    RES.view = "card";
    RES.sel.op = loc[1];
    RES.opage = Math.floor(loc[1] / 80) + 1;
  } else return;
  renderResults();
  const el = document.querySelector("#rmembers .card.open") || document.querySelector("#rmembers .card") ||
    document.querySelector("#rtags .tagline.on");
  if (el) el.scrollIntoView({block: "center"});
}

// ---- 保存

function resContentChanged() {
  try {
    const b = JSON.parse(RES.base || "null");
    if (!b || !RES.doc) return true;
    const strip = d => serialize({operators: d.operators, tags: d.tags});
    return strip(RES.doc) !== strip(b);
  } catch (e) { return true; }
}
function resNextVersion(v) {
  const m = /^v([1-9]\d*)$/.exec(String(v || ""));
  return m ? "v" + (Number(m[1]) + 1) : null;
}
async function resSaveDialog() {
  if (!RES.doc && RES.src) {  // 载入时就是坏 JSON 的文件：先在源码视图里修好，再允许保存
    try { RES.doc = JSON.parse(RES.src); RES.shape = resShape(RES.doc); } catch (e) {}
  }
  if (!RES.doc) return toast("先载入或新建一个 JSON", true);
  if (RES.view === "src" && !resEnsure()) return toast("源码不是合法 JSON，先修正：" + RES.srcErr, true);
  RES.dirty = resDirtyNow();
  const changed = resContentChanged();
  const next = resNextVersion(RES.doc.version);
  let list = RES.list;
  try { list = await api("/api/results/list", {}); RES.list = list; RES.today = list.today; } catch (e) { toast(e.message, true); }
  const today = (list && list.today) || new Date().toISOString().slice(0, 10);
  const files = ((list && list.files) || []).map(f => f.name);
  const target = RES.file && files.includes(RES.file) ? RES.file
    : (files.includes("operator-tags.json") ? "operator-tags.json" : (files[0] || ""));
  const hasCurrent = !!(RES.file && files.includes(RES.file));  // 没载入过文件时默认「新建」，避免误覆盖别的产物
  const html =
    "<h3>保存结果 JSON</h3>" +
    '<div class="mhint">所有编辑都只在内存中，这一步才写盘。</div>' +
    '<div class="mradio"><label><input type="radio" name="mtarget" value="overwrite"' + (hasCurrent ? " checked" : " disabled") + "> 覆盖已有文件</label>" +
    '<select id="mfile"' + (hasCurrent ? "" : " disabled") + ">" + files.map(f => "<option" + (f === target ? " selected" : "") + ">" + esc(f) + "</option>").join("") + "</select>" +
    (files.length ? "" : '<span class="hint">（results/ 下暂无 json）</span>') + "</div>" +
    '<div class="mradio"><label><input type="radio" name="mtarget" value="new"' + (hasCurrent ? "" : " checked") + "> 新建文件</label>" +
    '<input id="mnew" type="text" value="' + esc(RES.file || "operator-tags.json") + '" style="flex:1;min-width:12em"></div>' +
    '<div id="mcross" class="mhint err" hidden></div>' +
    '<div class="mradio"><label><input type="checkbox" id="mbump"' + (changed && next ? " checked" : "") + (changed && next ? "" : " disabled") + "> 内容有变时更新 version / updated</label>" +
    'version <input id="mver" type="text" style="width:5em" value="' + esc(next || RES.doc.version || "") + '">' +
    'updated <input id="mupd" type="date" value="' + esc(today) + '"></div>' +
    '<div class="mhint" id="mchg">' + (changed ? "内容有变化。" : "内容无变化，版本字段不变。") +
    (changed && !next ? "version 无法识别（规范：v1、v2…），请手动填写。" : "") + "</div>" +
    '<div class="mprobs" id="mprob">' + problemsHtml(RES.problems) + "</div>" +
    '<div class="mfoot"><label class="mhint"><input type="checkbox" id="mforce"> 强制覆盖（忽略外部改动）</label><span class="sp"></span>' +
    '<button data-act="cancel">取消</button><button class="primary" data-act="save" id="mok">保存</button></div>' +
    '<div class="mhint">Enter 保存 · Esc 关闭 · Ctrl+Enter 任意处保存</div>';
  openModal(html, card => bindSaveDialog(card, {files}));
  const j = await resDoCheck();
  const box = document.querySelector("#mprob");
  if (box && j) {
    box.innerHTML = problemsHtml(j.problems);
    bindProblemClicks(box, j.problems);
    const errs = j.problems.filter(p => p.level === "error").length;
    const ok = document.querySelector("#mok");
    if (ok && j.parsed && errs) ok.textContent = "仍有 " + errs + " 个问题，仍然保存";
    if (ok && !j.parsed) { ok.disabled = true; ok.textContent = "JSON 解析失败，无法保存"; }
  }
}
function bindProblemClicks(box, problems) {
  box.querySelectorAll(".mprob[data-k]").forEach(el => {
    el.onclick = () => {
      const p = problems[+el.dataset.k];
      if (!p) return;
      closeModal();
      jumpTo(p.loc);
    };
  });
}
function bindSaveDialog(card, ctx) {
  const radio = () => card.querySelector('input[name=mtarget]:checked').value;
  const sync = () => {
    const mode = radio();
    card.querySelector("#mfile").disabled = mode !== "overwrite";
    card.querySelector("#mnew").disabled = mode !== "new";
    const cross = mode === "overwrite" && card.querySelector("#mfile").value !== RES.file;
    const w = card.querySelector("#mcross");
    w.hidden = !cross;
    w.innerHTML = cross ? ("目标文件与当前载入的文件不同（当前：" + esc(RES.file || "未命名内存文档") +
      "），它的内容将被完全替换（可用 git 恢复）。" +
      '<label class="mhint"><input type="checkbox" id="mconfirm"> 我确认覆盖其他文件</label>') : "";
    if (cross) {
      const c = card.querySelector("#mconfirm");
      c.onchange = sync;
    }
    const crossOk = !cross || (card.querySelector("#mconfirm") && card.querySelector("#mconfirm").checked);
    card.querySelector("#mok").disabled = !crossOk;
    const exists = ctx.files.includes(card.querySelector("#mnew").value.trim());
    const nh = card.querySelector("#mnew");
    nh.classList.toggle("dirty", exists);
    nh.title = exists ? "已存在同名文件（请改用覆盖）" : "";
  };
  card.querySelectorAll('input[name=mtarget]').forEach(r => { r.onchange = sync; });
  card.querySelector("#mfile").onchange = sync;
  card.querySelector("#mnew").oninput = sync;
  card.querySelector("[data-act=cancel]").onclick = closeModal;
  card.querySelector("[data-act=save]").onclick = () => resDoSave(card);
  sync();
}
async function resDoSave(card) {
  const mode = card.querySelector('input[name=mtarget]:checked').value;
  const file = (mode === "overwrite" ? card.querySelector("#mfile").value : card.querySelector("#mnew").value).trim();
  const bumpBox = card.querySelector("#mbump");
  const bump = bumpBox.checked && !bumpBox.disabled;
  const ver = card.querySelector("#mver").value.trim();
  const upd = card.querySelector("#mupd").value.trim();
  const force = card.querySelector("#mforce").checked;
  const out = {...RES.doc};
  if (bump) {
    if (ver) out.version = ver;
    if (upd) out.updated = upd;
  }
  try {
    const j = await api("/api/results/save", {
      mode, file, text: serialize(out), eol: RES.eol,
      expect: mode === "overwrite" ? RES.expect : null, force,
    });
    RES.doc = out;
    RES.base = j.saved.text;
    RES.file = j.file;
    RES.expect = {digest: j.digest, mtime_ns: j.mtime_ns, size: j.size};
    RES.dirty = false;
    RES.problems = j.problems;
    RES.stats = j.stats;
    RES.shape = resShape(RES.doc);
    RES.src = serialize(RES.doc);
    localStorage.removeItem("res.v1");
    closeModal();
    renderResults();
    toast("已保存 results/" + j.file + (j.created ? "（新建）" : "（覆盖）") + " · " + Math.round(j.bytes / 1024) + " KB");
  } catch (e) {
    if (e.code === "drift") toast("文件已被外部改动：可勾「强制覆盖」再保存，或重新载入", true);
    else toast(e.message, true);
  }
}

// ---- 模态框

function openModal(html, onMount) {
  const m = document.getElementById("modal");
  const card = m.querySelector(".modal-card");
  card.innerHTML = html;
  m.hidden = false;
  if (onMount) onMount(card);
  return card;
}
function closeModal() {
  const m = document.getElementById("modal");
  if (m.hidden) return false;
  m.hidden = true;
  m.querySelector(".modal-card").innerHTML = "";
  return true;
}

// ---------------------------------------------------------------- 页签 / 跳转

function renderAll() {
  renderTags(); renderOps(); renderRec();
  renderInd(); renderIndList(); renderPicker();
}
function setTab(t) {
  ST.tab = t;
  document.getElementById("page-zhen").hidden = t !== "zhen";
  document.getElementById("page-induce").hidden = t !== "induce";
  document.getElementById("page-json").hidden = t !== "results";
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  for (const id of ("automergewrap,btmerge,btreload").split(",")) {
    const el = document.getElementById(id);
    if (el) el.hidden = t === "results";  // 这三个是前两页的控件
  }
  document.getElementById("hint").textContent = t === "zhen"
    ? "左键 = 加荐 · 右键 = 取消荐"
    : t === "induce"
      ? "选中目标子表后点临时区干员并入 · 干员行右键 = 扩展 / 移动 / 移除 · 卡片里点击条件或备注即可编辑"
      : "编辑只在内存中，点「保存…」才写盘（可覆盖已有文件，也可另存新名字）";
  if (t === "results") renderResults();
}
function gotoInduce(op, tagName) {
  if (tagName && tagName !== "__all__") {
    const t = tagOf(tagName);
    if (t) {
      ST.ind.browse = "p:" + t.name;
      ST.ind.browseOpen["p:" + t.name] = true;
      ST.ind.targets = [];
    }
  }
  ST.ind.openOp = op;
  setTab("induce");
  renderInd(); renderIndList();
  location.hash = "tab=induce&op=" + encodeURIComponent(op);
}

// ---------------------------------------------------------------- 启动

document.querySelectorAll(".tab").forEach(b => {
  b.onclick = () => {
    if (b.dataset.tab === ST.tab) return;
    if (ST.tab === "results" && !resGuard("切换页签")) return;
    setTab(b.dataset.tab);
  };
});
bindSearch("rtsearch", () => (RES.mode === "op" ? RES.q.o : RES.q.t),
  v => { if (RES.mode === "op") RES.q.o = v; else RES.q.t = v; }, renderResLeft);
bindSearch("rsearch", () => RES.q.m, v => RES.q.m = v, renderResMem);
document.getElementById("rstext").addEventListener("input", e => {
  RES.src = e.target.value;
  RES.srcParsed = true; RES.srcErr = "";
  RES.dirty = true;
  resDraft(); renderResBar(); renderResSrcErr();
});
document.getElementById("btload").onclick = () => { if (resGuard("加载其他文件")) resLoadDialog(); };
document.getElementById("btnew").onclick = () => {
  if (!resGuard("新建骨架")) return;
  resSet(resSkeleton(), {file: null, eol: "crlf"});
  renderResults();
  toast("已新建规范骨架（未命名，保存时选文件名）");
};
document.getElementById("btsort").onclick = () => {
  if (!RES.doc || RES.shape !== "ok") return toast("先载入结果 JSON", true);
  resSortAll();
};
document.getElementById("btcheck").onclick = () => resDoCheck();
document.getElementById("btview").onclick = () => { if (RES.doc) switchView(RES.view === "src" ? "card" : "src"); };
document.getElementById("btback").onclick = () => switchView("card");
document.getElementById("btformat").onclick = () => {
  try {
    RES.src = serialize(JSON.parse(document.getElementById("rstext").value));
    RES.srcParsed = true; RES.srcErr = "";
    renderResSrc();
    toast("已格式化");
  } catch (e) { toast("解析失败：" + e.message, true); }
};
document.getElementById("btmode").onclick = () => {
  RES.mode = RES.mode === "tag" ? "op" : "tag";
  RES.sel.mi = -1;
  renderResults();
};
document.getElementById("btsave").onclick = () => resSaveDialog();
document.getElementById("modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => {
  const m = document.getElementById("modal");
  if (m.hidden || e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
  const ok = m.querySelector("#mok");
  if (ok && !ok.disabled) ok.click();
});
window.addEventListener("beforeunload", e => {
  if (RES.doc && (RES.dirty || resDirtyNow())) { e.preventDefault(); e.returnValue = ""; return ""; }
});
bindSearch("search", () => ST.zhen.q, v => ST.zhen.q = v, renderOps);
bindSearch("isearch", () => ST.ind.q, v => ST.ind.q = v, renderIndList);
bindSearch("psearch", () => ST.ind.pq, v => ST.ind.pq = v, renderPicker);
bindSearch("tsearch", () => ST.ind.tq, v => ST.ind.tq = v, renderTree);
document.getElementById("btclear").onclick = () => {
  if (!ST.ind.stage.length) return;
  if (!confirm("清空临时区？（不会改动任何文件）")) return;
  ST.ind.stage = []; stageSave(); renderStage(); renderPicker();
};
document.getElementById("btreload").onclick = () => load(true).then(() => status("数据已刷新", "ok")).catch(e => toast(e.message, true));
document.getElementById("btmerge").onclick = async () => {
  status("正在重新生成…");
  try {
    const j = await api("/api/merge", {which: "both"});
    status(j.ok ? "名单文档已重新生成" : "重新生成失败", j.ok ? "ok" : "err");
    for (const [k, v] of Object.entries(j)) {
      if (k === "ok") continue;
      if (!v.ok) toast(k + " 重新生成失败：" + (v.err || v.out || ""), true);
    }
    if (j.ok) toast("docs/player-tags-members.md 与 docs/official-tags-members.md 已更新");
  } catch (e) { status("重新生成失败", "err"); toast(e.message, true); }
};
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (closeModal()) return;  // 模态框优先
  closeMenu();
  if (location.hash) history.replaceState(null, "", location.pathname);
  ST.ind.openOp = null;
  renderIndList();
});
document.addEventListener("click", e => { if (!e.target.closest(".menu")) closeMenu(); });
window.addEventListener("scroll", closeMenu, true);

(async function boot() {
  setTab("zhen");
  await load(false);
  try {
    const saved = JSON.parse(localStorage.getItem("induct.v1") || "null");
    if (saved) {
      ST.ind.targets = (saved.targets || []).filter(t => { const b = blockById(t.id); return b && b.sig === t.sig; });
      ST.ind.stage = (saved.stage || []).filter(s => s.op);
      markStageStale();
      renderInd(); renderIndList(); renderPicker();
    }
  } catch (e) {}
  const m = location.hash.match(/op=([^&]+)/);
  if (m) {
    const op = decodeURIComponent(m[1]);
    ST.ind.openOp = op;
    ST.ind.browse = ST.ind.browse || null;
    setTab("induce");
    renderInd(); renderIndList();
  }
})().catch(e => toast("加载失败：" + e.message, true));

# -*- coding: utf-8 -*-
"""PRTS 语料 → 机读属性层（`agent_workspace/tag_pipeline/stats.json`）。

解决的是「面板靠人读 PRTS 手抄」这一类系统性错误：把属性表、潜能表、模组各档固定属性
抽成结构化数据，面板由代码算（`panel_of()`），产物文本里的 `面板NNN` 再由
`tools/verify_numbers.py` 回头校准。

数据源与版式（三节都在 `material_datas/PRTS/<干员>/<干员>.md`）：

- `## 属性`：`|  | 精英0 1级 | 精英0 满级 | 精英1 满级 | 精英2 满级 | 信赖加成上限 |`，取 `| 攻击 | … |` 行。
- `## 潜能提升`：表头 `| 潜能2 | 潜能3 | 潜能4 | 潜能5 | 潜能6 |`，数据行逐列给效果。
- `## 模组`：`### 模组名` 分块，块内 `**<代号>**` 标代号、`**模组等级N**` 分档，档位块首行即固定属性
  （**多字段连写**，如 `攻击 +55防御 +45攻击速度 +7`，按内容切分——`docs/calc-rules.md` §3.2）。

用法：
    python -X utf8 tools/prts_stats.py            # 写 stats.json
    python -X utf8 tools/prts_stats.py --check    # 只报覆盖率与异常，不写盘
    python -X utf8 tools/prts_stats.py --panel 逻各斯 --stage e2 --pot 5 --module Δ --tier 3
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRTS = ROOT / "material_datas" / "PRTS"
OUT = ROOT / "agent_workspace" / "tag_pipeline" / "stats.json"

STAGE_LABEL = {"e0_1": "精英0 1级", "e0": "精英0 满级", "e1": "精英1 满级", "e2": "精英2 满级"}
STAGE_ORDER = ["e0_1", "e0", "e1", "e2"]
# 长词在前：`攻击速度` 必须先于 `攻击` 命中
ATTR_RE = re.compile(r"(法术抗性|攻击速度|部署费用|再部署|阻挡数|生命|攻击|防御) ([+\-]\d+)")
TIER_RE = re.compile(r"^\*\*模组等级([123])\*\*$")
CODE_RE = re.compile(r"^\*\*([A-Za-z][\w]*(?:-[A-Za-z0-9αβΔ]+)?)\*\*$")
POT_ATK_RE = re.compile(r"攻击力([+\-]\d+)")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def section(lines: list[str], title: str) -> list[str]:
    """取 `## <title>` 到下一个二级标题之间的行。"""
    for i, line in enumerate(lines):
        if line.strip() == f"## {title}":
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            return lines[i + 1:j]
    return []


def parse_attributes(seg: list[str]) -> tuple[dict, int]:
    """属性表 → ({阶段: 攻击}, 信赖加成上限)。表头定位列，不硬编码下标。"""
    header: list[str] = []
    atk: dict[str, int] = {}
    trust = 0
    for line in seg:
        if not line.startswith("|"):
            continue
        cs = cells(line)
        if "精英2 满级" in cs:
            header = cs
            continue
        if not header or not cs or cs[0] != "攻击":
            continue
        for stage, label in STAGE_LABEL.items():
            if label not in header:
                continue
            idx = header.index(label)
            raw = cs[idx] if idx < len(cs) else ""
            if re.fullmatch(r"\d+", raw):
                atk[stage] = int(raw)
        if "信赖加成上限" in header:
            idx = header.index("信赖加成上限")
            raw = cs[idx] if idx < len(cs) else ""
            trust = int(raw) if re.fullmatch(r"\d+", raw) else 0
    return atk, trust


def parse_potential(seg: list[str]) -> dict[str, str]:
    """潜能表 → {潜能等级: 效果原文}。"""
    header: list[str] = []
    for line in seg:
        if not line.startswith("|"):
            continue
        cs = cells(line)
        if re.fullmatch(r"潜能[2-6]", cs[0]) if cs else False:
            header = cs
            continue
        if not header or set("".join(cs)) <= set("-: ") or len(cs) != len(header):
            continue
        return {re.sub(r"\D", "", hdr): val for hdr, val in zip(header, cs) if val}
    return {}


def parse_modules(seg: list[str]) -> list[dict]:
    """模组段 → [{code, line, name, tiers:[{n, attrs, atk}]}]；基础证章（ORIGINAL，无档位）不入表。"""
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in seg:
        if line.startswith("### "):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append(cur)

    modules: list[dict] = []
    for block in blocks:
        # 块结构：### 名 → **代号** → **名** → **模组等级N** …（证章块无档位）
        code, name = "", ""
        for line in block[:5]:
            m = CODE_RE.match(line.strip())
            if m and not code:
                code = m.group(1)
                continue
            if code and not name and line.strip().startswith("**") and "模组等级" not in line:
                name = line.strip().strip("*").strip()
        tiers: list[dict] = []
        for i, line in enumerate(block):
            m = TIER_RE.match(line.strip())
            if not m:
                continue
            attrs: dict[str, int] = {}
            for nxt in block[i + 1:]:
                if nxt.strip():
                    attrs = {k: int(v) for k, v in ATTR_RE.findall(nxt)}
                    break
            tiers.append({"n": int(m.group(1)), "atk": attrs.get("攻击", 0), "attrs": attrs})
        if code and tiers:
            modules.append({"code": code, "line": code.split("-")[-1], "name": name, "tiers": tiers})
    return modules


def parse_operator(path: pathlib.Path) -> dict | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    atk, trust = parse_attributes(section(lines, "属性"))
    if not atk:
        return None
    return {"atk": atk, "trust": trust,
            "pot": parse_potential(section(lines, "潜能提升")),
            "modules": parse_modules(section(lines, "模组"))}


def build() -> dict:
    ops: dict[str, dict] = {}
    for path in sorted(PRTS.glob("*/*.md")):
        if path.parent.name != path.stem:      # 只要 <干员>/<干员>.md
            continue
        rec = parse_operator(path)
        if rec:
            ops[path.stem] = rec
    return {"note": "由 tools/prts_stats.py 从 material_datas/PRTS 抽取；属性/信赖/潜能/模组固定属性",
            "operators": ops}


_LOADED: dict | None = None


def load() -> dict:
    global _LOADED
    if _LOADED is None:
        _LOADED = json.loads(OUT.read_text(encoding="utf-8"))["operators"]
    return _LOADED


def pot_bonus(rec: dict, pot: int | None) -> tuple[int, list[tuple[int, int]]]:
    """潜能 2…N 的攻击力加成之和（达到该档时含其以下各档）→ (加成, [(档位, 加成)…])。"""
    if not pot:
        return 0, []
    total, hits = 0, []
    for n in range(2, pot + 1):
        m = POT_ATK_RE.search(rec.get("pot", {}).get(str(n), ""))
        if m:
            total += int(m.group(1))
            hits.append((n, int(m.group(1))))
    return total, hits


def module_of(rec: dict, line: str) -> dict | None:
    """按模组线（X／Y／Δ／ISW-α…）或完整代号取模组。"""
    for mod in rec.get("modules", []):
        if line in (mod["line"], mod["code"]):
            return mod
    return None


MODE_PREFIX = {"ISW": "集成战略", "RA": "生息演算", "SO": "岁的界园志异"}


def module_label(mod: dict, tier: int) -> str:
    """模组在产物里的写法（`docs/rulings.md`「模组代号进产物」）：`X模组3级（HOK-X）`／`集成战略特限模组3级（ISW-α）`。"""
    code, line = mod.get("code", ""), mod.get("line", "")
    name = f"{line}模组" if line in ("X", "Y", "Δ") else f"{MODE_PREFIX.get(code.split('-')[0], '')}特限模组"
    return f"{name}{tier}级（{code}）" if code else f"{name}{tier}级"


def module_tier(mod: dict | None, tier: int | None) -> dict | None:
    if not mod or not tier:
        return None
    for t in mod["tiers"]:
        if t["n"] == tier:
            return t
    return None


def panel_of(op: str, stage: str = "e2", pot: int | None = None,
             module: str | None = None, tier: int | None = None) -> dict:
    """面板攻击力（docs/calc-rules.md §4.1）：满信赖＋阶段满级＋有效潜能最高档＋条件点名模组档位固定属性。

    返回 {value, parts:[{label,value}], expr, labeled, missing}；数据缺失项记在 missing 里而不是静默省略。
    """
    rec = load().get(op)
    if not rec:
        return {"value": None, "parts": [], "expr": "", "labeled": "", "missing": [f"stats 无 {op}"]}
    missing: list[str] = []
    parts: list[dict] = []
    base = rec["atk"].get(stage)
    if base is None:
        missing.append(f"{op} 缺 {STAGE_LABEL[stage]} 攻击")
    else:
        parts.append({"label": STAGE_LABEL[stage], "value": base})
    if rec["trust"]:
        parts.append({"label": "满信赖", "value": rec["trust"]})
    pv, hits = pot_bonus(rec, pot)
    if pv:      # 标签按**提供加成的档位**写（如「潜能4攻击+34」），不写成「潜能5攻击+34」误导读者
        parts.append({"label": "＋".join(f"潜能{n}攻击" for n, _ in hits), "value": pv})
    elif pot:
        missing.append(f"{op} 潜能{pot} 无攻击加成（或 stats 未抽到）")
    if module and tier:
        mod = module_of(rec, module)
        t = module_tier(mod, tier)
        if mod is None:
            missing.append(f"{op} 缺模组 {module}")
        elif t is None:
            missing.append(f"{op} 缺模组 {module} {tier} 级")
        elif t["atk"]:
            parts.append({"label": f"{module_label(mod, tier)}攻击", "value": t["atk"]})
        else:
            missing.append(f"{op} 模组 {mod['code']}{tier} 级无攻击加成")
    values = [p["value"] for p in parts]
    total = sum(values)
    # 首项（阶段满级）不带符号，其余各项带 +：精英2满级671＋满信赖+90＋潜能4攻击+27＋Δ模组3级攻击+67＝855
    labeled = "＋".join([f"{p['label']}{p['value']}" if i == 0 else f"{p['label']}+{p['value']}"
                        for i, p in enumerate(parts)])
    return {"value": total, "parts": parts,
            "expr": "＋".join(str(v) for v in values) + f"＝{total}",
            "labeled": labeled + f"＝{total}",
            "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(description="PRTS 语料 → 机读属性层 stats.json")
    ap.add_argument("--check", action="store_true", help="只报覆盖率与异常")
    ap.add_argument("--panel", metavar="干员")
    ap.add_argument("--stage", default="e2", choices=STAGE_ORDER)
    ap.add_argument("--pot", type=int)
    ap.add_argument("--module", help="模组线（X／Y／Δ／ISW-α…）或完整代号")
    ap.add_argument("--tier", type=int)
    args = ap.parse_args()

    if args.panel:
        r = panel_of(args.panel, args.stage, args.pot, args.module, args.tier)
        print(f"面板 {r['value']}：{r['labeled']}" if r["value"] else "无数据")
        for m in r["missing"]:
            print("  缺失：" + m)
        return 0

    data = build()
    ops = data["operators"]
    pages = [p for p in PRTS.glob("*/*.md") if p.parent.name == p.stem]
    modules = [m for op in ops.values() for m in op["modules"]]
    bad: list[str] = []
    for name, rec in ops.items():
        if "e2" not in rec["atk"] and not all(s in rec["atk"] for s in ("e0_1",)):
            bad.append(f"{name}：属性表未取到攻击行")
        for mod in rec["modules"]:
            if [t["n"] for t in mod["tiers"]] != [1, 2, 3]:
                bad.append(f"{name}/{mod['code']}：档位不全 {[t['n'] for t in mod['tiers']]}")
    if not args.check:
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写出 {OUT.relative_to(ROOT)}（{OUT.stat().st_size} 字节）")
    print(f"干员 {len(ops)}/{len(pages)}；模组 {len(modules)} 个（档位 {sum(len(m['tiers']) for m in modules)} 块）"
          f"；有潜能表 {sum(1 for r in ops.values() if r['pot'])}/{len(ops)}")
    print(f"异常 {len(bad)} 条" + ("：" + "；".join(bad[:10]) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

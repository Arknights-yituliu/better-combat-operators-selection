# -*- coding: utf-8 -*-
"""ArkDPS 独立复核报告（A 支）：公式复刻 → 站点模型对账 → 我方模型对账 → 描述对账。

对账口径（开发者裁定）：
  1. 本地复刻站点公式，先套**站点数据模型**（站点 BaseAttack + 默认模组线 + 站点用法分支/目标数）
     → 必须复现排行榜 DPS（这一步只校验求值器，不涉及我方数据）。
  2. 再套**我方数据模型**（把我方面板攻击力代入同一公式、同一分支）→ 与我方成绩 DPS 比较。
  3. 比值落在容差内 → 一致；否则 → 需裁定（写入 workdocs/待裁定.md）。

用法：
  python tools/arkdps_report.py                # 全量 P01
  python tools/arkdps_report.py --tag P02      # 其它 TAG（仅做结构占位，暂不对账）
  python tools/arkdps_report.py --out x.txt
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arkdps_replicate as ar  # noqa: E402

TOL = 0.10          # 我方 DPS 与「站点公式 + 我方面板」的允许偏差
DUR_RE = re.compile(r"([\d.]+)\s*秒")
TOTAL_RE = re.compile(r"总伤\s*[≈约]\s*([\d.]+)")


# ---------------------------------------------------------------- 我方数据

def our_entries(tag: str = "P01") -> list[dict]:
    """我方条目：干员、技能、时长、总伤、面板、条件。"""
    d = json.loads((ROOT / "results" / "operator-tags.json").read_text(encoding="utf-8"))
    out = []
    for t in d["tags"]:
        if t["id"] != tag:
            continue
        for m in t["members"]:
            cond = m.get("condition", "")
            sk = re.search(r"([123])技能", cond)
            calc = m.get("calc") or {}
            scen = (calc.get("scenarios") or [{}])[0]
            panel = None
            for st in scen.get("steps", []):
                if "面板" in str(st.get("title") or ""):
                    try:
                        panel = int(float(st.get("result")))
                    except (TypeError, ValueError):
                        pass
                    break
            dur = total = None
            for b in m.get("remark") or []:
                if not str(b.get("label", "")).startswith("成绩"):
                    continue
                txt = " ".join(i.get("text", "") for i in b.get("items", []))
                mm = DUR_RE.search(txt)
                mt = TOTAL_RE.search(txt)
                if mm and mt:
                    dur, total = float(mm.group(1)), float(mt.group(1))
                    break
            out.append({"operator": m["operator"], "skill": sk.group(1) if sk else None,
                        "cond": cond, "panel": panel, "dur": dur, "total": total,
                        "has_calc": bool(calc), "member": m})
    return out


# ---------------------------------------------------------------- 站点数据

def site_index() -> tuple[dict[str, str], dict[str, dict], dict[str, str]]:
    """返回 (干员名→代号, 代号→{名}, 代号→默认模组线)。"""
    ops = ar.load_operators()
    name2code = {v["name"]: k for k, v in ops.items()}
    dmods = ar.load_default_modules()
    return name2code, ops, dmods


def resolve_name(name: str, name2code: dict[str, str]) -> str | None:
    """只接受精确同名。

    站内存在「陈 / 假日威龙陈」「煌 / 烛煌」「安洁莉娜 / 予愿安洁莉娜」这类同名后缀的
    不同干员，前缀/子串匹配会把异格错配成本体（面板与公式完全不同），因此一律不做模糊匹配。
    """
    return name2code.get(name)


def calib_ref() -> dict[str, str]:
    p = ar.OUT / "review" / "arkdps-calibration.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def ref_for(name: str, skill: str, ref: dict[str, str]) -> dict | None:
    pre = f"{name}{skill}"
    for k, v in ref.items():
        if k.startswith(pre) and k[len(pre):len(pre) + 1] not in "0123456789":
            return v
    return None


def eval_panel(fd: dict, bases: dict, code: str, line: str, ref: dict | None,
               panel: float | None, forced: dict | None = None,
               extra: dict | None = None) -> float | None:
    """按站点分支/副目标求值；panel 给定时替换成我方攻击力，forced 覆盖 LET 中间量。"""
    mode = (ref or {}).get("lineModeMinor", "").split("·")
    mname = mode[1] if len(mode) > 1 and mode[1].startswith("mode") else ""
    minor = next((int(x[2:]) for x in mode if x.startswith("副")), 0)
    raw = fd["modes"].get(mname) if mname else fd["raw"]
    if not raw:
        return None
    kw = {"TargetIncludeMinor": minor > 0, "EnemyCountMinor": minor}
    kw.update(extra or {})
    env = ar.make_env(bases, code, line, **kw)
    if panel:
        env[f"BaseAttack{code}{line}"] = float(panel)
    try:
        v = ar.eval_formula(raw, env, forced=forced)
    except Exception:  # noqa: BLE001
        return None
    return float(v) if isinstance(v, (int, float)) else None


def scenario_inputs(cond: str) -> dict:
    """从我方条件提取站点公式的输入维度（敌方档位、副目标数、元素值）。"""
    c = re.sub(r"精英[12]", "", cond)          # 去掉「精英2」这类晋升标记
    out: dict = {}
    if "领袖" in c:
        out["EnemyRankMajor"] = 3
    elif "精英" in c:
        out["EnemyRankMajor"] = 2
    m = (re.search(r"存在\s*(\d+)\s*名", c) or re.search(r"(?:至少|≥)\s*(\d+)\s*名", c)
         or re.search(r"对\s*(\d+)\s*个单位", c))
    if m:
        n = int(m.group(1))
        if c[max(0, m.start() - 2):m.start()].endswith("对"):
            n -= 1
        if n > 0:
            # 只用于公式内的「范围内 N 名敌人」增伤档位；成绩按单目标计，
            # 因此不打开 TargetIncludeMinor（否则会把副目标伤害也加进来）。
            out["EnemyCountMinor"] = n
    m = re.search(r"元素值\s*(\d+)", cond)
    if m:
        out["EnemyMaxElementMajor"] = int(m.group(1))
        out["EnemyMaxElementMinor"] = int(m.group(1))
    return out


FRAME_RE = re.compile(r"取整帧\s*(\d+)\s*帧")
DIV30_RE = re.compile(r"(\d+(?:\.\d+)?)\s*×\s*30\s*÷\s*(\d+(?:\.\d+)?)(?:\s*=\s*([\d.]+))?")
NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def our_model(member: dict, dur: float) -> tuple[int | None, int | None, list[str]]:
    """从我方步骤提取帧数/次数，并返回步骤标题（用于判断额外机制）。"""
    scen = (member.get("calc") or {}).get("scenarios") or [{}]
    frames = count = None
    titles: list[str] = []
    steps = [st for s in scen for st in s.get("steps", [])]
    # 1) 显式帧数
    for st in steps:
        txt = " ".join(str(st.get(k) or "") for k in ("expr", "result", "note", "title"))
        m = FRAME_RE.search(txt)
        if m:
            frames = int(m.group(1))
            break
    # 2) 次数：主攻击的「次数/轮/下数」步骤（跳过窗口、跳数、结算、爆发）
    for st in steps:
        title = str(st.get("title") or "")
        titles.append(title)
        if frames is None:
            m = DIV30_RE.search(st.get("expr") or "")
            if m:
                frames = int(float(m.group(2)))
        if not any(k in title for k in ("次数", "轮数", "下数", "轮")):
            continue
        if any(k in title for k in ("窗口", "跳", "结算", "爆发", "伤害", "段")):
            continue
        if count is not None:
            continue
        m = DIV30_RE.search(st.get("expr") or "")
        if m:
            frames = frames or int(float(m.group(2)))
            if m.group(3):
                count = int(round(float(m.group(3))))
                continue
        if st.get("result") is not None:
            try:
                count = int(round(float(str(st["result"]).strip())))
            except (TypeError, ValueError):
                continue
    # 3) 只有间隔秒数时反推帧数
    if frames is None:
        for st in steps:
            title = str(st.get("title") or "")
            if "间隔" not in title or "跳" in title or "结算" in title:
                continue
            try:
                sec = float(str(st.get("result")).strip())
            except (TypeError, ValueError):
                continue
            frames = max(1, ar._xround(sec * 30)) if sec else None
            if frames:
                break
    return frames, count, titles



# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="P01")
    ap.add_argument("--out", default="agent_workspace/_out/review/arkdps-comparison.txt")
    args = ap.parse_args()

    lb = ar.load_leaderboard()
    forms = ar.load_formulas()
    bases = ar.load_base_attacks()
    name2code, ops, dmods = site_index()
    ref = calib_ref()
    ours = our_entries(args.tag)

    lines = []
    detail = []
    stat = {"一致": 0, "接近": 0, "差异": 0, "无法对账": 0, "无法复刻": 0, "非伤害型": 0}
    lines.append(f"{'干员':12}{'技能':4}{'线':2}{'分支':10}{'站点面板':>9}{'我方面板':>9}"
                 f"{'站点DPS':>9}{'我方DPS':>9}{'比值':>7}  自检  结论")
    for e in ours:
        name, sk = e["operator"], e["skill"]
        if not (e["dur"] and e["total"]):
            stat["非伤害型"] += 1
            lines.append(f"{name:12}{sk or '-':4}{'-':2}{'-':10}{'-':>9}{'-':>9}{'-':>9}{'-':>9}{'-':>7}  -    非伤害型")
            continue
        our_dps = e["total"] / e["dur"]
        code = resolve_name(name, name2code)
        if not code or code not in forms:
            stat["无法复刻"] += 1
            lines.append(f"{name:12}{sk or '-':4}{'-':2}{'-':10}{'-':>9}{e['panel'] or 0:9}"
                         f"{'-':>9}{our_dps:9.0f}{'-':>7}  -    不在 ArkDPS")
            continue
        line = dmods.get(code) or next(iter(forms[code]))
        fd = (forms[code].get(line) or {}).get(f"skill{sk}")
        if not fd or not (fd["raw"] or fd["modes"]):
            # 站点只在部分模组线给出公式（如逻各斯 D 线无公式、只有 X/Y）；回退到有公式的线。
            for alt, skmap in forms[code].items():
                cand = skmap.get(f"skill{sk}")
                if cand and (cand["raw"] or cand["modes"]):
                    line, fd = alt, cand
                    break
        if not fd or not (fd["raw"] or fd["modes"]):
            stat["无法复刻"] += 1
            lines.append(f"{name:12}{sk:4}{line:2}{'-':10}{'-':>9}{e['panel'] or 0:9}"
                         f"{'-':>9}{our_dps:9.0f}{'-':>7}  -    无该技能公式")
            continue
        r = ref_for(ops[code]["name"], sk, ref)
        site_panel = bases.get(f"BaseAttack{code}{line}", 0.0)
        site_dps = eval_panel(fd, bases, code, line, r, None)
        ours_dps_site_model = eval_panel(fd, bases, code, line, r, e["panel"])
        if site_dps is None or ours_dps_site_model is None:
            stat["无法复刻"] += 1
            lines.append(f"{name:12}{sk:4}{line:2}{'-':10}{site_panel:9.0f}{e['panel'] or 0:9}"
                         f"{'-':>9}{our_dps:9.0f}{'-':>7}  -    公式求值失败")
            continue
        # 我方帧模型：只覆盖站点公式里真实存在的中间量（有些分支用 DPH 序列而非 AttackCount）
        frames, count, titles = our_model(e["member"], e["dur"])
        extra = scenario_inputs(e["cond"])
        forced: dict[str, float] = {"SkillTime": e["dur"]}
        model_dps = eval_panel(fd, bases, code, line, r, e["panel"], forced=forced, extra=extra)
        if model_dps is not None:
            keys = set(ar.TRACE)
            if "AttackSpan" in keys and frames:
                forced["AttackSpan"] = frames / 30.0
            if "AttackCount" in keys and count:
                forced["AttackCount"] = float(count)
            model_dps = eval_panel(fd, bases, code, line, r, e["panel"], forced=forced, extra=extra)
        model_total = model_dps * e["dur"] if model_dps is not None else None
        # 自检：站点模型复刻 vs 排行榜
        lb_dps = None
        for k, row in lb.items():
            if k.startswith(f"{ops[code]['name']}{sk}") and k[len(f"{ops[code]['name']}{sk}"):len(f"{ops[code]['name']}{sk}") + 1] not in "0123456789":
                lb_dps = row["dps"]
                break
        selfok = "✓" if lb_dps and abs(site_dps - lb_dps) <= max(1.0, lb_dps * 0.02) else "-"
        ratio = (e["total"] / model_total) if model_total else 0
        tag = (r or {}).get("lineModeMinor", line)
        if selfok != "✓":
            verdict = "无法对账"
        elif ratio and abs(ratio - 1) <= 0.02:
            verdict = "一致"
        elif ratio and abs(ratio - 1) <= 0.15:
            verdict = "接近"
        else:
            verdict = "差异"
        stat[verdict] = stat.get(verdict, 0) + 1
        lines.append(f"{name:12}{sk:4}{line:2}{tag:10}{site_panel:9.0f}{e['panel'] or 0:9}"
                     f"{site_dps:9.0f}{our_dps:9.0f}{ratio:7.3f}  {selfok:>2}    {verdict}"
                     f"  帧{frames or '-'}/次{count or '-'}")
        detail.append(f"{name} {sk} | {e['cond'][:40]} | 我方总伤 {e['total']:.0f} / 模型总伤 "
                      f"{model_total if model_total is None else round(model_total)} | 比值 {ratio:.3f} | "
                      f"帧 {frames} 次 {count} | 步骤: {' / '.join(titles)}")

    lines.append("")
    lines.append(f"汇总（{args.tag}）：{stat}")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    det = out.with_name(out.stem + "-detail.txt")
    det.write_text("\n".join(detail) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n写入 {out} 与 {det}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

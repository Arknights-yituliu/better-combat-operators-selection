# -*- coding: utf-8 -*-
"""产物数值校准：把 `results/operator-tags.json` 里的数字与 PRTS 语料复算值对照。

报五类（全部只报告、不改任何文件）：

1. **面板不符**：文本里的 `面板NNN` 与「条件声明的档位」复算值对不上——顺带给出「哪个档位组合才凑得出 NNN」。
2. **档位未取满**：条件点名的模组档低于该模组有增益（攻击／攻速）的最高档。
3. **恒等式**：`面板N×M%≈V`（V 应≈N×M÷100）与 `全时长总伤÷持续秒数≈DPS`。
4. **因子覆盖**：该干员的天赋／技能／模组／召唤物名有哪些从未在条目里出现（供人判「计入／未计入＋理由」）。
5. **代号残留**：范围代号、`S1/S2/S3`、`表 2A`、`路径⑤`、复算规则号等内部代号（写法规范见 docs/concept.md）。

用法：
    .venv/Scripts/python.exe -X utf8 verify_numbers.py                # 全库
    .venv/Scripts/python.exe -X utf8 verify_numbers.py --only P01     # 只查某个 TAG
    .venv/Scripts/python.exe -X utf8 verify_numbers.py --coverage     # 只出因子覆盖清单
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# 已复核的「档位取舍」例外：键＝(TAG 名, 干员)，值＝理由。
# 工具只报「存在更高档且有攻击／攻速增益」；该档**是否对本 TAG 有帮助**由人按本 TAG 的评定标准裁定
# （判据＝该档的效果是否改变本 TAG 所判维度、按绝对贡献衡量；纯固定攻击与取整帧后不改变计数的攻速
# 不构成帮助，见 docs/rulings.md「模组取档」），裁定为「不取」者登记在此——报告里转为「已复核」栏，
# 不再混进待修清单。每加一条即一次显式裁定。
REVIEWED_TIERS: dict[tuple[str, str], str] = {
    ("高档控制", "提丰"): "集成战略特限模组取 2 级——箭雨（8 次）与 0.1 秒晕眩自 2 级即具备，3 级只提高箭雨伤害（90%→110%）、控制不变，不取 3 级（docs/rulings.md「子 TAG『远距控制』」）",
    ("吃拐一轮秒", "机械师"): "集成战略特限模组 1→3 级只加固定攻击／防御／屏障与召唤物持续时间（本条窗口 7.5 秒、持续时间不构成约束），不改倍率／段数／窗口，不取",
    ("吃拐一轮秒", "归溟幽灵鲨"): "特限模组 2／3 级只加替身形态（非技能期）的每秒法术伤害、替换时技力与固定攻击，不改 25 次×322% 的判据，不取",
    ("吃拐一轮秒", "怒潮凛冬"): "X 模组 3 级只提升特性溅射伤害（PRTS 备注明写不对特性主目标生效）与固定攻击，不改按主目标计的倍率，不取",
    ("吃拐一轮秒", "能天使"): "Y 模组 3 级只加固定攻击与「逐渐无视防御力」（对敌穿透、默认木桩 0 防无增量），攻速／次数／段数不变，不取",
    ("吃拐一轮秒", "陈"): "X 模组 3 级只加固定攻击与攻速；本技能为固定 10 次斩击，段数与按 ≤0.4 秒／击计的窗口不变，不取",
    ("吃拐一轮秒", "鸿雪"): "Y 模组 3 级只提高「打字机」自身攻击力（本行按自身技能倍率计、不与面板折算）与固定攻击，不改 261.95% 的均值，不取",
    ("吃拐一轮秒", "伺夜"): "Y 模组 2／3 级只提高第二天赋的对敌穿透（无视 175／偷取 15，默认木桩 0 防无增量）与固定攻击，不改倍率／段数／窗口，不取",
    ("次数对策", "能天使"): "取 Y模组1级：2／3 级只更新第一天赋的无视防御（默认木桩无增量）与固定攻击，段数、结算间隔不变",
    ("次数对策", "安洁莉娜"): "取集成战略特限模组2级：3 级只提高单跳伤害、把攻速 +6→+7（取整帧同为 8 帧）并追加自行施加浮空的手段，跳数与结算间隔不变",
    ("次数对策", "赤刃明霄陈"): "X 模组 2／3 级只加固定攻击与第二天赋治疗量；段数 61、结算间隔与攻速不变，不取",
    ("次数对策", "空弦"): "取 Y模组1级——1／2／3 级取整帧同为 27 帧、段数同为 66；2／3 级只加固定攻击（+22／+24）与攻速（+3／+4），其天赋更新为技力向，对本 TAG 判据（段数）无新增帮助，不取",
    ("次数对策", "灵知"): "取集成战略特限模组1级——2／3 级只提高「坚冰」的脆弱数值与寒冷持续时间，跳数与结算间隔不变，不取",
    ("次数对策", "迷迭香"): "取 X模组1级——2／3 级只更新第一天赋「歼灭战装备」的无视防御（190／220）与固定攻击，默认木桩下无增量，段数与结算间隔不变，不取",
    ("吃拐一轮秒", "艾丽妮"): "取 X模组1级——2／3 级只提高物理穿透比例（默认木桩无增量）与击倒回技力，技能动画固定 3.5 秒、倍率与窗口不变，不取",
    ("吃拐一轮秒", "迷迭香"): "取 X模组1级——2／3 级只更新无视防御与固定攻击，段数不变，不取",
    ("插拔容错", "佩佩"): "取生息演算特限模组1级——「携带资源时再部署 −90%」在 1 级即完整；2／3 级只加余震、资源点、防御与宝箱视野，不改再部署，不取",
    ("插拔容错", "凯尔希"): "取集成战略特限模组2级——「不占用部署位」自 2 级起具备；3 级只把 Mon3tr 生命／攻击 +25%→+50% 并追加受治疗 +50%，不改 25 秒再部署与救急窗口，不取",
    ("吃拐一轮秒", "蓝毒"): "取 Y模组1级——2／3 级只加固定攻击（+26／+30）与取整帧后同为 27 帧的攻速（+3／+4），并把天赋中毒数值 75→85／95（按解耦不折入倍率），对本 TAG 判据无新增帮助，不取",
    ("次数对策", "暮落"): "取 X模组1级：2／3 级只更新第二天赋「厄运宣告」的减抗概率与持续时间（作用于敌方法术抗性数值、默认木桩 0 抗无增量），段数与结算间隔不变",
    ("次数对策", "斩业星熊"): "X 模组 2／3 级只更新第二天赋坚忍的攻击力与门槛；二连击／三连击的段数与结算间隔不变，不取",
    ("插拔容错", "艾雅法拉"): "Y 模组 3 级只追加乱火的随机攻速 6~15，取最大值后技力与 3 连发不变、攻速不落在「初动为满」判据上，不取",
    ("插拔容错", "菲亚梅塔"): "集成战略特限模组 2／3 级只提高「陈述苦难」与「再度施放」并加攻速，不改变「倒下时立即重新部署」，不取",
    ("插拔容错", "麒麟R夜刀"): "Y 模组 3 级只把法术附加 23%→25%、术法充盈 35%→50%；X 线 2／3 级只提高第二天赋攻击力与固定攻击——两线的「首次撤退再部署为 0」「撤退返还 80%」自 1 级即具备，不取",
    ("充电", "矩"): "X 模组 2／3 级只追加对生命值低于一半单位的 +8%／+12% 增伤（自身输出向），击杀者回复技力 1／2 点不变，不取",
    ("充电", "罗小黑"): "Y 模组 2／3 级只追加对低生命值单位的 +8%／+12% 增伤（自身输出向），击倒回复的技力不变，不取",
    ("充电", "嵯峨"): "X 模组 2／3 级只追加对低生命值单位的 +10%／+15% 增伤（自身输出向），回复技力不变，不取",
    ("充电", "白铁"): "X 模组 2／3 级只提高白铁自身的技力回复速度（+0.1／+0.2 每秒、需周围 8 格有自身装置）——只回自身，本 TAG 判的是给他人回复，不取",
    ("充电", "瑕光"): "Y 模组 2／3 级只使「其他卡西米尔干员部署时自身获得 2／3 点技力」——只回自身，不取",
    ("充电", "铃兰"): "X 线 2／3 级的技力数值与无模组同为 +0.4 每秒，追加的是受光环【辅助】攻击力 +6%／+9%，不取",
    ("充电", "陈"): "取 X模组2级：3 级追加「自身额外回复 1 点」只回自身，给他人数值不变，不取 3 级",
    ("充电", "推进之王"): "取 Y模组2级：3 级只把自身回复 1→3 点，给予他人的 1 点不变，不取 3 级",
    ("充电", "空弦"): "特限线取集成战略特限模组2级：3 级追加的增伤不改技力数值，不取 3 级",
    ("充电", "异客"): "不取通用线——X 线仅自身 +0.25 每秒、Y 线仅自身增伤，只写特限线",
    ("充电", "归溟幽灵鲨"): "不取集成战略特限线——该线下第二天赋为未更新版本、不回复技力，只写通用线",
    ("初动增加", "新约能天使"): "X 模组 1 级只追加自身技力回复速度、2／3 级只更新第一天赋轰炸，均不改给予的 6 点技力，不取",
    ("初动增加", "炎狱炎熔"): "X 模组 1 级只追加攻击范围、2／3 级只把首次部署的自身部分提到 33／35 点，对术师的 +4 不变，不取",
}

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from prts_stats import load as load_stats, panel_of, module_of          # noqa: E402
from generate_results import PrtsIndex                                  # noqa: E402

RESULTS = ROOT / "results" / "operator-tags.json"
TOL = 0.01                     # 相对容差（文本里的 ≈ 值经过分步取整）

PANEL_RE = re.compile(r"面板(\d+)")
IDENT_RE = re.compile(r"面板(\d+)×([\d.]+)%≈(\d+)")
DPS_RE = re.compile(r"全技能持续 ([\d.]+) 秒总伤 ≈(\d+)(?:（[^）]*）)?、平均 DPS ≈(\d+)/秒")
ELITE_RE = re.compile(r"精英([012])")
POT_RE = re.compile(r"潜能(\d)")
# 模组线：X／Y／Δ 中文线名（线与「模组」间可有空格）；模式限定模组按产物写法「集成战略特限模组 3级」等
MODULE_RE = re.compile(
    r"([XYΔ])\s?模组\s?(\d)\s?级(?:（([A-Z]{2,5}-[A-Za-zΔαβ])）)?"
    r"|(集成战略特限模组|生息演算特限模组|岁的界园志异特限模组|ISW-α|RA-α|SO-α|SO-β)"
    r"(?:「([^」]+)」)?[^\d；。]{0,8}?(\d)\s?级(?:（([A-Z]{2,5}-[A-Za-zΔαβ])）)?"
    r"|([A-Z]{2,5}-[A-Za-zΔαβ])\s?模组\s?(\d)\s?级")
# 模式限定写法 → 语料里的模组线代号（stats.json 的 line）
MODE_ALIAS = {"集成战略特限模组": "α", "生息演算特限模组": "α", "岁的界园志异特限模组": "α",
              "ISW-α": "α", "RA-α": "α", "SO-α": "α", "SO-β": "α"}
STAGE_OF = {"0": "e0", "1": "e1", "2": "e2"}
CODEX_RE = re.compile(r"代号\s*[\w\-]+|(?<![A-Za-z])S[123](?![0-9])|表\s?\d[AB]?|路径[①②③④⑤⑥]")
BLOCK_SHORT = 10               # 块标签前 10 字里出现档位口径即视为该块的声明


def entry_text(member: dict, skip_note: bool = False) -> str:
    """条目的全部可见文本：条件 + 备注各块的块标签与各条（块标签承载成绩档位口径）。

    `skip_note` 去掉「说明」块——说明里会写**未取**的对照口径（如未被取用的另一条模组路线），
    那些数字不该与已声明口径对表。
    """
    parts = [str(member.get("condition", ""))]
    for block in member.get("remark", []):
        if not isinstance(block, dict):
            continue
        if skip_note and str(block.get("label", "")) == "说明":
            continue
        parts.append(str(block.get("label", "")))
        for item in block.get("items", []):
            parts.append(f"{item.get('label', '')}{item.get('text', '')}")
    return "；".join(parts)


def parse_config(text: str) -> dict:
    """文本里的档位口径 → {stage, pot, mods:[(线,档)]}。

    模组写法（`docs/rulings.md`「模组代号进产物」）：`X模组3级（HOK-X）`／
    `集成战略特限模组3级（ISW-α）`／`HOK-X 模组1级`。**带了代号就用代号**（同一模式可能有多条线，
    如 岁的界园志异 的 α「特勤证章」与 β「新起点」，只有完整代号唯一）；没带代号时按模块名
    （`…特限模组「新起点」3级`）或 MODE_ALIAS 兜底。
    """
    elite = ELITE_RE.search(text)
    pot = POT_RE.search(text)
    mods: list[tuple[str, int]] = []
    for m in MODULE_RE.finditer(text):
        if m.group(1):
            mods.append((m.group(3) or m.group(1), int(m.group(2))))
        elif m.group(4):
            key = m.group(7) or (f"name:{m.group(5)}" if m.group(5) else MODE_ALIAS.get(m.group(4), m.group(4)))
            mods.append((key, int(m.group(6))))
        elif m.group(8):
            mods.append((m.group(8), int(m.group(9))))
    return {"stage": STAGE_OF.get(elite.group(1), "e2") if elite else "e2",
            "pot": int(pot.group(1)) if pot else None,
            "mods": list(dict.fromkeys(mods))}


def resolve_line(op: str, key: str) -> str:
    """把 mods 的键解析成 stats.json 里的模组线（`module_of` 同时认线名与完整代号）；`name:…` 键按模块名解析。"""
    if not key.startswith("name:"):
        return key
    want = key[5:]
    rec = load_stats().get(op, {})
    return next((m["line"] for m in rec.get("modules", []) if m.get("name") == want), None) or "α"


def panel_of_config(op: str, cfg: dict) -> list[dict]:
    if not cfg["mods"]:
        return [panel_of(op, cfg["stage"], cfg["pot"])]
    return [panel_of(op, cfg["stage"], cfg["pot"], resolve_line(op, line), tier) for line, tier in cfg["mods"]]


def explain_panel(op: str, target: int) -> str:
    """反查「哪个档位组合才凑得出这个面板」——把「对不上」变成可执行的修正方向。"""
    stats = load_stats()
    rec = stats.get(op, {})
    lines = sorted({m["line"] for m in rec.get("modules", [])}) or [None]
    hits = []
    for stage in ("e0", "e1", "e2"):
        for line in lines:
            tiers = [t["n"] for t in (module_of(rec, line) or {"tiers": []})["tiers"]] if line else [None]
            for tier in tiers:
                for pot in (None, 2, 3, 4, 5, 6):     # 潜能档由低到高：取能凑出的最低档
                    r = panel_of(op, stage, pot, line, tier)
                    if r["value"] == target:
                        hits.append(r["labeled"].split("＝")[0])
                        break
    return "；".join(list(dict.fromkeys(hits))[:3]) if hits else "无任何档位组合凑得出"


def check_entry(tag: str, member: dict, idx: PrtsIndex, stats: dict,
                reviewed: list[str]) -> list[str]:
    op = member.get("operator") or ""
    text = entry_text(member)
    who = f"{tag}｜{op or member.get('combo', '')}"
    out: list[str] = []
    if op not in stats:
        return out

    # ① 面板不符：条件 +「计算」块的面板组成式（逐情形一条，主来源）+ 带档位的成绩块标签（兼容）各是一套口径
    declared = {"条件": parse_config(str(member.get("condition", "")))}
    for block in member.get("remark", []):
        if not isinstance(block, dict):
            continue
        label = str(block.get("label", ""))
        if label.startswith("计算"):
            for item in block.get("items", []):
                txt = str(item.get("label", "") or "") + str(item.get("text", "") or "")
                if PANEL_RE.search(txt):
                    declared[f"计算·{txt[:BLOCK_SHORT]}"] = parse_config(txt)
            continue
        if label:
            cfg = parse_config(label)
            if cfg["pot"] or cfg["mods"] or ELITE_RE.search(label):
                declared[label[:BLOCK_SHORT]] = cfg
    known: dict[int, list[str]] = {}
    for name, cfg in declared.items():
        cfgs = [cfg]
        # 条件里的「精英0/1 可满足 ／ 精英2 最高档」多档写法：每个提到的精英档都算已申报口径，
        # 否则只取第一个 精英N 会与成绩块的高档面板对不上（双档行的正常形态）。
        if name == "条件":
            tiers = sorted(set(ELITE_RE.findall(str(member.get("condition", "")))))
            if len(tiers) > 1:
                cfgs = [{**cfg, "stage": STAGE_OF.get(t, "e2")} for t in tiers]
        for c2 in cfgs:
            for r in panel_of_config(op, c2):
                if r["value"]:
                    known.setdefault(r["value"], []).append(f"{name}（{r['labeled'].split('＝')[0]}）")
    for p in sorted({int(n) for n in PANEL_RE.findall(entry_text(member, skip_note=True))}):
        if p not in known:
            out.append(f"{who}：面板 {p} 与任何已声明口径都对不上；能凑出它的是「{explain_panel(op, p)}」")

    # ② 档位未取满（更高档有攻击或攻速增益）——只在条目确实算伤害时才提：面板/倍率是本 TAG 判据的场合
    damage_entry = bool(PANEL_RE.search(text)) or bool(re.search(r"×\d+(?:\.\d+)?%", text))
    if damage_entry:
        for line, tier in declared["条件"]["mods"]:
            mod = module_of(stats[op], resolve_line(op, line))
            if not mod:
                continue
            cur = next((t for t in mod["tiers"] if t["n"] == tier), None)
            best = max(mod["tiers"], key=lambda t: (t["atk"], t["attrs"].get("攻击速度", 0)))
            if cur and best["n"] > cur["n"] and (best["atk"] > cur["atk"]
                                                 or best["attrs"].get("攻击速度", 0) > cur["attrs"].get("攻击速度", 0)):
                msg = (f"{who}：条件取 {mod['line']}模组{tier}级，但 {best['n']} 级有增益"
                       f"（攻击 {cur['atk']}→{best['atk']}、攻速 {cur['attrs'].get('攻击速度', 0)}→{best['attrs'].get('攻击速度', 0)}）")
                done = REVIEWED_TIERS.get((tag, op))
                (reviewed if done else out).append(msg + (f"｜已复核：{done}" if done else ""))

    # ③ 恒等式
    for base, rate, value in IDENT_RE.findall(text):
        want = float(base) * float(rate) / 100
        if abs(want - int(value)) > max(2.0, want * TOL):
            out.append(f"{who}：{base}×{rate}%≈{value} 不成立（应≈{want:.0f}）")
    for dur, total, dps in DPS_RE.findall(text):
        want = int(total) / float(dur)
        if abs(want - int(dps)) > max(2.0, want * TOL):
            out.append(f"{who}：总伤 {total} ÷ {dur} ≈ {int(dps)} 不成立（应≈{want:.0f}）")
    if "15 秒窗口总伤" in text:
        out.append(f"{who}：成绩句仍为旧式「15 秒窗口总伤」，未迁移全时长口径")

    # ④ 代号残留
    found = {m.group(0).strip() for m in CODEX_RE.finditer(text)}
    if found:
        out.append(f"{who}：产物文本含内部代号 {'、'.join(sorted(found)[:6])}")

    return out


def coverage_entry(tag: str, member: dict, idx: PrtsIndex,
                   kinds: tuple[str, ...] = ("talent", "module", "summon")) -> list[str]:
    """因子覆盖：该干员的哪些天赋／模组／召唤物名从未在条目里出现（写手核对用，非产物要求）。"""
    op = member.get("operator")
    if not op:
        return []
    names = idx.get(op)
    text = entry_text(member)
    miss = []
    for kind, label in (("talent", "天赋"), ("module", "模组"), ("summon", "召唤物")):
        if kind not in kinds:
            continue
        gone = sorted(n for n in names[kind]
                      if 2 <= len(n) <= 12 and "/" not in n and not n.startswith("※") and n != "---" and n not in text)
        if gone:
            miss.append(f"{label}：「{'／'.join(gone)}」")
    return [f"{tag}｜{op}：未提及 " + "；".join(miss)] if miss else []


def main() -> int:
    ap = argparse.ArgumentParser(description="产物数值校准")
    ap.add_argument("--only", default="", help="只查 id 或名字含该串的 TAG")
    ap.add_argument("--coverage", action="store_true", help="只出因子覆盖清单")
    args = ap.parse_args()

    doc = json.loads(RESULTS.read_text(encoding="utf-8"))
    stats = load_stats()
    idx = PrtsIndex()
    n, issues, cover, reviewed = 0, [], [], []
    for tag in doc["tags"]:
        if args.only and args.only not in tag["id"] and args.only not in tag["name"]:
            continue
        for member in tag["members"]:
            n += 1
            if not args.coverage:
                issues += check_entry(tag["name"], member, idx, stats, reviewed)
            # 因子覆盖只对玩家 TAG 的数值条目出：官方 TAG 只引用原文、不承担「逐项计入」的义务
            if tag["source"] == "player" and re.search(r"\d+\s*%", entry_text(member)):
                cover += coverage_entry(tag["name"], member, idx)
    print(f"扫描 {n} 条成员\n")
    if not args.coverage:
        print(f"■ 数值可疑：{len(issues)} 条")
        for x in issues:
            print("  " + x)
        if reviewed:
            print(f"\n■ 档位取舍已复核（REVIEWED_TIERS，按各 TAG 判据裁定不取更高档）：{len(reviewed)} 条")
            for x in reviewed:
                print("  " + x.split("｜已复核：")[0] + "｜" + x.split("｜已复核：")[-1])
    print(f"\n■ 因子覆盖提示：{len(cover)} 条（只列条目里从未出现的名字；**仅供写手自查，不再是产物要求**——条目只写与本 TAG 相关的内容，未计入项不再逐条写入）")
    for x in cover[:40]:
        print("  " + x)
    if len(cover) > 40:
        print(f"  …另有 {len(cover) - 40} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

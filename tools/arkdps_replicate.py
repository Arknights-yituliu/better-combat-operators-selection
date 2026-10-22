# -*- coding: utf-8 -*-
"""ArkDPS 公式复刻：把站点「计算公式」弹窗的 rawFormula 解析求值，用于独立复核我方 calc。

流程（对应开发者裁定的三支复核）：
  A. ArkDPS 有公式 → 用站点数据模型（不含潜能）复刻 → 与排行榜 DPS 对账（校核求值器）
     → 换成我方数据模型（含潜能/模组档）→ 与我方成绩比对 → 与计算详情描述比对。
  B. ArkDPS 有帧模型 → 判断潜能/模组是否改变帧（攻速类才改变）→ 改变则按帧对齐公式重算。
  C. ArkDPS 无此干员 → 参照描述复核；不确定走裁定。

用法：
  python tools/arkdps_replicate.py --list                  # 可复刻的干员/技能
  python tools/arkdps_replicate.py --calibrate             # 求值器 vs 排行榜 DPS
  python tools/arkdps_replicate.py --replicate 逻各斯        # 复刻并对比我方
"""
from __future__ import annotations

import argparse
import io
import json
import math
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "agent_workspace" / "_out"
sys.path.insert(0, str(ROOT / "tools"))

DIALOG = OUT / "_arkdps_1016_dialog.js"
MAIN = OUT / "_arkdps_1016_raw_main-CBjSGln9.js"
LEADERBOARD = ROOT / "docs" / "temp.txt"


# ---------------------------------------------------------------- 读取站点资产

def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _brace_block(text: str, start: int) -> tuple[str, int]:
    """从 start（指向 `{` 之后）取到匹配的 `}` 之前的内容与结束位置。"""
    depth, i = 1, start
    while i < len(text) and depth:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return text[start:i - 1], i


def _mode_formulas(seg: str) -> dict[str, str]:
    """技能块 → {mode名: 公式}；无 mode 时返回 {"": 公式}。"""
    out: dict[str, str] = {}
    if "mode" in seg and re.search(r"mode\d+:\{", seg):
        for mm in re.finditer(r"(mode\d+):\{", seg):
            body, _ = _brace_block(seg, mm.end())
            fm = re.search(r"rawFormula:`(.*?)`", body, re.S)
            if fm:
                out[mm.group(1)] = fm.group(1)
        return out
    fm = re.search(r"rawFormula:`(.*?)`", seg, re.S)
    return {"": fm.group(1)} if fm else {}


def load_formulas() -> dict[str, dict[str, dict[str, dict]]]:
    """{code: {"X"|"Y"|"D": {skillN: {"raw": 基础公式, "modes": {modeN: 公式}}}}}"""
    text = read(DIALOG)
    out: dict[str, dict[str, dict[str, dict]]] = {}
    for m in re.finditer(r"([A-Z]{2}\d{2}):\{([XYD]):\{", text):
        code, line = m.group(1), m.group(2)
        body, _ = _brace_block(text, m.end())
        skills: dict[str, dict] = {}
        for sm in re.finditer(r"skill(\d+):\{", body):
            seg, _ = _brace_block(body, sm.end())
            modes = _mode_formulas(seg)
            if not modes:
                continue
            raw = modes.pop("", "")
            skills[f"skill{sm.group(1)}"] = {"raw": raw, "modes": modes}
        if skills:
            out.setdefault(code, {})[line] = skills
    return out


def load_base_attacks() -> dict[str, float]:
    """{BaseAttackKEY: attack}，如 RE03D=828、RE03Y=821。"""
    text = read(MAIN)
    return {k: float(v) for k, v in re.findall(r"(BaseAttack[A-Z]{2}\d{2}[A-Z]|\b[A-Z]{2}\d{2}[XYD]):\{attack:([\d.]+)", text)} | \
           {f"BaseAttack{k}": float(v) for k, v in re.findall(r"\b([A-Z]{2}\d{2}[XYD]):\{attack:([\d.]+)", text)}


def load_operators() -> dict[str, dict]:
    text = read(MAIN)
    out = {}
    for m in re.finditer(r"([A-Z]{2}\d{2}):\{name:`([^`]+)`", text):
        out[m.group(1)] = {"name": m.group(2)}
    return out


def load_default_modules() -> dict[str, str]:
    """站点每个干员的默认模组线（defaultModuleId：X／Y／D）。"""
    text = read(MAIN)
    out: dict[str, str] = {}
    for m in re.finditer(r"([A-Z]{2}\d{2}):\{name:`([^`]+)`(.*?)(?=\},\s*[A-Z]{2}\d{2}:\{name:|$)", text, re.S):
        dm = re.search(r"defaultModuleId:`([A-Z]+)`", m.group(3))
        if dm:
            out[m.group(1)] = dm.group(1)
    return out


def solve_formula(skill: dict, bases: dict, code: str, line: str, target: float | None = None):
    """求值一条技能公式：基础式 + 各用法分支 × 副目标数（0–3）；target 给定时选最接近的。

    返回 (mode名, 副目标数, 值) 或 None。排行榜每个条目的「用法分支 + 目标数」在站点上是
    显式设置，本地快照未记录，故按与排行榜 DPS 最接近的组合反推（等价于站点计算条件）。
    """
    cands: list[tuple[str, int, float]] = []
    entries = [("", skill["raw"])] if skill.get("raw") else []
    entries += [(k, v) for k, v in (skill.get("modes") or {}).items() if v]
    for mode, raw in entries:
        if not raw:
            continue
        try:
            ast = Parser(tokenize(raw)).parse()
        except Exception:  # noqa: BLE001
            continue
        for minor in (0, 1, 2, 3):
            env = make_env(bases, code, line,
                           TargetIncludeMinor=minor > 0, EnemyCountMinor=minor)
            try:
                v = evaluate(ast, env)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(v, (int, float)):
                cands.append((mode, minor, float(v)))
    if not cands:
        return None
    if target:
        cands.sort(key=lambda x: abs(x[2] - target))
    return cands[0]


# ---------------------------------------------------------------- 公式语言

class FormulaError(Exception):
    pass


_TOKEN = re.compile(r"""
    (?P<num>\d+(?:\.\d+)?(?:E[+-]?\d+)?)
  | (?P<str>"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)
  | (?P<ident>BaseAttack[A-Z]{2}\d{2}[XYD]|B[A-Z]{2}\d{2}[XYD]|[A-Za-z_@][A-Za-z0-9_]*)
  | (?P<op><>|<=|>=|[-+*/^(),<>=])
""", re.X)


def tokenize(src: str) -> list[tuple[str, str]]:
    src = src.replace("!0", "True").replace("!1", "False")
    # 站点公式里的注释用 N("…") 包裹，但注释文本自身可能含 `=`、`（）` 等字符；
    # 先把整段 N("…") 换成一个 N(0)，再走通用分词。
    src = re.sub(r'N\(\s*"(?:[^"\\]|\\.)*"\s*\)', "N(0)", src)
    src = re.sub(r"N\(\s*`(?:[^`\\]|\\.)*`\s*\)", "N(0)", src)
    src = src.strip()
    if src.startswith("="):
        src = src[1:].lstrip()
    pos, out = 0, []
    while pos < len(src):
        if src[pos] in " \t\r\n":
            pos += 1
            continue
        m = _TOKEN.match(src, pos)
        if not m:
            raise FormulaError(f"无法识别的字符 @{pos}: {src[pos:pos+30]!r}")
        kind = m.lastgroup
        out.append((kind, m.group()))
        pos = m.end()
    return out


class Parser:
    """Pratt 解析 → AST（元组）。"""

    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, val=None):
        tok = self.peek()
        if val is not None and tok[1] != val:
            raise FormulaError(f"期望 {val!r}，得到 {tok[1]!r}")
        self.i += 1
        return tok

    def parse(self):
        node = self.expr(0)
        if self.i != len(self.t):
            raise FormulaError(f"多余 token: {self.t[self.i:]}")
        return node

    PREC = {"<": 1, ">": 1, "<=": 1, ">=": 1, "=": 1, "<>": 1,
            "+": 2, "-": 2, "*": 3, "/": 3, "^": 4}

    def expr(self, minp):
        left = self.unary()
        while True:
            kind, val = self.peek()
            if kind != "op" or val not in self.PREC or self.PREC[val] < minp:
                return left
            self.take()
            right = self.expr(self.PREC[val] + 1)
            left = ("bin", val, left, right)

    def unary(self):
        kind, val = self.peek()
        if kind == "op" and val in ("-", "+"):
            self.take()
            return ("neg", self.unary()) if val == "-" else self.unary()
        return self.primary()

    def primary(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", float(val))
        if kind == "str":
            return ("str", val[1:-1])
        if kind == "ident":
            nk, nv = self.peek()
            if nv == "(":
                self.take("(")
                args = []
                if self.peek()[1] != ")":
                    while True:
                        args.append(self.expr(0))
                        if self.peek()[1] == ",":
                            self.take(",")
                            continue
                        break
                self.take(")")
                return ("call", val.upper(), args)
            return ("var", val)
        if val == "(":
            node = self.expr(0)
            self.take(")")
            return node
        raise FormulaError(f"意外的 token {val!r}")


#: 最近一次求值的 LET 绑定（SkillTime / AttackSpan / AttackCount …），供复核脚本读取。
TRACE: dict[str, float] = {}
#: 覆盖 LET 绑定值（如用我方帧模型替换站点的 AttackSpan / AttackCount）。
FORCED: dict[str, float] = {}


def eval_formula(raw: str, env: dict, forced: dict | None = None) -> float:
    """求值一条公式，清空并回填 TRACE；forced 覆盖同名 LET 绑定。"""
    global FORCED
    TRACE.clear()
    FORCED = dict(forced or {})
    try:
        return evaluate(Parser(tokenize(raw)).parse(), env)
    finally:
        FORCED = {}


def _xround(x: float, digits: int = 0) -> float:
    """Excel ROUND：四舍五入（half away from zero），与 Python 的银行家舍入不同。"""
    from decimal import Decimal, ROUND_HALF_UP  # noqa: PLC0415

    q = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def evaluate(node, env: dict):
    t = node[0]
    if t == "num":
        return node[1]
    if t == "str":
        return node[1]
    if t == "var":
        name = node[1]
        if name in env:
            return env[name]
        if name in ("True", "true", "TRUE"):
            return True
        if name in ("False", "false", "FALSE"):
            return False
        if name.startswith("BaseSummonAttack"):
            # 召唤物面板：快照未收录召唤物基础攻击；站点公式里它只以 `0*BaseSummonAttack…`
            # 形式出现（用于占位），取 0 与站点基准场景等价。
            return 0.0
        raise FormulaError(f"未定义变量 {name}")
    if t == "neg":
        return -evaluate(node[1], env)
    if t == "bin":
        op = node[1]
        a = evaluate(node[2], env)
        b = evaluate(node[3], env)
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        if op == "/": return a / b if b else 0.0
        if op == "^": return a ** b
        if op == "<": return a < b
        if op == ">": return a > b
        if op == "<=": return a <= b
        if op == ">=": return a >= b
        if op == "=": return a == b
        if op == "<>": return a != b
        raise FormulaError(f"未知运算 {op}")
    if t == "call":
        fn = node[1]
        args = node[2]
        if fn == "N":            # 注释
            return 0.0
        if fn == "IF":
            c = evaluate(args[0], env)
            return evaluate(args[1], env) if c else (evaluate(args[2], env) if len(args) > 2 else 0.0)
        if fn == "IFS":
            for i in range(0, len(args) - 1, 2):
                if evaluate(args[i], env):
                    return evaluate(args[i + 1], env)
            return evaluate(args[-1], env) if len(args) % 2 else 0.0
        if fn == "LET":
            local = dict(env)
            for i in range(0, len(args) - 1, 2):
                name = args[i][1]
                val = evaluate(args[i + 1], local)
                if name in FORCED:
                    val = FORCED[name]
                local[name] = val
                TRACE[name] = val
            return evaluate(args[-1], local)
        vals = [evaluate(a, env) for a in args]
        if fn == "ROUND":
            # 站点/ECharts 公式用 Excel 语义：四舍五入（half away from zero）。
            # Python 内置 round 是银行家舍入（10.5→10），会系统性少算攻击次数。
            return _xround(vals[0], int(vals[1]) if len(vals) > 1 else 0)
        if fn == "ROUNDUP" or fn == "CEILING":
            n = vals[1] if len(vals) > 1 else 0
            f = 10 ** int(n)
            return math.ceil(vals[0] * f) / f
        if fn == "ROUNDDOWN":
            n = vals[1] if len(vals) > 1 else 0
            f = 10 ** int(n)
            return math.floor(vals[0] * f) / f
        if fn == "MROUND":
            step = vals[1] or 1
            return _xround(vals[0] / step) * step
        if fn == "INT":
            return int(vals[0])
        if fn == "MEDIAN":
            s = sorted(vals)
            return s[len(s) // 2]
        if fn == "MIN":
            return min(vals)
        if fn == "MAX":
            return max(vals)
        if fn == "MOD":
            return math.fmod(vals[0], vals[1])
        if fn == "POWER":
            return vals[0] ** vals[1]
        if fn == "AND":
            return all(vals)
        if fn == "OR":
            return any(vals)
        if fn == "NOT":
            return not vals[0]
        if fn == "SUM":
            return sum(vals)
        if fn == "ABS":
            return abs(vals[0])
        if fn == "COUNTIF":
            # COUNTIF(range, 判据)：站点用它检查「是否有攻速/技力类增益来源」，本文档基准场景为 0。
            crit = vals[1] if len(vals) > 1 else True
            seq = vals[0] if isinstance(vals[0], (list, tuple)) else [vals[0]]
            return sum(1 for x in seq if x == crit)
        raise FormulaError(f"未实现函数 {fn}")
    raise FormulaError(f"未知节点 {t}")


# ---------------------------------------------------------------- 环境

def default_env() -> dict:
    """站点默认场景：普通敌人、单目标、0 防 0 抗、主目标计入。"""
    return {
        "EnemyRankMajor": 1, "EnemyRankMinor": 1,
        "LiteralEnemyRankNormal": 1, "LiteralEnemyRankElite": 2, "LiteralEnemyRankLeader": 3,
        "TargetIncludeMajor": True, "TargetIncludeMinor": False,
        "EnemyCountMajor": 1, "EnemyCountMinor": 0,
        "EnemyDefenseMajor": 0, "EnemyDefenseMinor": 0,
        "EnemyResistanceMajor": 0, "EnemyResistanceMinor": 0,
        "EnemyElementalResistanceMajor": 0, "EnemyElementalResistanceMinor": 0,
        "EnemyInjuryResistanceMajor": 0, "EnemyInjuryResistanceMinor": 0,
        "EnemyMaxElementMajor": 1000, "EnemyMaxElementMinor": 1000,
        "EnemyAerial": False, "EnemySeparated": False,
        "EnemyWeightMajor": 0, "EnemyWeightMinor": 0,
        "AttackSpeed": 0, "SkillAutomatic": 0,
        # 站点「增益来源」变量（@Xxx）：默认全部关闭；开启某一来源时按站点 buff 模型逐个赋值
        "BuffSourceIds": "", "BuffDamageSkillPointSupplyEnablesOffensive": 0,
        "DamageTimeWindow": float("inf"),
    }


def make_env(base_attacks: dict[str, float], code: str, line: str, **overrides) -> dict:
    env = default_env()
    for k, v in base_attacks.items():
        env[k] = v
    env[f"BaseAttack{code}{line}"] = base_attacks.get(f"BaseAttack{code}{line}", 0.0)
    env[code] = 0.0
    env[line] = 0.0
    env.update(overrides)
    return env


# ---------------------------------------------------------------- 排行榜

def load_leaderboard() -> dict[str, dict]:
    """{「干员N技能名」: {dps, total, grade, ...}}"""
    text = read(LEADERBOARD)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)

    def cells(r):
        return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]

    out = {}
    cur = None
    for r in rows:
        cs = cells(r)
        if len(cs) >= 3 and cs[0] and cs[1].replace(".", "").isdigit():
            cur = cs[0]
            out[cur] = {"dps": float(cs[1]), "total": cs[2], "grade": cs[3] if len(cs) > 3 else ""}
        elif cur and len(cs) >= 2 and cs[0] in ("技能持续", "持续", "攻击间隔", "DPH", "模组"):
            out[cur][cs[0]] = cs[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ArkDPS 公式复刻与独立复核")
    ap.add_argument("--list", action="store_true", help="列出可复刻的干员/技能")
    ap.add_argument("--calibrate", action="store_true", help="求值器 vs 排行榜 DPS")
    ap.add_argument("--replicate", metavar="干员", help="复刻指定干员")
    args = ap.parse_args()

    formulas = load_formulas()
    ops = load_operators()
    bases = load_base_attacks()
    lb = load_leaderboard()
    name2code = {v["name"]: k for k, v in ops.items()}

    if args.list:
        for code, lines in sorted(formulas.items()):
            name = ops.get(code, {}).get("name", "?")
            skills = sorted({s for sk in lines.values() for s in sk})
            print(f"{code} {name:10} {'/'.join(lines)}  {','.join(skills)}")
        print(f"\n共 {len(formulas)} 个代号有公式；排行榜 {len(lb)} 条")
        return 0

    if args.calibrate:
        ok = bad = err = 0
        diffs = []
        hits = []
        dmods = load_default_modules()
        for key, row in lb.items():
            m = re.match(r"(.+?)(\d)(.+)$", key)
            if not m:
                continue
            name, sk = m.group(1), m.group(2)
            code = name2code.get(name)
            if not code or code not in formulas:
                continue
            default_line = dmods.get(code) or next(iter(formulas[code]))
            line = default_line
            skmap = formulas[code].get(line) or {}
            f = skmap.get(f"skill{sk}")
            if not f:
                # 默认模组线可能没有公式（如逻各斯默认 Δ 线），回退到有公式的线
                for alt, amap in formulas[code].items():
                    cand = amap.get(f"skill{sk}")
                    if cand and (cand["raw"] or cand["modes"]):
                        line, f = alt, cand
                        break
            if not f:
                continue
            if line != default_line:
                # 回退线只用于我方复核，不参与「求值器 vs 排行榜」校准
                # （排行榜的该行对应的是默认线场景，换线后 BaseAttack 不同，不可比）
                continue
            got = solve_formula(f, bases, code, line, target=row["dps"])
            if not got:
                err += 1
                print(f"[ERR] {key} {line}: 无法求值")
                continue
            mode, minor, v = got
            tag = f"{line}{('·' + mode) if mode else ''}{f'·副{minor}' if minor else ''}"
            if abs(v - row["dps"]) <= max(1.0, row["dps"] * 0.02):
                ok += 1
                hits.append((key, tag, row["dps"], v))
            else:
                bad += 1
                diffs.append((key, tag, row["dps"], v, v / row["dps"]))
        diffs.sort(key=lambda d: abs(d[4] - 1), reverse=True)
        for d in diffs:
            print(f"[DIFF] {d[0]:28} {d[1]:<12} 站点 {d[2]:>7} 复刻 {d[3]:>9.1f} 比值 {d[4]:.2f}")
        calib = OUT / "review" / "arkdps-calibration.json"
        calib.parent.mkdir(parents=True, exist_ok=True)
        calib.write_text(json.dumps(
            {k: {"lineModeMinor": t, "siteDps": s, "reproDps": round(v, 2)}
             for k, t, s, v in hits}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n校准命中写入 {calib.relative_to(ROOT)}（{len(hits)} 条）")
        print(f"\n吻合 {ok} / 偏差 {bad} / 异常 {err}")
        return 0

    if args.replicate:
        name = args.replicate
        code = name2code.get(name)
        if not code:
            print(f"{name} 不在 ArkDPS（走描述参照/裁定分支）")
            return 1
        for line, skmap in formulas.get(code, {}).items():
            for sid, f in sorted(skmap.items()):
                if not f["raw"]:
                    continue
                try:
                    ast = Parser(tokenize(f["raw"])).parse()
                    v = evaluate(ast, make_env(bases, code, line))
                    print(f"{code} {line} {sid}: {v:.1f}")
                except Exception as e:  # noqa: BLE001
                    print(f"{code} {line} {sid}: ERR {e}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

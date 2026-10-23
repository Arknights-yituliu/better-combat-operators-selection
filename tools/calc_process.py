# -*- coding: utf-8 -*-
"""计算过程详情（calc）与帧级时间轴（timelines）的读入、展开、校验与写出。

真源：`agent_workspace/tag_pipeline/calc_process/<干员>.json`（一干员一文件）。
产物：`results/operator-timelines.json`（由 `--emit` 写出；`operator-tags.json` 的成员只带
`calc.timeline` 引用与分步 `steps`，见 `docs/calc-process-spec.md`）。

数据分三层，时间轴与应用它的成员分开存：

- **时间轴**（`timelines.<name>`）：一条技能一次演算的帧级事件池，按 `scenarios`（情形）分组。
  `series[]` 是**数据单元**（`key`），`group` 是**图例单位**——同一 group 的多条 series 在图上
  合并为一条曲线、图例只出现一次（如逻各斯「每次攻击本身造成的法术伤害」由主攻击＋法术附加＋
  第二天赋固定点三条 series 组成）。
- **成员规则**（`members[]`）：`(tag, match, timeline, metric, scenarios)`；`match` 与清洗后的
  `condition` 前缀比对，定位到具体成员行。生成器按此写入成员 `calc`。
- **步骤**（`scenarios.<id>[].steps`）：分步算式，`section` 分组、`expr` 只放算式、`note` 只放注释。

pattern 只存在于撰写源；展开后产物里永远是显式 `events: [[frame, damage, hits], ...]`。

用法：
    .venv/Scripts/python.exe -X utf8 tools/calc_process.py --check   # 校验（含数值对账）
    .venv/Scripts/python.exe -X utf8 tools/calc_process.py --emit    # 写 results/operator-timelines.json
    .venv/Scripts/python.exe -X utf8 tools/calc_process.py --show 克莱门莎   # 打印某干员展开结果
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIPE = ROOT / "agent_workspace" / "tag_pipeline"
SRC_DIR = PIPE / "calc_process"
OUT_FILE = ROOT / "results" / "operator-timelines.json"
RESULTS_FILE = ROOT / "results" / "operator-tags.json"

FPS = 30
DAMAGE_TYPES = ("physical", "art", "element", "true", "fixed")
# 颜色角色：图例按伤害类型取色（docs/calc-process-spec.md §2.1）。
# 与 damageType 不同——它区分元素损伤的四个子类，并把 fixed（固定值附伤）按实际类型归类。
COLOR_ROLES = ("physical", "art", "true", "weakpoint", "element", "apoptosis", "burn", "neural", "erosion")
TOP_KEYS = ("operator", "timelines", "members")
MEMBER_KEYS = ("tag", "match", "subTag", "timeline", "metric", "scenarios", "note", "scoreNames", "expected", "scenarioNames")
STEP_KEYS = ("section", "title", "expr", "result", "unit", "note")
TL_KEYS = ("fps", "scenarios")
SCENARIO_KEYS = ("id", "name", "durationFrames", "panel", "series")
SERIES_KEYS = ("key", "group", "groupDesc", "label", "damageType", "colorRole", "pattern", "events")
CALC_SCENARIO_KEYS = ("id", "name", "steps")

# 图例短名上限（含标点）：整句一律不合格，见 docs/calc-process-spec.md §2.1
GROUP_MAX = 12

# expr 只放算式：这些自然语言词不得出现（单位/函数名白名单另见 EXPR_OK_WORDS）
EXPR_BAD_WORDS = ("因为", "所以", "其中", "按", "即", "见", "详见", "此时", "因此", "取整", "含首击")

# 数字守恒：抽取源「计算」块里的数字令牌（`文件:行号` 证据先摘掉）
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
EV_RE = re.compile(r"[；，、]?\s*[^（）()；。\s]*\.md:\d[\d,\-–\s]*")
# 只取「计算」块：备注单元格里 `｜计算：…` 到下一个 `｜` 之前
CALC_BLOCK_RE = re.compile(r"(?:^|｜)\s*计算[：:].*?(?=｜|$)")

PROBLEMS: list[str] = []


def problem(msg: str) -> None:
    PROBLEMS.append(msg)


# ---------------------------------------------------------------- 读取

def load_file(path: pathlib.Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["_file"] = path.name
    return doc


def load_all() -> list[dict]:
    """读 calc_process/*.json（按文件名排序，保证输出稳定）。"""
    if not SRC_DIR.is_dir():
        return []
    return [load_file(p) for p in sorted(SRC_DIR.glob("*.json"))]


# ---------------------------------------------------------------- pattern 展开

def _segments_damage(segments: list[dict], frame: int) -> float:
    """按 `untilFrame` 升序匹配首个 frame < untilFrame 的分段；无 untilFrame 的是兜底段。"""
    for seg in segments:
        until = seg.get("untilFrame")
        if until is None or frame < until:
            return float(seg["damage"])
    return float(segments[-1]["damage"])


def expand_pattern(pattern: dict) -> list[list]:
    """pattern → [[frame, damage, hits], ...]（升序、整帧）。

    支持四型：
    - list：`events` 原样（撰写侧手算/状态机输出）。
    - periodic：`startFrame` 起每 `intervalFrames` 一次，共 `count` 次；伤害取 `segments` 分段
      或固定 `damage`。
    - periodicInWindows：每个 `[start, end]` 窗口内从 start 起每 `intervalFrames` 一次，
      至多 `countPerWindow` 次；伤害固定 `damage`。
    - windowsPerSecond：每个窗口内每秒 1 次持续点伤（`perSecond`）；尾帧按窗口内剩余时长折算
      比例（如 800/秒 × 22.6 秒 = 18080）。
    """
    kind = pattern.get("type")
    out: list[list] = []
    if kind == "list":
        for ev in pattern.get("events", []):
            frame, damage = int(ev[0]), float(ev[1])
            hits = int(ev[2]) if len(ev) > 2 else 1
            out.append([frame, round(damage, 4), hits])
    elif kind == "periodic":
        start = int(pattern.get("startFrame", 0))
        interval = int(pattern["intervalFrames"])
        segments = pattern.get("segments")
        for i in range(int(pattern["count"])):
            frame = start + i * interval
            damage = _segments_damage(segments, frame) if segments else float(pattern["damage"])
            hits = int(pattern.get("hits", 1))
            out.append([frame, round(damage, 4), hits])
    elif kind == "periodicInWindows":
        interval = int(pattern["intervalFrames"])
        per = int(pattern.get("countPerWindow", 3))
        for start, end in pattern["windows"]:
            for i in range(per):
                frame = int(start) + i * interval
                if frame > int(end):
                    break
                out.append([frame, round(float(pattern["damage"]), 4), int(pattern.get("hits", 1))])
    elif kind == "windowsPerSecond":
        per_second = float(pattern["perSecond"])
        for start, end in pattern["windows"]:
            start, end = int(start), int(end)
            span = end - start
            # 每秒结算一次：整数秒按整次，余数按比例折算（与「覆盖 22.6 秒 × 800」同口径）
            whole, rest = divmod(span, FPS)
            for i in range(whole):
                out.append([start + i * FPS, round(per_second, 4), int(pattern.get("hits", 0))])
            if rest:
                out.append([start + whole * FPS, round(per_second * rest / FPS, 4), int(pattern.get("hits", 0))])
    else:
        raise ValueError(f"未知 pattern 类型：{kind!r}")
    out.sort(key=lambda e: (e[0],))
    return out


def expand_series(series: dict) -> list[list]:
    if "events" in series:
        return expand_pattern({"type": "list", "events": series["events"]})
    return expand_pattern(series["pattern"])


def expand_scenario(sc: dict) -> dict:
    series = []
    for s in sc["series"]:
        series.append({
            "key": s["key"],
            "group": s.get("group") or s.get("label") or s["key"],
            "groupDesc": s.get("groupDesc") or s.get("group") or s.get("label") or s["key"],
            "label": s.get("label") or s["key"],
            "damageType": s["damageType"],
            "colorRole": s["colorRole"],
            "events": expand_series(s),
        })
    return {
        "id": sc["id"],
        "name": sc["name"],
        "durationFrames": int(sc["durationFrames"]),
        "panel": sc.get("panel"),
        "series": series,
    }


def expand_timeline(tl: dict) -> dict:
    return {"fps": int(tl.get("fps", FPS)), "scenarios": [expand_scenario(s) for s in tl["scenarios"]]}


def timeline_key(operator: str, name: str) -> str:
    return f"{operator}@{name}"


def build_timelines(docs: list[dict]) -> dict[str, dict]:
    """全部撰写源 → 产物 timelines（键 `干员@名称`）。"""
    out: dict[str, dict] = {}
    for doc in docs:
        op = doc["operator"]
        for name, tl in (doc.get("timelines") or {}).items():
            key = timeline_key(op, name)
            if key in out:
                problem(f"{doc['_file']}：时间轴重复定义 {key}")
                continue
            out[key] = expand_timeline(tl)
    return out


# ---------------------------------------------------------------- 成员规则与应用

def build_rules(docs: list[dict]) -> list[dict]:
    rules: list[dict] = []
    for doc in docs:
        op = doc["operator"]
        for m in doc.get("members") or []:
            rule = dict(m)
            rule["operator"] = op
            rule["_file"] = doc["_file"]
            rule["_timeline"] = timeline_key(op, m["timeline"]) if m.get("timeline") else None
            rules.append(rule)
    return rules


def build_calc(rule: dict) -> dict:
    """规则 → 成员 calc 字段（不含展开后的事件，只带引用与步骤）。"""
    calc: dict = {"metric": rule.get("metric") or "damage"}
    if rule.get("_timeline"):
        calc["timeline"] = rule["_timeline"]
    calc["scenarios"] = [
        {"id": sid, "name": name, "steps": [dict(st) for st in steps]}
        if name else {"id": sid, "steps": [dict(st) for st in steps]}
        for sid, steps in (rule.get("scenarios") or {}).items()
        for name in [(rule.get("scenarioNames") or {}).get(sid)]
    ]
    if rule.get("note"):
        calc["note"] = rule["note"]
    return calc


def subtag_set(tag_no: str, h3: str, h4: str) -> set[str]:
    """成员表所在子表 → 该行可能的子 TAG 取值集合（与 generate_results.player_subtags 同源规则）。

    用于在「同 TAG 同干员同条件」的多行之间消歧：同一行可能同时属于多个子 TAG。
    """
    out: set[str] = set()
    h3 = (h3 or "").strip()
    h4 = (h4 or "").strip()
    if tag_no in ("02", "03", "07", "13"):
        for v in re.split(r"[、＋+]", h3):
            v = v.strip()
            if v:
                # P04 的表标题形如「表 1 · 超远距离打击（本体 / …）」：取「·」之后、括号之前
                v = re.sub(r"^表\s*\d+\s*·\s*", "", v)
                v = re.sub(r"[（(].*$", "", v).strip()
                if v:
                    out.add(v)
    if tag_no == "09":
        m = re.match(r"[一二三四五六七八九十]+、([^（(]+)", h3)
        if m:
            out.add(m.group(1).strip())
    if tag_no in ("05", "13") and h4:
        out.add(h4.strip())
    return out


def match_rule(rule: dict, tag_no: str, operator: str, condition: str, subtags: set[str] | list[dict] | None = None) -> bool:
    """规则 → 成员行判定。

    同一干员在同一 TAG 下可能有**条件完全相同**的多行（分属不同子 TAG，如 P13 的「硬控」与
    「软控」），仅靠 `match` 前缀无法区分。规则可加 `subTag`（子 TAG 的 value）进一步定位。
    `subtags` 可传 set[str]，也可传成员对象的 `subTags` 数组。
    """
    if rule["tag"] != tag_no or rule["operator"] != operator:
        return False
    prefix = (rule.get("match") or "").strip()
    if prefix and not condition.startswith(prefix):
        return False
    want = (rule.get("subTag") or "").strip()
    if want:
        raw = subtags or []
        if raw and isinstance(next(iter(raw)), dict):
            have = {str(s.get("value") or "") for s in raw}
        else:
            have = set(raw)
        if want not in have:
            return False
    return True


# ---------------------------------------------------------------- 校验

def collect_timelines(docs: list[dict], results: dict | None) -> dict[str, dict]:
    """展开后的时间轴，只保留产物成员真正引用的那些（键 `干员@名称`）。"""
    all_tl = build_timelines(docs)
    used = collect_used_timelines(docs, results)
    return {k: all_tl[k] for k in used if k in all_tl}


def validate(docs: list[dict], results: dict | None, baseline: str = "HEAD") -> list[str]:
    """校验撰写源（含数值对账、数字守恒）；返回问题列表（不抛异常）。"""
    global PROBLEMS
    PROBLEMS = []
    _validate(docs, results, baseline)
    return list(PROBLEMS)


def _validate(docs: list[dict], results: dict | None, baseline: str = "HEAD") -> None:
    timelines = build_timelines(docs)
    rules = build_rules(docs)
    member_index: dict[tuple[str, str], list[dict]] = {}
    if results:
        for t in results.get("tags", []):
            tid = t.get("id", "")
            if tid == "P12":
                continue
            for m in t.get("members", []):
                member_index.setdefault((tid, m.get("operator", "")), []).append(m)

    # ---- 结构
    for doc in docs:
        extra = set(doc) - set(TOP_KEYS) - {"_file"}
        if extra:
            problem(f"{doc['_file']}：规范之外的顶层字段 {sorted(extra)}")
        if not doc.get("operator"):
            problem(f"{doc['_file']}：缺少 operator")
        for name, tl in (doc.get("timelines") or {}).items():
            extra = set(tl) - set(TL_KEYS)
            if extra:
                problem(f"{doc['_file']}｜{name}：规范之外的字段 {sorted(extra)}")
            ids = []
            groups: list[str] = []
            group_roles: dict[str, str] = {}
            for sc in tl.get("scenarios") or []:
                extra = set(sc) - set(SCENARIO_KEYS)
                if extra:
                    problem(f"{doc['_file']}｜{name}｜{sc.get('id')}：规范之外的字段 {sorted(extra)}")
                ids.append(sc.get("id"))
                for s in sc.get("series") or []:
                    extra = set(s) - set(SERIES_KEYS) - {"hits"}
                    if extra:
                        problem(f"{doc['_file']}｜{name}｜{sc.get('id')}｜{s.get('key')}：规范之外的字段 {sorted(extra)}")
                    if s.get("damageType") not in DAMAGE_TYPES:
                        problem(f"{doc['_file']}｜{s.get('key')}：damageType 应为 {'/'.join(DAMAGE_TYPES)}")
                    if s.get("colorRole") not in COLOR_ROLES:
                        problem(f"{doc['_file']}｜{s.get('key')}：colorRole 必填，应为 {'/'.join(COLOR_ROLES)}"
                                f"（当前 {s.get('colorRole')!r}）")
                    if "pattern" not in s and "events" not in s:
                        problem(f"{doc['_file']}｜{s.get('key')}：缺少 pattern/events")
                    group = s.get("group") or s.get("label") or s.get("key")
                    if group not in groups:
                        groups.append(group)
                        if len(group) > GROUP_MAX:
                            problem(f"{doc['_file']}｜{name}｜图例「{group}」超过 {GROUP_MAX} 字，"
                                    f"应写短名并把完整语义放进 groupDesc")
                        if not s.get("groupDesc") and s.get("group"):
                            problem(f"{doc['_file']}｜{name}｜图例「{group}」缺 groupDesc（完整语义）")
                    # 图例才是配色单位：同一时间轴内同一 group 的各条 series 必须同色角色
                    prev = group_roles.setdefault(group, s.get("colorRole"))
                    if s.get("colorRole") != prev:
                        problem(f"{doc['_file']}｜{name}｜图例「{group}」内 colorRole 不一致："
                                f"{prev!r} 与 {s.get('colorRole')!r}")
            if len(set(ids)) != len(ids):
                problem(f"{doc['_file']}｜{name}：scenario id 重复")
        for m in doc.get("members") or []:
            extra = set(m) - set(MEMBER_KEYS) - {"_file", "_timeline", "operator"}
            if extra:
                problem(f"{doc['_file']}｜{m.get('tag')}/{m.get('match')}：规范之外的字段 {sorted(extra)}")
            if not re.fullmatch(r"P\d+", m.get("tag", "")):
                problem(f"{doc['_file']}：tag 应形如 P01（当前 {m.get('tag')!r}）")
            if m.get("metric") not in (None, "damage", "hits"):
                problem(f"{doc['_file']}：metric 应为 damage/hits")
            if m.get("timeline"):
                key = timeline_key(doc["operator"], m["timeline"])
                if key not in timelines:
                    problem(f"{doc['_file']}：时间轴引用不存在 {key}")
                else:
                    have = {sc["id"] for sc in timelines[key]["scenarios"]}
                    want = set((m.get("scenarios") or {}).keys())
                    # 时间轴里的情形必须都有步骤；步骤可以有多余情形（无图、只出分步算式，
                    # 如 P02 同时覆盖 2 技能与 3 技能，而时间轴只建了 3 技能）
                    if have - want:
                        problem(f"{doc['_file']}｜{m['tag']}：时间轴情形 {sorted(have - want)} 缺步骤")
                    names = m.get("scenarioNames") or {}
                    for sid in sorted(want - have):
                        if not names.get(sid):
                            problem(f"{doc['_file']}｜{m['tag']}：无图情形「{sid}」缺 scenarioNames 名称")
            for sid, steps in (m.get("scenarios") or {}).items():
                _check_steps(doc["_file"], m, sid, steps)
            # 无时间轴的条目：多情形时必须有情形名（否则页面只能显示 normal / leader 这类 id）
            if not m.get("timeline") and len(m.get("scenarios") or {}) > 1:
                names = m.get("scenarioNames") or {}
                for sid in (m.get("scenarios") or {}):
                    if not names.get(sid):
                        problem(f"{doc['_file']}｜{m.get('tag')}：无时间轴且多情形，"
                                f"情形「{sid}」缺 scenarioNames 名称")

    # ---- 每条规则恰好命中一条成员行
    for rule in rules:
        hits = [m for m in member_index.get((rule["tag"], rule["operator"]), [])
                if match_rule(rule, rule["tag"], rule["operator"], m.get("condition", ""), m.get("subTags"))]
        # 条件字节相同、源计算块也相同的重复行（同一干员同 TAG 跨子 TAG 共用一份演算）：
        # 一条规则覆盖多行是允许的——只要这些行的 condition 完全一致。
        conds = {m.get("condition", "") for m in hits}
        if len(hits) != 1 and len(conds) != 1:
            problem(f"{rule['_file']}｜{rule['tag']}/{rule.get('match')}：命中 {len(hits)} 条成员（应恰好 1 条）")

    # ---- 数值对账
    for rule in rules:
        if not rule.get("_timeline"):
            continue
        tl = timelines[rule["_timeline"]]
        expect = score_expectations(rule, member_index)
        for sc in tl["scenarios"]:
            total = sum(ev[1] for s in sc["series"] for ev in s["events"])
            hits = sum(ev[2] for s in sc["series"] for ev in s["events"])
            if rule["metric"] == "hits" or rule["tag"] == "P02":
                if sc["id"] in expect["hits"]:
                    want = expect["hits"][sc["id"]]
                    if abs(hits - want) > max(1, want * 0.005):
                        problem(f"{rule['_file']}｜{rule['tag']}｜{sc['id']}：段数 {hits} 与成绩 {want} 不符")
            if sc["id"] in expect["damage"]:
                want = expect["damage"][sc["id"]]
                if want and abs(total - want) > max(1.0, want * 0.005):
                    problem(f"{rule['_file']}｜{rule['tag']}｜{sc['id']}：总伤 {total:.1f} 与成绩 {want} 不符")
            for s in sc["series"]:
                for frame, _dmg, _h in s["events"]:
                    if frame < 0 or frame > sc["durationFrames"]:
                        problem(f"{rule['_file']}｜{sc['id']}｜{s['key']}：事件帧 {frame} 越界 [0, {sc['durationFrames']}]")
                        break


    # ---- 数字守恒：源「计算」块（或 git HEAD 的迁移前原文）的每个数字都要落到 steps/events
    source_calcs = load_source_calcs()
    for rule in rules:
        if rule.get("tag") == "P12":
            continue
        hit = None
        for (tid, op, cond), text in source_calcs.items():
            if tid == rule["tag"] and op == rule["operator"] and match_rule(rule, tid, op, cond, _SUBSETS.get((tid, op, cond))):
                hit = text
                break
        if hit is None and baseline:
            tag_no = rule["tag"][1:]
            for _no, _nm, path in _player_files_cached():
                if _no == tag_no:
                    rel = path.relative_to(ROOT).as_posix()
                    hit = git_calc_text(rel, rule["operator"], _first_cond(rule, member_index))
                    break
        if not hit:
            continue
        missing = check_number_conservation(rule, hit, timelines)
        if missing:
            problem(f"{rule['_file']}｜{rule['tag']}/{rule.get('match')}："
                    f"数字守恒缺 {len(missing)} 个：{sorted(set(missing))[:12]}")


def _player_files_cached() -> list[tuple[str, str, pathlib.Path]]:
    global _PLAYER_FILES
    if _PLAYER_FILES is None:
        sys.path.insert(0, str(PIPE))
        import partdoc  # noqa: PLC0415

        _PLAYER_FILES = partdoc.player_files()
    return _PLAYER_FILES


def _first_cond(rule: dict, member_index: dict) -> str:
    hits = member_index.get((rule["tag"], rule["operator"]), [])
    for m in hits:
        if match_rule(rule, rule["tag"], rule["operator"], m.get("condition", ""), m.get("subTags")):
            return m.get("condition", "")
    return ""


_PLAYER_FILES: list[tuple[str, str, pathlib.Path]] | None = None


def _check_steps(file: str, member: dict, scenario_id: str, steps: list[dict]) -> None:
    if not steps:
        problem(f"{file}｜{member.get('tag')}｜{scenario_id}：步骤为空")
        return
    section = None
    for st in steps:
        extra = set(st) - set(STEP_KEYS)
        if extra:
            problem(f"{file}｜{member.get('tag')}｜{scenario_id}：规范之外的步骤字段 {sorted(extra)}")
        if not st.get("expr") and not st.get("result"):
            problem(f"{file}｜{member.get('tag')}｜{scenario_id}：步骤缺 expr 与 result")
        expr = st.get("expr") or ""
        for w in EXPR_BAD_WORDS:
            if w in expr:
                problem(f"{file}｜{member.get('tag')}｜{scenario_id}：expr 含自然语言「{w}」：{expr[:30]}")
        if st.get("section"):
            section = st["section"]
    if section is None:
        problem(f"{file}｜{member.get('tag')}｜{scenario_id}：没有任何分节（section）")


# 「成绩」块文本 → {「普通/精英」: 总伤} 之类的期望值；只做粗对账，取块里的第一个 ≈N。
DAMAGE_RE = re.compile(r"总伤\s*≈?\s*(\d+(?:\.\d+)?)")
SEG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*段")


_SUBSETS: dict[tuple[str, str, str], set[str]] = {}


def load_source_calcs() -> dict[tuple[str, str, str], str]:
    """读分文件成员表 → {(TAG id, 干员, condition): 「计算」块原文}。

    源侧已删除「计算」块的条目不在返回里（数字守恒改走 git 历史，见 `git_calc_text`）。
    """
    sys.path.insert(0, str(PIPE))
    import partdoc  # noqa: PLC0415

    out: dict[tuple[str, str, str], str] = {}
    for tag_no, _tag_name, path in partdoc.player_files():
        if tag_no == "12":
            continue
        doc = partdoc.load(path)
        for _h3, _h4, header, rows, _bi in partdoc.member_tables(doc):
            if "条件" not in header or "备注" not in header:
                continue
            ci, ni = header.index("条件"), header.index("备注")
            for cells in rows:
                if len(cells) <= max(ci, ni):
                    continue
                text = calc_block_text(cells[ni])
                if text:
                    key = (f"P{tag_no}", cells[0].strip(), cells[ci].strip())
                    out[key] = text
                    subs = subtag_set(tag_no, _h3, _h4)
                    if subs:
                        _SUBSETS.setdefault(key, set()).update(subs)
    return out


def git_calc_text(git_path: str, operator: str, condition: str) -> str:
    """从 git HEAD 侧取迁移前的「计算」块（源已删除时用）。"""
    import subprocess  # noqa: PLC0415

    r = subprocess.run(["git", "show", f"HEAD:{git_path}"], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return ""
    try:
        doc = json.loads(r.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ""
    sys.path.insert(0, str(PIPE))
    import partdoc  # noqa: PLC0415

    text = partdoc.render(doc)
    # 用同一套表格解析：按行找「干员｜…｜条件｜…｜备注」
    header = None
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if header is None and "条件" in cells and "备注" in cells:
            header = cells
            continue
        if header is None or len(cells) != len(header):
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if cells[0].replace("**", "").strip() == operator and cells[header.index("条件")].strip() == condition:
            return calc_block_text(cells[header.index("备注")])
    return ""


def _score_texts(results: dict | None, tag_id: str, operator: str) -> list[tuple[str, str]]:
    """返回该成员的成绩块（情形名, 正文）列表。"""
    out = []
    if not results:
        return out
    for t in results.get("tags", []):
        if t.get("id") != tag_id:
            continue
        for m in t.get("members", []):
            if m.get("operator") != operator:
                continue
            for b in m.get("remark") or []:
                label = b.get("label") or ""
                if label.startswith("成绩"):
                    out.append((label[len("成绩"):].strip(), "；".join(i.get("text", "") for i in b.get("items", []))))
    return out


def score_expectations(rule: dict, member_index: dict) -> dict:
    """规则 → 对账期望（按情形 id）。

    两条来源：① `scoreNames` 把情形 id 映射到成绩块的情形名，从正文里取第一个「总伤 ≈N」「N 段」；
    ② `expected` 直接写死期望值（成绩块把多情形挤在一句里、无法按名取数时用）。
    """
    expect = {"damage": {}, "hits": {}}
    scores = _score_texts(RESULTS, rule["tag"], rule["operator"])
    by_name = {name: text for name, text in scores}
    mapping = rule.get("scoreNames") or {}
    for sid in (rule.get("scenarios") or {}).keys():
        name = mapping.get(sid)
        text = by_name.get(name) if name is not None else None
        if text is None:
            continue
        m = DAMAGE_RE.search(text)
        if m and rule.get("metric", "damage") == "damage":
            expect["damage"][sid] = float(m.group(1))
        m = SEG_RE.search(text)
        if m and (rule.get("metric") == "hits" or rule["tag"] == "P02"):
            expect["hits"][sid] = float(m.group(1))
    for kind, by_sid in (rule.get("expected") or {}).items():
        if kind in expect:
            for sid, val in by_sid.items():
                expect[kind][sid] = float(val)
    return expect


# ---------------------------------------------------------------- 数字守恒（源「计算」块 → steps/events）

def strip_calc_blocks(cell: str) -> str:
    """从备注单元格里剥掉 `｜计算：…` 段，返回其余文本（供审计与守恒比对）。"""
    return CALC_BLOCK_RE.sub("", cell or "")


def calc_block_text(cell: str) -> str:
    """取备注单元格里的「计算」块正文（无则空串）。"""
    hits = CALC_BLOCK_RE.findall(cell or "")
    return "；".join(h.strip().lstrip("｜").lstrip() for h in hits)


def _numbers(text: str) -> list[float]:
    return [float(x) for x in NUM_RE.findall(EV_RE.sub("", text or ""))]


def _step_text(rule: dict) -> str:
    parts = [rule.get("note") or ""]
    for steps in (rule.get("scenarios") or {}).values():
        for st in steps:
            parts += [st.get("expr") or "", st.get("result") or "", st.get("unit") or "",
                      st.get("note") or "", st.get("title") or ""]
    return "；".join(parts)


#: 独立复核中确认并更正的旧数字：源「计算」块里的这些值本身有误，迁移后的步骤写的是正确值。
#: 数字守恒对它们放行（必须写明原因）；新增条目需附复核依据。
CORRECTIONS: dict[tuple[str, str], dict] = {
    ("斩业星熊", "P01"): {
        "numbers": {"264.8", "291.28", "26.48", "11968.96", "95991",
                    "3071.68", "20257.2", "162463", "9479.84"},
        "reason": "满血档每击倍率把 2648 点误写成 264.8%（按面板应为 330%），连带总伤与 15 秒窗口重算；"
                  "窗口另按 15×30÷48＝9 轮（原写 10 击）校正",
    },
    ("艾雅法拉", "P01"): {
        "numbers": {"13", "34.6", "8610", "69913"},
        "reason": "2026-10-22 裁定（B）：基础攻击间隔按游戏数据 49 帧（1.6333 秒），Y 模组攻速 +15 后为 14 帧、"
                  "32 下；旧 13 帧/34.6/8610/69913 随旧帧模型删除（实测与 ArkDPS 一致）",
    },
    ("仇白", "P01"): {
        "numbers": {"12792", "108604"},
        "reason": "2026-10-22 裁定（B）：按 ArkDPS/实测取 46 击（首击 t＝1.0 秒），总伤 108604→104079；"
                  "旧 48 击的 12792%、108604 随旧口径删除",
    },
    ("逻各斯", "P01"): {
        "numbers": {"3.2", "6.4", "9.0", "11.4", "16.2", "18.2", "21.4", "22.4", "22.6",
                    "30.4", "65.0", "114.6", "260.0", "400.0", "401.0", "1440.0", "2160.0",
                    "2964.0", "5004.0", "5016.0", "6300.0", "7600.0", "12724.0", "12960.0",
                    "18080.0", "102634.0", "108790.0", "113806.0", "120610.0", "131886.0"},
        "reason": "2026-10-22 裁定（B）：按 ArkDPS 的 Δ 模组公式重写（逐击 4915.2、凋亡累积 393.2、"
                  "爆条按 10/15 秒不可累积并按攻击帧对齐、元素持续按 floor(15×次数)）；旧分项与总伤"
                  "（131886/120610）随旧写法删除",
    },
}


def check_number_conservation(rule: dict, source_calc: str, timelines: dict) -> list[str]:
    """源「计算」块的每个数字都要能在 steps（含 note/result）或时间轴事件里找到（±1%）。

    返回缺失的数字（字符串）。源块为空（已迁移并删除）时由调用方跳过。
    """
    if not source_calc.strip():
        return []
    allowed = CORRECTIONS.get((rule.get("operator", ""), rule.get("tag", "")), {}).get("numbers", set())
    have = _numbers(_step_text(rule))
    for s in (timelines.get(rule.get("_timeline")) or {}).get("scenarios", []):
        for ser in s.get("series", []):
            for ev in ser.get("events", []):
                have.append(float(ev[1]))
                have.append(float(ev[0]))
                if len(ev) > 2:
                    have.append(float(ev[2]))
    missing = []
    for raw in _numbers(source_calc):
        if any(abs(raw - float(a)) <= 1e-9 for a in allowed):
            continue
        if not any(abs(raw - h) <= max(1e-9, abs(raw) * 0.01) for h in have):
            missing.append(raw)
    return missing


RESULTS: dict | None = None


# ---------------------------------------------------------------- CLI

def collect_used_timelines(docs: list[dict], results: dict | None) -> list[str]:
    """只保留真正被产物里的成员引用的时间轴（未迁移的规则不写进产物）。"""
    used: list[str] = []
    if not results:
        return used
    for t in results.get("tags", []):
        for m in t.get("members", []):
            provs = m.get("providers") or []
            for holder in [m] + provs:
                calc = holder.get("calc") or {}
                key = calc.get("timeline")
                if key and key not in used:
                    used.append(key)
    return used


def _pending() -> list[str]:
    """仍有「计算」块、尚无 calc 的成员（按 TAG 分组）。

    以「TAG＋干员＋条件」为键——同一干员在同一 TAG 下可有多行（不同技能/子 TAG），
    只按「TAG＋干员」去重会漏掉第二行。
    """
    source = load_source_calcs()
    covered: set[tuple[str, str, str]] = set()
    if RESULTS:
        for t in RESULTS.get("tags", []):
            for m in t.get("members", []):
                if m.get("calc"):
                    covered.add((t.get("id", ""), m.get("operator", ""), m.get("condition", "")))
    rules = build_rules(load_all())
    rows = []
    for (tid, op, cond), _text in sorted(source.items()):
        if (tid, op, cond) in covered:
            continue
        # 已被某条规则覆盖（规则命中的条件前缀）也算已迁移
        subs = _SUBSETS.get((tid, op, cond)) or set()
        if any(match_rule(r, tid, op, cond, subs) for r in rules):
            continue
        rows.append(f"{tid}\t{op}\t{cond[:70]}")
    return rows


def _find_member_rows(tag_id: str, operator: str) -> list[tuple[str, list[str], dict]]:
    """(tag_no, cells, doc) —— 分文件里该干员在指定 TAG 的成员行（已清洗前原值）。"""
    tag_no = tag_id[1:]
    out = []
    for no, _nm, path in _player_files_cached():
        if no != tag_no:
            continue
        sys.path.insert(0, str(PIPE))
        import partdoc  # noqa: PLC0415

        doc = partdoc.load(path)
        for _h3, _h4, header, rows, _bi in partdoc.member_tables(doc):
            if cells_ok(header):
                ci = header.index("条件")
                for cells in rows:
                    if cells and cells[0].strip() == operator:
                        out.append((tag_no, cells, doc))
    return out


def cells_ok(header: list[str]) -> bool:
    return "条件" in header and "备注" in header


def _show_entry(tag_id: str, operator: str) -> int:
    rows = _find_member_rows(tag_id, operator)
    if not rows:
        print(f"未找到 {tag_id}｜{operator} 的成员行")
        return 1
    for _no, cells, doc in rows:
        header = _header_of(doc, cells)
        cond = cells[header.index("条件")] if header and "条件" in header else ""
        note = cells[header.index("备注")] if header and "备注" in header else ""
        print(f"== {tag_id}｜{operator} ==")
        print(f"条件：{cond}")
        print("备注里的「计算」块：")
        print("  " + (calc_block_text(note) or "（无）"))
        print("成绩块：")
        for part in (note or "").split("｜"):
            if part.strip().startswith("成绩"):
                print("  " + part.strip()[:300])
    return 0


def _header_of(doc: dict, cells: list[str]) -> list[str] | None:
    for _h3, _h4, header, rows, _bi in partdoc_member_tables(doc):
        for r in rows:
            if r is cells:
                return header
    return None


def partdoc_member_tables(doc: dict):
    sys.path.insert(0, str(PIPE))
    import partdoc  # noqa: PLC0415

    return partdoc.member_tables(doc)


def _init(tag_id: str, operator: str) -> int:
    """从源「计算」块拆出草稿 steps，写入 calc_process/<干员>.json 的 members[] 骨架。"""
    rows = _find_member_rows(tag_id, operator)
    if not rows:
        print(f"未找到 {tag_id}｜{operator} 的成员行")
        return 1
    path = SRC_DIR / f"{operator}.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"operator": operator, "timelines": {}, "members": []}
    added = 0
    for _no, cells, src in rows:
        header = _header_of(src, cells)
        cond = cells[header.index("条件")] if header and "条件" in header else ""
        text = calc_block_text(cells[header.index("备注")] if header and "备注" in header else "")
        if not text:
            continue
        if any(m.get("tag") == tag_id and cond.startswith(m.get("match", "")) for m in doc["members"]):
            continue
        steps = []
        for i, part in enumerate(p for p in text.split("；") if p.strip()):
            seg = part.strip()
            expr, result = seg, ""
            if "＝" in seg:
                expr, result = seg.split("＝", 1)
            elif "=" in seg:
                expr, result = seg.split("=", 1)
            steps.append({"section": "① 草稿", "title": f"第 {i + 1} 条",
                          "expr": expr.strip(), "result": result.strip(), "note": "（草稿，需改写）"})
        doc["members"].append({"tag": tag_id, "match": cond[:24], "metric": "hits" if tag_id == "P02" else "damage",
                               "scenarios": {"default": steps}})
        added += 1
    if added:
        SRC_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已写入草稿 {path.relative_to(ROOT)}（新增 {added} 条；请改写 steps 后重跑 --check）")
    else:
        print("没有可拆的「计算」块（或该条目已存在）")
    return 0


def _strip(tag_id: str, operator: str) -> int:
    """从分文件源单元格删除该成员的「计算」块（其余块保留）。"""
    tag_no = tag_id[1:]
    changed = 0
    for no, _nm, path in _player_files_cached():
        if no != tag_no:
            continue
        sys.path.insert(0, str(PIPE))
        import partdoc  # noqa: PLC0415

        doc = partdoc.load(path)
        for _h3, _h4, header, rows, _bi in partdoc.member_tables(doc):
            if not cells_ok(header):
                continue
            ni = header.index("备注")
            for cells in rows:
                if cells and cells[0].strip() == operator and "计算" in cells[ni]:
                    before = cells[ni]
                    cells[ni] = strip_calc_blocks(before).strip("｜ ")
                    if cells[ni] != before:
                        changed += 1
        if changed:
            partdoc.save(doc, path)
            print(f"已从 {path.relative_to(ROOT)} 删除 {changed} 处「计算」块")
    if not changed:
        print(f"{tag_id}｜{operator}：源里没有可删的「计算」块")
    return 0


def main() -> int:
    global RESULTS, PROBLEMS
    ap = argparse.ArgumentParser(description="计算过程详情 / 帧级时间轴的校验与写出")
    ap.add_argument("--check", action="store_true", help="校验（含数值对账、数字守恒），不写盘")
    ap.add_argument("--emit", action="store_true", help="写 results/operator-timelines.json")
    ap.add_argument("--show", metavar="干员", help="打印某干员展开后的时间轴")
    ap.add_argument("--pending", action="store_true", help="列出仍有「计算」块、尚无 calc 的成员")
    ap.add_argument("--show-entry", nargs=2, metavar=("TAG", "干员"), help="打印该成员源「计算」块与成绩块")
    ap.add_argument("--init", nargs=2, metavar=("TAG", "干员"), help="从「计算」块拆出草稿 steps 写入源")
    ap.add_argument("--strip", nargs=2, metavar=("TAG", "干员"), help="删除源单元格里的「计算」块")
    ap.add_argument("--baseline", default="HEAD", help="数字守恒的 git 基准（默认 HEAD；空串关闭）")
    args = ap.parse_args()

    RESULTS = json.loads(RESULTS_FILE.read_text(encoding="utf-8")) if RESULTS_FILE.exists() else None

    if args.pending:
        rows = _pending()
        print(f"待迁移 {len(rows)} 条：")
        for r in rows:
            print("  " + r)
        return 0
    if args.show_entry:
        return _show_entry(args.show_entry[0], args.show_entry[1])
    if args.init:
        return _init(args.init[0], args.init[1])
    if args.strip:
        return _strip(args.strip[0], args.strip[1])

    docs = load_all()
    if not docs:
        print("calc_process/ 下没有文件")
        return 0 if args.check else 1
    PROBLEMS = validate(docs, RESULTS, args.baseline)

    print(f"撰写源 {len(docs)} 个文件：{', '.join(d['operator'] for d in docs)}")
    if args.show:
        timelines = build_timelines(docs)
        for key, tl in timelines.items():
            if key.startswith(args.show + "@"):
                print(f"\n== {key} ==")
                for sc in tl["scenarios"]:
                    print(f"  [{sc['id']}] {sc['name']}  {sc['durationFrames']} 帧")
                    for s in sc["series"]:
                        total = sum(e[1] for e in s["events"])
                        print(f"    {s['key']:<16} {s['group']:<24} {len(s['events']):>4} 事件  Σ={total:.1f}")

    if PROBLEMS:
        print(f"\n问题 {len(PROBLEMS)} 条：")
        for p in PROBLEMS:
            print("  " + p)
    else:
        print("校验：无问题")

    if args.check:
        return 1 if PROBLEMS else 0
    if args.emit:
        if PROBLEMS:
            print("存在问题，拒绝写出")
            return 1
        out = collect_timelines(docs, RESULTS) if RESULTS else build_timelines(docs)
        version = (RESULTS or {}).get("version", "v0")
        updated = (RESULTS or {}).get("updated", "")
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"version": version, "updated": updated, "timelines": out},
                          ensure_ascii=False, indent=2) + "\n"
        OUT_FILE.write_text(text.replace("\n", "\r\n"), encoding="utf-8")
        print(f"已写出 {OUT_FILE.relative_to(ROOT)}（{OUT_FILE.stat().st_size} 字节，{len(out)} 条时间轴）")
    return 0 if not PROBLEMS else 1


if __name__ == "__main__":
    raise SystemExit(main())

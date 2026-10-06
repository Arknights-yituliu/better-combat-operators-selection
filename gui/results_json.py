# -*- coding: utf-8 -*-
"""results/ 下的结果 JSON：文件名白名单、读写、按 docs/output-standard.md 的校验。"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
import urllib.parse

from .config import ROOT
from .errors import UserError
from .md import write_atomic

RESULTS_DIR = ROOT / "results"
NAME_RE = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,100}\.json$', re.IGNORECASE)
WIN_RESERVED = {"con", "prn", "aux", "nul",
                *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
RESULT_CATEGORIES = ["A 控制·异常", "B 伤害类型", "C 生存与增益", "D 部署与编队", "E 技力与技能资源",
                     "F 治疗与支援", "G 召唤物", "H 攻击行为特征", "I 全场光环"]
RESULT_CLASSES = ["先锋", "近卫", "狙击", "重装", "医疗", "辅助", "术师", "特种"]
RESULT_TOP_KEYS = ("version", "updated", "operators", "tags")
DOC_LEAK_HINTS = ("依据", "评定标准", "证据", "检索记录", "边界与排除", "待开发者确认")
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DOC_LINE_RE = re.compile(r"\.md:\d+")


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def safe_name(name) -> str:
    """results/ 下的文件名白名单：无路径分隔符/控制字符，必须 .json 结尾，不出目录。"""
    if not isinstance(name, str) or not name or name != name.strip():
        raise UserError("文件名不合法（不能为空或首尾有空白）", "filename")
    if name.startswith(".") or not NAME_RE.fullmatch(name):
        raise UserError('文件名只能含中文/字母/数字/空格/._-，且必须以 .json 结尾', "filename")
    if name.endswith((".", " ")) or pathlib.PurePath(name).stem.lower() in WIN_RESERVED:
        raise UserError("文件名不合法（Windows 保留名，或以点/空格结尾）", "filename")
    path = (RESULTS_DIR / name).resolve()
    if path.parent != RESULTS_DIR.resolve() or path.name != name:
        raise UserError("文件名不合法（越出 results/ 目录）", "filename")
    return name


def list_results() -> dict:
    files = []
    if RESULTS_DIR.exists():
        for entry in os.scandir(RESULTS_DIR):
            if entry.is_file() and entry.name.lower().endswith(".json"):
                st = entry.stat()
                files.append({"name": entry.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns})
    files.sort(key=lambda f: -f["mtime_ns"])
    return {"ok": True, "dir": "results", "exists": RESULTS_DIR.exists(), "today": today_str(),
            "default": "operator-tags.json", "files": files}


def file_digest(path: pathlib.Path) -> str:
    """文件内容摘要：用作「是否被外部改动」的判据（Windows 的 mtime 会被延迟刷新，不可靠）。"""
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def load_results(payload: dict) -> dict:
    name = safe_name(payload.get("file", ""))
    path = RESULTS_DIR / name
    if not path.exists() or not path.is_file():
        raise UserError(f"文件不存在：{name}", "notfound")
    blob = path.read_bytes()
    raw = blob.decode("utf-8-sig")  # 顺手吃掉 BOM
    eol = "crlf" if "\r\n" in raw else "lf"
    text = raw.replace("\r\n", "\n")
    parsed, error = True, ""
    try:
        json.loads(text)
    except Exception as exc:  # noqa: BLE001
        parsed, error = False, str(exc)
    st = path.stat()
    return {"ok": True, "file": name, "text": text, "parsed": parsed, "error": error, "eol": eol,
            "mtime_ns": st.st_mtime_ns, "size": st.st_size,
            "digest": hashlib.sha1(blob).hexdigest()[:12], "today": today_str()}


def render_results(doc, eol: str = "crlf") -> str:
    """仓库既有落盘风格：ensure_ascii=False、2 空格缩进、末尾换行（eol 决定 LF/CRLF）。"""
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", "\r\n") if eol == "crlf" else text


def _check_combo(label: str, ti: int, mi: int, mem: dict, plc: list, names: dict, seen: dict,
                 combo_names: dict, add) -> None:
    """阵容组合（P12）：成员＝组合条目（combo/condition/remark/beneficiaries/providers），
    提供者按干员成员的同套规则逐项校验；唯一性以组合为界（组合内提供者不重复、跨组合可重复）。"""
    mplc = plc + ["members", mi]
    base = f"tags[{ti}].members[{mi}]"
    cname = mem.get("combo")
    if not isinstance(cname, str) or not cname.strip():
        add("error", "C1", f"{base}.combo", mplc + ["combo"], label, "缺少 combo（组合名）")
        cname = ""
    elif cname in combo_names:
        add("error", "C4", f"{base}.combo", mplc + ["combo"], label + " · " + cname,
            f"组合名重复（首次出现在 members[{combo_names[cname]}]）")
    else:
        combo_names[cname] = mi
        seen.setdefault(cname, set()).add(("组合名", cname, ""))  # R1：组合名本身也是合法荐（与组员荐独立）
    clabel = label + " · " + cname if cname else label
    cond = mem.get("condition")
    if not isinstance(cond, str) or not cond.strip():
        add("error", "C2", f"{base}.condition", mplc + ["condition"], clabel, "组合 condition 必填（来自「触发条件」bullet）")
    if "remark" in mem:
        check_remark(mem.get("remark"), add, "C6", f"{base}.remark", mplc + ["remark"], clabel)
    bens = mem.get("beneficiaries")
    if bens is not None and not (isinstance(bens, list) and all(isinstance(x, str) and x.strip() for x in bens)):
        add("error", "C3", f"{base}.beneficiaries", mplc + ["beneficiaries"], clabel, "beneficiaries 应为字符串数组")
    provs = mem.get("providers")
    if not isinstance(provs, list) or not provs:
        add("error", "C1", f"{base}.providers", mplc + ["providers"], clabel, "providers 必填且至少一名提供者")
        provs = []
    pseen: set[str] = set()
    for pi, prov in enumerate(provs):
        pplc = mplc + ["providers", pi]
        pbase = f"{base}.providers[{pi}]"
        if not isinstance(prov, dict):
            add("error", "C1", pbase, pplc, clabel, "提供者必须是对象")
            continue
        pname = prov.get("operator")
        plabel = clabel + " · " + (pname if isinstance(pname, str) else "")
        if not isinstance(pname, str) or not pname.strip():
            add("error", "C1", f"{pbase}.operator", pplc + ["operator"], clabel, "缺少提供者 operator")
            pname = ""
        elif pname not in names:
            add("error", "M3", f"{pbase}.operator", pplc + ["operator"], plabel, f"「{pname}」不在 operators[] 中")
        elif pname in pseen:
            add("error", "C4", f"{pbase}.operator", pplc + ["operator"], plabel, f"同一组合内提供者重复：{pname}")
        if pname:
            pseen.add(pname)
            seen.setdefault(pname, set()).add(("组合", cname, ""))
        pcond = prov.get("condition")
        if not isinstance(pcond, str) or not pcond.strip():
            add("error", "M5", f"{pbase}.condition", pplc + ["condition"], plabel, "condition 必填（精英 0·1 级即具备写「无」）")
        if "remark" in prov:
            check_remark(prov.get("remark"), add, "M6", f"{pbase}.remark", pplc + ["remark"], plabel)
        purl = prov.get("prtsUrl")
        if not isinstance(purl, str) or not purl.strip():
            add("error", "M10", f"{pbase}.prtsUrl", pplc + ["prtsUrl"], plabel, "prtsUrl 必填")
        else:
            head = purl.split("#", 1)[0]
            if not head.startswith("https://prts.wiki/w/"):
                add("warn", "M11", f"{pbase}.prtsUrl", pplc + ["prtsUrl"], plabel, "prtsUrl 应以 https://prts.wiki/w/ 开头")
            elif pname and urllib.parse.unquote(head[len("https://prts.wiki/w/"):]) != pname:
                add("warn", "M11", f"{pbase}.prtsUrl", pplc + ["prtsUrl"], plabel, "prtsUrl 的干员名与 operator 不一致（注意 percent 编码）")
        for key in prov:
            if key not in ("operator", "condition", "remark", "prtsUrl"):
                add("warn", "M12", f"{pbase}.{key}", pplc + [key], plabel, f"规范之外的字段「{key}」")
    for key in mem:
        if key not in ("combo", "condition", "remark", "beneficiaries", "providers", "source", "subTags"):
            add("warn", "M12", f"{base}.{key}", mplc + [key], clabel, f"规范之外的字段「{key}」")


def check_remark(remark, add, code: str, path: str, loc: list, label: str) -> None:
    """remark 块数组结构（docs/output-standard.md §4.2）：块 {label?, items[]}、条 {label?, text}。"""
    if not isinstance(remark, list) or not remark:
        add("warn", code, path, loc, label, "remark 应为非空块数组；无内容时应省略该字段")
        return
    for bi, block in enumerate(remark):
        bpath, bloc = f"{path}[{bi}]", loc + ["remark", bi]
        if not isinstance(block, dict):
            add("error", code, bpath, bloc, label, "remark 的块必须是对象")
            continue
        bl = block.get("label")
        if bl is not None and (not isinstance(bl, str) or not bl.strip()):
            add("warn", code, bpath + ".label", bloc + ["label"], label, "块 label 为空时应省略该字段")
        items = block.get("items")
        if not isinstance(items, list) or not items:
            add("error", code, bpath + ".items", bloc + ["items"], label, "块的 items 必填且至少一条")
            continue
        for ii, item in enumerate(items):
            ipath, iloc = f"{bpath}.items[{ii}]", bloc + ["items", ii]
            if not isinstance(item, dict):
                add("error", code, ipath, iloc, label, "条必须是对象")
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                add("error", code, ipath + ".text", iloc + ["text"], label, "条的 text 必填")
            il = item.get("label")
            if il is not None and (not isinstance(il, str) or not il.strip()):
                add("warn", code, ipath + ".label", iloc + ["label"], label, "条 label 为空时应省略该字段")
            for key in item:
                if key not in ("label", "text"):
                    add("warn", code, f"{ipath}.{key}", iloc + [key], label, f"规范之外的字段「{key}」")
        for key in block:
            if key not in ("label", "items"):
                add("warn", code, f"{bpath}.{key}", bloc + [key], label, f"规范之外的字段「{key}」")


def validate_results(doc) -> tuple[list[dict], dict | None]:
    """按 docs/output-standard.md 校验结果 JSON；只列问题，不做阻断。"""
    problems: list[dict] = []

    def add(level, code, path, loc, label, msg):
        problems.append({"level": level, "code": code, "path": path, "loc": loc,
                         "label": label, "message": msg})

    if not isinstance(doc, dict):
        add("error", "T1", "", [], "", f"顶层必须是 JSON 对象（当前是 {type(doc).__name__}）")
        return problems, None

    for key in RESULT_TOP_KEYS:
        if key not in doc:
            add("error", "T2", key, [key], "", f"缺少顶层字段 {key}")
    for key in doc:
        if key not in RESULT_TOP_KEYS:
            add("warn", "T6", key, [key], "", f"顶层出现规范之外的字段「{key}」")
    version = doc.get("version")
    if not (isinstance(version, str) and re.fullmatch(r"v[1-9]\d*", version)):
        add("error", "T3", "version", ["version"], "", f"version 应为 v1、v2…（当前 {version!r}）")
    updated = doc.get("updated")
    try:
        ok_date = isinstance(updated, str) and bool(DATE_RE.match(updated)) and bool(time.strptime(updated, "%Y-%m-%d"))
    except ValueError:
        ok_date = False
    if not ok_date:
        add("error", "T4", "updated", ["updated"], "", f"updated 应为 yyyy-MM-dd 的真实日期（当前 {updated!r}）")

    raw_ops, raw_tags = doc.get("operators"), doc.get("tags")
    if not isinstance(raw_ops, list):
        add("error", "T5", "operators", ["operators"], "", "operators 必须是数组")
        raw_ops = []
    if not isinstance(raw_tags, list):
        add("error", "T5", "tags", ["tags"], "", "tags 必须是数组")
        raw_tags = []

    # ---- operators[] ----
    names: dict[str, int] = {}
    dates: dict[str, str] = {}
    for i, op in enumerate(raw_ops):
        plc = ["operators", i]
        if not isinstance(op, dict):
            add("error", "O1", f"operators[{i}]", plc, "", "干员条目必须是对象")
            continue
        nm = op.get("name")
        if not isinstance(nm, str) or not nm.strip():
            add("error", "O2", f"operators[{i}].name", plc + ["name"], "", "缺少干员名 name")
        else:
            if nm in names:
                add("error", "O4", f"operators[{i}].name", plc + ["name"], nm, f"干员名重复（首次出现在 operators[{names[nm]}]）")
            else:
                names[nm] = i
            dates[nm] = op.get("releaseDate", "") if isinstance(op.get("releaseDate"), str) else ""
        for field in ("rarity", "class", "branch", "faction", "releaseDate", "prtsUrl"):
            if field not in op:
                add("error", "O2", f"operators[{i}].{field}", plc + [field], str(nm or ""), f"缺少字段 {field}")
        rarity = op.get("rarity")
        if "rarity" in op and (not isinstance(rarity, int) or isinstance(rarity, bool) or not 1 <= rarity <= 6):
            add("error", "O3", f"operators[{i}].rarity", plc + ["rarity"], str(nm or ""), f"rarity 应为 1–6 的整数（当前 {rarity!r}）")
        cls = op.get("class")
        if "class" in op and cls not in RESULT_CLASSES:
            add("error", "O3", f"operators[{i}].class", plc + ["class"], str(nm or ""), f"class 应为八个职业之一（当前 {cls!r}）")
        if op.get("releaseDate") == "":
            add("warn", "O7", f"operators[{i}].releaseDate", plc + ["releaseDate"], str(nm or ""), "releaseDate 为空串")
        elif isinstance(op.get("releaseDate"), str) and not DATE_RE.match(op["releaseDate"]):
            add("error", "O3", f"operators[{i}].releaseDate", plc + ["releaseDate"], str(nm or ""), f"releaseDate 应为 yyyy-MM-dd（当前 {op['releaseDate']!r}）")
        if "prtsUrl" in op and not isinstance(op.get("prtsUrl"), str):
            add("error", "O3", f"operators[{i}].prtsUrl", plc + ["prtsUrl"], str(nm or ""), "prtsUrl 应为字符串")
        for key in op:
            if key not in ("name", "charId", "rarity", "class", "branch", "faction", "releaseDate", "prtsUrl"):
                add("warn", "O6", f"operators[{i}].{key}", plc + [key], str(nm or ""), f"规范之外的字段「{key}」")
    for i in range(1, len(raw_ops)):
        a, b = raw_ops[i - 1], raw_ops[i]
        if isinstance(a, dict) and isinstance(b, dict):
            da, db = a.get("releaseDate") or "", b.get("releaseDate") or ""
            if DATE_RE.match(da) and DATE_RE.match(db) and da < db:
                add("warn", "O5", f"operators[{i}].releaseDate", ["operators", i, "releaseDate"], str(b.get("name", "")),
                    f"未按实装时间倒序（{b.get('name')} {db} 排在 {a.get('name')} {da} 之后）")

    # ---- tags[] ----
    ids: dict[str, int] = {}
    prev_cat = ""
    seen_player = False
    stats = {"operators": len(raw_ops), "tags": len(raw_tags), "members": 0, "official": 0, "player": 0,
             "recommended": 0, "recommendedFallback": 0,
             "recommendedBySub": 0, "recommendedFallbackBySub": 0}
    for ti, tag in enumerate(raw_tags):
        plc = ["tags", ti]
        if not isinstance(tag, dict):
            add("error", "G1", f"tags[{ti}]", plc, "", "TAG 条目必须是对象")
            continue
        tid, tname, src = tag.get("id"), tag.get("name"), tag.get("source")
        label = str(tname or tid or "")
        for field in ("id", "name", "source", "members"):
            if field not in tag:
                add("error", "G2", f"tags[{ti}].{field}", plc + [field], label, f"缺少字段 {field}")
        if isinstance(tid, str):
            if tid in ids:
                add("error", "G4", f"tags[{ti}].id", plc + ["id"], label, f"id 重复（首次出现在 tags[{ids[tid]}]）")
            else:
                ids[tid] = ti
            if src == "official" and not re.fullmatch(r"[A-I]_[a-z0-9_]+", tid):
                add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"官方 id 形态应为 A_x 之类（当前 {tid!r}）")
            if src == "player" and not re.fullmatch(r"P(0[1-9]|1[0-3])", tid):
                add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"玩家 id 应为 P01–P12（当前 {tid!r}）")
        else:
            add("error", "G3", f"tags[{ti}].id", plc + ["id"], label, f"id 应为字符串（当前 {tid!r}）")
        if src not in ("official", "player"):
            add("error", "G6", f"tags[{ti}].source", plc + ["source"], label, f'source 应为 "official" 或 "player"（当前 {src!r}）')
        if not isinstance(tname, str) or not tname.strip():
            add("error", "G2", f"tags[{ti}].name", plc + ["name"], label, "缺少 TAG 名 name")
        if src == "official":
            stats["official"] += 1
            cat = tag.get("category")
            if cat not in RESULT_CATEGORIES:
                add("error", "G7", f"tags[{ti}].category", plc + ["category"], label, f"category 应为九个类别之一（当前 {cat!r}）")
            else:
                if seen_player:
                    add("warn", "G12", f"tags[{ti}].source", plc + ["source"], label, "官方 TAG 出现在玩家 TAG 之后（规范：官方在前）")
                elif prev_cat and cat < prev_cat:
                    add("warn", "G12", f"tags[{ti}].category", plc + ["category"], label, f"官方 TAG 未按类别 A→I 排列（{cat} 排在 {prev_cat} 之后）")
                prev_cat = max(prev_cat, cat) if prev_cat else cat
            if "recommended" in tag:
                add("error", "G8", f"tags[{ti}].recommended", plc + ["recommended"], label, "官方 TAG 不应有 recommended 字段")
        elif src == "player":
            stats["player"] += 1
            seen_player = True
            if "recommended" not in tag:
                add("warn", "G9", f"tags[{ti}].recommended", plc + ["recommended"], label, "玩家 TAG 缺少 recommended（无荐时也应为空数组）")
        for key in tag:
            if key not in ("id", "name", "source", "category", "recommended", "recommendedFallback",
                           "recommendedBySub", "recommendedFallbackBySub", "members"):
                add("warn", "G11", f"tags[{ti}].{key}", plc + [key], label, f"规范之外的字段「{key}」")
        members = tag.get("members")
        if not isinstance(members, list):
            add("error", "G2", f"tags[{ti}].members", plc + ["members"], label, "members 必须是数组")
            members = []
        subs_any = any(isinstance(m, dict) and m.get("subTags") for m in members)
        seen: dict[str, set] = {}  # 干员名 → 已占用的末端子 TAG 集合（无子 TAG 者以 ("", "", "") 记）
        combo_names: dict[str, int] = {}  # 阵容组合（P12）：组合名 → 首次出现的成员序号
        for mi, mem in enumerate(members):
            mplc = plc + ["members", mi]
            stats["members"] += 1
            if not isinstance(mem, dict):
                add("error", "M1", f"tags[{ti}].members[{mi}]", mplc, label, "成员必须是对象")
                continue
            if tid == "P12":  # 阵容组合：成员＝组合条目
                _check_combo(label, ti, mi, mem, plc, names, seen, combo_names, add)
                continue
            mname = mem.get("operator")
            if not isinstance(mname, str) or not mname.strip():
                add("error", "M2", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label, "缺少 operator")
                mname = ""
            elif mname not in names:
                add("error", "M3", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label + " · " + mname,
                    f"「{mname}」不在 operators[] 中")
            cond = mem.get("condition")
            if not isinstance(cond, str) or not cond.strip():
                add("error", "M5", f"tags[{ti}].members[{mi}].condition", mplc + ["condition"], label + " · " + (mname or ""),
                    "condition 必填（精英 0·1 级即具备写「无」）")
            if "remark" in mem:
                check_remark(mem.get("remark"), add, "M6", f"tags[{ti}].members[{mi}].remark",
                             mplc + ["remark"], label + " · " + (mname or ""))
            subs = mem.get("subTags")
            leaves = {("", "", "")}
            if subs is not None:
                if not isinstance(subs, list):
                    add("error", "M7", f"tags[{ti}].members[{mi}].subTags", mplc + ["subTags"], label + " · " + (mname or ""), "subTags 必须是数组")
                else:
                    pairs = set()
                    leaves = set()
                    for si, sub in enumerate(subs):
                        splc = mplc + ["subTags", si]
                        if not isinstance(sub, dict) or not str(sub.get("group", "")).strip() or not str(sub.get("value", "")).strip():
                            add("error", "M7", f"tags[{ti}].members[{mi}].subTags[{si}]", splc, label + " · " + (mname or ""),
                                "子 TAG 需同时有 group 与 value")
                            continue
                        pairv = (sub["group"], sub["value"])
                        if pairv in pairs:
                            add("error", "M8", f"tags[{ti}].members[{mi}].subTags[{si}]", splc, label + " · " + (mname or ""),
                                f"同一组值重复：{sub['group']}／{sub['value']}")
                        pairs.add(pairv)
                        leaves.add((sub["group"], sub["value"], sub.get("detail", "")))
                        if "detail" in sub and sub["value"] != "触发时":
                            add("warn", "M9", f"tags[{ti}].members[{mi}].subTags[{si}].detail", splc + ["detail"], label + " · " + (mname or ""),
                                "detail 仅在 value 为「触发时」时使用")
            # 唯一性以「同一条目的子 TAG 组合」为界：同一干员可因不同技能各占一行，但两行的子 TAG 组合不得完全相同（如 决战歼灭 的范围轴＋伤害轴、次数对策 的多段伤害/间隔伤害）
            if mname:
                rowset = frozenset(leaves)
                if mname in seen and rowset in seen[mname]:
                    shared = "／".join(sorted({g + "／" + v for g, v, _ in rowset} - {"／"}))
                    add("error", "M4", f"tags[{ti}].members[{mi}].operator", mplc + ["operator"], label + " · " + mname,
                        f"同一条目的子 TAG 组合重复（{shared or '无子 TAG'}）")
                seen.setdefault(mname, set()).add(rowset)
            purl = mem.get("prtsUrl")
            if not isinstance(purl, str) or not purl.strip():
                add("error", "M10", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + (mname or ""), "prtsUrl 必填")
            else:
                head = purl.split("#", 1)[0]
                if not head.startswith("https://prts.wiki/w/"):
                    add("warn", "M11", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + (mname or ""),
                        "prtsUrl 应以 https://prts.wiki/w/ 开头")
                elif mname and urllib.parse.unquote(head[len("https://prts.wiki/w/"):]) != mname:
                    add("warn", "M11", f"tags[{ti}].members[{mi}].prtsUrl", mplc + ["prtsUrl"], label + " · " + mname,
                        "prtsUrl 的干员名与 operator 不一致（注意 percent 编码）")
            for key in mem:
                if key not in ("operator", "condition", "remark", "subTags", "prtsUrl", "source"):
                    add("warn", "M12", f"tags[{ti}].members[{mi}].{key}", mplc + [key], label + " · " + (mname or ""),
                        f"规范之外的字段「{key}」")
        # 成员顺序（阵容组合按组合分组，跳过）
        if tid != "P12":
            for mi in range(1, len(members)):
                a, b = members[mi - 1], members[mi]
                if isinstance(a, dict) and isinstance(b, dict):
                    na, nb = a.get("operator"), b.get("operator")
                    da, db = dates.get(na, ""), dates.get(nb, "")
                    if DATE_RE.match(da) and DATE_RE.match(db) and da < db:
                        add("warn", "M13", f"tags[{ti}].members[{mi}]", plc + ["members", mi], label + " · " + str(nb),
                            f"成员未按实装时间倒序（{nb} {db} 排在 {na} {da} 之后）")
        # 子 TAG 覆盖（玩家 TAG）：有子 TAG 的 TAG，全部成员必须至少带一个子 TAG（去重并集＝全部成员）
        if src == "player" and subs_any:
            for m in members:
                if isinstance(m, dict) and not m.get("subTags"):
                    nm = m.get("operator") or m.get("combo") or ""
                    add("error", "M14", f"tags[{ti}].members", plc + ["members"], label + " · " + str(nm),
                        "成员未归属任何子 TAG（有子 TAG 的 TAG 应全员至少带一个子 TAG，去重并集＝全部成员）")
        rec = tag.get("recommended")
        if rec is not None:
            if not (isinstance(rec, list) and all(isinstance(x, str) for x in rec)):
                add("error", "G10", f"tags[{ti}].recommended", plc + ["recommended"], label, "recommended 应为字符串数组")
            else:
                stats["recommended"] += len(rec)
                dup = {x for x in rec if rec.count(x) > 1}
                for x in sorted(dup):
                    add("error", "R2", f"tags[{ti}].recommended", plc + ["recommended"], label, f"荐重复：{x}")
                for k, x in enumerate(rec):
                    if x not in seen:
                        add("error", "R1", f"tags[{ti}].recommended[{k}]", plc + ["recommended", k], label,
                            f"荐「{x}」不是本 TAG 的成员")
        rec_fb = tag.get("recommendedFallback")
        if rec_fb is not None:
            if not (isinstance(rec_fb, list) and all(isinstance(x, str) for x in rec_fb)):
                add("error", "G12", f"tags[{ti}].recommendedFallback", plc + ["recommendedFallback"], label,
                    "recommendedFallback 应为字符串数组")
            else:
                stats["recommendedFallback"] += len(rec_fb)
                dup = {x for x in rec_fb if rec_fb.count(x) > 1}
                for x in sorted(dup):
                    add("error", "R3", f"tags[{ti}].recommendedFallback", plc + ["recommendedFallback"], label,
                        f"兜底荐重复：{x}")
                for k, x in enumerate(rec_fb):
                    if x not in seen:
                        add("error", "R4", f"tags[{ti}].recommendedFallback[{k}]", plc + ["recommendedFallback", k],
                            label, f"兜底荐「{x}」不是本 TAG 的成员")
        # TAG 级不设荐：有子 TAG 的 TAG（成员带 subTags 或已用 recommendedBySub），荐需下沉到子 TAG
        if src == "player" and (subs_any or tag.get("recommendedBySub") or tag.get("recommendedFallbackBySub")):
            for fld in ("recommended", "recommendedFallback"):
                v = tag.get(fld)
                if isinstance(v, list) and v:
                    add("error", "R7", f"tags[{ti}].{fld}", plc + [fld], label,
                        f"{fld} 非空（有子 TAG 的 TAG 不应有 TAG 级荐，荐需下沉到子 TAG）")
        for fld, base_code in (("recommendedBySub", "G13"), ("recommendedFallbackBySub", "G14")):
            subs = tag.get(fld)
            if subs is None:
                continue
            if not isinstance(subs, list):
                add("error", base_code, f"tags[{ti}].{fld}", plc + [fld], label, f"{fld} 应为数组")
                continue
            for si, s in enumerate(subs):
                spath, sloc = f"tags[{ti}].{fld}[{si}]", plc + [fld, si]
                if not isinstance(s, dict):
                    add("error", base_code, spath, sloc, label, f"{fld} 元素应为对象")
                    continue
                for key in s:
                    if key not in ("group", "value", "names"):
                        add("warn", "G11", f"{spath}.{key}", sloc + [key], label, f"规范之外的字段「{key}」")
                names_l = s.get("names")
                if not isinstance(names_l, list) or not all(isinstance(x, str) for x in names_l):
                    add("error", base_code, f"{spath}.names", sloc + ["names"], label, "names 应为字符串数组")
                    continue
                stats[fld] += len(names_l)
                dup = {x for x in names_l if names_l.count(x) > 1}
                for x in sorted(dup):
                    add("error", "R5", f"{spath}.names", sloc + ["names"], label, f"荐重复：{x}")
                for k, x in enumerate(names_l):
                    if x not in seen:
                        add("error", "R6", f"{spath}.names[{k}]", sloc + ["names", k], label,
                            f"荐「{x}」不是本 TAG 的成员")

    # ---- 未被任何 TAG 引用的干员 ----
    used = set()
    for tag in raw_tags:
        if isinstance(tag, dict) and isinstance(tag.get("members"), list):
            for mem in tag["members"]:
                if not isinstance(mem, dict):
                    continue
                if isinstance(mem.get("operator"), str):
                    used.add(mem["operator"])
                if isinstance(mem.get("providers"), list):  # 阵容组合：组合内提供者
                    for prov in mem["providers"]:
                        if isinstance(prov, dict) and isinstance(prov.get("operator"), str):
                            used.add(prov["operator"])
    for nm, i in names.items():
        if nm not in used:
            add("warn", "O8", f"operators[{i}]", ["operators", i], nm, f"「{nm}」未被任何 TAG 引用")

    # ---- 生产文档残留 / 非法字符 ----
    def walk(node, loc):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str):
                    for hint in DOC_LEAK_HINTS:
                        if hint in k:
                            add("warn", "T7", ".".join(str(x) for x in loc + [k]), loc + [k], "", f"键名含生产文档用语「{hint}」")
                    if SURROGATE_RE.search(k):
                        add("error", "X1", ".".join(str(x) for x in loc + [k]), loc + [k], "", "键名含非法字符（孤立代理项）")
                walk(v, loc + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, loc + [i])
        elif isinstance(node, str):
            if DOC_LINE_RE.search(node):
                add("warn", "T7", ".".join(str(x) for x in loc), loc, "", "文本里出现「文件:行号」形式的证据")
            if SURROGATE_RE.search(node):
                add("error", "X1", ".".join(str(x) for x in loc), loc, "", "文本含非法字符（孤立代理项），无法以 UTF-8 写出")

    walk(doc, [])
    return problems, stats


def check_results(payload: dict) -> dict:
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise UserError("文本缺失或过大（>800 万字符）", "too_big")
    try:
        doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "parsed": False, "stats": None,
                "problems": [{"level": "error", "code": "parse", "path": "", "loc": [], "label": "",
                              "message": f"JSON 解析失败：{exc}"}]}
    problems, stats = validate_results(doc)
    return {"ok": True, "parsed": True, "problems": problems, "stats": stats}


def save_results(payload: dict) -> dict:
    """把内存中的文本写回 results/。只有「不是合法 JSON」才硬拦，规范问题只列不挡。"""
    name = safe_name(payload.get("file", ""))
    text = payload.get("text", "")
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise UserError("文本缺失或过大（>800 万字符）", "too_big")
    try:
        doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"内容不是合法 JSON，未写盘：{exc}", "parse") from None
    mode = payload.get("mode", "overwrite")
    if mode not in ("overwrite", "new"):
        raise UserError(f"未知保存方式：{mode}", "mode")
    eol = "lf" if payload.get("eol") == "lf" else "crlf"
    path = RESULTS_DIR / name
    if path.is_dir():
        raise UserError(f"results/{name} 是一个目录，不能作为文件保存", "exists")
    exists = path.exists()
    if mode == "new" and exists:
        raise UserError(f"已存在同名文件：{name}，请改用「覆盖」或换个名字", "exists")
    if mode == "overwrite" and not exists:
        raise UserError(f"文件不存在：{name}（可能已被删除或改名），请改用「新建」", "missing")
    expect = payload.get("expect")
    if mode == "overwrite" and isinstance(expect, dict) and not payload.get("force"):
        if expect.get("digest"):
            drift = expect["digest"] != file_digest(path)
        else:  # 兼容没有摘要的旧载荷
            st = path.stat()
            drift = (st.st_mtime_ns, st.st_size) != (int(expect.get("mtime_ns", -1)), int(expect.get("size", -1)))
        if drift:
            raise UserError("文件已被外部改动，请重新载入，或确认后强制覆盖", "drift")
    out_lf = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    text_out = out_lf.replace("\n", "\r\n") if eol == "crlf" else out_lf
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        write_atomic(path, text_out)
    except UnicodeEncodeError:
        raise UserError("内容含非法字符（孤立代理项 \\ud800–\\udfff），无法以 UTF-8 写出", "encoding") from None
    st = path.stat()
    problems, stats = validate_results(doc)
    return {"ok": True, "file": name, "created": not exists, "bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns, "size": st.st_size,
            "digest": hashlib.sha1(text_out.encode("utf-8")).hexdigest()[:12], "eol": eol,
            "normalized": out_lf != text, "saved": {"text": out_lf},
            "problems": problems, "stats": stats, "today": today_str()}

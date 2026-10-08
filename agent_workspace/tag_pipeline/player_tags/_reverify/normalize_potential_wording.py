# -*- coding: utf-8 -*-
"""潜级写法统一（一次性）：把条件/替换文本中的潜级写法统一为「N潜（…）」形式。

规则（开发者裁定）：干员默认即为 1 潜（基准），帮助效果在基准即具备时不写潜级；
条件只写 ≥2 的所需潜级，形式为「N潜」。本脚本归并
「需潜能5／需潜5／需 5 潜／潜5／潜能5」等写法 → 「5潜」。

安全自检：逐条转换后重算「替换对依序应用」结果；若与 new_remark_expected /
cond_new_expected 不再一致，则跳过该条的转换并列报告（防误伤）。

用法：python -X utf8 normalize_potential_wording.py [--dry-run]
"""
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
RV = pathlib.Path(__file__).resolve().parent
PARTS = RV / "parts"


def norm(text: str) -> str:
    if not isinstance(text, str):
        return text
    s = re.sub(r"需\s*潜\s*能\s*(\d)", r"\1潜", text)
    s = re.sub(r"需\s*潜\s*(\d)", r"\1潜", s)
    s = re.sub(r"需\s*(\d)\s*潜", r"\1潜", s)
    s = re.sub(r"(?<![0-9A-Za-z])潜能\s*(\d)", r"\1潜", s)
    s = re.sub(r"(?<![0-9A-Za-z])潜\s*(\d)", r"\1潜", s)
    return s


def apply_pairs(raw, pairs):
    ordered = sorted(pairs, key=lambda p: raw.find(p[0]))
    out = raw
    for old, new in ordered:
        out = out.replace(old, new, 1)
    return out


def main() -> int:
    dry = "--dry-run" in sys.argv
    items = {json.loads(l)["id"]: json.loads(l)
             for l in (RV / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    changed_items = changed_fields = skipped = 0
    for f in sorted(PARTS.glob("G*.jsonl")):
        out_lines = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                out_lines.append(line)
                continue
            o = json.loads(line)
            orig = json.dumps(o, ensure_ascii=False, sort_keys=True)
            hits = 0
            for key in ("new_fragment", "new_remark_expected", "cond_new_expected"):
                if key in o and o[key] != norm(o[key]):
                    o[key] = norm(o[key])
                    hits += 1
            ce = o.get("cond_edits")
            if ce:
                for p in (ce if isinstance(ce, list) else [ce]):
                    if p.get("new") != norm(p["new"]):
                        p["new"] = norm(p["new"])
                        hits += 1
            for e in o.get("extra_edits") or []:
                if e.get("new") != norm(e["new"]):
                    e["new"] = norm(e["new"])
                    hits += 1
            if hits:
                # 自检：替换自洽性必须保持
                it = items.get(o["id"], {})
                pairs = [(o["old_fragment"], o["new_fragment"])] + \
                        [(e["old"], e["new"]) for e in o.get("extra_edits") or []]
                ok = bool(it) and apply_pairs(it["raw_note"], pairs) == o.get("new_remark_expected")
                ce2 = o.get("cond_edits")
                if ok and ce2:
                    exp = it["raw_cond"]
                    for p in (ce2 if isinstance(ce2, list) else [ce2]):
                        exp = exp.replace(p["old"], p["new"], 1)
                    ok = exp == o.get("cond_new_expected")
                if not ok:
                    skipped += 1
                    print(f"[SKIP] {o['id']}：转换后自检不通过，保持原样")
                    o = json.loads(orig)
                else:
                    changed_items += 1
                    changed_fields += hits
                    print(f"[{'DRY' if dry else 'FIX'}] {o['id']}（{hits} 处）")
            out_lines.append(json.dumps(o, ensure_ascii=False))
        if not dry:
            f.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"{'将' if dry else '已'}统一 {changed_items} 条、{changed_fields} 处；跳过 {skipped} 条；"
          f"{'（dry-run 未写盘）' if dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

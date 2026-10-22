# -*- coding: utf-8 -*-
"""帧模型自检（B 支）：核对 calc 步骤里的「攻击间隔 → 取整帧 → 攻击次数」是否自洽。

判定规则（ArkDPS 同口径，30 FPS）：
  frames = ROUND(interval_seconds × 30)          # half away from zero
  count  = ROUND(duration_seconds × 30 ÷ frames) # 弹药/限制次数另取 min

做法：
  1. 在「…间隔…」步骤里收集所有秒数（含 note 中的推导，如「0.5×100÷115≈0.435 秒」）；
  2. 在「…次数…」步骤里收集 `X × 30 ÷ F` 的 F（或 note 中的「取整帧 F 帧」）；
  3. 只要第 1 步任一秒数取整帧后等于 F，即视为自洽。
     跳数/DoT 类步骤（标题含「跳」）不参与攻击间隔判定。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "agent_workspace" / "tag_pipeline" / "calc_process"
FPS = 30

SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*秒")
FRAME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*×\s*30\s*[÷/]\s*(\d+(?:\.\d+)?)")
FRAME_NOTE_RE = re.compile(r"取整帧\s*(\d+)\s*帧")


def xround(x: float) -> int:
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def step_text(st: dict) -> str:
    return " ".join(str(st.get(k) or "") for k in ("expr", "result", "unit", "note", "title"))


def check_member(member: dict) -> list[str]:
    issues: list[str] = []
    for sid, steps in (member.get("scenarios") or {}).items():
        if not isinstance(steps, list):
            continue
        interval_secs: list[float] = []
        frames_used: list[tuple[float, str]] = []
        for st in steps:
            txt = step_text(st)
            title = str(st.get("title") or "")
            if "跳" in title or "结算" in title or "每秒" in title or "动作" in title:
                continue
            if "攻击间隔" in title or title.startswith("实际间隔"):
                interval_secs += [float(x) for x in SEC_RE.findall(txt)]
            if "攻击次数" in title or title.startswith("实际间隔") or "内攻击" in title:
                for m in FRAME_RE.finditer(txt):
                    frames_used.append((float(m.group(2)), title))
                for m in FRAME_NOTE_RE.finditer(txt):
                    frames_used.append((float(m.group(1)), title))
        interval_secs = sorted(set(interval_secs))
        if not frames_used or not interval_secs:
            continue
        for frames, title in sorted(set(frames_used)):
            if frames <= 0:
                continue
            if not any(xround(sec * FPS) == frames for sec in interval_secs):
                near = ", ".join(f"{s:g}秒→{xround(s * FPS)}帧" for s in interval_secs)
                issues.append(f"[{sid}] 「{title}」用 {frames:g} 帧；间隔秒数换算为 {near}")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", help="只查该干员")
    args = ap.parse_args()
    total = bad = 0
    lines = []
    for p in sorted(SRC.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        op = d.get("operator") or p.stem
        if args.op and args.op not in op:
            continue
        for m in d.get("members") or []:
            total += 1
            issues = check_member(m)
            if issues:
                bad += 1
                lines.append(f"{op} [{m.get('tag')}] {str(m.get('match'))[:46]}")
                lines += [f"    {i}" for i in issues]
    print("\n".join(lines))
    print(f"\n检查 {total} 个成员，{bad} 个存在帧/次数疑点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

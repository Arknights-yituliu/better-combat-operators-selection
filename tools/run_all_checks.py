# -*- coding: utf-8 -*-
"""一键全量校验：依次运行项目校验套件并汇总结果。

用法（Windows；POSIX 用 .venv/bin/python）：
    .venv/Scripts/python.exe -X utf8 tools/run_all_checks.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

CHECKS: list[tuple[str, list[str]]] = [
    ("属性层覆盖率", [PY, "-X", "utf8", "tools/prts_stats.py", "--check"]),
    ("数值校准", [PY, "-X", "utf8", "tools/verify_numbers.py"]),
    ("生成规范与文本 lint", [PY, "-X", "utf8", "tools/generate_results.py", "--check"]),
    ("排序层校验", [PY, "-X", "utf8", "tools/apply_tag_order.py", "--check"]),
    ("评定标准严谨版校验", [PY, "-X", "utf8", "tools/criteria_to_json.py", "--check"]),
    ("迁移守恒", [PY, "-X", "utf8", ".claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py"]),
    ("证据层审计", [PY, "-X", "utf8", "crawlers/strip_prts_noncombat.py", "--audit"]),
    ("GUI 自检", [PY, "-X", "utf8", "recommend_gui.py", "--check"]),
]


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    results: list[tuple[str, int, float]] = []
    for name, cmd in CHECKS:
        print(f"\n===== {name} =====", flush=True)
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=ROOT, env=env)
        results.append((name, proc.returncode, time.monotonic() - started))

    print("\n===== 汇总 =====")
    failed = 0
    for name, code, secs in results:
        status = "PASS" if code == 0 else "FAIL"
        if code != 0:
            failed += 1
        print(f"[{status}] {name}  ({secs:.1f}s)")
    print(f"{len(results) - failed}/{len(results)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
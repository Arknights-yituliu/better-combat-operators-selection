# -*- coding: utf-8 -*-
"""调用两个名单合并脚本（玩家 / 官方），用子进程运行。"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from .config import MERGE_OFFICIAL, MERGE_PLAYER, ROOT


def run_merge_script(script: pathlib.Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {"ok": proc.returncode == 0, "returncode": proc.returncode,
            "out": (proc.stdout or "").strip(), "err": (proc.stderr or "").strip()}


def run_merge(which: str = "both") -> dict:
    out: dict = {}
    if which in ("player", "both"):
        out["player"] = run_merge_script(MERGE_PLAYER)
    if which in ("official", "both"):
        out["official"] = run_merge_script(MERGE_OFFICIAL)
    out["ok"] = all(v["ok"] for v in out.values())
    return out

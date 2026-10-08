# -*- coding: utf-8 -*-
"""把 results/ 下的产物同步到消费端目录（路径取自仓库根目录的 local.json）。

local.json（本地，不进库；模板见 local.example.json）：
    {"frontend_results_dir": "D:/path/to/frontend/src/static/json/combat"}

用法：
    python -X utf8 tools/sync_results.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CONFIG = ROOT / "local.json"


def md5(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 results/ 产物到 local.json 配置的目录")
    ap.add_argument("--check", action="store_true", help="只打印计划与校验，不复制")
    args = ap.parse_args()

    if not CONFIG.exists():
        print(f"未找到 {CONFIG}；请复制 local.example.json 为 local.json 并填写 frontend_results_dir")
        return 1
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        print(f"local.json 不是合法 JSON：{exc}")
        return 1
    target = cfg.get("frontend_results_dir") or ""
    if not target:
        print("local.json 未填写 frontend_results_dir")
        return 1
    target_dir = pathlib.Path(target)
    if not target_dir.is_dir():
        print(f"目标目录不存在：{target_dir}")
        return 1

    files = sorted(RESULTS.glob("*.json"))
    if not files:
        print("results/ 下没有 JSON 产物")
        return 1
    for src in files:
        dst = target_dir / src.name
        src_md5 = md5(src)
        if args.check:
            state = "一致" if dst.exists() and md5(dst) == src_md5 else "需同步"
            print(f"[{state}] {src.name}  md5={src_md5}")
            continue
        shutil.copyfile(src, dst)
        ok = md5(dst) == src_md5
        print(f"[{'已同步' if ok else '校验失败'}] {src.name}  md5={src_md5}")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# -*- coding: utf-8 -*-
"""玩家体感 TAG「荐」维护工具。

「荐」＝人工指定的、某 TAG 下推荐使用的干员。一个干员可以在 A TAG
有荐、在 B TAG 没有。荐只维护在本工具的数据文件里，不写进名单文档：

    material_datas/tag_pipeline/player_tags/_recommend.json
        { "充电": ["白铁", "娜斯提"], "保人": ["夜莺"] }
    （键＝TAG 名；值为干员名数组，顺序不含展示优先级语义）

生成最终结果 JSON（见 docs/output-standard.md §6）时按 TAG 名合并进
`recommended` 字段；重新生成不会丢失荐。

用法：
    python recommend.py                     # 列出 13 个 TAG 及当前荐
    python recommend.py list 充电           # 查看某 TAG 的荐
    python recommend.py add 充电 白铁 [干员...]
    python recommend.py remove 充电 白铁 [干员...]
    python recommend.py check               # 校验全部荐（TAG / 成员是否有效）

校验：TAG 必须存在；干员必须是该 TAG 主表成员——边界与排除记录里的干员
不能设为荐（避免悬空引用）。本工具只写 _recommend.json，不动其他文件。
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
PARTS = ROOT / "material_datas" / "tag_pipeline" / "player_tags"
RECOMMEND = PARTS / "_recommend.json"

# 成员表区间：起于「## 成员表」或「## §A」，止于下列任一标题
START_MARKS = ("## 成员表", "## §A")
STOP_MARKS = (
    "## 边界与排除记录",
    "## 待开发者确认",
    "## 检索记录",
    "## 数据结构建议",
    "## 交叉引用",
    "## 多 TAG 检查",
)
SEP_ROW = re.compile(r"^\|[\s:|-]+\|$")


def load_tags() -> list[tuple[str, str, pathlib.Path]]:
    """扫描分文件，返回 [(TAG 名, 文件路径), ...]，按编号排序。"""
    out = []
    for path in PARTS.glob("*.md"):
        m = re.fullmatch(r"(\d{2})-(.+)\.md", path.name)
        if m:
            out.append((int(m.group(1)), m.group(2), path))
    out.sort(key=lambda t: t[0])
    return [(name, path) for _, name, path in out]


def main_table_members(path: pathlib.Path) -> list[str]:
    """读取分文件主成员表第一列的干员名（按表内顺序，去重取值）。"""
    names: list[str] = []
    inside = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            inside = line.startswith(START_MARKS) and not line.startswith(STOP_MARKS)
            continue
        if not inside or not line.startswith("|") or SEP_ROW.match(line):
            continue
        first = line.strip("|").split("|")[0].strip().replace("**", "")
        if first and first != "干员" and first not in names:
            names.append(first)
    return names


def close_matches(word: str, pool: list[str], n: int = 3) -> str:
    hits = difflib.get_close_matches(word, pool, n=n, cutoff=0.4)
    return f"（相近：{'、'.join(hits)}）" if hits else ""


def load_recommend() -> dict[str, list[str]]:
    if not RECOMMEND.exists():
        return {}
    data = json.loads(RECOMMEND.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{RECOMMEND} 格式错误：顶层应为 JSON 对象")
    return {k: list(v) for k, v in data.items()}


def save_recommend(data: dict[str, list[str]], order: list[str]) -> None:
    """按 TAG 编号顺序写回；空名单的 TAG 不写入文件。"""
    ordered = {tag: data[tag] for tag in order if data.get(tag)}
    for tag in data:  # 顺序表之外的键（异常数据）保留在末尾
        if tag not in ordered and data[tag]:
            ordered[tag] = data[tag]
    RECOMMEND.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def resolve_tag(tag: str, tags: list[str]) -> str:
    if tag in tags:
        return tag
    raise SystemExit(f"未知 TAG：{tag}{close_matches(tag, tags)}\n可用 TAG：{'、'.join(tags)}")


def cmd_list(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args) -> int:
    if getattr(args, "tag", None):
        name = resolve_tag(args.tag, [t for t, _ in tags])
        ops = data.get(name, [])
        print(f"「{name}」荐（{len(ops)} 人）：")
        for op in ops:
            mark = "" if op in main_table_members(dict(tags)[name]) else "  <- 已不在该 TAG 成员表，请用 check 复核"
            print(f"  {op}{mark}")
        return 0
    print("玩家体感 TAG 荐一览：")
    for name, path in tags:
        ops = data.get(name, [])
        print(f"  {name}：{len(ops)} 人" + (f"（{'、'.join(ops)}）" if ops else ""))
    return 0


def cmd_add(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args) -> int:
    name = resolve_tag(args.tag, [t for t, _ in tags])
    members = main_table_members(dict(tags)[name])
    ops = data.setdefault(name, [])
    new_ops: list[str] = []
    for op in args.operators:
        if op not in members:
            raise SystemExit(
                f"「{op}」不是「{name}」的成员，不能设为荐。"
                f"{close_matches(op, members)}\n"
                "（边界与排除记录中的干员不在主表内；如名单有误请先修改分文件）"
            )
        if op in ops or op in new_ops:
            print(f"  跳过：{op} 已是「{name}」的荐")
        else:
            new_ops.append(op)
            print(f"  添加：{op} -> 「{name}」")
    if new_ops:
        ops.extend(new_ops)
        save_recommend(data, [t for t, _ in tags])
        print(f"「{name}」当前荐：{'、'.join(ops)}")
    return 0


def cmd_remove(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args) -> int:
    name = resolve_tag(args.tag, [t for t, _ in tags])
    ops = data.get(name, [])
    changed = False
    for op in args.operators:
        if op in ops:
            ops.remove(op)
            changed = True
            print(f"  移除：{op} <- 「{name}」")
        else:
            print(f"  跳过：{op} 不在「{name}」的荐名单中")
    if changed:
        save_recommend(data, [t for t, _ in tags])
        print(f"「{name}」当前荐：{'、'.join(ops) if ops else '（空）'}")
    return 0


def cmd_check(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args) -> int:
    tag_names = [t for t, _ in tags]
    problems: list[str] = []
    for name, ops in data.items():
        if name not in tag_names:
            problems.append(f"未知 TAG：{name}")
            continue
        members = main_table_members(dict(tags)[name])
        dup = {op for op in ops if ops.count(op) > 1}
        for op in ops:
            if op not in members:
                problems.append(f"「{name}」的荐 {op} 不在该 TAG 成员表中{close_matches(op, members)}")
        for op in sorted(dup):
            problems.append(f"「{name}」的荐 {op} 重复出现")

    n_ops = sum(len(v) for v in data.values())
    print(f"荐文件：{RECOMMEND.relative_to(ROOT)}")
    print(f"共 {len(data)} 个 TAG 设有荐、{n_ops} 条荐；TAG 总数 {len(tag_names)}。")
    if problems:
        print("发现问题：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("校验通过。")
    return 0


def main() -> int:
    tags = load_tags()
    if not tags:
        raise SystemExit(f"未在 {PARTS} 找到分 TAG 文件（NN-*.md）")
    data = load_recommend()

    parser = argparse.ArgumentParser(
        description="玩家体感 TAG「荐」维护工具（数据文件：_recommend.json）"
    )
    sub = parser.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="查看荐名单")
    p_list.add_argument("tag", nargs="?", help="TAG 名；省略时列出全部 TAG")
    p_add = sub.add_parser("add", help="添加荐")
    p_add.add_argument("tag", help="TAG 名")
    p_add.add_argument("operators", nargs="+", help="干员名（可多个）")
    p_rm = sub.add_parser("remove", help="移除荐")
    p_rm.add_argument("tag", help="TAG 名")
    p_rm.add_argument("operators", nargs="+", help="干员名（可多个）")
    sub.add_parser("check", help="校验荐名单")
    args = parser.parse_args()

    if args.cmd in (None, "list"):
        return cmd_list(tags, data, args)
    if args.cmd == "add":
        return cmd_add(tags, data, args)
    if args.cmd == "remove":
        return cmd_remove(tags, data, args)
    if args.cmd == "check":
        return cmd_check(tags, data, args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

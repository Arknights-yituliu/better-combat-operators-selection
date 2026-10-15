# -*- coding: utf-8 -*-
"""玩家体感 TAG「荐」维护工具。

「荐」＝人工指定的名单。默认指定「该 TAG 下推荐新手优先培养」的干员；当该 TAG
没有值得新手优先培养的干员时，转为指定「该 TAG 下综合实力较强」的干员（写入
兜底文件）。两份名单均人工指定，程序只负责读取与渲染。

**作用域**：有子 TAG 的顶级 TAG，荐一律下沉到子 TAG——键写 `TAG/子值`（如
`高档控制/纯御天花板`），裸 TAG 键不得放人（`add` 拒绝、`check` 列出）；没有子 TAG 的顶级 TAG 用裸 TAG 键。
子值即前端可见的子 TAG 名（`results/operator-tags.json` 中该 TAG 的 subTags.values）。

数据文件：

    agent_workspace/tag_pipeline/player_tags/_recommend.json
        { "充电": ["白铁", "娜斯提"], "高档控制/纯御天花板": ["蛇屠箱"] }
    agent_workspace/tag_pipeline/player_tags/_recommend_fallback.json
        { ... }   # 兜底荐：该作用域没有新手向荐时展示的第二名单

生成最终结果 JSON（见 docs/output-standard.md §6）时按作用域合并进
`recommended` / `recommendedBySub`（及其 Fallback 对应字段）。

用法：
    python tools/recommend.py                     # 列出 11 个 TAG 及当前荐
    python tools/recommend.py list 充电           # 查看某 TAG 的荐（含各子作用域）
    python tools/recommend.py list 高档控制/纯御天花板
    python tools/recommend.py add 充电/直接补充技力 白铁 [干员...]
    python tools/recommend.py add 高档控制/纯御天花板 蛇屠箱
    python tools/recommend.py remove 充电/直接补充技力 白铁 [干员...]
    python tools/recommend.py --fallback add 高档控制/纯御天花板 蛇屠箱
    python tools/recommend.py check               # 校验两份名单（TAG／子值／成员是否有效）

校验：TAG 必须存在；子值必须是该 TAG 的子 TAG 名；干员必须是该 TAG 主表成员或
组合名——边界与排除记录里的干员不能设为荐（避免悬空引用）；有子 TAG 的 TAG 不得使用
裸 TAG 键（TAG 级不承载，荐需下沉到子 TAG）。本工具只写荐数据文件。
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTS = ROOT / "agent_workspace" / "tag_pipeline" / "player_tags"
sys.path.insert(0, str(PARTS.parent))
import partdoc  # noqa: E402  （分文件 JSON 的唯一读写实现）
import tag_order  # noqa: E402  （TAG 展示顺序的唯一维护处）


def _tag_order() -> dict:
    """顺序文件（惰性加载：坏文件不应在 import 期炸掉本模块）。"""
    try:
        return tag_order.load()
    except tag_order.OrderError:
        return tag_order.empty_order()


RECOMMEND = PARTS / "_recommend.json"
RECOMMEND_FALLBACK = PARTS / "_recommend_fallback.json"

SEP_ROW = re.compile(r"^\|[\s:|-]+\|$")


def load_tags() -> list[tuple[str, str, pathlib.Path]]:
    """扫描分文件（NN-*.json），返回 [(TAG 名, 文件路径), ...]，按编号排序。"""
    out = []
    for path in PARTS.glob("*.json"):
        m = re.fullmatch(r"(\d{2})-(.+)\.json", path.name)
        if m:
            out.append((int(m.group(1)), m.group(2), path))
    order = _tag_order()
    rank = tag_order.player_rank(order)
    # 顺序文件的玩家 TAG 序（未登记的回退到编号序，置于末尾）
    out.sort(key=lambda t: (rank.get(f"P{t[0]}", len(rank)), t[0]))
    return [(name, path) for _, name, path in out]


def main_table_members(path: pathlib.Path) -> list[str]:
    """读取分文件主成员表第一列的干员名（按文档顺序，去重取值）。

    与视图侧同语义：`## 成员表…` 节内一切竖线行——成员表数据行与空行隔开的
    孤立单行（12 的 B 组合提供者行）——都取第一列（已是现行行为，逐字节保持）。
    """
    doc = partdoc.load(path)
    names: list[str] = []

    def take(line: str) -> None:
        if not line.startswith("|") or SEP_ROW.match(line.strip()):
            return
        first = line.strip("|").split("|")[0].strip().replace("**", "")
        if first and first != "干员" and first not in names:
            names.append(first)

    in_members = False
    for it in doc["body"]:
        if it["t"] == "heading":
            if it["level"] == 2:
                in_members = partdoc.clean_heading(it["text"]).startswith("成员表")
        elif in_members and it["t"] == "p":
            for line in it["lines"]:
                take(line)
        elif in_members and it["t"] == "table":
            for row in it["rows"]:
                first = row[0].replace("**", "").strip()
                if first and first != "干员" and first not in names:
                    names.append(first)
    return names


def combo_names(path: pathlib.Path) -> list[str]:
    """阵容组合（12）：成员表区间内 `### A<N>.`（势力）/ `### B<N>.`（用法）标题去序号前缀。"""
    doc = partdoc.load(path)
    names: list[str] = []
    in_members = False
    for it in doc["body"]:
        if it["t"] != "heading":
            continue
        if it["level"] == 2:
            in_members = partdoc.clean_heading(it["text"]).startswith("成员表")
            continue
        if not in_members:
            continue
        m = re.fullmatch(r"### [AB]\d+\.\s*(.+)", it["text"].strip())
        if m and m.group(1).strip() not in names:
            names.append(m.group(1).strip())
    return names


def recommendable_members(path: pathlib.Path) -> list[str]:
    """可设为荐的名字：默认＝主表成员；阵容组合另含组合名（荐可为组合或单个提供者，两者独立）。"""
    members = main_table_members(path)
    if path.name.startswith("12-"):
        return members + [n for n in combo_names(path) if n not in members]
    return members


def close_matches(word: str, pool: list[str], n: int = 3) -> str:
    hits = difflib.get_close_matches(word, pool, n=n, cutoff=0.4)
    return f"（相近：{'、'.join(hits)}）" if hits else ""


def split_key(key: str) -> tuple[str, str | None]:
    """`TAG` 或 `TAG/子值` → (TAG, 子值 or None)；TAG 名不含「/」。"""
    tag, sep, scope = key.partition("/")
    return tag, (scope if sep else None)



_SUB_CACHE: dict[str, list[str]] | None = None


def tag_scope_values(tag_name: str) -> list[str] | None:
    """该 TAG 可作为荐作用域的子项值（取自生成产物，保持出现顺序）。
    产物不存在或该 TAG 未收录时返回 None（跳过子值校验）。"""
    global _SUB_CACHE
    if _SUB_CACHE is None:
        _SUB_CACHE = {}
        rp = ROOT / "results" / "operator-tags.json"
        if rp.exists():
            for t in json.loads(rp.read_text(encoding="utf-8")).get("tags", []):
                if t.get("source") != "player":
                    continue
                vals: list[str] = []
                for m in t.get("members", []):
                    for s in m.get("subTags", []):
                        if s.get("value") and s["value"] not in vals:
                            vals.append(s["value"])
                rank = tag_order.sub_rank(_tag_order(), str(t.get("id") or ""))
                if rank:  # 作用域栏顺序与 tag_order.json 同步（按 id，改名不丢位）
                    kv = [(str(s.get("group") or ""), str(s.get("value") or "")) for s in
                          (x for m in t.get("members", []) for x in m.get("subTags", []))]
                    pos = {}
                    for g, v in kv:
                        if v not in pos or rank.get((g, v), len(rank)) < pos[v]:
                            pos[v] = rank.get((g, v), len(rank))
                    vals.sort(key=lambda v: pos.get(v, len(rank)))
                _SUB_CACHE[t["name"]] = vals
    return _SUB_CACHE.get(tag_name)


def load_recommend(path: pathlib.Path = RECOMMEND) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} 格式错误：顶层应为 JSON 对象")
    return {k: list(v) for k, v in data.items()}


def save_recommend(data: dict[str, list[str]], order: list[str], path: pathlib.Path = RECOMMEND) -> None:
    """按 TAG 编号顺序写回（同 TAG 下先 TAG 级、再按子值排序）；空名单的键不写入文件。"""
    tag_index = {t: i for i, t in enumerate(order)}

    def sort_key(k: str) -> tuple:
        tag, scope = split_key(k)
        return (tag_index.get(tag, 10 ** 6), 0 if scope is None else 1, scope or "")

    ordered = {k: data[k] for k in sorted((k for k in data if data.get(k)), key=sort_key)}
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def resolve_tag(tag: str, tags: list[str]) -> str:
    if tag in tags:
        return tag
    raise SystemExit(f"未知 TAG：{tag}{close_matches(tag, tags)}\n可用 TAG：{'、'.join(tags)}")


def resolve_scope(tag: str, scope: str) -> str:
    vals = tag_scope_values(tag)
    if vals is None:
        return scope
    if scope in vals:
        return scope
    raise SystemExit(f"「{tag}」没有子 TAG「{scope}」{close_matches(scope, vals)}\n可用子 TAG：{'、'.join(vals)}")


def cmd_list(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args) -> int:
    tag_names = [t for t, _ in tags]
    if getattr(args, "tag", None):
        raw = args.tag
        tag, scope = split_key(raw)
        name = resolve_tag(tag, tag_names)
        members = recommendable_members(dict(tags)[name])

        def show(key: str) -> None:
            ops = data.get(key, [])
            print(f"「{key}」荐（{len(ops)} 人）：")
            for op in ops:
                mark = "" if op in members else "  <- 已不在该 TAG 成员表／组合名中，请用 check 复核"
                print(f"  {op}{mark}")

        if scope is None:
            show(name)
            for k in data:
                t2, s2 = split_key(k)
                if t2 == name and s2 and data[k]:
                    show(k)
        else:
            resolve_scope(name, scope)
            show(f"{name}/{scope}")
        return 0
    print("玩家体感 TAG 荐一览（含子作用域）：")
    for name, _path in tags:
        keys = [k for k in data if split_key(k)[0] == name and data[k]]
        n = sum(len(data[k]) for k in keys)
        detail = "；".join(f"{split_key(k)[1]}（{len(data[k])}）" for k in keys if split_key(k)[1])
        print(f"  {name}：{n} 人" + (f"（子作用域：{detail}）" if detail else ""))
    return 0


def cmd_add(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args,
            path: pathlib.Path = RECOMMEND) -> int:
    tag, scope = split_key(args.tag)
    name = resolve_tag(tag, [t for t, _ in tags])
    vals = tag_scope_values(name) or []
    if scope is None and vals:
        raise SystemExit(
            f"「{name}」有子 TAG：荐须落在子 TAG 上（TAG 级不能单独放人）。\n"
            f"可用子 TAG：{'、'.join(vals)}\n"
            f"例：tools/recommend.py add {name}/{vals[0]} 干员名"
        )
    key = name if scope is None else f"{name}/{resolve_scope(name, scope)}"
    members = recommendable_members(dict(tags)[name])
    ops = data.setdefault(key, [])
    new_ops: list[str] = []
    for op in args.operators:
        if op not in members:
            raise SystemExit(
                f"「{op}」不是「{name}」的成员（或组合名），不能设为荐。"
                f"{close_matches(op, members)}\n"
                "（边界与排除记录中的干员不在主表内；阵容组合的「组合名」同样可设为荐；如名单有误请先修改分文件）"
            )
        if op in ops or op in new_ops:
            print(f"  跳过：{op} 已是「{key}」的荐")
        else:
            new_ops.append(op)
            print(f"  添加：{op} -> 「{key}」")
    if new_ops:
        ops.extend(new_ops)
        save_recommend(data, [t for t, _ in tags], path)
        print(f"「{key}」当前荐：{'、'.join(ops)}")
    return 0


def cmd_remove(tags: list[tuple[str, pathlib.Path]], data: dict[str, list[str]], args,
               path: pathlib.Path = RECOMMEND) -> int:
    tag, scope = split_key(args.tag)
    name = resolve_tag(tag, [t for t, _ in tags])
    key = name if scope is None else f"{name}/{resolve_scope(name, scope)}"
    ops = data.get(key, [])
    changed = False
    for op in args.operators:
        if op in ops:
            ops.remove(op)
            changed = True
            print(f"  移除：{op} <- 「{key}」")
        else:
            print(f"  跳过：{op} 不在「{key}」的荐名单中")
    if changed:
        save_recommend(data, [t for t, _ in tags], path)
        print(f"「{key}」当前荐：{'、'.join(ops) if ops else '（空）'}")
    return 0


def _check_one(data: dict[str, list[str]], tag_names: list[str], label: str,
               problems: list[str]) -> None:
    for key, ops in data.items():
        tag, scope = split_key(key)
        if tag not in tag_names:
            problems.append(f"{label}：未知 TAG「{tag}」（键「{key}」）")
            continue
        vals = tag_scope_values(tag)
        if scope is None and vals:
            problems.append(f"{label}：「{key}」是 TAG 级键，但「{tag}」有子 TAG——荐需下沉到子 TAG（如 「{tag}/{vals[0]}」）")
        if scope is not None:
            if vals is None:
                problems.append(f"{label}：「{key}」使用了子值，但生成产物中无此 TAG 的子项数据，无法校验")
            elif scope not in vals:
                problems.append(f"{label}：「{key}」的子值不是「{tag}」的子 TAG{close_matches(scope, vals)}")
        dup = {op for op in ops if ops.count(op) > 1}
        for op in ops:
            if op not in _MEMBER_CACHE.get(tag, []):
                problems.append(f"{label}：「{key}」的「{op}」不在该 TAG 成员表／组合名中")
        for op in sorted(dup):
            problems.append(f"{label}：「{key}」的「{op}」重复出现")


_MEMBER_CACHE: dict[str, list[str]] = {}


def cmd_check(tags: list[tuple[str, pathlib.Path]], primary: dict[str, list[str]],
              fallback: dict[str, list[str]], args) -> int:
    tag_names = [t for t, _ in tags]
    global _MEMBER_CACHE
    _MEMBER_CACHE = {name: recommendable_members(path) for name, path in tags}
    problems: list[str] = []
    for label, data in (("荐", primary), ("兜底荐", fallback)):
        _check_one(data, tag_names, label, problems)

    n_ops = sum(len(v) for v in primary.values())
    n_fb = sum(len(v) for v in fallback.values())
    print(f"荐文件：{RECOMMEND.relative_to(ROOT)}")
    print(f"兜底荐文件：{RECOMMEND_FALLBACK.relative_to(ROOT)}")
    print(f"共 {len([k for k in primary if primary[k]])} 个键设有荐（{n_ops} 条）、"
          f"{len([k for k in fallback if fallback[k]])} 个键设有兜底荐（{n_fb} 条）；TAG 总数 {len(tag_names)}。")
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
        raise SystemExit(f"未在 {PARTS} 找到分 TAG 文件（NN-*.json）")
    primary = load_recommend(RECOMMEND)
    fallback = load_recommend(RECOMMEND_FALLBACK)

    parser = argparse.ArgumentParser(
        description="玩家体感 TAG「荐」维护工具（数据文件：_recommend.json／_recommend_fallback.json）"
    )
    parser.add_argument("--fallback", action="store_true",
                        help="操作「兜底荐」名单：该作用域没有新手向荐时展示的第二名单")
    sub = parser.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="查看荐名单")
    p_list.add_argument("tag", nargs="?", help="TAG 名或 TAG/子值；省略时列出全部 TAG")
    p_add = sub.add_parser("add", help="添加荐")
    p_add.add_argument("tag", help="TAG 名或 TAG/子值")
    p_add.add_argument("operators", nargs="+", help="干员名（可多个）")
    p_rm = sub.add_parser("remove", help="移除荐")
    p_rm.add_argument("tag", help="TAG 名或 TAG/子值")
    p_rm.add_argument("operators", nargs="+", help="干员名（可多个）")
    sub.add_parser("check", help="校验两份名单")
    args = parser.parse_args()

    data = fallback if args.fallback else primary
    path = RECOMMEND_FALLBACK if args.fallback else RECOMMEND
    if args.cmd in (None, "list"):
        return cmd_list(tags, data, args)
    if args.cmd == "add":
        return cmd_add(tags, data, args, path)
    if args.cmd == "remove":
        return cmd_remove(tags, data, args, path)
    if args.cmd == "check":
        return cmd_check(tags, primary, fallback, args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

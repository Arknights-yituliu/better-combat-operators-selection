# -*- coding: utf-8 -*-
"""一次性转换：25 个 TAG 分文件 md → tag-part/json（结构性镜像）。

三门无损校验（任一不过即中止）：
1. 行归属——源文件每一物理行归属到恰好一个 schema 元素（标题 1 行 + 各元素行数求和）；
2. 往返——render(parse(md)) 与「仅把分隔行规范化为 |---|…| 的源文本」逐字节相等；
3. 幂等——--verify 时 load(已写 json) 与本次 parse 结果相等，且再渲染同样通过往返门。

用法（仓库根）：
    py -X utf8 tools/parts_md_to_json.py            # 干跑：解析 + 三门 + 计数对账，不写盘
    py -X utf8 tools/parts_md_to_json.py --write    # 写出 .json 至分文件同目录
    py -X utf8 tools/parts_md_to_json.py --verify   # 复核已写 .json（load ↔ parse 相等 + 往返）
报告写入 agent_workspace/_out/migration-baseline/convert-report.txt。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent_workspace" / "tag_pipeline"))
sys.path.insert(0, str(ROOT / "agent_workspace" / "tag_pipeline" / "player_tags"))
sys.path.insert(0, str(ROOT / "agent_workspace" / "tag_pipeline" / "official_tags"))

import partdoc  # noqa: E402
import _merge_to_docs as pm  # noqa: E402  （玩家分文件名与顺序的唯一来源）
import _merge_official_to_docs as om  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# 与 gui --check 输出对账的成员计数（当前真值）
PLAYER_EXPECT = {"01": (7, 29), "02": (2, 61), "03": (3, 51), "04": (4, 44), "05": (1, 60),
                 "06": (2, 6), "07": (3, 25), "08": (1, 99), "09": (6, 84), "12": (16, 49),
                 "13": (8, 130)}
PLAYER_ROWS_TOTAL = 638
OFFICIAL_EXPECT = (79, 1231)

DEF_RE = re.compile(r"^\*\*(?P<name>.+)\*\*（(?P<n>\d+) 人 · 首现 (?P<d>[\d-]+)）：(?P<rest>.*)$")
HEAD_RE = re.compile(r"^(#{2,6}) (.+)$")


class ConvertError(Exception):
    pass


def split_lines(text: str) -> tuple[list[str], int]:
    parts = text.split("\r\n")
    trailing = 0
    while parts and parts[-1] == "":
        parts.pop()
        trailing += 1
    return parts, trailing


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ConvertError(f"{path.name}: 含 BOM")
    text = raw.decode("utf-8")
    if text.count("\n") != text.count("\r\n") or "\r" in text.replace("\r\n", ""):
        raise ConvertError(f"{path.name}: 存在非 CRLF 换行")
    return text


def is_sep(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def cells_of(s: str) -> list[str]:
    return [c.strip() for c in s.strip().strip("|").split("|")]


def parse_table(block: list[str], where: str, lineno: int) -> tuple[dict, int, int]:
    """md 表格行组 → (table item, 分隔行行号(1 起), 列数)。"""
    header = cells_of(block[0])
    if len(block) < 2:
        raise ConvertError(f"{where}:{lineno}: 孤立的竖线行（块长 {len(block)}）：{block[0][:60]!r}")
    if not is_sep(cells_of(block[1])):
        raise ConvertError(f"{where}:{lineno}: 表格第 2 行不是分隔行：{block[1][:60]!r}")
    rows = []
    for k, ln in enumerate(block[2:]):
        cs = cells_of(ln)
        if len(cs) != len(header):
            raise ConvertError(f"{where}:{lineno + 2 + k}: 行宽 {len(cs)} ≠ 列数 {len(header)}：{ln[:60]!r}")
        rows.append(cs)
    return {"t": "table", "columns": header, "rows": rows}, lineno + 1, len(header)


def canon_text(lines: list[str], trailing: int, sep_fixes: list[tuple[int, int]]) -> str:
    out = list(lines)
    for lineno, ncols in sep_fixes:
        out[lineno - 1] = "|" + "---|" * ncols
    return "\r\n".join(out) + "\r\n" * trailing


def check_roundtrip(where: str, doc: dict, canon: str) -> None:
    partdoc.validate(doc, where)
    rendered = partdoc.render(doc)
    if rendered != canon:
        for k, (a, b) in enumerate(zip(rendered.split("\r\n"), canon.split("\r\n"))):
            if a != b:
                raise ConvertError(f"{where}: 往返首个差异在第 {k + 1} 行：\n"
                                   f"  render: {a[:120]!r}\n  canon : {b[:120]!r}")
        raise ConvertError(f"{where}: 往返长度不一致 {len(rendered)} vs {len(canon)}")


def parse_player(path: Path) -> tuple[dict, str, int]:
    text = read_text(path)
    lines, trailing = split_lines(text)
    num = path.name[:2]
    name = path.stem.split("-", 1)[1]
    if lines[0] != f"# {name}":
        raise ConvertError(f"{path.name}: 首行应为「# {name}」，实为 {lines[0]!r}")
    body: list[dict] = []
    p_buf: list[str] = []
    sep_fixes: list[tuple[int, int]] = []
    in_fence = False
    consumed = 1  # 标题行

    def flush_p() -> None:
        nonlocal consumed
        if p_buf:
            body.append({"t": "p", "lines": list(p_buf)})
            consumed += len(p_buf)
            p_buf.clear()

    i = 1
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            in_fence = not in_fence
        if ln.startswith("|"):
            if in_fence:
                raise ConvertError(f"{path.name}:{i + 1}: 代码块内出现表格行")
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            if j - i == 1:
                # 孤立单行竖线（如 12 的 B1/B2 组合中空行隔开的提供者行）：现行管道的语义是
                # 合并视图原样透传、GUI 与生成器一律跳过——按原文行存储即精确镜像。
                p_buf.append(ln)
                i += 1
                continue
            flush_p()
            item, sep_lineno, ncols = parse_table(lines[i:j], path.name, i + 1)
            sep_fixes.append((sep_lineno, ncols))
            body.append(item)
            consumed += (j - i)
            i = j
            continue
        mh = HEAD_RE.match(ln)
        if mh:
            if in_fence:
                raise ConvertError(f"{path.name}:{i + 1}: 代码块内出现标题行")
            flush_p()
            body.append({"t": "heading", "level": len(mh.group(1)), "text": ln})
            consumed += 1
            i += 1
            continue
        if re.match(r"^\s+\|", ln):
            raise ConvertError(f"{path.name}:{i + 1}: 缩进的竖线行（合并脚本会当表格处理）：{ln[:60]!r}")
        p_buf.append(ln)
        i += 1
    flush_p()
    if consumed != len(lines):
        raise ConvertError(f"{path.name}: 行归属 {consumed} ≠ 总行数 {len(lines)}")
    doc = {"format": partdoc.FORMAT, "kind": "player", "num": num, "name": name,
           "title": lines[0], "body": body, "trailing_newlines": trailing}
    return doc, canon_text(lines, trailing, sep_fixes), len(sep_fixes)


def parse_official(path: Path) -> tuple[dict, str, int]:
    text = read_text(path)
    lines, trailing = split_lines(text)
    entries: list[dict] = []
    def_lines: list[str] = []
    cur: dict | None = None
    p_buf: list[str] = []
    sep_fixes: list[tuple[int, int]] = []
    consumed = 0

    def flush_p() -> None:
        nonlocal consumed
        if p_buf and cur is not None:
            cur["items"].append({"t": "p", "lines": list(p_buf)})
            consumed += len(p_buf)
            p_buf.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        m = DEF_RE.match(ln)
        if m:
            flush_p()
            cur = {"name": m.group("name"), "rest": m.group("rest"), "items": []}
            entries.append(cur)
            def_lines.append(ln)
            consumed += 1
            i += 1
            continue
        if cur is None:
            raise ConvertError(f"{path.name}:{i + 1}: 条目头之前的行：{ln[:60]!r}")
        if ln.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            flush_p()
            if any(it["t"] == "table" for it in cur["items"]):
                raise ConvertError(f"{path.name}:{i + 1}: 同一条目出现第二张表")
            item, sep_lineno, ncols = parse_table(lines[i:j], path.name, i + 1)
            if item["columns"] != ["干员", "编号", "条件", "备注"]:
                raise ConvertError(f"{path.name}:{i + 1}: 列头异常：{item['columns']}")
            sep_fixes.append((sep_lineno, ncols))
            cur["items"].append(item)
            consumed += (j - i)
            i = j
            continue
        p_buf.append(ln)
        i += 1
    flush_p()
    if consumed != len(lines):
        raise ConvertError(f"{path.name}: 行归属 {consumed} ≠ 总行数 {len(lines)}")
    # 条目头声明值与派生值对账（转换即验证「0 处失配」）
    for e, ln0 in zip(entries, def_lines):
        m = DEF_RE.match(ln0)
        n, first = partdoc.official_stat(e)
        if int(m.group("n")) != n or m.group("d") != first:
            raise ConvertError(f"{path.name}: 条目「{e['name']}」头为 {m.group('n')}/{m.group('d')}，"
                               f"派生为 {n}/{first}")
    doc = {"format": partdoc.FORMAT, "kind": "official", "entries": entries,
           "trailing_newlines": trailing}
    return doc, canon_text(lines, trailing, sep_fixes), len(sep_fixes)


def main() -> int:
    mode = "write" if "--write" in sys.argv else ("verify" if "--verify" in sys.argv else "dry")
    report: list[str] = []
    errors: list[str] = []
    player_rows_total = 0
    official_entries_total = 0
    official_rows_total = 0

    for num, name, md_name in pm.TAGS:
        md_path = ROOT / "agent_workspace" / "tag_pipeline" / "player_tags" / md_name
        json_path = md_path.with_suffix(".json")
        try:
            doc, canon, n_fix = parse_player(md_path)
            check_roundtrip(md_name, doc, canon)
            tables = list(partdoc.member_tables(doc))
            got = (len(tables), sum(len(t[3]) for t in tables))
            if got != PLAYER_EXPECT[num]:
                raise ConvertError(f"{md_name}: 成员表计数 {got} ≠ 预期 {PLAYER_EXPECT[num]}")
            player_rows_total += got[1]
            if mode == "write":
                partdoc.save(doc, json_path)
            elif mode == "verify":
                back = partdoc.load(json_path)
                if back != doc:
                    raise ConvertError(f"{json_path.name}: 已写 json 与本次解析不一致")
                check_roundtrip(json_path.name, back, canon)
            report.append(f"OK  player  {md_name}：成员表 {got[0]} / 行 {got[1]}，"
                          f"结尾换行 {doc['trailing_newlines']}，分隔行规范化 {n_fix}")
        except ConvertError as e:
            errors.append(str(e))

    for cat, flist in om.FILES:
        for md_name in flist:
            md_path = ROOT / "agent_workspace" / "tag_pipeline" / "official_tags" / md_name
            json_path = md_path.with_suffix(".json")
            try:
                doc, canon, n_fix = parse_official(md_path)
                check_roundtrip(md_name, doc, canon)
                n_rows = sum(len(it["rows"]) for e in doc["entries"]
                             for it in e["items"] if it["t"] == "table")
                official_entries_total += len(doc["entries"])
                official_rows_total += n_rows
                if mode == "write":
                    partdoc.save(doc, json_path)
                elif mode == "verify":
                    back = partdoc.load(json_path)
                    if back != doc:
                        raise ConvertError(f"{json_path.name}: 已写 json 与本次解析不一致")
                    check_roundtrip(json_path.name, back, canon)
                report.append(f"OK  official {md_name}：条目 {len(doc['entries'])} / 行 {n_rows}，"
                              f"结尾换行 {doc['trailing_newlines']}，分隔行规范化 {n_fix}")
            except ConvertError as e:
                errors.append(str(e))

    if not errors:
        if player_rows_total != PLAYER_ROWS_TOTAL:
            errors.append(f"玩家成员行合计 {player_rows_total} ≠ 预期 {PLAYER_ROWS_TOTAL}")
        if (official_entries_total, official_rows_total) != OFFICIAL_EXPECT:
            errors.append(f"官方条目/行合计 {official_entries_total}/{official_rows_total} "
                          f"≠ 预期 {OFFICIAL_EXPECT}")
    print("\n".join(report))
    if errors:
        print("\n=== 失败 ===")
        for e in errors:
            print("✗", e)
        return 1
    print(f"\n全部通过：玩家 {len(pm.TAGS)} 文件（成员行合计 {player_rows_total}）、"
          f"官方 {sum(len(f) for _, f in om.FILES)} 文件（条目 {official_entries_total} / 行 {official_rows_total}）。"
          f"模式={mode}")
    out = ROOT / "agent_workspace" / "_out" / "migration-baseline" / "convert-report.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

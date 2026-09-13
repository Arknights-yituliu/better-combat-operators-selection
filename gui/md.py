# -*- coding: utf-8 -*-
"""markdown 表格的行级读写：单元格工具、原子写、按原始行号寻址的 Doc 单元模型。"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import time

from .errors import UserError


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def row_op(cells: list[str]) -> str:
    return cells[0].replace("**", "").strip() if cells else ""


def sig_of(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:8]


def write_atomic(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    os.replace(tmp, path)


class Doc:
    """一次读入的文档：按原始行号（uid）寻址增删改，最后整体原子写回。"""

    def __init__(self, path: pathlib.Path, kind: str):
        self.path, self.kind = path, kind
        self.text = path.read_text(encoding="utf-8", newline="")
        self.eol = "\r\n" if "\r\n" in self.text else "\n"
        self.units: list[list] = [[i + 1, t] for i, t in enumerate(self.text.splitlines(keepends=True))]

    def text_of(self, uid: int) -> str:
        for u in self.units:
            if u[0] == uid:
                return u[1].rstrip("\r\n")
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def replace(self, uid: int, text_no_eol: str) -> None:
        for u in self.units:
            if u[0] == uid:
                eol = "\r\n" if u[1].endswith("\r\n") else ("\n" if u[1].endswith("\n") else "")
                u[1] = text_no_eol + eol
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def insert_before(self, uid: int, text_no_eol: str) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                self.units.insert(i, [-1, text_no_eol + self.eol])
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def insert_after(self, uid: int, text_no_eol: str) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                if not u[1].endswith(("\n", "\r")):
                    u[1] += self.eol
                self.units.insert(i + 1, [-1, text_no_eol + self.eol])
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def delete(self, uid: int) -> None:
        for i, u in enumerate(self.units):
            if u[0] == uid:
                del self.units[i]
                return
        raise UserError("行号越界，文件可能已被外部改动，请点「刷新数据」后重试")

    def rows_after(self, header_uid: int) -> list[list]:
        """表头之后连续以 | 开头的行（含分隔行）。"""
        out, started = [], False
        for u in self.units:
            if u[0] == header_uid:
                started = True
                continue
            if not started:
                continue
            if u[1].lstrip().startswith("|"):
                out.append(u)
            else:
                break
        return out

    def render(self) -> str:
        return "".join(u[1] for u in self.units)


def parse_block_id(bid: str) -> tuple[str, str, int]:
    kind, _, rest = bid.partition(":")
    fname, _, idx = rest.rpartition("#")
    try:
        return kind, fname, int(idx)
    except ValueError:
        raise UserError(f"无效的子表编号：{bid}") from None


def build_row(header: list[str], op: str, cells: dict[str, str]) -> str:
    parts = []
    for c in header:
        v = op if c == "干员" else (cells.get(c, "") or "")
        parts.append(f" {v} " if v else "  ")
    return "|" + "|".join(parts) + "|"


def check_value(label: str, value: str) -> str:
    if "|" in value:
        raise UserError(f"{label}不能包含竖线 |（会破坏表格结构）")
    if "\n" in value or "\r" in value:
        raise UserError(f"{label}不能包含换行（表格单元格必须单行）")
    return value.strip()

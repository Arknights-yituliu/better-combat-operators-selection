# -*- coding: utf-8 -*-
"""可以直接展示给使用者的错误。"""

from __future__ import annotations


class UserError(Exception):
    """可以直接展示给使用者的错误（code 供前端区分处理，如漂移 / 重名 / 解析失败）。"""

    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code

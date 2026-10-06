# -*- coding: utf-8 -*-
"""HTTP 层：路由、令牌、静态资源与全局写锁。"""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import STATIC_DIR, STATIC_TYPES
from .errors import UserError
from .merges import run_merge
from .model import build_model
from .recommends import apply_recommend
from .results_json import check_results, list_results, load_results, save_results
from .writeback import apply_ops, save_cell

# 写锁：覆盖 build_model 与所有写入路径（含合并子进程），避免并发丢更新
LOCK = threading.RLock()
TOKEN = secrets.token_urlsafe(18)


def render_index() -> bytes:
    """把 __TOKEN__ 替换为本次会话的令牌后返回首页。"""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    n = html.count("__TOKEN__")
    if n != 1:
        raise RuntimeError(f"gui/static/index.html 里的 __TOKEN__ 应恰好出现一次，实际 {n} 次")
    return html.replace("__TOKEN__", TOKEN).encode("utf-8")


def static_bytes(name: str) -> tuple[bytes, str] | None:
    """白名单静态资源（index.html / app.css / app.js）；越界或不存在返回 None。"""
    ctype = STATIC_TYPES.get(name)
    if ctype is None:
        return None
    path = (STATIC_DIR / name).resolve()
    if path.parent != STATIC_DIR.resolve() or not path.is_file():
        return None
    return path.read_bytes(), ctype


class Handler(BaseHTTPRequestHandler):
    server_version = "RecommendGui"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 静默，不打访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        path, qs = parts.path, urllib.parse.parse_qs(parts.query)
        try:
            if path in ("/", "/index.html"):
                self._send(200, render_index(), "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                got = static_bytes(path[len("/static/"):])
                if got is None:
                    self._json({"ok": False, "error": "not found"}, 404)
                else:
                    self._send(200, got[0], got[1])
            elif path == "/api/data":
                with LOCK:
                    self._json(build_model(fresh=qs.get("fresh") == ["1"]))
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if self.headers.get("X-Token") != TOKEN:
            self._json({"ok": False, "error": "令牌无效，请刷新页面"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            with LOCK:
                if path == "/api/recommend":
                    self._json(apply_recommend(payload))
                elif path == "/api/cell":
                    self._json(save_cell(payload["file"], int(payload["line"]), payload["original"], payload["cond"], payload["note"], payload.get("sub"), payload.get("subcol", "子 TAG")))
                elif path == "/api/apply":
                    self._json(apply_ops(payload))
                elif path == "/api/results/list":
                    self._json(list_results())
                elif path == "/api/results/load":
                    self._json(load_results(payload))
                elif path == "/api/results/check":
                    self._json(check_results(payload))
                elif path == "/api/results/save":
                    self._json(save_results(payload))
                elif path == "/api/merge":
                    self._json(run_merge(payload.get("which", "both")))
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
        except UserError as exc:
            self._json({"ok": False, "error": str(exc), "code": getattr(exc, "code", "")}, 400)
        except KeyError as exc:
            self._json({"ok": False, "error": f"请求缺少字段：{exc}"}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": f"服务端异常：{exc}"}, 500)

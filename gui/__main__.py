# -*- coding: utf-8 -*-
"""干员 TAG 名单维护面板（本地网页版）。三个页签：

「荐」  只管玩家体感 TAG 的荐：左键干员 = 加荐，右键 = 取消荐；点「详情」在右栏查看干员信息卡片。
「人工归纳」  上半筛选（左 TAG 树 / 右干员列表）、下半临时区、右侧全量干员摘选区：
    · 摘选区左键 = 以「扩展」方式放入临时区（并入后新行的条件/备注为空，自行填写）。
    · 干员行右键 = 扩展 / 移动 / 移除；移动会把源行的条件/备注/依据带到新行，
      落点成功后再删除源行；移除 = 直接删除该行。
    · 选中 TAG 子表（区块）后点临时区条目即并入；Ctrl 多选可一次并入多个区块，
      移动只允许落到一个区块。
    · 干员卡片内点击 条件 / 备注 即可编辑（Enter/✓ 保存，Esc/× 取消，不自动保存）。
「结果 JSON」  编辑 results/ 下的结果 JSON（规范：docs/output-standard.md）：
    · 「加载…」选 results/*.json，或「新建骨架」起一份符合规范的空文档；
    · 编辑只发生在内存（结构化卡片 + 源码视图共用同一份数据），点「保存…」才写盘，
      保存可选「覆盖已有文件」或「新建自定义文件名」，写盘前按规范列出问题但不阻断。

写入的文件（前两页即时落盘，「结果 JSON」页仅在点保存时写）：
    material_datas/tag_pipeline/player_tags/_recommend.json   （荐）
    material_datas/tag_pipeline/player_tags/NN-*.md           （成员行增删、条件/备注）
    material_datas/tag_pipeline/official_tags/[A-I]-*.md      （成员行增删、条件/备注、条目头人数重算）
    results/*.json                                             （结果 JSON 页保存）
    docs/player-tags-members.md、docs/official-tags-members.md 由合并脚本重新生成（只读）。

用法：
    .venv/Scripts/python.exe -X utf8 recommend_gui.py                  # 启动并打开浏览器
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --port 8520 --no-browser
    .venv/Scripts/python.exe -X utf8 recommend_gui.py --check          # 只解析自检，不起服务
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

if __package__ in (None, ""):  # 支持 python gui/__main__.py
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from gui.config import STATIC_DIR
from gui.selfcheck import run_check
from gui.server import Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="干员 TAG 名单维护面板（荐 + 人工归纳 + 结果 JSON，本地网页版）")
    parser.add_argument("--port", type=int, default=8520, help="监听端口（默认 8520，被占用时自动换一个）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="只解析自检一次，不起服务")
    args = parser.parse_args()

    if args.check:
        return run_check()

    if not STATIC_DIR.is_dir():
        print(f"缺少静态资源目录：{STATIC_DIR}", file=sys.stderr)
        return 1

    port = args.port
    for candidate in (port, 0):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = srv.server_address[1]
            break
        except OSError:
            continue
    else:
        print("无法绑定本地端口", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}/"
    print(f"名单维护面板已启动：{url}")
    print("   「荐」页：左键加荐 / 右键取消荐；「人工归纳」页：选子表后并入、右键扩展/移动/移除；")
    print("   「结果 JSON」页：载入 results/*.json 后在内存中编辑，点「保存…」选覆盖或另存；Ctrl+C 退出")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

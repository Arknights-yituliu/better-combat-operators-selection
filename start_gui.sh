#!/usr/bin/env sh
# 一键启动干员 TAG 维护面板（GUI 仅依赖 Python 标准库）
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
exec "$PY" -X utf8 recommend_gui.py "$@"
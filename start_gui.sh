#!/usr/bin/env sh
# One-click launcher for the TAG maintenance panel (stdlib-only GUI).
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
exec "$PY" -X utf8 recommend_gui.py "$@"
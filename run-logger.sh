#!/bin/bash
# Fire Logger — background runner. The launchd agent calls this.
# It runs the recorder under caffeinate, which keeps the Mac awake
# (no idle sleep) for as long as the recorder is running.
# The screen can still go dark — only full system sleep is prevented.
cd "$(dirname "$0")" || exit 1

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

exec /usr/bin/caffeinate -i "$PY" -u recorder.py

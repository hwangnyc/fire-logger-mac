#!/bin/bash
# Fire Logger — transcriber runner. The launchd agent calls this.
# Uses the Whisper environment (.venv-whisper), never the recorder's.
cd "$(dirname "$0")" || exit 1

PY=".venv-whisper/bin/python"
if [ ! -x "$PY" ]; then
  echo "❌ .venv-whisper not found — run INSTALL-TRANSCRIBER.command first."
  exit 1
fi

exec "$PY" -u transcriber.py

#!/bin/bash
# Fire Logger — install the Whisper transcriber (v4).
#
# What this does:
#   1. Builds a private Python environment (.venv-whisper) with
#      MLX Whisper — separate from the recorder's, on purpose.
#   2. Installs a second background agent (com.henry.firetranscriber)
#      that keeps the large model loaded and transcribes every new
#      clip the recorder saves.
# The recorder itself is NOT touched and keeps running throughout.
# First run takes a few minutes (install + the model is already
# downloaded from the earlier test, so no big download expected).

cd "$(dirname "$0")" || exit 1
LABEL="com.henry.firetranscriber"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
VENV=".venv-whisper"

echo "==============================================="
echo " Fire Logger — installing the transcriber"
echo "==============================================="

# 1. Whisper environment (first run only).
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating the Whisper environment (one time)..."
  PY="$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)"
  echo "Using $PY"
  "$PY" -m venv "$VENV" || { echo "❌ Could not create the environment. Tell Muse."; read -n 1; exit 1; }
  echo "Installing MLX Whisper (a few minutes)..."
  "$VENV/bin/pip" install --quiet --upgrade pip mlx-whisper || {
    echo "❌ Install failed. Tell Muse what this window says."; read -n 1; exit 1;
  }
  echo "✅ Whisper environment ready."
else
  echo "Whisper environment already exists — skipping setup."
fi

# 2. Install the agent definition (template -> real paths).
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__FIRELOGGER_DIR__|$(pwd)|g" "$LABEL.plist" > "$PLIST_DST" || {
  echo "❌ Could not copy the agent file. Tell Muse."; read -n 1; exit 1;
}

# 3. Load it (reload fresh if it was already there).
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "transcriber.py" 2>/dev/null
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST" || {
  echo "❌ macOS would not load the agent. Tell Muse what this window says."; read -n 1; exit 1;
}
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null

# 4. Verify. The daemon warms the model up at start, which can take
#    up to a minute — poll the log for the warm line.
echo ""
echo "Waiting for the transcriber to load the model..."
for i in $(seq 1 30); do
  if grep -q "Model loaded and warm" transcriber.log 2>/dev/null; then
    echo "✅ Transcriber is running and the model is warm."
    break
  fi
  if [ "$i" = "30" ]; then
    echo "⚠️ Still warming up after a minute — check transcriber.log."
  fi
  sleep 2
done
echo ""
echo "The transcriber's log (last few lines):"
tail -n 6 transcriber.log 2>/dev/null
echo ""
echo "==============================================="
echo " NOTES"
echo " * Every NEW clip the recorder saves now gets a"
echo "   transcript beside it (.txt) within seconds."
echo " * Old clips are left alone."
echo " * To stop the transcriber for good, run"
echo "   STOP-TRANSCRIBER.command in this same folder."
echo "==============================================="
echo "Press any key to close."
read -n 1

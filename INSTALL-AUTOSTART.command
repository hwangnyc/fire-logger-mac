#!/bin/bash
# Fire Logger — install the background autostart (belt and suspenders).
# After this runs, the recorder:
#   * starts by itself every time you log in
#   * restarts by itself if it ever crashes
#   * keeps the Mac awake while it runs (the screen can still sleep)
# You will not need the Terminal window anymore.

cd "$(dirname "$0")" || exit 1
LABEL="com.henry.firelogger"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "==============================================="
echo " Fire Logger — installing background autostart"
echo "==============================================="

# 1. Stop the recorder if it is running in a Terminal window,
#    so we don't end up with two of them recording at once.
if pgrep -f "recorder.py" >/dev/null 2>&1; then
  echo "Stopping the recorder that's running now..."
  pkill -f "recorder.py" 2>/dev/null
  sleep 2
fi

# 2. Install the agent definition. The plist in this folder is a
#    template — fill in this folder's real path as it is installed.
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__FIRELOGGER_DIR__|$(pwd)|g" "$LABEL.plist" > "$PLIST_DST" || {
  echo "❌ Could not copy the agent file. Tell Muse."
  echo "Press any key to close."; read -n 1; exit 1;
}

# 3. Load it (reload fresh if it was already there).
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST" || {
  echo "❌ macOS would not load the agent. Tell Muse what this window says."
  echo "Press any key to close."; read -n 1; exit 1;
}
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null

# 4. Verify it is alive.
sleep 3
echo ""
if launchctl list | grep -q "$LABEL"; then
  echo "✅ Fire Logger is now running in the background."
else
  echo "⚠️ The agent loaded but doesn't show as running yet."
  echo "   Tell Muse — the log below will say why."
fi
echo ""
echo "The recorder's log (last few lines):"
tail -n 5 firelogger.log 2>/dev/null
echo ""
echo "==============================================="
echo " NOTES"
echo " * If macOS pops up asking to let something use"
echo "   the microphone, click Allow — that's the recorder."
echo " * The old Terminal recorder window can be closed."
echo " * To stop the logger for good, double-click"
echo "   STOP-FIRE-LOGGER.command in this same folder."
echo "==============================================="
echo "Press any key to close."
read -n 1

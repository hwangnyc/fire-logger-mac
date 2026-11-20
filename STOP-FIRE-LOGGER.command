#!/bin/bash
# Fire Logger — stop the background recorder and turn off autostart.
# Run INSTALL-AUTOSTART.command to turn it back on.

LABEL="com.henry.firelogger"

echo "Stopping Fire Logger..."
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "recorder.py" 2>/dev/null
sleep 1

if pgrep -f "recorder.py" >/dev/null 2>&1; then
  echo "⚠️ It is still running. Tell Muse."
else
  echo "✅ Fire Logger is stopped and will not auto-start."
fi
echo "Press any key to close."
read -n 1

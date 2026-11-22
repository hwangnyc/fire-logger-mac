#!/bin/bash
# Fire Logger — stop the Whisper transcriber for good.
# (The recorder is a separate agent and keeps running.)
LABEL="com.henry.firetranscriber"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "transcriber.py" 2>/dev/null
echo "✅ Transcriber stopped. The recorder is unaffected."
echo "Press any key to close."
read -n 1

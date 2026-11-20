#!/bin/bash
# Fire Logger — one-click starter for Henry's Mac mini.
# Double-click this file. It sets everything up the first time
# (a few minutes), then starts listening to the radio.
# Leave the window open while it's running. Close it to stop.

cd "$(dirname "$0")" || exit 1
echo "==============================================="
echo " Fire Logger — starting up"
echo " Folder: $(pwd)"
echo "==============================================="

# 1. PortAudio (the library PyAudio needs to hear the Sabrent)
if ! brew list portaudio >/dev/null 2>&1; then
  echo "Installing portaudio (one time only)..."
  brew install portaudio
fi

# 2. A modern Python from Homebrew (the built-in one is too old for PyAudio wheels)
PY=""
for v in 3.13 3.12 3.11; do
  if [ -x "/opt/homebrew/bin/python$v" ]; then PY="/opt/homebrew/bin/python$v"; break; fi
done
if [ -z "$PY" ]; then
  echo "Installing Python 3.12 (one time only)..."
  brew install python@3.12
  PY="/opt/homebrew/bin/python3.12"
fi
echo "Using Python: $PY"

# 3. Private Python environment for this app (keeps the Mac clean)
if [ ! -d ".venv" ]; then
  echo "Creating the app's Python environment (one time only)..."
  "$PY" -m venv .venv
fi
echo "Making sure the audio pieces are installed..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet pyaudio supabase || {
  echo "❌ Could not install the audio pieces. Tell Muse what this window says."
  echo "Press any key to close."; read -n 1; exit 1;
}

# 4. Show what the Mac hears (goes in the log for Muse to check)
echo ""
echo "Audio input devices on this Mac:"
.venv/bin/python recorder.py --list

# 5. Go
echo ""
echo "==============================================="
echo " ✅ LISTENING. Leave this window open."
echo " When Muse says so, make the radio talk."
echo " Clips land in the 'clips' folder next to this file."
echo "==============================================="
/usr/bin/caffeinate -i .venv/bin/python -u recorder.py 2>&1 | tee -a firelogger.log

echo ""
echo "Recorder stopped. Press any key to close."
read -n 1

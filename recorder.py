#!/usr/bin/env python3
"""
Fire Logger — Mac mini version
==============================
Listens to the Sabrent USB sound adapter fed by the Motorola radio /
Minitor amplified base. When the sound level crosses THRESHOLD it
records; when the sound stops for SILENCE_TIMEOUT seconds it saves
the clip and goes back to listening.

This is a straight port of Henry's original Raspberry Pi script
(recovered from his Gemini chat "Fire Rescue Systems CAD Integration"),
with the same proven settings:
    THRESHOLD = 500, SILENCE_TIMEOUT = 3, MAX_RECORD_SECONDS = 90,
    SAMPLE_RATE = 48000 (48k for the Sabrent)

Differences from the Pi version:
  * Saves clips LOCALLY to ./clips (WAV + MP3 if ffmpeg is present).
  * Upload to the dashboard's Supabase is built in but OFF by default.
    Turn it on in config.json after the dashboard-side setup is done.
    It uses a NEW key you paste into config.json on this Mac only —
    never reuse the old Pi script's key (it was pasted into a chat).
  * No Slack. The dashboard is the alert surface now.

Usage:
    python3 recorder.py              # listen and record
    python3 recorder.py --list       # list audio input devices (find MIC_ID)
    python3 recorder.py --test FILE.wav   # run the VOX logic over a WAV file
                                          # instead of the mic (for testing)

Config: edit config.json next to this file (created on first run).
"""

import json
import math
import os
import struct
import subprocess
import sys
import time
import wave
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

DEFAULT_CONFIG = {
    # --- Audio (same values as the original Pi script) ---
    "mic_id": None,            # None = system default input. Run --list to find the Sabrent's number.
    "sample_rate": 48000,      # 48k for Sabrent
    "threshold": 500,          # Sensitivity: sound louder than this starts a recording
    "silence_timeout": 3,      # Stop after this many seconds of silence
    "max_record_seconds": 90,  # Hard stop (safety limit)
    "min_record_seconds": 1.0, # Discard clips shorter than this (squelch clicks)
    # --- Saving ---
    "clips_dir": os.path.join(HERE, "clips"),
    "make_mp3": True,          # Needs ffmpeg (brew install ffmpeg). WAV is always saved.
    # --- Dashboard upload (OFF until the dashboard setup is done) ---
    "upload_enabled": False,
    "supabase_url": "",        # e.g. https://YOURPROJECT.supabase.co  (the DASHBOARD project)
    "supabase_key": "",        # Paste the key on THIS Mac only. Never commit this file.
    "bucket": "dispatch-audio",
    "clips_table": "radio_clips"
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(json.load(f))
            return cfg
    with open(CONFIG_PATH, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"📝 Wrote default config to {CONFIG_PATH} — edit mic_id there if needed.")
    return dict(DEFAULT_CONFIG)


# ----------------------------------------------------------------------
# Audio math — identical to the original script
# ----------------------------------------------------------------------
def calculate_rms(data):
    count = len(data) // 2
    if count == 0:
        return 0
    fmt = "%dh" % count
    shorts = struct.unpack(fmt, data[: count * 2])
    sum_squares = 0.0
    for sample in shorts:
        sum_squares += sample * sample
    return math.sqrt(sum_squares / count)


def segment_frames(frames_iter, cfg, chunk):
    """
    Pure VOX segmentation, shared by the live mic loop and --test mode.
    frames_iter yields (data_bytes) chunks of `chunk` frames each.
    Yields one list of frames per detected transmission.
    """
    threshold = cfg["threshold"]
    max_silence_chunks = int((cfg["sample_rate"] / chunk) * cfg["silence_timeout"])
    max_total_chunks = int((cfg["sample_rate"] / chunk) * cfg["max_record_seconds"])
    min_chunks = int((cfg["sample_rate"] / chunk) * cfg["min_record_seconds"])

    recording = None
    silence_chunks = 0
    for data in frames_iter:
        rms = calculate_rms(data)
        if recording is None:
            if rms > threshold:
                print(f"🔊 Triggered! (Vol: {int(rms)}) - Recording started...")
                recording = [data]
                silence_chunks = 0
        else:
            recording.append(data)
            if rms < threshold:
                silence_chunks += 1
            else:
                silence_chunks = 0
            if silence_chunks > max_silence_chunks:
                print("🛑 Silence detected. Stopping.")
                if len(recording) >= min_chunks:
                    yield recording
                else:
                    print("… clip too short, discarded (probably a squelch click).")
                recording = None
            elif len(recording) > max_total_chunks:
                print("🛑 Max duration reached. Stopping.")
                yield recording
                recording = None
    if recording is not None and len(recording) >= min_chunks:
        yield recording


# ----------------------------------------------------------------------
# Saving + (optional) upload
# ----------------------------------------------------------------------
def save_clip(frames, cfg, channels, started_at):
    os.makedirs(cfg["clips_dir"], exist_ok=True)
    stamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    wav_path = os.path.join(cfg["clips_dir"], f"{stamp}.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # paInt16
        wf.setframerate(cfg["sample_rate"])
        wf.writeframes(b"".join(frames))
    print(f"💾 Saved {wav_path}")

    mp3_path = None
    if cfg["make_mp3"]:
        try:
            mp3_path = os.path.join(cfg["clips_dir"], f"{stamp}.mp3")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                 "-codec:a", "libmp3lame", "-q:a", "4", mp3_path],
                check=True)
            print(f"💾 Saved {mp3_path}")
        except Exception as e:
            print(f"⚠️ MP3 conversion skipped ({e}). WAV is saved.")
            mp3_path = None
    return wav_path, mp3_path


def upload_clip(mp3_path, wav_path, cfg, started_at):
    """Upload to the dashboard Supabase project and log a radio_clips row.
    Only runs when upload_enabled is true in config.json."""
    if not cfg["upload_enabled"]:
        return
    try:
        from supabase import create_client
    except ImportError:
        print("⚠️ Upload is on but the supabase package isn't installed "
              "(pip3 install supabase). Clip is saved locally.")
        return
    path = mp3_path or wav_path
    ext = "mp3" if mp3_path else "wav"
    stamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    cloud_path = f"{stamp}.{ext}"
    try:
        sb = create_client(cfg["supabase_url"], cfg["supabase_key"])
        with open(path, "rb") as f:
            sb.storage.from_(cfg["bucket"]).upload(
                path=cloud_path, file=f,
                file_options={"content-type": "audio/mpeg" if ext == "mp3" else "audio/wav"})
        public_url = sb.storage.from_(cfg["bucket"]).get_public_url(cloud_path)
        sb.table(cfg["clips_table"]).insert({
            # timezone-aware: the dashboard matches clips to CAD dispatch
            # times, so a bare local time would be misread as UTC.
            "started_at": started_at.astimezone().isoformat(),
            "storage_path": cloud_path,
            "public_url": public_url,
        }).execute()
        print(f"☁️ Uploaded: {public_url}")
    except Exception as e:
        print(f"❌ Upload error: {e}  (clip is still saved locally)")


# ----------------------------------------------------------------------
# Live listening
# ----------------------------------------------------------------------
def list_devices():
    import pyaudio
    p = pyaudio.PyAudio()
    print("Audio devices on this Mac:")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"  {i}: {info['name']}  (inputs: {info['maxInputChannels']}, "
                  f"default rate: {int(info['defaultSampleRate'])})")
    p.terminate()
    print("\nPut the Sabrent's number in config.json as \"mic_id\".")


def find_usb_input(p):
    """Auto-detect the Sabrent: first input device with 'USB' in its name."""
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and "usb" in info["name"].lower():
            return i
    return None


def listen(cfg):
    import pyaudio
    chunk = 1024
    p = pyaudio.PyAudio()
    if cfg.get("mic_id") is None:
        auto = find_usb_input(p)
        if auto is not None:
            print(f"🎙️ Auto-detected USB input device {auto}: "
                  f"{p.get_device_info_by_index(auto)['name']}")
            cfg = dict(cfg)
            cfg["mic_id"] = auto
        else:
            print("🎙️ No USB input found by name — using the system default input. "
                  "Run --list and set mic_id in config.json if recordings are silent.")
    # Try mono first, fall back to stereo — same as the original script.
    channels = 1
    try:
        print(f"👂 Connecting to device {cfg['mic_id']} at {cfg['sample_rate']}Hz (mono)...")
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=cfg["sample_rate"],
                        input=True, input_device_index=cfg["mic_id"],
                        frames_per_buffer=chunk)
    except Exception as e:
        print(f"⚠️ Mono failed ({e}), trying stereo...")
        channels = 2
        stream = p.open(format=pyaudio.paInt16, channels=2, rate=cfg["sample_rate"],
                        input=True, input_device_index=cfg["mic_id"],
                        frames_per_buffer=chunk)
    print("✅ Waiting for radio traffic... (Ctrl+C to stop)")

    def mic_frames():
        while True:
            yield stream.read(chunk, exception_on_overflow=False)

    try:
        for frames in segment_frames(mic_frames(), cfg, chunk):
            # The clip's start = now minus its length (it ends ~now,
            # including the silence tail). Close enough to match CAD times.
            from datetime import timedelta
            clip_seconds = len(frames) * chunk / cfg["sample_rate"]
            started = datetime.now() - timedelta(seconds=clip_seconds)
            wav_path, mp3_path = save_clip(frames, cfg, channels, started)
            upload_clip(mp3_path, wav_path, cfg, started)
            print("💤 Resetting listener (5s)...")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        p.terminate()


# ----------------------------------------------------------------------
# Test mode: run the VOX logic over an existing WAV file
# ----------------------------------------------------------------------
def test_file(path, cfg):
    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        print(f"Test file: {rate}Hz, {channels} channel(s), {width} bytes/sample, "
              f"{wf.getnframes() / rate:.1f}s long")
        if width != 2:
            print("Only 16-bit WAV is supported in test mode.")
            return
        cfg = dict(cfg)
        cfg["sample_rate"] = rate
        chunk = 1024

        def file_frames():
            while True:
                data = wf.readframes(chunk)
                if not data:
                    break
                if channels == 2:  # crude downmix: take left channel
                    samples = struct.unpack("%dh" % (len(data) // 2), data)
                    data = struct.pack("%dh" % (len(samples) // 2), *samples[::2])
                yield data

        n = 0
        for frames in segment_frames(file_frames(), cfg, chunk):
            n += 1
            secs = len(frames) * chunk / rate
            print(f"  → Clip {n}: {secs:.1f}s of audio would be recorded")
        print(f"Done. {n} clip(s) detected.")


def main():
    cfg = load_config()
    if "--list" in sys.argv:
        list_devices()
    elif "--test" in sys.argv:
        i = sys.argv.index("--test")
        test_file(sys.argv[i + 1], cfg)
    else:
        listen(cfg)


if __name__ == "__main__":
    main()

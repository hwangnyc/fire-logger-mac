#!/usr/bin/env python3
"""
Fire Logger — warm Whisper transcriber daemon. (v5)

Runs beside the recorder (its own launchd agent; the recorder is
untouched). Loads the Whisper model ONCE at startup and keeps it in
memory, then watches the clips folder: every new .wav the recorder
saves gets transcribed, and the text is written next to the clip
(<clip>.txt + <clip>.whisper.json) and echoed to transcriber.log.

v5 — built from the first real call (#499, Nov 21, 2026): the second
airing's transcript came back as "!" even though the audio was loud
and clear. Whisper's decoder had collapsed on the opening alert
tones (NaN logprob, decoding stopped after ~6s). Fixes:
  * condition_on_previous_text=False on every call — one bad segment
    can no longer poison the rest of the clip.
  * If a transcript comes back effectively empty while the clip is
    measurably loud, retry WITHOUT the vocabulary prompt.
  * If it is STILL empty, retry in 10-second chunks
    (clip_timestamps) — a collapse in one window can't kill the
    speech in the others.
  * If every attempt is empty on loud audio, the .txt is still
    written (so the clip isn't retried forever) and the log carries
    a loud warning line.
(An earlier idea — trimming the tones by crest-factor analysis —
was tested against the real #499 audio and rejected: speech and
tones interleave too closely at 100 ms resolution to trim safely.)

Settings come from the logger's config.json (re-read every cycle):
    clips_dir       where the recorder saves (default: ./clips)
    whisper_model   tiny|base|small|medium|large (default: large)
    whisper_prompt  vocabulary hint (default: the Albertson prompt)

Fully local: MLX Whisper on Apple Silicon. Nothing leaves the Mac.
"""

import json
import math
import os
import struct
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
}

DEFAULT_MODEL = "large"
DEFAULT_PROMPT = ("Firecom dispatch for Albertson and Williston Park. "
                  "Signal 9A. Signal 110.")
POLL_SECONDS = 2
SETTLE_SECONDS = 5       # a clip is done being written once it's this old
RETRY_AFTER = 300        # a failed clip is retried after 5 minutes
LOUD_RMS = 1000          # a clip averaging above this definitely has audio
CHUNK_SECONDS = 10       # window size for the chunked last-resort pass


def load_settings():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    clips_dir = cfg.get("clips_dir") or os.path.join(HERE, "clips")
    model = cfg.get("whisper_model") or DEFAULT_MODEL
    if model not in MODELS:
        model = DEFAULT_MODEL
    prompt = cfg.get("whisper_prompt")
    if prompt is None:
        prompt = DEFAULT_PROMPT
    return clips_dir, model, prompt


def find_ready_clips(clips_dir, sizes, failed):
    """WAVs that are finished recording and not yet transcribed."""
    ready = []
    if not os.path.isdir(clips_dir):
        return ready
    now = time.time()
    for name in sorted(os.listdir(clips_dir)):
        if not name.lower().endswith(".wav"):
            continue
        path = os.path.join(clips_dir, name)
        base, _ = os.path.splitext(path)
        if os.path.exists(base + ".txt"):
            continue                      # already transcribed
        if path in failed and now - failed[path] < RETRY_AFTER:
            continue                      # recently failed; don't hammer it
        try:
            st = os.stat(path)
        except OSError:
            continue
        if now - st.st_mtime < SETTLE_SECONDS:
            continue                      # too fresh — may still be writing
        prev = sizes.get(path)
        sizes[path] = st.st_size
        if prev is None or prev != st.st_size:
            continue                      # size not proven stable yet
        ready.append(path)
    return ready


def clip_stats(path):
    """(overall RMS, duration in seconds) of a WAV, stdlib only."""
    with wave.open(path) as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    samples = struct.unpack(f"<{n * ch}h", raw)
    if ch == 2:
        samples = samples[::2]
    if not samples:
        return 0.0, 0.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return rms, n / float(rate)


def effectively_empty(text):
    return sum(c.isalnum() for c in text or "") < 3


def chunk_timestamps(duration):
    """'0,10,10,20,...' clip_timestamps covering the whole clip."""
    pairs = []
    duration = round(duration, 1)
    start = 0.0
    while start < duration:
        end = min(start + CHUNK_SECONDS, duration)
        pairs.append(f"{start:g},{end:g}")
        start = end
    return ",".join(pairs)


def _run_whisper(mlx_whisper, path, model, prompt, **extra):
    return mlx_whisper.transcribe(
        path,
        path_or_hf_repo=MODELS[model],
        initial_prompt=prompt or None,
        condition_on_previous_text=False,
        verbose=False,
        **extra,
    )


def transcribe(path, model, prompt):
    """Transcribe with a fallback ladder for tone-collapse failures.
    Returns (text, result_dict, note) — note names the rescue used."""
    import mlx_whisper
    rms, duration = clip_stats(path)
    loud = rms > LOUD_RMS

    result = _run_whisper(mlx_whisper, path, model, prompt)
    text = (result.get("text") or "").strip()
    if not effectively_empty(text) or not loud:
        return text, result, ""

    print(f"↻ First pass empty on loud audio (RMS {rms:.0f}) — retrying without the prompt...", flush=True)
    result = _run_whisper(mlx_whisper, path, model, None)
    text = (result.get("text") or "").strip()
    if not effectively_empty(text):
        return text, result, " (recovered on no-prompt retry)"

    print("↻ Still empty — retrying in chunks...", flush=True)
    result = _run_whisper(mlx_whisper, path, model, None,
                          clip_timestamps=chunk_timestamps(duration))
    text = (result.get("text") or "").strip()
    if not effectively_empty(text):
        return text, result, " (recovered on chunked retry)"
    return text, result, " ⚠️ ALL PASSES EMPTY despite loud audio"


def warm_up(model, prompt):
    """Load the model before the first real call, using 1s of silence."""
    tmp = os.path.join(HERE, ".warmup.wav")
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"\x00\x00" * 48000)
        import mlx_whisper
        mlx_whisper.transcribe(tmp, path_or_hf_repo=MODELS[model],
                               initial_prompt=None,
                               condition_on_previous_text=False,
                               verbose=False)
        print("🔥 Model loaded and warm.", flush=True)
    except Exception as e:
        print(f"⚠️ Warm-up failed ({e}); the first real clip will load the model instead.", flush=True)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def main():
    clips_dir, model, prompt = load_settings()
    print("=" * 55, flush=True)
    print(" Fire Logger — transcriber starting (v5)", flush=True)
    print(f" Model: {model}   Watching: {clips_dir}", flush=True)
    print("=" * 55, flush=True)
    warm_up(model, prompt)

    sizes = {}
    failed = {}
    while True:
        try:
            clips_dir, model, prompt = load_settings()
            for path in find_ready_clips(clips_dir, sizes, failed):
                name = os.path.basename(path)
                print(f"🎙️ Transcribing {name} ...", flush=True)
                t0 = time.time()
                try:
                    text, result, note = transcribe(path, model, prompt)
                    base, _ = os.path.splitext(path)
                    with open(base + ".txt", "w") as f:
                        f.write(text + "\n")
                    with open(base + ".whisper.json", "w") as f:
                        json.dump(result, f, indent=2)
                    failed.pop(path, None)
                    print(f"📝 {name} ({time.time() - t0:.1f}s): {text}{note}", flush=True)
                except Exception as e:
                    failed[path] = time.time()
                    print(f"⚠️ Transcription failed for {name}: {e} (will retry later)", flush=True)
        except Exception as e:
            print(f"⚠️ Transcriber loop error: {e}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())

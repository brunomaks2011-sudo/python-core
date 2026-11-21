#!/usr/bin/env python3
"""Radio voice lines for both army HQs via ElevenLabs text-to-speech.

Writes one MP3 per line to Assets/Audio/Voice/raw/<team>_<line>.mp3 and skips
lines that already exist, so re-running only fills gaps. build_audio.py then
applies the radio treatment and packs them into the voice sheets.

Usage: python3 Tools/audio/gen_voice.py [--force]
Needs ELEVENLABS_API_KEY in the environment (in the cloud dev container the
network proxy supplies the key, so any placeholder value works there).
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "Assets" / "Audio" / "Voice" / "raw"

# Blue HQ: warm, measured. Red HQ: deep, clipped. (ElevenLabs premade voices.)
VOICES = {1: "JBFqnCBsd6RMkjVDRZzb", 2: "nPczCjzI2devNBz1zQrb"}
MODEL = "eleven_multilingual_v2"

POINTS = {"A": ("Alpha", "the industrial complex"), "B": ("Bravo", "the village"), "C": ("Charlie", "the military base")}


def lines() -> dict[str, str]:
    out = {}
    for pid, (call, place) in POINTS.items():
        out[f"captured_{pid}"] = f"{call} is ours. We hold {place}."
        out[f"lost_{pid}"] = f"We have lost {call}. The enemy holds {place}."
        out[f"losing_{pid}"] = f"{call} has been neutralized. Retake that flag."
        out[f"contested_{pid}"] = f"Enemy troops at {call}. Hold your ground."
    out["victory"] = "All units, this is Command. The battle is won. Outstanding work."
    out["defeat"] = "All units, this is Command. Fall back. The battle is lost."
    out["artillery_out"] = "Rocket artillery is on the way. Keep your heads down."
    out["artillery_incoming"] = "Incoming artillery! Get to cover!"
    out["sudden_death"] = "Sudden death. Both armies one second from victory. Take another flag to win."
    return out


def tts(voice: str, text: str) -> bytes:
    key = os.environ.get("ELEVENLABS_API_KEY", "proxy-supplied")
    body = json.dumps({
        "text": text,
        "model_id": MODEL,
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True},
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64",
        data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise SystemExit(f"TTS failed ({e.code}): {e.read()[:300]!r}")
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    raise SystemExit("TTS failed")


def main() -> None:
    force = "--force" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0
    for team, voice in VOICES.items():
        for name, text in lines().items():
            path = OUT / f"{team}_{name}.mp3"
            if path.exists() and not force:
                continue
            path.write_bytes(tts(voice, text))
            made += 1
            print(f"  {path.relative_to(ROOT)}  \"{text}\"")
    (OUT / "lines.json").write_text(json.dumps({"voices": VOICES, "model": MODEL, "lines": lines()}, indent=2) + "\n")
    print(f"gen_voice: {made} new line(s), {len(lines()) * len(VOICES)} total")


if __name__ == "__main__":
    main()

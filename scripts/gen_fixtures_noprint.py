#!/usr/bin/env python3
"""
Generate TTS audio fixtures for e2e_p2 test suite.
Encoding-safe version: avoids printing path strings with Cyrillic chars
that break cp1252 consoles on Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Force stdout to utf-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SESSION_DIR = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "session"
FFMPEG_BIN = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

TRACKS = [
    {
        "stem": "1-test_gm",
        "text": (
            "Хорошо, начинаем игру. "
            "Вы находитесь в таверне Золотой дракон. "
            "На столе горит свеча, за окном слышен шум дождя."
        ),
    },
    {
        "stem": "2-test_player",
        "text": (
            "Мой персонаж осматривает комнату. "
            "Есть ли здесь что-нибудь подозрительное? "
            "Я хочу проверить углы и проверить нет ли скрытых дверей."
        ),
    },
    {
        "stem": "3-test_player2",
        "text": (
            "Я подхожу к стойке и прошу у бармена кружку эля. "
            "Попутно спрашиваю, не появлялось ли здесь в последние дни чужаков."
        ),
    },
]


def main() -> int:
    FIXTURE_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    ffmpeg = str(FFMPEG_BIN) if FFMPEG_BIN.exists() else "ffmpeg"
    print(f"ffmpeg found: {FFMPEG_BIN.exists()}")

    try:
        import pyttsx3
    except ImportError:
        print("ERROR: pyttsx3 not installed. Run: pip install pyttsx3", file=sys.stderr)
        return 1

    engine = pyttsx3.init()

    # Find Russian voice
    voices = engine.getProperty("voices")
    russian_keywords = ["irina", "pavel", "russian", "ru-ru", "ru_ru"]
    russian_voice_id = None
    for v in voices:
        name_lower = v.name.lower()
        id_lower = v.id.lower()
        if any(kw in name_lower or kw in id_lower for kw in russian_keywords):
            russian_voice_id = v.id
            print(f"Selected voice: {v.name}")
            break

    if not russian_voice_id:
        print("WARNING: No Russian voice found, using default voice.")

    if russian_voice_id:
        engine.setProperty("voice", russian_voice_id)
    engine.setProperty("rate", 160)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for track in TRACKS:
            stem = track["stem"]
            text = track["text"]
            wav_path = tmp / f"{stem}.wav"
            flac_path = FIXTURE_SESSION_DIR / f"{stem}.flac"

            # Skip if already exists (allows partial re-runs)
            if flac_path.exists() and flac_path.stat().st_size > 1000:
                sz = flac_path.stat().st_size
                print(f"[{stem}] Already exists ({sz} bytes), skipping.")
                continue

            print(f"[{stem}] Synthesizing...")
            engine.save_to_file(text, str(wav_path))
            engine.runAndWait()

            if not wav_path.exists() or wav_path.stat().st_size == 0:
                print(f"ERROR: pyttsx3 did not write {wav_path.name}", file=sys.stderr)
                return 1

            print(f"[{stem}] WAV: {wav_path.stat().st_size} bytes -> converting to FLAC...")
            cmd = [
                ffmpeg, "-y",
                "-i", str(wav_path),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "flac",
                str(flac_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                print(f"ERROR: ffmpeg failed: {result.stderr[-500:]}", file=sys.stderr)
                return 1

            if not flac_path.exists():
                print(f"ERROR: FLAC not created for {stem}", file=sys.stderr)
                return 1

            print(f"[{stem}] FLAC: {flac_path.stat().st_size} bytes OK")

    print("=== Done ===")
    for track in TRACKS:
        p = FIXTURE_SESSION_DIR / f"{track['stem']}.flac"
        sz = p.stat().st_size if p.exists() else 0
        status = "OK" if sz > 1000 else "MISSING"
        print(f"  {track['stem']}.flac: {sz} bytes [{status}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())

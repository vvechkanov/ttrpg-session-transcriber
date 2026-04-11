#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate TTS audio fixtures for e2e_p2 test suite.

Uses pyttsx3 (Windows SAPI5, offline) to synthesize Russian speech,
then converts WAV -> 16kHz mono FLAC via ffmpeg for WhisperX compatibility.

Usage:
    python scripts/generate_e2e_fixtures.py

Requirements:
    pip install pyttsx3
    ffmpeg must be available in PATH or at tools/ffmpeg/bin/ffmpeg.exe

Output:
    tests/fixtures/e2e_p2/session/1-test_gm.flac
    tests/fixtures/e2e_p2/session/2-test_player.flac
    tests/fixtures/e2e_p2/session/3-test_player2.flac
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SESSION_DIR = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "session"
FFMPEG_BIN = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"

# ── TTS phrases ───────────────────────────────────────────────────────────────

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


def _find_ffmpeg() -> str:
    """Return path to ffmpeg: prefer local tools/, fallback to PATH."""
    if FFMPEG_BIN.exists():
        return str(FFMPEG_BIN)
    # Try PATH
    for candidate in ["ffmpeg", "ffmpeg.exe"]:
        try:
            subprocess.run(
                [candidate, "-version"],
                capture_output=True,
                check=True,
            )
            return candidate
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    raise RuntimeError(
        f"ffmpeg not found. Expected at {FFMPEG_BIN} or in PATH."
    )


def _find_russian_voice(engine) -> str | None:
    """Return voice id for a Russian SAPI5 voice, or None if not found."""
    voices = engine.getProperty("voices")
    print(f"Available SAPI5 voices ({len(voices)} total):")
    for v in voices:
        langs = getattr(v, "languages", [])
        print(f"  id={v.id!r}  name={v.name!r}  langs={langs}")

    # Priority: explicit Russian voice names
    russian_keywords = ["irina", "pavel", "russian", "ru-ru", "ru_ru"]
    for v in voices:
        name_lower = v.name.lower()
        id_lower = v.id.lower()
        if any(kw in name_lower or kw in id_lower for kw in russian_keywords):
            print(f"\nSelected Russian voice: {v.name!r} ({v.id})")
            return v.id

    print("\nWARNING: No Russian voice found. Using default voice.")
    print("The generated audio will be in the default language (likely English).")
    print("WhisperX transcription quality for Russian text will be very low.")
    print("Consider installing Microsoft Irina Desktop or similar Russian TTS voice.")
    return None


def _tts_to_wav(engine, text: str, wav_path: Path) -> None:
    """Synthesize text to WAV via pyttsx3."""
    engine.save_to_file(text, str(wav_path))
    engine.runAndWait()


def _wav_to_flac_16k_mono(ffmpeg: str, wav_path: Path, flac_path: Path) -> None:
    """Convert WAV to 16kHz mono FLAC using ffmpeg."""
    cmd = [
        ffmpeg,
        "-y",                    # overwrite output
        "-i", str(wav_path),
        "-ar", "16000",          # 16 kHz sample rate (WhisperX requirement)
        "-ac", "1",              # mono
        "-c:a", "flac",
        str(flac_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {wav_path.name}:\n{result.stderr}"
        )


def main() -> int:
    FIXTURE_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    # ── Find ffmpeg ────────────────────────────────────────────────────────
    try:
        ffmpeg = _find_ffmpeg()
        print(f"Using ffmpeg: {ffmpeg}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # ── Init pyttsx3 ───────────────────────────────────────────────────────
    try:
        import pyttsx3
    except ImportError:
        print(
            "ERROR: pyttsx3 not installed. Run: pip install pyttsx3",
            file=sys.stderr,
        )
        return 1

    engine = pyttsx3.init()

    # ── Select voice ───────────────────────────────────────────────────────
    russian_voice_id = _find_russian_voice(engine)
    if russian_voice_id:
        engine.setProperty("voice", russian_voice_id)

    # Slightly slower rate for clearer synthesis (default ~200 wpm)
    engine.setProperty("rate", 160)

    # ── Generate tracks ────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for track in TRACKS:
            stem = track["stem"]
            text = track["text"]
            wav_path = tmp / f"{stem}.wav"
            flac_path = FIXTURE_SESSION_DIR / f"{stem}.flac"

            print(f"\n[{stem}] Synthesizing: {text[:60]}...")
            _tts_to_wav(engine, text, wav_path)

            if not wav_path.exists() or wav_path.stat().st_size == 0:
                print(f"  ERROR: pyttsx3 did not write {wav_path}", file=sys.stderr)
                return 1

            wav_size_kb = wav_path.stat().st_size / 1024
            print(f"  WAV size: {wav_size_kb:.1f} KB")

            print(f"  Converting to FLAC 16kHz mono -> {flac_path.name}")
            _wav_to_flac_16k_mono(ffmpeg, wav_path, flac_path)

            if not flac_path.exists():
                print(f"  ERROR: FLAC not created: {flac_path}", file=sys.stderr)
                return 1

            flac_size_kb = flac_path.stat().st_size / 1024
            print(f"  FLAC size: {flac_size_kb:.1f} KB -> {flac_path}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n=== Fixture generation complete ===")
    total_bytes = 0
    for track in TRACKS:
        p = FIXTURE_SESSION_DIR / f"{track['stem']}.flac"
        if p.exists():
            sz = p.stat().st_size
            total_bytes += sz
            print(f"  {p.name}: {sz / 1024:.1f} KB")
        else:
            print(f"  {track['stem']}.flac: MISSING")

    total_kb = total_bytes / 1024
    print(f"\nTotal fixture audio size: {total_kb:.1f} KB")
    if total_kb > 900:
        print("WARNING: Total > 900 KB, approaching 1 MB git limit. Consider shortening phrases.")
    else:
        print("Size OK (< 1 MB target).")

    return 0


if __name__ == "__main__":
    sys.exit(main())

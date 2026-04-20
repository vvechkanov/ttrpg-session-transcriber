"""Pytest configuration for discord-session-transcriber test suite.

Inserts the project root into sys.path so that `import core`, `import domain`,
`import sources`, etc. work when running pytest from the repo root without
installing the package.
"""

import io
import os
import struct
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

# Project root = parent of tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Headless Qt platform for all tests that spin up Qt objects.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Audio fixtures
# ---------------------------------------------------------------------------

def _make_sine_wav_bytes(
    *,
    duration_sec: float = 1.0,
    sample_rate: int = 16_000,
    freq_hz: float = 440.0,
    amplitude: float = 0.3,
) -> bytes:
    """Return raw bytes of a minimal mono PCM WAV file (no external libs).

    Uses the Python stdlib ``wave`` module so the fixture works even
    without ``soundfile`` / ``libsndfile`` installed.  16-bit signed PCM,
    mono, 16 kHz by default — enough for the pipeline to see a real file
    path and not error on "no audio".
    """
    n_frames = int(duration_sec * sample_rate)
    t = np.linspace(0.0, duration_sec, n_frames, endpoint=False, dtype=np.float64)
    samples = (np.sin(2.0 * np.pi * freq_hz * t) * amplitude * 32767).astype(
        np.int16
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.fixture()
def tiny_wav_factory(tmp_path: Path):
    """Factory fixture — call it with a filename stem to get a .wav Path.

    Usage::

        def test_foo(tiny_wav_factory):
            p = tiny_wav_factory("player1")
            assert p.exists()

    The file is a 1-second 440 Hz sine, 16 kHz mono PCM WAV.
    """

    def _make(stem: str, *, duration_sec: float = 1.0) -> Path:
        path = tmp_path / f"{stem}.wav"
        path.write_bytes(
            _make_sine_wav_bytes(duration_sec=duration_sec)
        )
        return path

    return _make


@pytest.fixture()
def two_track_session(tmp_path: Path):
    """Session directory with two tiny .wav audio files.

    Returns ``(session_dir, [track0_path, track1_path])``.

    Naming follows Craig's convention (``<id>-<username>.flac``-style
    stems without the ``craig-`` prefix so ``detect_audio_files`` picks
    them up).
    """
    session_dir = tmp_path / "session_fixture"
    session_dir.mkdir()

    wav_bytes = _make_sine_wav_bytes(duration_sec=1.0)
    tracks = []
    for stem in ("001-player_one", "002-player_two"):
        p = session_dir / f"{stem}.wav"
        p.write_bytes(wav_bytes)
        tracks.append(p)

    return session_dir, tracks

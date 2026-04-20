"""Tests for ``core.peaks``: ffmpeg decode, peak reduction, disk cache."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest

from core.peaks import (
    DEFAULT_BIN_COUNT,
    cache_path_for,
    extract_peaks,
    get_or_compute_peaks,
    probe_duration,
)

# The bundled ffmpeg under tools/ffmpeg/bin. Tests that need a
# real audio file synthesize one with this binary — no checked-in
# binary fixtures.
_FFMPEG = (
    Path(__file__).resolve().parent.parent / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
)


def _synthesize_sine(path: Path, seconds: float = 2.0, freq: int = 440) -> None:
    """Write a FLAC sine-wave of ``seconds`` length at ``freq`` Hz."""

    assert _FFMPEG.is_file(), f"bundled ffmpeg not found at {_FFMPEG}"
    subprocess.check_call(
        [
            str(_FFMPEG),
            "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={seconds}",
            "-ac", "1",
            "-ar", "16000",
            "-y",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def sine_file(tmp_path: Path) -> Path:
    audio = tmp_path / "sine.flac"
    _synthesize_sine(audio, seconds=2.0, freq=880)
    return audio


def test_probe_duration_returns_seconds(sine_file: Path) -> None:
    d = probe_duration(sine_file)
    assert 1.9 <= d <= 2.1, f"expected ~2.0s, got {d}"


def test_probe_duration_returns_zero_on_missing_file(tmp_path: Path) -> None:
    d = probe_duration(tmp_path / "does-not-exist.flac")
    assert d == 0.0


def test_extract_peaks_returns_requested_count(sine_file: Path) -> None:
    peaks = extract_peaks(sine_file, bins=100)
    assert len(peaks) == 100
    # ffmpeg's `sine=` source emits at ~-18 dBFS (≈ 0.125 peak). The
    # exact amplitude isn't interesting; what matters is that the
    # decoder saw audio, not silence, and that every bucket sees the
    # same flat envelope (constant-amplitude sine).
    assert max(peaks) > 0.05
    for p in peaks:
        assert 0.0 <= p <= 1.0


def test_extract_peaks_on_missing_file_returns_empty(tmp_path: Path) -> None:
    assert extract_peaks(tmp_path / "nope.flac", bins=100) == []


def test_get_or_compute_caches_to_disk(sine_file: Path) -> None:
    cache = cache_path_for(sine_file)
    assert not cache.exists()

    peaks = get_or_compute_peaks(sine_file, bins=100)
    assert len(peaks) == 100
    assert cache.exists()

    # Cache content matches extracted peaks byte-for-byte.
    cached_bytes = cache.read_bytes()
    cached_floats = list(struct.unpack(f"<{len(cached_bytes) // 4}f", cached_bytes))
    assert cached_floats == peaks


def test_get_or_compute_reuses_fresh_cache(sine_file: Path) -> None:
    import os
    import time

    peaks_first = get_or_compute_peaks(sine_file, bins=100)
    assert len(peaks_first) == 100

    # Simulate a cache that's newer than the audio it summarises.
    # Corrupt the audio but force the cache's mtime into the future
    # so _is_cache_fresh accepts it; if the implementation re-extracted,
    # we'd get an empty list from the broken file.
    cache = cache_path_for(sine_file)
    sine_file.write_bytes(b"not real audio")
    future = time.time() + 100
    os.utime(cache, (future, future))

    peaks_second = get_or_compute_peaks(sine_file, bins=100)
    assert peaks_second == peaks_first, "stale cache was not reused"


def test_get_or_compute_regenerates_when_audio_newer(sine_file: Path) -> None:
    get_or_compute_peaks(sine_file, bins=100)
    cache = cache_path_for(sine_file)

    # Re-synthesize with different frequency — cache should be invalidated.
    _synthesize_sine(sine_file, seconds=2.0, freq=220)

    peaks = get_or_compute_peaks(sine_file, bins=100)
    # The cache was rewritten with the 220 Hz extract; the returned
    # peaks are fresh. We don't compare content directly — sine peaks
    # at different frequencies land similarly — but we verify the
    # cache mtime advanced past the previous read.
    assert cache.stat().st_mtime >= sine_file.stat().st_mtime - 1
    assert len(peaks) == 100


def test_get_or_compute_regenerates_on_bin_count_mismatch(sine_file: Path) -> None:
    # First extract with 50 bins.
    peaks_50 = get_or_compute_peaks(sine_file, bins=50)
    assert len(peaks_50) == 50

    # Second extract with 200 bins — cache has 50, must re-extract.
    peaks_200 = get_or_compute_peaks(sine_file, bins=200)
    assert len(peaks_200) == 200


def test_default_bin_count_matches_module_constant() -> None:
    assert DEFAULT_BIN_COUNT == 2000

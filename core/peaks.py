"""Waveform peak extraction with on-disk cache.

Decodes an audio file to mono 16 kHz signed-16-bit PCM via the
bundled ffmpeg, reduces the sample stream to a fixed number of
``max(abs(x))`` peaks per chunk, and caches the result next to the
audio as ``<audio>.peaks.bin`` (little-endian float32 array).

Cache invalidation is by mtime: a regenerate fires if the audio is
newer than the cache, or if the cached bin count differs from the
requested one.

Used from :mod:`ui.engines.peaks_worker` on a background QThread so
decoding never blocks the UI. The module is deliberately ffmpeg-only
(no torch/torchaudio) so a freshly-extracted GUI bundle can render
waveforms before the ML runtime is provisioned into ``%APPDATA%``.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

#: Default number of peaks produced for one waveform. ~2 k is enough
#: for a 1200-px-wide timeline lane and small enough to cache fast.
DEFAULT_BIN_COUNT: int = 2000

#: Byte size of one peak in the cache (float32).
_PEAK_BYTES: int = 4

#: Repo root derived from this file's location; used to find the
#: bundled ``tools/ffmpeg/bin`` executables during development. A
#: PyInstaller-packaged bundle puts the same path under its own
#: ``sys._MEIPASS`` root, so this lookup still resolves — see the
#: fall-through to the PATH for any layout we don't recognise.
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def _bundled_tool(name: str) -> str:
    """Return the bundled ffmpeg/ffprobe path, or the bare name on fallback."""

    bundled = _REPO_ROOT / "tools" / "ffmpeg" / "bin" / f"{name}.exe"
    if bundled.is_file():
        return str(bundled)
    return name


def probe_duration(audio_path: Path) -> float:
    """Return audio duration in seconds via ``ffprobe``; 0.0 on failure.

    Metadata-only — sub-second per file even on slow disks. Safe to
    call synchronously from the GUI thread on ingest.
    """

    try:
        out = subprocess.check_output(
            [
                _bundled_tool("ffprobe"),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return 0.0
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def extract_peaks(audio_path: Path, bins: int = DEFAULT_BIN_COUNT) -> list[float]:
    """Decode and reduce to a ``bins``-long list of peak values in [0..1].

    Empty list on decode failure or zero-length audio — callers treat
    it the same way as missing data and render an empty lane.
    """

    if bins <= 0:
        return []
    try:
        proc = subprocess.run(
            [
                _bundled_tool("ffmpeg"),
                "-v", "error",
                "-i", str(audio_path),
                "-ac", "1",
                "-ar", "16000",
                "-f", "s16le",
                "-",
            ],
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []

    data = proc.stdout
    samples = len(data) // 2
    if samples <= 0:
        return []

    # Distribute samples into `bins` contiguous windows. The last
    # window may be slightly larger to absorb the remainder.
    chunk_samples = max(1, samples // bins)
    peaks: list[float] = []
    for i in range(bins):
        start = i * chunk_samples * 2
        end = (i + 1) * chunk_samples * 2 if i < bins - 1 else len(data)
        if start >= end:
            peaks.append(0.0)
            continue
        window = struct.unpack(f"<{(end - start) // 2}h", data[start:end])
        peak = max(abs(x) for x in window) / 32768.0
        peaks.append(peak)
    return peaks


def cache_path_for(audio_path: Path) -> Path:
    """Return the ``.peaks.bin`` cache path for ``audio_path``."""

    return audio_path.with_suffix(audio_path.suffix + ".peaks.bin")


def _is_cache_fresh(audio_path: Path, cache_path: Path) -> bool:
    if not cache_path.is_file():
        return False
    try:
        audio_mtime = audio_path.stat().st_mtime
        cache_mtime = cache_path.stat().st_mtime
    except OSError:
        return False
    return cache_mtime >= audio_mtime


def _read_cache(cache_path: Path) -> list[float]:
    try:
        data = cache_path.read_bytes()
    except OSError:
        return []
    count = len(data) // _PEAK_BYTES
    if count <= 0:
        return []
    try:
        return list(struct.unpack(f"<{count}f", data))
    except struct.error:
        return []


def _write_cache(cache_path: Path, peaks: list[float]) -> None:
    try:
        cache_path.write_bytes(struct.pack(f"<{len(peaks)}f", *peaks))
    except OSError:
        # Best-effort: missing disk space or read-only mount must not
        # block the in-memory peaks flow.
        return


def get_or_compute_peaks(
    audio_path: Path,
    bins: int = DEFAULT_BIN_COUNT,
) -> list[float]:
    """Return cached peaks if fresh, else extract anew and cache.

    A cache is considered fresh when its mtime is >= the audio's and
    its element count matches ``bins`` exactly (a user's zoom level
    change could legitimately request a different density, forcing a
    re-extract rather than a stretch/squeeze of stale data).
    """

    cache = cache_path_for(audio_path)
    if _is_cache_fresh(audio_path, cache):
        cached = _read_cache(cache)
        if len(cached) == bins:
            return cached
    peaks = extract_peaks(audio_path, bins)
    if peaks:
        _write_cache(cache, peaks)
    return peaks

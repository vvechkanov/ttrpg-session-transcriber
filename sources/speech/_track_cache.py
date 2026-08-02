"""Per-track reuse of the canonical transcript JSON.

Every speech backend already writes ``transcripts/<stem>.json`` after
each track (ADR-8). Nothing ever read it back, so a second run over the
same session redid all the ASR — on a real six-track Craig session that
is eighteen minutes to reproduce a byte-identical result. Re-running is
not an edge case either: it happens after fixing a speaker name, after
one track fails, or after simply opening the folder again.

This module adds the missing half. The writer stamps a cache key into
the same file; the reader hands the segments back when that key still
matches, and stays silent otherwise.

The key deliberately covers only inputs that change the transcript:

    * the audio file's size and mtime — a re-export or a re-encode
      invalidates;
    * the engine name and every knob that reaches the decoder.

It does **not** cover the speaker map. Speaker labels are applied to
the returned segments after loading, so renaming a player re-labels a
cached track instead of re-transcribing it — which is the whole point
of caching for that particular edit.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Mapping

from domain.annotations import SpeechSegment

logger = logging.getLogger(__name__)

#: Bump when the on-disk shape changes in a way older readers can't
#: handle. Entries written by an older version simply miss and get
#: recomputed.
CACHE_SCHEMA_VERSION = 1


def compute_cache_key(audio_path: Path, config: Mapping[str, Any]) -> str:
    """Stable digest of everything that would change the transcript."""

    try:
        stat = audio_path.stat()
        audio_part = f"{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        # Unreadable audio can't be keyed; return something that never
        # matches so we fall through to a real transcription (which will
        # raise its own, clearer error).
        audio_part = "unstattable"

    config_part = json.dumps(
        {k: str(v) for k, v in sorted(config.items())},
        ensure_ascii=False,
    )
    raw = f"v{CACHE_SCHEMA_VERSION}|{audio_part}|{config_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def load_cached_segments(
    path: Path,
    expected_key: str,
    *,
    speaker: str | None = None,
) -> list[SpeechSegment] | None:
    """Return cached segments for this key, or ``None`` on any miss.

    A miss is never an error: a corrupt, truncated or older file just
    means the track gets transcribed again.
    """

    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.debug("cache: unreadable %s, will re-transcribe", path.name)
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("cache_key") != expected_key:
        return None

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        return None

    segments: list[SpeechSegment] = []
    for item in raw_segments:
        try:
            segments.append(SpeechSegment(
                start=float(item["start"]),
                end=float(item["end"]),
                speaker=speaker,
                text=str(item["text"]),
            ))
        except (KeyError, TypeError, ValueError):
            logger.debug("cache: malformed entry in %s, will re-transcribe",
                         path.name)
            return None
    return segments


def write_cached_segments(
    segments: list[SpeechSegment],
    path: Path,
    *,
    source_engine: str,
    schema_version: int,
    cache_key: str | None = None,
) -> None:
    """Write the canonical JSON, stamped with ``cache_key`` when given.

    Keeps the ADR-8 shape (``schema_version`` / ``source_engine`` /
    ``segments`` of start-end-text only); ``cache_key`` is additive, so
    a file written here still reads correctly anywhere that ignores it.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "source_engine": source_engine,
        "segments": [
            {"start": s.start, "end": s.end, "text": s.text} for s in segments
        ],
    }
    if cache_key is not None:
        payload["cache_key"] = cache_key
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "compute_cache_key",
    "load_cached_segments",
    "write_cached_segments",
]

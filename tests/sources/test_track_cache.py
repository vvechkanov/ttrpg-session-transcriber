"""Per-track transcript reuse.

Every backend already wrote transcripts/<stem>.json after each track and
nothing ever read it back, so a second run over the same session redid
all the ASR — eighteen minutes on a real six-track session to reproduce
a byte-identical result.
"""

from __future__ import annotations

import json
from pathlib import Path

from domain.annotations import SpeechSegment
from sources.speech._track_cache import (
    compute_cache_key,
    load_cached_segments,
    write_cached_segments,
)


def _segs() -> list[SpeechSegment]:
    return [
        SpeechSegment(start=0.0, end=1.5, speaker=None, text="привет"),
        SpeechSegment(start=2.0, end=4.0, speaker=None, text="как дела"),
    ]


def _audio(tmp_path: Path, name: str = "1-alice.flac") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fLaC" + b"\0" * 64)
    return p


CONFIG = {"engine": "gigaam", "variant": "rnnt", "device": "cpu"}


def test_round_trip(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    out = tmp_path / "transcripts" / "1-alice.json"
    key = compute_cache_key(audio, CONFIG)

    write_cached_segments(
        _segs(), out, source_engine="gigaam", schema_version=1, cache_key=key
    )
    got = load_cached_segments(out, key, speaker="Алиса")

    assert got is not None
    assert [s.text for s in got] == ["привет", "как дела"]
    assert [s.start for s in got] == [0.0, 2.0]
    assert all(s.speaker == "Алиса" for s in got), (
        "speaker is applied on load, not stored — renaming a player must "
        "not invalidate the cache"
    )


def test_changed_settings_miss(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    out = tmp_path / "t.json"
    write_cached_segments(
        _segs(), out, source_engine="gigaam", schema_version=1,
        cache_key=compute_cache_key(audio, CONFIG),
    )

    other = dict(CONFIG, device="cuda")
    assert load_cached_segments(out, compute_cache_key(audio, other)) is None


def test_reencoded_audio_misses(tmp_path: Path) -> None:
    """Re-exporting the session must invalidate — same name, new bytes."""

    audio = _audio(tmp_path)
    out = tmp_path / "t.json"
    old_key = compute_cache_key(audio, CONFIG)
    write_cached_segments(
        _segs(), out, source_engine="gigaam", schema_version=1,
        cache_key=old_key,
    )

    audio.write_bytes(b"fLaC" + b"\0" * 128)  # different size
    assert compute_cache_key(audio, CONFIG) != old_key
    assert load_cached_segments(out, compute_cache_key(audio, CONFIG)) is None


def test_missing_file_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    assert load_cached_segments(tmp_path / "nope.json", "k") is None


def test_corrupt_file_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    out = tmp_path / "t.json"
    out.write_text("{ this is not json", encoding="utf-8")
    assert load_cached_segments(out, "k") is None


def test_truncated_entry_is_a_miss(tmp_path: Path) -> None:
    out = tmp_path / "t.json"
    out.write_text(json.dumps({
        "schema_version": 1,
        "cache_key": "k",
        "segments": [{"start": 0.0}],  # no end, no text
    }), encoding="utf-8")
    assert load_cached_segments(out, "k") is None


def test_unkeyed_legacy_file_is_a_miss(tmp_path: Path) -> None:
    """Files written before caching existed carry no key — recompute."""

    out = tmp_path / "t.json"
    write_cached_segments(
        _segs(), out, source_engine="gigaam", schema_version=1, cache_key=None
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "cache_key" not in payload
    assert load_cached_segments(out, "anything") is None


def test_canonical_shape_preserved(tmp_path: Path) -> None:
    """ADR-8 readers that ignore cache_key must still parse the file."""

    out = tmp_path / "t.json"
    write_cached_segments(
        _segs(), out, source_engine="gigaam", schema_version=1, cache_key="k"
    )
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["source_engine"] == "gigaam"
    assert [set(s) for s in payload["segments"]] == [
        {"start", "end", "text"}, {"start", "end", "text"}
    ]

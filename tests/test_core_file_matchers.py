"""Tests for :mod:`core.file_matchers`.

The module is pure-stdlib and UI-free, so everything here is plain
``pathlib`` fixtures built with ``tmp_path`` — no Qt, no pytest-qt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from core.file_matchers import (
    AUDIO_EXTENSIONS,
    CraigSegment,
    accepted_extensions_for,
    accepts_file_for,
    detect_audio_files,
    detect_combat_logs,
    detect_craig_segments,
    detect_fvtt_chat_logs,
    match_speaker,
)


def _touch(dir_: Path, name: str, content: str = "") -> Path:
    """Create a regular file inside ``dir_`` and return its path."""
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


# ── detect_audio_files ────────────────────────────────────────────────


class TestDetectAudioFiles:
    def test_empty_directory(self, tmp_path: Path) -> None:
        assert detect_audio_files(tmp_path) == ()

    def test_returns_only_audio_extensions(self, tmp_path: Path) -> None:
        _touch(tmp_path, "notes.txt")
        flac = _touch(tmp_path, "1-andrey.flac")
        _touch(tmp_path, "info.json")
        wav = _touch(tmp_path, "2-boris.wav")

        result = detect_audio_files(tmp_path)
        assert set(result) == {flac, wav}

    def test_excludes_craig_mix(self, tmp_path: Path) -> None:
        good = _touch(tmp_path, "1-andrey.flac")
        _touch(tmp_path, "craig-2024-01-15.flac")
        _touch(tmp_path, "Craig-mix.flac")  # case-insensitive

        result = detect_audio_files(tmp_path)
        assert result == (good,)

    def test_skips_dotfiles(self, tmp_path: Path) -> None:
        _touch(tmp_path, ".hidden.flac")
        keep = _touch(tmp_path, "keep.flac")
        assert detect_audio_files(tmp_path) == (keep,)

    def test_sorted_alphabetically(self, tmp_path: Path) -> None:
        a = _touch(tmp_path, "a.flac")
        b = _touch(tmp_path, "b.flac")
        c = _touch(tmp_path, "c.flac")
        # Created in reverse order but sorted by path
        _ = (c, b, a)
        result = detect_audio_files(tmp_path)
        assert list(result) == [a, b, c]

    def test_all_recognised_extensions(self, tmp_path: Path) -> None:
        files = [
            _touch(tmp_path, f"track{i}{ext}")
            for i, ext in enumerate(AUDIO_EXTENSIONS)
        ]
        result = detect_audio_files(tmp_path)
        assert set(result) == set(files)

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-such-folder"
        assert detect_audio_files(missing) == ()

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        upper = _touch(tmp_path, "track.FLAC")
        assert upper in detect_audio_files(tmp_path)


# ── detect_fvtt_chat_logs ─────────────────────────────────────────────


class TestDetectFvttChatLogs:
    def test_matches_fvtt_log_prefix(self, tmp_path: Path) -> None:
        match = _touch(tmp_path, "fvtt-log-2024-01-15.txt")
        _touch(tmp_path, "other.txt")
        result = detect_fvtt_chat_logs(tmp_path)
        assert result == (match,)

    def test_multiple_logs(self, tmp_path: Path) -> None:
        a = _touch(tmp_path, "fvtt-log-a.txt")
        b = _touch(tmp_path, "fvtt-log-b.txt")
        result = detect_fvtt_chat_logs(tmp_path)
        assert set(result) == {a, b}

    def test_rejects_non_txt(self, tmp_path: Path) -> None:
        _touch(tmp_path, "fvtt-log.json")
        assert detect_fvtt_chat_logs(tmp_path) == ()


# ── detect_combat_logs ────────────────────────────────────────────────


class TestDetectCombatLogs:
    def test_cyrillic_combat_name(self, tmp_path: Path) -> None:
        a = _touch(tmp_path, "Бой_дракон.json")
        b = _touch(tmp_path, "Бой_гоблины.json")
        result = detect_combat_logs(tmp_path)
        assert set(result) == {a, b}

    def test_cyrillic_combat_txt_accepted(self, tmp_path: Path) -> None:
        txt = _touch(tmp_path, "Бой_финал.txt")
        assert detect_combat_logs(tmp_path) == (txt,)

    def test_combat_english(self, tmp_path: Path) -> None:
        c = _touch(tmp_path, "combat_old.json")
        _touch(tmp_path, "combat_note.txt")  # english combat needs .json
        assert detect_combat_logs(tmp_path) == (c,)

    def test_encounter_prefix(self, tmp_path: Path) -> None:
        e = _touch(tmp_path, "encounter-round-3.json")
        assert detect_combat_logs(tmp_path) == (e,)

    def test_irrelevant_files_ignored(self, tmp_path: Path) -> None:
        _touch(tmp_path, "info.txt")
        _touch(tmp_path, "transcript.json")
        assert detect_combat_logs(tmp_path) == ()


# ── accepts_file_for ──────────────────────────────────────────────────


class TestAcceptsFileFor:
    def test_gigaam_accepts_flac(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "a.flac")
        assert accepts_file_for("gigaam", p) is True

    def test_gigaam_rejects_txt(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "a.txt")
        assert accepts_file_for("gigaam", p) is False

    def test_faster_whisper_accepts_wav(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "a.wav")
        assert accepts_file_for("faster-whisper", p) is True

    def test_fvtt_chat_accepts_txt(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "fvtt-log.txt")
        assert accepts_file_for("fvtt-chat", p) is True

    def test_fvtt_chat_rejects_mp3(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "audio.mp3")
        assert accepts_file_for("fvtt-chat", p) is False

    def test_unknown_parser_returns_false(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "anything.flac")
        assert accepts_file_for("nonexistent-parser", p) is False
        # Also never raises
        assert accepts_file_for("", p) is False

    def test_case_insensitive_suffix(self, tmp_path: Path) -> None:
        p = _touch(tmp_path, "a.FLAC")
        assert accepts_file_for("gigaam", p) is True


# ── accepted_extensions_for ───────────────────────────────────────────


class TestAcceptedExtensionsFor:
    def test_known_keys_return_tuples(self) -> None:
        assert ".flac" in accepted_extensions_for("gigaam")
        assert ".txt" in accepted_extensions_for("fvtt-chat")

    def test_unknown_key_returns_empty_tuple(self) -> None:
        assert accepted_extensions_for("not-a-parser") == ()


# ── Layer discipline ───────────────────────────────────────────────────


class TestLayerDiscipline:
    def test_no_ui_imports(self) -> None:
        """`core/file_matchers.py` must not import from ``ui.*``.

        We parse the source file rather than relying on
        ``sys.modules`` so a future accidental `from ui...` import
        is caught without needing an explicit fixture.
        """
        from core import file_matchers

        source = Path(file_matchers.__file__).read_text(encoding="utf-8")
        assert "from ui" not in source
        assert "import ui" not in source


# ── Symlink handling — Windows often disallows without admin ──────────


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Symlink creation requires Developer Mode or admin on Windows",
)
class TestSymlinkSecurity:
    def test_symlink_outside_session_is_skipped(self, tmp_path: Path) -> None:
        outside_dir = tmp_path / "elsewhere"
        outside_dir.mkdir()
        target = _touch(outside_dir, "secret.flac")

        session = tmp_path / "session"
        session.mkdir()
        link = session / "link.flac"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not permitted on this platform")

        assert detect_audio_files(session) == ()

    def test_symlink_inside_session_is_kept(self, tmp_path: Path) -> None:
        session = tmp_path / "session"
        session.mkdir()
        target = _touch(session, "real.flac")

        link = session / "alias.flac"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not permitted on this platform")

        # link.resolve() points back inside session_dir, so it should
        # survive the safe-file filter. We match on resolved paths
        # because the symlink and its target share one inode.
        files = detect_audio_files(session)
        assert target in files


# ── match_speaker ──────────────────────────────────────────────────────


class TestMatchSpeaker:
    def test_strips_leading_digit_prefix(self) -> None:
        assert match_speaker("1-sir_o_genri") == "sir_o_genri"

    def test_same_speaker_across_segments(self) -> None:
        # Craig assigns different join-order prefixes in each segment
        # — the normalised key must be identical so grouping collapses
        # the two files into one row.
        assert match_speaker("1-sir_o_genri") == match_speaker("2-sir_o_genri")

    def test_multi_digit_prefix(self) -> None:
        assert match_speaker("12-kozeff") == "kozeff"

    def test_no_prefix_is_lowercased(self) -> None:
        assert match_speaker("Andrey") == "andrey"

    def test_preserves_underscores_in_stem(self) -> None:
        assert match_speaker("1-v_vladimir") == "v_vladimir"


# ── detect_craig_segments ─────────────────────────────────────────────


class TestDetectCraigSegments:
    def test_flat_layout_returns_single_segment_wrapper(
        self, tmp_path: Path
    ) -> None:
        # Session with audio files directly in session_dir and no
        # Craig-style subfolder — legacy layout, covered by every
        # pre-feature-#4 fixture.
        a = _touch(tmp_path, "1-andrey.flac")
        b = _touch(tmp_path, "2-boris.flac")

        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, CraigSegment)
        assert seg.dir == tmp_path
        assert set(seg.audio_files) == {a, b}
        assert seg.info_path is None

    def test_flat_layout_with_info_txt(self, tmp_path: Path) -> None:
        _touch(tmp_path, "1-andrey.flac")
        info = _touch(tmp_path, "info.txt", "Start time: 2026-04-09T17:21:29.274Z")

        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 1
        assert segments[0].info_path == info

    def test_two_craig_subfolders_cyrillic_and_latin(
        self, tmp_path: Path
    ) -> None:
        craig1 = tmp_path / "craig-1"
        craig1.mkdir()
        _touch(craig1, "1-sir_o_genri.flac")
        _touch(craig1, "2-v_vladimir.flac")
        _touch(craig1, "info.txt", "Start time: 2026-04-09T17:21:29Z")

        craig2 = tmp_path / "крэйг-2"
        craig2.mkdir()
        _touch(craig2, "1-kozeff.flac")
        _touch(craig2, "2-sir_o_genri.flac")
        _touch(craig2, "info.txt", "Start time: 2026-04-09T18:30:00Z")

        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 2
        # Alphabetical by casefold: "craig-1" < "крэйг-2" (ASCII before
        # Cyrillic in Unicode ordering).
        assert segments[0].dir.name == "craig-1"
        assert segments[1].dir.name == "крэйг-2"
        # Each segment sees its own files + info.txt.
        assert segments[0].info_path == craig1 / "info.txt"
        assert segments[1].info_path == craig2 / "info.txt"
        assert len(segments[0].audio_files) == 2
        assert len(segments[1].audio_files) == 2

    def test_subfolder_without_prefix_match_but_with_info_counts(
        self, tmp_path: Path
    ) -> None:
        # A manually-renamed segment folder with no ``craig`` / ``крэйг``
        # in its name still qualifies when it has info.txt + audio.
        custom = tmp_path / "session-part-2"
        custom.mkdir()
        _touch(custom, "1-andrey.flac")
        _touch(custom, "info.txt", "Start time: 2026-04-09T18:00:00Z")

        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 1
        assert segments[0].dir == custom

    def test_empty_subfolder_with_craig_name_is_still_included(
        self, tmp_path: Path
    ) -> None:
        # Edge case: an empty ``craig-3`` folder (recording never
        # started) still matches the name regex and registers as a
        # zero-audio segment. Callers decide what to do with empty
        # ``audio_files``.
        (tmp_path / "craig-3").mkdir()
        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 1
        assert segments[0].audio_files == ()

    def test_random_subfolder_without_info_is_ignored(
        self, tmp_path: Path
    ) -> None:
        # Folder with audio but no info.txt and no ``craig`` name —
        # not a Craig segment. Audio inside it is NOT merged into the
        # fallback flat-layout wrapper either; the fallback only
        # scans ``session_dir`` itself.
        random_dir = tmp_path / "my-notes"
        random_dir.mkdir()
        _touch(random_dir, "recording.flac")

        segments = detect_craig_segments(tmp_path)
        # Fallback fires because no qualifying subfolder was found,
        # and session_dir itself has no audio → one empty segment.
        assert len(segments) == 1
        assert segments[0].dir == tmp_path
        assert segments[0].audio_files == ()

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert detect_craig_segments(tmp_path / "no-such-folder") == ()

    def test_craig_mix_file_excluded_per_segment(self, tmp_path: Path) -> None:
        craig1 = tmp_path / "craig-1"
        craig1.mkdir()
        good = _touch(craig1, "1-andrey.flac")
        _touch(craig1, "craig-2024-01-15.flac")  # mix-down, must be filtered

        segments = detect_craig_segments(tmp_path)
        assert len(segments) == 1
        assert segments[0].audio_files == (good,)


# ── detect_audio_files shim across Craig segments ─────────────────────


class TestDetectAudioFilesAcrossSegments:
    def test_returns_union_of_all_segments(self, tmp_path: Path) -> None:
        craig1 = tmp_path / "craig-1"
        craig1.mkdir()
        a = _touch(craig1, "1-andrey.flac")
        b = _touch(craig1, "2-boris.flac")

        craig2 = tmp_path / "крэйг-2"
        craig2.mkdir()
        c = _touch(craig2, "1-cybrea.flac")

        result = detect_audio_files(tmp_path)
        assert set(result) == {a, b, c}
        # And it's a tuple, path-sorted.
        assert list(result) == sorted([a, b, c])

    def test_flat_session_unchanged(self, tmp_path: Path) -> None:
        # Regression: single-Craig (flat) sessions return the exact
        # same tuple as before feature #4 — existing test suite and
        # real-world sessions depend on this.
        a = _touch(tmp_path, "1-andrey.flac")
        b = _touch(tmp_path, "2-boris.flac")
        assert detect_audio_files(tmp_path) == (a, b)

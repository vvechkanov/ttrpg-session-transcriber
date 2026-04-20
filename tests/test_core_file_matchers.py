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
    accepted_extensions_for,
    accepts_file_for,
    detect_audio_files,
    detect_combat_logs,
    detect_fvtt_chat_logs,
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

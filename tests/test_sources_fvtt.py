"""Tier 1 — FvttChatSource parse tests with tiny fixture file.

No audio, no ASR models. Must run in <5s.

Uses tests/fixtures/fvtt_chat_tiny.txt as the fixture file.
The info.txt anchor (recording start time) is generated dynamically
via tmp_path to align timestamps deterministically.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FVTT_TINY = FIXTURE_DIR / "fvtt_chat_tiny.txt"


class TestFvttChatSourceParse:
    """Parse the tiny fixture file — no real session dir needed."""

    def _make_info_txt(self, tmp_path: Path, start_dt: str) -> Path:
        """Write a minimal Craig info.txt with the given UTC start time."""
        info = tmp_path / "info.txt"
        info.write_text(f"Start time: {start_dt}\n", encoding="utf-8")
        return info

    def test_fixture_file_exists(self):
        """Confirm the test fixture is present."""
        assert FVTT_TINY.exists(), f"Fixture missing: {FVTT_TINY}"

    def test_parse_returns_chat_messages(self, tmp_path):
        """Parsing the tiny fixture returns ChatMessage objects.

        Fixture timestamps are local PM times on 2025-07-11 (Moscow UTC+3).
        First message: 3:00:00 PM local = 12:00 UTC.
        rec_start = 11:55:00 UTC -> messages are ~5 min into recording.
        """
        from sources.game_log.fvtt_chat import FvttChatSource
        # 15:00 local (UTC+3) = 12:00 UTC; rec_start 11:55 UTC => at = 300s
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,  # UTC+3 (Moscow time)
        )
        messages = src.extract(tmp_path)
        assert len(messages) > 0

    def test_plus_message_filtered(self, tmp_path):
        """Messages with text '+' are filtered out (trivial messages)."""
        from sources.game_log.fvtt_chat import FvttChatSource
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,
        )
        messages = src.extract(tmp_path)
        texts = [m.text for m in messages]
        assert "+" not in texts

    def test_channel_is_ic_by_default(self, tmp_path):
        """All messages use 'ic' channel (FVTT log has no ic/ooc markup)."""
        from sources.game_log.fvtt_chat import FvttChatSource
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,
        )
        messages = src.extract(tmp_path)
        assert all(m.channel == "ic" for m in messages)

    def test_authors_present(self, tmp_path):
        """Known authors from fixture appear in parsed messages."""
        from sources.game_log.fvtt_chat import FvttChatSource
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,
        )
        messages = src.extract(tmp_path)
        authors = {m.author for m in messages}
        # Fixture has TestGM and TestPlayer1 with non-trivial messages
        assert "TestGM" in authors
        assert "TestPlayer1" in authors

    def test_timestamps_are_nonnegative(self, tmp_path):
        """Messages before recording start are filtered; remaining at >= 0."""
        from sources.game_log.fvtt_chat import FvttChatSource
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,
        )
        messages = src.extract(tmp_path)
        assert all(m.at >= 0 for m in messages)

    def test_timestamps_monotonically_increasing(self, tmp_path):
        """Messages should be in chronological order (fixture is chronological)."""
        from sources.game_log.fvtt_chat import FvttChatSource
        info = self._make_info_txt(tmp_path, "2025-07-11T11:55:00Z")
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=info,
            tz_offset=3.0,
        )
        messages = src.extract(tmp_path)
        timestamps = [m.at for m in messages]
        assert timestamps == sorted(timestamps)

    def test_missing_info_file_raises(self, tmp_path):
        """Passing no info file and no info.txt in session_dir raises FileNotFoundError."""
        from sources.game_log.fvtt_chat import FvttChatSource
        src = FvttChatSource(
            chat_log_path=FVTT_TINY,
            info_file_path=None,  # No explicit path
        )
        empty_dir = tmp_path / "no_info"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            src.extract(empty_dir)


class TestFvttChatSourceInternals:
    """Tests for internal parsing helpers (imported directly)."""

    def test_parse_fvtt_log_returns_entries(self):
        from sources.game_log.fvtt_chat import parse_fvtt_log
        entries = parse_fvtt_log(FVTT_TINY)
        assert len(entries) >= 3  # 3 non-trivial entries (+ one is skipped)
        assert all("datetime" in e for e in entries)
        assert all("speaker" in e for e in entries)
        assert all("text" in e for e in entries)

    def test_parse_info_start_time(self, tmp_path):
        from sources.game_log.fvtt_chat import parse_info_start_time
        info = tmp_path / "info.txt"
        info.write_text("Start time: 2025-07-11T15:00:00Z\n", encoding="utf-8")
        dt = parse_info_start_time(info)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 11
        assert dt.hour == 15

    def test_parse_info_start_time_missing_key_raises(self, tmp_path):
        from sources.game_log.fvtt_chat import parse_info_start_time
        info = tmp_path / "info.txt"
        info.write_text("No relevant content here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Start time"):
            parse_info_start_time(info)

    def test_guess_tz_offset_empty_entries(self):
        from sources.game_log.fvtt_chat import guess_tz_offset
        from datetime import timezone
        rec_start = datetime(2025, 7, 11, 15, 0, 0, tzinfo=timezone.utc)
        offset = guess_tz_offset([], rec_start)
        assert offset == 0.0

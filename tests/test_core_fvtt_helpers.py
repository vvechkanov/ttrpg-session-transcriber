"""Tier 1 — core.fvtt_helpers tests.

Tests detect_fvtt_tz_offset with tmp_path fixtures. Tests the thin
core-layer shim that wraps the sources.game_log.fvtt_chat parsing
helpers (the only path by which UI is allowed to reach that logic,
since ui → sources is forbidden by the layer rules).
"""

import pytest


_TWO_ENTRY_LOG = (
    "[7/11/2025, 6:00:00 PM] Alice\n"
    "hello world\n"
    "---------------------------\n"
    "[7/11/2025, 6:05:00 PM] Bob\n"
    "hi there\n"
    "---------------------------\n"
)


class TestDetectFvttTzOffset:
    def test_returns_zero_for_empty_log(self, tmp_path):
        from core.fvtt_helpers import detect_fvtt_tz_offset
        chat = tmp_path / "fvtt-log-empty.txt"
        chat.write_text("", encoding="utf-8")
        info = tmp_path / "info.txt"
        info.write_text("Start time: 2025-07-11T15:00:00Z\n", encoding="utf-8")
        assert detect_fvtt_tz_offset(chat, info) == 0.0

    def test_detects_offset_matching_recording_start(self, tmp_path):
        # First entry at local 6:00 PM = 18:00.
        # Recording start 15:00 UTC → UTC offset should be +3.
        from core.fvtt_helpers import detect_fvtt_tz_offset
        chat = tmp_path / "fvtt-log-1.txt"
        chat.write_text(_TWO_ENTRY_LOG, encoding="utf-8")
        info = tmp_path / "info.txt"
        info.write_text("Start time: 2025-07-11T15:00:00Z\n", encoding="utf-8")
        assert detect_fvtt_tz_offset(chat, info) == 3.0

    def test_raises_when_info_missing_start_time(self, tmp_path):
        from core.fvtt_helpers import detect_fvtt_tz_offset
        chat = tmp_path / "fvtt-log-1.txt"
        chat.write_text(_TWO_ENTRY_LOG, encoding="utf-8")
        info = tmp_path / "info.txt"
        info.write_text("No start time key here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Start time"):
            detect_fvtt_tz_offset(chat, info)

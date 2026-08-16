"""Tier 1 — core.fvtt_helpers tests.

Tests detect_fvtt_tz_offset / describe_fvtt_tz with tmp_path fixtures.
This is the thin core-layer shim wrapping the sources.game_log.fvtt_chat
resolver (the only path by which UI is allowed to reach that logic,
since ui → sources is forbidden by the layer rules).

The resolver consults the *system* timezone as one of its steps, so
every test here pins that step explicitly via the ``pin_system_tz``
fixture from conftest. A test that lets the real machine timezone leak
in passes in Prague and fails in CI.
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

# Same log, but Alice drops the marker at the moment Record is pressed.
# Marker at local 18:00 against a 15:00 UTC recording start → +3.
_ANCHORED_LOG = (
    "[7/11/2025, 6:00:00 PM] Alice\n"
    "craig-start\n"
    "---------------------------\n"
    "[7/11/2025, 6:05:00 PM] Bob\n"
    "hi there\n"
    "---------------------------\n"
)


def _write_pair(tmp_path, log_text, start_time="2025-07-11T15:00:00Z"):
    chat = tmp_path / "fvtt-log-1.txt"
    chat.write_text(log_text, encoding="utf-8")
    info = tmp_path / "info.txt"
    info.write_text(f"Start time: {start_time}\n", encoding="utf-8")
    return chat, info


class TestDetectFvttTzOffset:
    def test_returns_zero_for_empty_log(self, tmp_path, pin_system_tz):
        from core.fvtt_helpers import detect_fvtt_tz_offset
        pin_system_tz(5.0)
        chat, info = _write_pair(tmp_path, "")
        assert detect_fvtt_tz_offset(chat, info) == 0.0

    def test_empty_log_does_not_read_info_txt(self, tmp_path, pin_system_tz):
        """A broken info.txt must not break the Timeline screen.

        The offset is meaningless when there are no entries to shift,
        so the resolver never gets far enough to need a start time.
        """
        from core.fvtt_helpers import detect_fvtt_tz_offset
        pin_system_tz(5.0)
        chat = tmp_path / "fvtt-log-1.txt"
        chat.write_text("", encoding="utf-8")
        info = tmp_path / "info.txt"
        info.write_text("no start time key here\n", encoding="utf-8")
        assert detect_fvtt_tz_offset(chat, info) == 0.0

    def test_anchor_marker_wins_over_system_tz(self, tmp_path, pin_system_tz):
        from core.fvtt_helpers import describe_fvtt_tz
        pin_system_tz(2.0)
        chat, info = _write_pair(tmp_path, _ANCHORED_LOG)
        resolution = describe_fvtt_tz(chat, info)
        assert resolution.source == "anchor"
        assert resolution.offset_hours == 3.0

    def test_falls_back_to_system_tz(self, tmp_path, pin_system_tz):
        """No marker → machine timezone, *not* the heuristic.

        The heuristic would answer +3 here (first entry 18:00 local vs
        15:00 UTC start). The machine says +2, and the machine is the
        one that exported the log — it wins.
        """
        from core.fvtt_helpers import describe_fvtt_tz
        pin_system_tz(2.0)
        chat, info = _write_pair(tmp_path, _TWO_ENTRY_LOG)
        resolution = describe_fvtt_tz(chat, info)
        assert resolution.source == "system"
        assert resolution.offset_hours == 2.0

    def test_falls_back_to_heuristic_without_system_tz(
        self, tmp_path, pin_system_tz
    ):
        from core.fvtt_helpers import describe_fvtt_tz
        pin_system_tz(None)
        chat, info = _write_pair(tmp_path, _TWO_ENTRY_LOG)
        resolution = describe_fvtt_tz(chat, info)
        assert resolution.source == "heuristic"
        assert resolution.offset_hours == 3.0
        assert resolution.is_reliable is False

    def test_raises_when_info_missing_start_time(self, tmp_path, pin_system_tz):
        from core.fvtt_helpers import detect_fvtt_tz_offset
        pin_system_tz(2.0)
        chat = tmp_path / "fvtt-log-1.txt"
        chat.write_text(_TWO_ENTRY_LOG, encoding="utf-8")
        info = tmp_path / "info.txt"
        info.write_text("No start time key here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Start time"):
            detect_fvtt_tz_offset(chat, info)

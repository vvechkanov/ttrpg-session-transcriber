"""Tier-1 tests for scripts/parse_fvtt_chat.py — layered tz fallback."""

from datetime import datetime, timezone

import pytest


# ── guess_tz_offset (regression: Session 6 case) ──────────────────────


class TestGuessTzOffset:
    def test_empty_entries_returns_zero(self):
        from parse_fvtt_chat import guess_tz_offset
        rec_start = datetime(2025, 7, 11, 15, 0, 0, tzinfo=timezone.utc)
        assert guess_tz_offset([], rec_start) == 0.0

    def test_first_entry_before_rec_start_picks_correct_offset(self):
        """Real Session 6 case — pre-game banter starts ~3 min BEFORE Craig.

        Old heuristic required ``delta >= 0`` and silently picked +1 (CET).
        Fix uses ``min |delta|``, so the correct +2 (CEST, Serbia) wins.
        """
        from parse_fvtt_chat import guess_tz_offset
        first_local = datetime(2026, 4, 18, 18, 12, 13)  # 6:12:13 PM
        rec_start = datetime(2026, 4, 18, 16, 15, 16, tzinfo=timezone.utc)
        entries = [{"datetime": first_local, "speaker": "X", "text": "27"}]
        assert guess_tz_offset(entries, rec_start) == 2.0


# ── find_anchor_offset (craig-start marker) ───────────────────────────


class TestFindAnchorOffset:
    def test_returns_none_when_no_marker(self):
        from parse_fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21),
             "speaker": "X", "text": "27"},
        ]
        assert find_anchor_offset(entries, rec_start) is None

    def test_picks_exact_offset_from_marker(self):
        """Session 7 hypothetical: user types craig-start at the moment
        they hit Record. Local 20:09:05 ↔ UTC 18:09:01 → +2."""
        from parse_fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21),
             "speaker": "P1", "text": "27"},
            {"datetime": datetime(2026, 4, 25, 20, 9, 5),
             "speaker": "GM", "text": "craig-start"},
            {"datetime": datetime(2026, 4, 25, 20, 11, 0),
             "speaker": "P1", "text": "let's go"},
        ]
        assert find_anchor_offset(entries, rec_start) == 2.0

    def test_marker_variants_all_match(self):
        from parse_fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        local_at_marker = datetime(2026, 4, 25, 20, 0, 0)
        for variant in (
            "craig-start",
            "Craig Start",
            "CRAIG_START",
            "[craig-start]",
            "/craig-start",
            "craig start session 7",
        ):
            entries = [{"datetime": local_at_marker, "speaker": "GM",
                        "text": variant}]
            assert find_anchor_offset(entries, rec_start) == 2.0, variant

    def test_unrelated_text_not_matched(self):
        from parse_fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 20, 0, 0), "speaker": "X",
             "text": "starting craig now"},
            {"datetime": datetime(2026, 4, 25, 20, 1, 0), "speaker": "X",
             "text": "Craig is starting"},
        ]
        assert find_anchor_offset(entries, rec_start) is None

    def test_implausible_offset_returns_none(self):
        """Marker that resolves to >14h offset is treated as garbage."""
        from parse_fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 26, 12, 0, 0), "speaker": "GM",
             "text": "craig-start"},
        ]
        assert find_anchor_offset(entries, rec_start) is None


# ── system_utc_offset_hours ───────────────────────────────────────────


class TestSystemUtcOffsetHours:
    def test_returns_float_or_none(self):
        from parse_fvtt_chat import system_utc_offset_hours
        result = system_utc_offset_hours()
        assert result is None or isinstance(result, float)
        if result is not None:
            assert -14.0 <= result <= 14.0


# ── resolve_tz_offset orchestrator ────────────────────────────────────


class TestResolveTzOffset:
    def _entries_with_marker(self):
        return [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21),
             "speaker": "P1", "text": "27"},
            {"datetime": datetime(2026, 4, 25, 20, 9, 5),
             "speaker": "GM", "text": "craig-start"},
        ]

    def _entries_without_marker(self):
        return [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21),
             "speaker": "P1", "text": "27"},
        ]

    def test_override_wins_over_everything(self, monkeypatch):
        import parse_fvtt_chat
        monkeypatch.setattr(
            parse_fvtt_chat, "system_utc_offset_hours", lambda: 5.0
        )
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        entries = self._entries_with_marker()
        offset, source = parse_fvtt_chat.resolve_tz_offset(
            entries, rec_start, override=7.0
        )
        assert offset == 7.0
        assert source == "override"

    def test_marker_wins_over_system_tz(self, monkeypatch):
        import parse_fvtt_chat
        monkeypatch.setattr(
            parse_fvtt_chat, "system_utc_offset_hours", lambda: 5.0
        )
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        offset, source = parse_fvtt_chat.resolve_tz_offset(
            self._entries_with_marker(), rec_start
        )
        assert offset == 2.0
        assert source == "marker"

    def test_system_tz_wins_when_no_marker(self, monkeypatch):
        import parse_fvtt_chat
        monkeypatch.setattr(
            parse_fvtt_chat, "system_utc_offset_hours", lambda: 2.0
        )
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        offset, source = parse_fvtt_chat.resolve_tz_offset(
            self._entries_without_marker(), rec_start
        )
        assert offset == 2.0
        assert source == "system"

    def test_heuristic_used_when_system_tz_unavailable(self, monkeypatch):
        import parse_fvtt_chat
        monkeypatch.setattr(
            parse_fvtt_chat, "system_utc_offset_hours", lambda: None
        )
        rec_start = datetime(2026, 4, 18, 16, 15, 16, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 18, 18, 12, 13),
             "speaker": "P1", "text": "27"},
        ]
        offset, source = parse_fvtt_chat.resolve_tz_offset(entries, rec_start)
        assert offset == 2.0
        assert source == "heuristic"

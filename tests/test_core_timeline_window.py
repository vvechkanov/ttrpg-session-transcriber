"""Tier-1 tests for ``core.timeline_window``.

Exercises the pure parsers (info.txt, combat JSON, chat span helper)
and the window builder. No audio, no Qt — should finish in <1s.

Fixture strategy: every test writes its own mini ``info.txt`` /
``Бой N.txt`` under ``tmp_path``. We never depend on real session
folders on disk so the suite is portable and deterministic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.timeline_window import (
    CombatMeta,
    TimelineWindow,
    build_window,
    chat_span,
    parse_combat_file,
    parse_info_start,
)


# ── parse_info_start ─────────────────────────────────────────────────────


class TestParseInfoStart:
    def _write_info(self, tmp_path: Path, body: str) -> Path:
        p = tmp_path / "info.txt"
        p.write_text(body, encoding="utf-8")
        return p

    def test_real_craig_format(self, tmp_path):
        body = (
            "Recording MZ9C7mMW3ezw\n"
            "\n"
            "Guild:\t\tДомик для НРИ (980220093663416340)\n"
            "Channel:\tИгровая-1 (1380600668556890122)\n"
            "Requester:\tv.vladimir#0 (246934307128475648)\n"
            "Start time:\t2026-04-09T17:21:29.274Z\n"
            "\n"
            "Tracks:\n"
            "\tsir.o.genri#0 (364804526735097859)\n"
        )
        info = self._write_info(tmp_path, body)
        dt = parse_info_start(info)
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime(2026, 4, 9, 17, 21, 29, 274_000, tzinfo=timezone.utc)

    def test_missing_file_returns_none(self, tmp_path):
        assert parse_info_start(tmp_path / "nonexistent.txt") is None

    def test_missing_start_line_returns_none(self, tmp_path):
        info = self._write_info(tmp_path, "Recording foo\nNo start anywhere.\n")
        assert parse_info_start(info) is None

    def test_bad_format_returns_none(self, tmp_path):
        info = self._write_info(tmp_path, "Start time: totally-not-iso\n")
        assert parse_info_start(info) is None

    def test_naive_timestamp_assumes_utc(self, tmp_path):
        info = self._write_info(tmp_path, "Start time: 2026-04-09T17:21:29\n")
        dt = parse_info_start(info)
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime(2026, 4, 9, 17, 21, 29, tzinfo=timezone.utc)

    def test_non_utc_offset_normalises_to_utc(self, tmp_path):
        info = self._write_info(tmp_path, "Start time: 2026-04-09T20:21:29+03:00\n")
        dt = parse_info_start(info)
        assert dt is not None
        # 20:21 +03:00 == 17:21 UTC
        assert dt == datetime(2026, 4, 9, 17, 21, 29, tzinfo=timezone.utc)


# ── parse_combat_file ────────────────────────────────────────────────────


class TestParseCombatFile:
    def _write_combat(self, tmp_path: Path, name: str, data: dict | str) -> Path:
        p = tmp_path / name
        if isinstance(data, dict):
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        else:
            p.write_text(data, encoding="utf-8")
        return p

    def test_real_encounter_format(self, tmp_path):
        data = {
            "encounter_id": "p4TFstzKNDs4IGjI",
            "scene_name": "Unknown Scene",
            "started_at": "2026-04-09T19:25:33.183Z",
            "ended_at": "2026-04-09T20:45:45.523Z",
            "initiative_order": [],
        }
        p = self._write_combat(tmp_path, "Бой 1.txt", data)
        meta = parse_combat_file(p)
        assert meta is not None
        assert meta.label == "Бой 1"
        assert meta.started_at == datetime(
            2026, 4, 9, 19, 25, 33, 183_000, tzinfo=timezone.utc
        )
        assert meta.ended_at == datetime(
            2026, 4, 9, 20, 45, 45, 523_000, tzinfo=timezone.utc
        )

    def test_invalid_json_returns_none(self, tmp_path):
        p = self._write_combat(tmp_path, "Бой 1.txt", "{not json")
        assert parse_combat_file(p) is None

    def test_missing_started_at_returns_none(self, tmp_path):
        p = self._write_combat(
            tmp_path, "Бой 1.txt",
            {"ended_at": "2026-04-09T20:45:45.523Z"},
        )
        assert parse_combat_file(p) is None

    def test_missing_ended_at_returns_none(self, tmp_path):
        p = self._write_combat(
            tmp_path, "Бой 1.txt",
            {"started_at": "2026-04-09T19:25:33.183Z"},
        )
        assert parse_combat_file(p) is None

    def test_ended_before_started_returns_none(self, tmp_path):
        p = self._write_combat(tmp_path, "Бой 1.txt", {
            "started_at": "2026-04-09T20:00:00Z",
            "ended_at":   "2026-04-09T19:00:00Z",
        })
        assert parse_combat_file(p) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert parse_combat_file(tmp_path / "ghost.json") is None

    def test_label_from_stem_en(self, tmp_path):
        p = self._write_combat(tmp_path, "combat_1.json", {
            "started_at": "2026-04-09T19:00:00Z",
            "ended_at":   "2026-04-09T20:00:00Z",
        })
        meta = parse_combat_file(p)
        assert meta is not None
        assert meta.label == "combat_1"

    def test_non_object_json_returns_none(self, tmp_path):
        p = self._write_combat(tmp_path, "Бой 1.txt", "[]")
        assert parse_combat_file(p) is None


# ── TimelineWindow.pct_for ───────────────────────────────────────────────


class TestTimelineWindowPctFor:
    def _window(self) -> TimelineWindow:
        t0 = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
        t_end = datetime(2026, 4, 9, 21, 0, 0, tzinfo=timezone.utc)  # +4h
        return TimelineWindow(t0=t0, t_end=t_end)

    def test_start_returns_zero(self):
        w = self._window()
        assert w.pct_for(w.t0) == pytest.approx(0.0)

    def test_end_returns_hundred(self):
        w = self._window()
        assert w.pct_for(w.t_end) == pytest.approx(100.0)

    def test_middle_is_fifty(self):
        w = self._window()
        mid = datetime(2026, 4, 9, 19, 0, 0, tzinfo=timezone.utc)
        assert w.pct_for(mid) == pytest.approx(50.0)

    def test_before_t0_clamps_to_zero(self):
        w = self._window()
        before = datetime(2026, 4, 9, 15, 0, 0, tzinfo=timezone.utc)
        assert w.pct_for(before) == 0.0

    def test_after_tend_clamps_to_hundred(self):
        w = self._window()
        after = datetime(2026, 4, 9, 23, 0, 0, tzinfo=timezone.utc)
        assert w.pct_for(after) == 100.0

    def test_naive_datetime_raises(self):
        w = self._window()
        naive = datetime(2026, 4, 9, 19, 0, 0)
        with pytest.raises(ValueError, match="timezone-aware"):
            w.pct_for(naive)

    def test_non_utc_tz_is_converted(self):
        w = self._window()
        # 22:00 +03:00 == 19:00 UTC == middle
        import datetime as dt_mod
        non_utc = datetime(
            2026, 4, 9, 22, 0, 0,
            tzinfo=dt_mod.timezone(dt_mod.timedelta(hours=3)),
        )
        assert w.pct_for(non_utc) == pytest.approx(50.0)


# ── build_window ─────────────────────────────────────────────────────────


class TestBuildWindow:
    def test_info_plus_combat_session4(self):
        """Reproduce the expected layout for the session-4 fixture."""
        info_start = datetime(2026, 4, 9, 17, 21, 29, tzinfo=timezone.utc)
        combat = CombatMeta(
            started_at=datetime(2026, 4, 9, 19, 25, 33, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 9, 20, 45, 45, tzinfo=timezone.utc),
            label="Бой 1",
        )
        window = build_window(
            info_start=info_start,
            max_track_duration=None,
            chat=None,
            combats=[combat],
        )
        assert window is not None
        assert window.t0 == info_start
        # Combat ends ~3h24m in; default 4h floor wins.
        assert (window.t_end - window.t0).total_seconds() == pytest.approx(4 * 3600)

    def test_no_info_no_data_returns_none(self):
        assert build_window(None, None, None, []) is None

    def test_no_info_with_chat_uses_chat_start(self):
        chat_first = datetime(2026, 4, 9, 18, 0, 0, tzinfo=timezone.utc)
        chat_last = datetime(2026, 4, 9, 22, 0, 0, tzinfo=timezone.utc)
        window = build_window(
            info_start=None,
            max_track_duration=None,
            chat=(chat_first, chat_last),
            combats=[],
        )
        assert window is not None
        assert window.t0 == chat_first
        assert window.t_end == chat_last

    def test_short_window_rejected(self):
        """Windows < 10 minutes fall back to None."""
        chat_first = datetime(2026, 4, 9, 18, 0, 0, tzinfo=timezone.utc)
        chat_last = datetime(2026, 4, 9, 18, 1, 0, tzinfo=timezone.utc)  # 1 min
        window = build_window(
            info_start=None,
            max_track_duration=None,
            chat=(chat_first, chat_last),
            combats=[],
        )
        assert window is None

    def test_combat_extends_end_beyond_default(self):
        """Combat ending after info_start + default pushes t_end out."""
        info_start = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
        # Combat ends 6h after start — beyond the 4h default floor.
        combat = CombatMeta(
            started_at=datetime(2026, 4, 9, 22, 0, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 9, 23, 0, 0, tzinfo=timezone.utc),
            label="Бой поздний",
        )
        window = build_window(
            info_start=info_start,
            max_track_duration=None,
            chat=None,
            combats=[combat],
        )
        assert window is not None
        assert window.t_end == combat.ended_at

    def test_max_track_duration_extends_end(self):
        """max_track_duration beats the default-hours floor when larger."""
        info_start = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
        window = build_window(
            info_start=info_start,
            max_track_duration=6 * 3600,  # 6h
            chat=None,
            combats=[],
        )
        assert window is not None
        assert (window.t_end - window.t0).total_seconds() == pytest.approx(6 * 3600)

    def test_window_scenario_yields_expected_percents(self):
        """End-to-end: session-4-like inputs produce the planned pct values."""
        info_start = datetime(2026, 4, 9, 17, 21, 29, tzinfo=timezone.utc)
        combat = CombatMeta(
            started_at=datetime(2026, 4, 9, 19, 25, 33, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 9, 20, 45, 45, tzinfo=timezone.utc),
            label="Бой 1",
        )
        window = build_window(
            info_start=info_start,
            max_track_duration=None,
            chat=None,
            combats=[combat],
        )
        assert window is not None
        # Total span = 4h = 240 min.
        # combat.started_at offset from t0 = 2h4m4s = 7444s ≈ 51.7%
        start_pct = window.pct_for(combat.started_at)
        end_pct = window.pct_for(combat.ended_at)
        assert 50.0 < start_pct < 53.0
        assert 84.0 < end_pct < 86.0


# ── chat_span ────────────────────────────────────────────────────────────


class TestChatSpan:
    def test_none_info_start_returns_none(self, tmp_path):
        chat_path = tmp_path / "fvtt-log.txt"
        chat_path.write_text("", encoding="utf-8")
        assert chat_span(chat_path, None) is None

    def test_missing_chat_returns_none(self, tmp_path):
        ghost = tmp_path / "no-such-chat.txt"
        info_start = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
        assert chat_span(ghost, info_start) is None

    def test_tiny_fixture_returns_ordered_span(self, tmp_path):
        """Use the project's existing tiny fixture."""
        fixture = Path(__file__).resolve().parent / "fixtures" / "fvtt_chat_tiny.txt"
        assert fixture.exists(), "fvtt_chat_tiny.txt fixture missing"
        # Fixture local times: 2025-07-11 15:00..15:03 PM.
        # info_start just before the first message so tz guess picks +3.
        info_start = datetime(2025, 7, 11, 11, 55, 0, tzinfo=timezone.utc)
        span = chat_span(fixture, info_start)
        assert span is not None
        first, last = span
        assert first.tzinfo is not None
        assert last.tzinfo is not None
        assert first <= last

    def test_empty_chat_returns_none(self, tmp_path):
        chat_path = tmp_path / "fvtt-log.txt"
        chat_path.write_text("", encoding="utf-8")
        info_start = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
        assert chat_span(chat_path, info_start) is None


class TestWindowCoversTimeBeforeRecording:
    """The window starts with the session, not with the recording.

    Anchoring t0 on info_start assumed nothing happens before Record is
    pressed. When someone presses it late, everything earlier clamped
    onto 0%: the chat bar started flush with the audio and an encounter
    that finished before the recording collapsed to zero width — drawn
    as a one-pixel tick directly under a banner announcing it had no
    audio.
    """

    #: A real shape: chat from 18:55, fight 19:11-20:18, Record at 20:42.
    CHAT_FIRST = datetime(2026, 8, 15, 16, 55, 9, tzinfo=timezone.utc)
    CHAT_LAST = datetime(2026, 8, 15, 21, 31, 2, tzinfo=timezone.utc)
    REC_START = datetime(2026, 8, 15, 18, 42, 9, tzinfo=timezone.utc)
    COMBAT = CombatMeta(
        started_at=datetime(2026, 8, 15, 17, 11, 48, tzinfo=timezone.utc),
        ended_at=datetime(2026, 8, 15, 18, 18, 35, tzinfo=timezone.utc),
        label="Бой",
    )

    def _window(self):
        return build_window(
            info_start=self.REC_START,
            max_track_duration=11879.8,
            chat=(self.CHAT_FIRST, self.CHAT_LAST),
            combats=[self.COMBAT],
        )

    def test_starts_at_the_earliest_event_not_the_recording(self):
        window = self._window()
        assert window is not None
        assert window.t0 == self.CHAT_FIRST
        assert window.t0 < self.REC_START

    def test_recording_start_is_kept_separately(self):
        window = self._window()
        assert window.recording_start == self.REC_START
        assert window.covers_time_before_recording
        # 1h47m of a 5h47m window.
        assert window.recording_start_pct == pytest.approx(30.8, abs=0.2)

    def test_missed_encounter_keeps_its_width(self):
        """The fight must be a bar you can see, not a collapsed pixel."""
        window = self._window()
        start = window.pct_for(self.COMBAT.started_at)
        end = window.pct_for(self.COMBAT.ended_at)
        assert end - start == pytest.approx(19.2, abs=0.3)
        # And it sits wholly left of the recording — that is the point.
        assert end < window.recording_start_pct

    def test_chat_no_longer_pretends_to_start_with_the_audio(self):
        window = self._window()
        assert window.pct_for(self.CHAT_FIRST) == 0.0
        assert window.recording_start_pct > 0.0

    def test_no_shading_when_the_recording_covers_everything(self):
        """Record pressed first — nothing to mark as missing."""
        rec = datetime(2026, 8, 15, 16, 0, 0, tzinfo=timezone.utc)
        window = build_window(
            info_start=rec,
            max_track_duration=None,
            chat=(self.CHAT_FIRST, self.CHAT_LAST),
            combats=[self.COMBAT],
        )
        assert window.t0 == rec
        assert window.recording_start_pct == 0.0
        assert window.covers_time_before_recording is False

    def test_recording_start_is_none_without_info_txt(self):
        window = build_window(
            info_start=None,
            max_track_duration=None,
            chat=(self.CHAT_FIRST, self.CHAT_LAST),
            combats=[],
        )
        assert window.recording_start is None
        assert window.recording_start_pct == 0.0
        assert window.covers_time_before_recording is False


class TestEventDensity:
    """Real event positions, replacing the fabricated tick comb.

    SourceLaneRow used to draw 12-18 ticks at positions derived from the
    parser id's character codes — the same pattern on every session,
    described in the source as a "content density suggestion". It looked
    like data. These are the actual moments instead.
    """

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"

    def test_combat_events_are_parsed(self):
        meta = parse_combat_file(self.FIXTURE / "combat.json")
        assert meta is not None
        assert len(meta.events) == 170
        assert all(e.tzinfo is not None for e in meta.events)
        # Every roll belongs inside the encounter it came from.
        assert min(meta.events) >= meta.started_at
        assert max(meta.events) <= meta.ended_at

    def test_combat_events_default_to_empty(self):
        """A dump without chat_messages still parses — just no ticks."""
        meta = CombatMeta(
            started_at=datetime(2026, 8, 15, 17, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc),
            label="Бой",
        )
        assert meta.events == ()

    @pytest.mark.parametrize(
        "payload",
        [
            {"rounds": {"1": {}}},
            {"rounds": "nope"},
            {"rounds": [{"turns": ["x"]}]},
            {"rounds": [{"turns": [{"chat_messages": [["a"]]}]}]},
        ],
    )
    def test_malformed_dump_yields_no_events(self, tmp_path, payload):
        """Wrong types must cost the ticks, not raise out of a parser."""
        import json

        payload = dict(payload)
        payload["started_at"] = "2026-08-15T17:00:00Z"
        payload["ended_at"] = "2026-08-15T18:00:00Z"
        path = tmp_path / "Бой.txt"
        path.write_text(json.dumps(payload), encoding="utf-8")

        meta = parse_combat_file(path)
        assert meta is not None
        assert meta.events == ()

    def test_chat_events_land_where_the_merger_puts_them(self, pin_system_tz):
        """Ticks must agree with the offset the merge will actually use."""
        from core.timeline_window import chat_events

        pin_system_tz(9.0)  # deliberately wrong; the combat anchor wins
        info_start = parse_info_start(self.FIXTURE / "info.txt")
        moments = chat_events(self.FIXTURE / "fvtt-log-fixture.txt", info_start)

        assert len(moments) == 353
        assert list(moments) == sorted(moments)
        # First entry is 18:55:09 local at the true +2 → 16:55:09Z.
        assert moments[0] == datetime(2026, 8, 15, 16, 55, 9, tzinfo=timezone.utc)

    def test_chat_events_empty_without_info_start(self):
        from core.timeline_window import chat_events

        assert chat_events(self.FIXTURE / "fvtt-log-fixture.txt", None) == ()

    def test_chat_events_empty_for_missing_file(self, tmp_path):
        from core.timeline_window import chat_events

        info_start = parse_info_start(self.FIXTURE / "info.txt")
        assert chat_events(tmp_path / "nope.txt", info_start) == ()


class TestDisplayOffsetHonesty:
    """A ruler must not label UTC as if it were the session's clock."""

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"

    def test_none_without_any_anchor(self):
        """No chat log and no recording time — nothing to say.

        Returning 0.0 here (as it did) is indistinguishable from a real
        UTC+0 session, and the ruler happily stamped UTC hours onto a
        session recorded at +2.
        """
        from core.timeline_window import display_offset_hours

        assert display_offset_hours(None, None) is None

    def test_resolved_offset_when_the_chat_says_so(self, pin_system_tz):
        from core.timeline_window import display_offset_hours

        pin_system_tz(9.0)  # wrong on purpose; the combat anchor wins
        info_start = parse_info_start(self.FIXTURE / "info.txt")
        assert (
            display_offset_hours(self.FIXTURE / "fvtt-log-fixture.txt", info_start)
            == 2.0
        )

    def test_none_when_the_offset_was_only_guessed(self, tmp_path, monkeypatch):
        """A guessed offset must not become a clock label.

        The whole point of TzResolution.is_reliable is that a guess is
        distinguishable; spending it on wall-clock hours would put a
        confident time on an uncertain number.
        """
        import sources.game_log.fvtt_chat as fvtt
        from core.timeline_window import display_offset_hours

        monkeypatch.setattr(fvtt, "_system_utc_offset_hours", lambda *_a: None)

        chat = tmp_path / "fvtt-log-x.txt"
        chat.write_text(
            "[8/15/2026, 8:00:00 PM] GM\nhi\n---------------------------\n",
            encoding="utf-8",
        )
        info_start = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)
        assert display_offset_hours(chat, info_start) is None


class TestWindowDoesNotRunAway:
    """A whole-campaign chat export must not stretch the window to weeks."""

    REC = datetime(2026, 8, 15, 18, 42, tzinfo=timezone.utc)

    def test_ancient_chat_is_clipped(self):
        ancient = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        window = build_window(
            info_start=self.REC,
            max_track_duration=11879.8,
            chat=(ancient, datetime(2026, 8, 15, 21, 31, tzinfo=timezone.utc)),
            combats=[],
        )
        assert window is not None
        assert window.t0 > ancient
        assert (self.REC - window.t0).total_seconds() == pytest.approx(12 * 3600)

    def test_a_normal_late_start_is_untouched(self):
        """1h47m early is ordinary and must survive the clip intact."""
        chat_first = datetime(2026, 8, 15, 16, 55, 9, tzinfo=timezone.utc)
        window = build_window(
            info_start=self.REC,
            max_track_duration=11879.8,
            chat=(chat_first, datetime(2026, 8, 15, 21, 31, tzinfo=timezone.utc)),
            combats=[],
        )
        assert window.t0 == chat_first

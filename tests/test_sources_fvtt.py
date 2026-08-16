"""Tier 1 — FvttChatSource parse tests with tiny fixture file.

No audio, no ASR models. Must run in <5s.

Uses tests/fixtures/fvtt_chat_tiny.txt as the fixture file.
The info.txt anchor (recording start time) is generated dynamically
via tmp_path to align timestamps deterministically.
"""

import json

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

    def test_guess_tz_offset_when_first_entry_before_rec_start(self):
        """Regression: real Session 6 case — pre-game banter in FVTT chat
        a few minutes before someone hits Record in Craig.

        First entry: ``[4/18/2026, 6:12:13 PM]`` naive local (Serbia, CEST = UTC+2)
        Craig start: ``2026-04-18T16:15:16Z`` UTC
        → first entry corresponds to 16:12:13 UTC, i.e. ~3 min BEFORE rec_start.

        Old heuristic required ``delta >= 0`` and silently picked offset +1
        (CET), shifting the entire chat one hour forward in merged.txt. The
        fix uses ``min |delta|``, so the correct offset +2 (CEST) wins.
        """
        from sources.game_log.fvtt_chat import guess_tz_offset
        first_local = datetime(2026, 4, 18, 18, 12, 13)  # 6:12:13 PM, naive
        rec_start = datetime(2026, 4, 18, 16, 15, 16, tzinfo=timezone.utc)
        entries = [{"datetime": first_local, "speaker": "Бель", "text": "27"}]
        assert guess_tz_offset(entries, rec_start) == 2.0


class TestFindAnchorOffset:
    """Маркер ``craig-start`` в чате как точный якорь UTC offset."""

    def test_returns_none_when_no_marker(self):
        from sources.game_log.fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21), "speaker": "X", "text": "27"},
        ]
        assert find_anchor_offset(entries, rec_start) is None

    def test_picks_exact_offset_from_marker(self):
        """Real Session 7 case (with hypothetical marker added).

        Craig started at 18:09:01Z. If user types ``craig-start`` at the
        moment they hit Record, that message has local time = Craig start
        in user's local tz. For Serbia/CEST that's 20:09:01 local.
        """
        from sources.game_log.fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 9, 1, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 18, 13, 21), "speaker": "P1", "text": "27"},
            {"datetime": datetime(2026, 4, 25, 20, 9, 5), "speaker": "GM", "text": "craig-start"},
            {"datetime": datetime(2026, 4, 25, 20, 11, 0), "speaker": "P1", "text": "let's go"},
        ]
        # Marker at 20:09:05 local vs rec_start at 18:09:01Z → ~2h offset.
        assert find_anchor_offset(entries, rec_start) == 2.0

    def test_marker_variants_all_match(self):
        from sources.game_log.fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        local_at_marker = datetime(2026, 4, 25, 20, 0, 0)  # +2 offset
        for variant in (
            "craig-start",
            "Craig Start",
            "CRAIG_START",
            "[craig-start]",
            "/craig-start",
            "craig start session 7",
        ):
            entries = [{"datetime": local_at_marker, "speaker": "GM", "text": variant}]
            assert find_anchor_offset(entries, rec_start) == 2.0, variant

    def test_unrelated_text_not_matched(self):
        from sources.game_log.fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        entries = [
            {"datetime": datetime(2026, 4, 25, 20, 0, 0), "speaker": "X",
             "text": "starting craig now"},  # word order matters
            {"datetime": datetime(2026, 4, 25, 20, 1, 0), "speaker": "X",
             "text": "Craig is starting"},
        ]
        assert find_anchor_offset(entries, rec_start) is None

    def test_implausible_offset_returns_none(self):
        """Marker that resolves to >14h offset is treated as garbage."""
        from sources.game_log.fvtt_chat import find_anchor_offset
        rec_start = datetime(2026, 4, 25, 18, 0, 0, tzinfo=timezone.utc)
        # Marker dated next day at noon → ~18h offset → implausible.
        entries = [
            {"datetime": datetime(2026, 4, 26, 12, 0, 0), "speaker": "GM",
             "text": "craig-start"},
        ]
        assert find_anchor_offset(entries, rec_start) is None


class TestExtractFallbackOrder:
    """Проверяем, что extract применяет слоёный fallback в правильном порядке."""

    def _write_info(self, tmp_path: Path, start_iso: str) -> Path:
        info = tmp_path / "info.txt"
        info.write_text(f"Start time: {start_iso}\n", encoding="utf-8")
        return info

    def _write_chat(self, tmp_path: Path, body: str) -> Path:
        chat = tmp_path / "fvtt-log.txt"
        chat.write_text(body, encoding="utf-8")
        return chat

    def test_marker_wins_over_system_tz(self, tmp_path, monkeypatch):
        """Якорь в чате имеет приоритет над системной tz."""
        from sources.game_log import fvtt_chat
        # Системная tz возвращает UTC+5, маркер должен дать +2 и победить.
        monkeypatch.setattr(fvtt_chat, "_system_utc_offset_hours", lambda *_a: 5.0)
        info = self._write_info(tmp_path, "2026-04-25T18:00:00Z")
        chat = self._write_chat(
            tmp_path,
            "[4/25/2026, 8:00:05 PM] GM\n"
            "craig-start\n"
            "---------------------------\n"
            "[4/25/2026, 8:01:00 PM] P1\n"
            "hi\n"
            "---------------------------\n",
        )
        src = fvtt_chat.FvttChatSource(chat_log_path=chat, info_file_path=info)
        messages = src.extract(tmp_path)
        # При offset=+2 второе сообщение в 20:01 local = 18:01 UTC = +60s от start.
        assert any(abs(m.at - 60.0) < 1.0 for m in messages)

    def test_system_tz_wins_when_no_marker(self, tmp_path, monkeypatch):
        """Без маркера — берём системную tz, не эвристику."""
        from sources.game_log import fvtt_chat
        # Системная tz +2, эвристика на этих данных дала бы 0 (Session 7).
        monkeypatch.setattr(fvtt_chat, "_system_utc_offset_hours", lambda *_a: 2.0)
        info = self._write_info(tmp_path, "2026-04-25T18:09:01Z")
        chat = self._write_chat(
            tmp_path,
            "[4/25/2026, 6:13:21 PM] P1\n"  # 16:13:21 UTC при +2 — до rec, отбросится
            "hello\n"
            "---------------------------\n"
            "[4/25/2026, 8:10:01 PM] P1\n"  # 18:10:01 UTC при +2 — +60s от rec
            "go\n"
            "---------------------------\n",
        )
        src = fvtt_chat.FvttChatSource(chat_log_path=chat, info_file_path=info)
        messages = src.extract(tmp_path)
        # Если бы выбрали offset 0 (эвристика), 8:10 PM попал бы на +7860s.
        # При корректном +2 — на +60s.
        assert len(messages) == 1
        assert abs(messages[0].at - 60.0) < 1.0

    def test_heuristic_used_when_system_tz_unavailable(self, tmp_path, monkeypatch):
        """Если системная tz недоступна — катимся в эвристику."""
        from sources.game_log import fvtt_chat
        monkeypatch.setattr(fvtt_chat, "_system_utc_offset_hours", lambda *_a: None)
        info = self._write_info(tmp_path, "2026-04-18T16:15:16Z")
        chat = self._write_chat(
            tmp_path,
            "[4/18/2026, 6:12:13 PM] P1\n"
            "27\n"
            "---------------------------\n",
        )
        src = fvtt_chat.FvttChatSource(chat_log_path=chat, info_file_path=info)
        # Эвристика min|delta| на этих данных даёт +2 — первое сообщение
        # окажется до rec_start и отфильтруется (at < 0).
        messages = src.extract(tmp_path)
        assert messages == []

    def test_explicit_tz_offset_overrides_everything(self, tmp_path, monkeypatch):
        """Явный tz_offset в конструкторе побеждает все автодетекты."""
        from sources.game_log import fvtt_chat
        # Системная tz и маркер оба сказали бы +2, но мы передаём +5 явно.
        monkeypatch.setattr(fvtt_chat, "_system_utc_offset_hours", lambda *_a: 2.0)
        info = self._write_info(tmp_path, "2026-04-25T18:00:00Z")
        chat = self._write_chat(
            tmp_path,
            "[4/25/2026, 11:00:00 PM] P1\n"  # 23:00 local
            "hi\n"
            "---------------------------\n",
        )
        src = fvtt_chat.FvttChatSource(
            chat_log_path=chat, info_file_path=info, tz_offset=5.0
        )
        messages = src.extract(tmp_path)
        # 23:00 local при offset=+5 → 18:00 UTC = ровно rec_start (at=0).
        assert len(messages) == 1
        assert abs(messages[0].at) < 1.0


class TestSystemUtcOffsetHours:
    def test_returns_float_or_none(self):
        from sources.game_log.fvtt_chat import _system_utc_offset_hours
        from datetime import datetime, timezone
        at = datetime(2026, 8, 15, 18, 42, 9, tzinfo=timezone.utc)
        result = _system_utc_offset_hours(at)
        # На любом нормальном CI должен вернуть float, не None.
        assert result is None or isinstance(result, float)
        if result is not None:
            assert -14.0 <= result <= 14.0


class TestResolveTzOffset:
    """Direct tests for the ladder itself.

    The steps are covered end-to-end through FvttChatSource above; these
    pin the resolver's own contract — what it returns, and what it feeds
    the steps below it.
    """

    _ENTRIES = [{"datetime": datetime(2026, 8, 15, 20, 0, 0), "speaker": "P1", "text": "hi"}]
    _REC_START = datetime(2026, 8, 15, 18, 0, 0, tzinfo=timezone.utc)

    def test_explicit_zero_is_honoured(self):
        """``explicit=0.0`` must not be mistaken for "not supplied".

        UTC+0 is a real timezone; ``if explicit:`` would silently drop it
        through to autodetection.
        """
        from sources.game_log.fvtt_chat import resolve_tz_offset
        result = resolve_tz_offset(self._ENTRIES, self._REC_START, explicit=0.0)
        assert result.offset_hours == 0.0
        assert result.source == "explicit"
        assert result.is_reliable is True

    def test_empty_entries_short_circuit(self):
        from sources.game_log.fvtt_chat import (
            EMPTY_LOG_RESOLUTION,
            resolve_tz_offset,
        )
        result = resolve_tz_offset([], self._REC_START)
        assert result is EMPTY_LOG_RESOLUTION
        assert result.offset_hours == 0.0
        assert result.is_reliable is False

    def test_system_step_gets_the_session_date_not_today(self, monkeypatch):
        """Regression: the system step must ask about the *recording*.

        ``datetime.now().astimezone()`` answers for today, so a January
        session merged in August picks up the summer offset and the whole
        chat slides by an hour — silently, because ``system`` counts as
        reliable.
        """
        from sources.game_log import fvtt_chat
        seen = []

        def _spy(at):
            seen.append(at)
            return 1.0

        monkeypatch.setattr(fvtt_chat, "_system_utc_offset_hours", _spy)
        winter = datetime(2026, 1, 15, 18, 0, 0, tzinfo=timezone.utc)
        fvtt_chat.resolve_tz_offset(self._ENTRIES, winter)
        assert seen == [winter]

    def test_naive_recording_start_treated_as_utc(self, monkeypatch):
        """Craig always writes UTC; a naive value must not shift anything."""
        from sources.game_log import fvtt_chat
        seen = []
        monkeypatch.setattr(
            fvtt_chat,
            "_system_utc_offset_hours",
            lambda at: seen.append(at) or 2.0,
        )
        naive = datetime(2026, 8, 15, 18, 0, 0)
        fvtt_chat.resolve_tz_offset(self._ENTRIES, naive)
        assert seen == [naive.replace(tzinfo=timezone.utc)]

    def test_offset_recording_start_normalised_to_utc(self):
        """``Start time`` with a +02:00 zone must anchor like the same UTC instant.

        Without normalisation ``find_anchor_offset`` strips the tzinfo and
        reads the wall clock as UTC — two hours of silent drift, the very
        failure this ladder exists to prevent.
        """
        from datetime import timedelta
        from sources.game_log.fvtt_chat import resolve_tz_offset

        entries = [
            {
                "datetime": datetime(2026, 8, 15, 20, 0, 5),
                "speaker": "GM",
                "text": "craig-start",
            }
        ]
        as_utc = datetime(2026, 8, 15, 18, 0, 0, tzinfo=timezone.utc)
        as_offset = datetime(
            2026, 8, 15, 20, 0, 0, tzinfo=timezone(timedelta(hours=2))
        )
        assert resolve_tz_offset(entries, as_utc) == resolve_tz_offset(
            entries, as_offset
        )
        assert resolve_tz_offset(entries, as_offset).source == "anchor"
        assert resolve_tz_offset(entries, as_offset).offset_hours == 2.0


class TestFindCombatOffset:
    """The combat dump as a timezone anchor.

    Бой*.txt writes chat_messages[].timestamp in real UTC while the chat
    export writes browser-local time. The same events in two coordinate
    systems is a free measurement of the offset between them.
    """

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"

    def _entries(self):
        from sources.game_log.fvtt_chat import parse_fvtt_log
        return parse_fvtt_log(self.FIXTURE / "fvtt-log-fixture.txt")

    def test_measures_the_real_session(self):
        from sources.game_log.fvtt_chat import find_combat_offset
        assert find_combat_offset(
            self._entries(), [self.FIXTURE / "combat.json"]
        ) == 2.0

    def test_beats_a_wrong_machine_timezone(self, monkeypatch):
        """This is the rung's whole purpose.

        The system step is right only while the log is exported and
        merged on the same machine. Open the session elsewhere and it
        confidently answers with the wrong zone — the anchor does not
        care where it runs.
        """
        from sources.game_log import fvtt_chat

        monkeypatch.setattr(
            fvtt_chat, "_system_utc_offset_hours", lambda *_a: 9.0
        )
        rec_start = fvtt_chat.parse_info_start_time(self.FIXTURE / "info.txt")
        result = fvtt_chat.resolve_tz_offset(
            self._entries(),
            rec_start,
            combat_paths=[self.FIXTURE / "combat.json"],
        )
        assert result.source == "combat"
        assert result.offset_hours == 2.0
        assert result.is_reliable is True

    def test_marker_still_outranks_the_dump(self, monkeypatch):
        """An explicit craig-start marker is exact; the anchor is measured."""
        from sources.game_log import fvtt_chat

        entries = [
            {
                "datetime": datetime(2026, 8, 15, 21, 42, 9),
                "speaker": "GM",
                "text": "craig-start",
            }
        ] + self._entries()
        rec_start = fvtt_chat.parse_info_start_time(self.FIXTURE / "info.txt")
        result = fvtt_chat.resolve_tz_offset(
            entries, rec_start, combat_paths=[self.FIXTURE / "combat.json"]
        )
        assert result.source == "anchor"
        assert result.offset_hours == 3.0

    def test_none_without_combat_files(self):
        from sources.game_log.fvtt_chat import find_combat_offset
        assert find_combat_offset(self._entries(), []) is None

    def test_none_for_unreadable_file(self, tmp_path):
        """A broken dump must fall through to the next rung, not explode."""
        from sources.game_log.fvtt_chat import find_combat_offset

        junk = tmp_path / "Бой.txt"
        junk.write_text("{not json", encoding="utf-8")
        missing = tmp_path / "nope.txt"
        assert find_combat_offset(self._entries(), [junk, missing]) is None

    def test_none_when_too_few_events(self, tmp_path):
        """Three dice rolls lining up is coincidence, not a measurement."""
        from sources.game_log.fvtt_chat import find_combat_offset

        dump = tmp_path / "Бой.txt"
        dump.write_text(
            json.dumps({
                "rounds": [{
                    "turns": [{
                        "chat_messages": [
                            {"timestamp": f"2026-08-15T17:{m:02d}:00Z"}
                            for m in range(3)
                        ]
                    }]
                }]
            }),
            encoding="utf-8",
        )
        entries = [
            {
                "datetime": datetime(2026, 8, 15, 19, m, 0),
                "speaker": "P1",
                "text": "x",
            }
            for m in range(3)
        ]
        assert find_combat_offset(entries, [dump]) is None

    def test_none_when_no_candidate_stands_out(self, tmp_path):
        """Chat spread evenly across the day matches every offset equally.

        Without the margin check the sort order would hand the tie to
        whichever candidate came first, and the resolver would pass that
        off as a measurement.
        """
        from sources.game_log.fvtt_chat import find_combat_offset

        dump = tmp_path / "Бой.txt"
        dump.write_text(
            json.dumps({
                "rounds": [{
                    "turns": [{
                        "chat_messages": [
                            {"timestamp": f"2026-08-15T{h:02d}:00:00Z"}
                            for h in range(0, 20)
                        ]
                    }]
                }]
            }),
            encoding="utf-8",
        )
        # One chat entry on every whole hour — every candidate offset
        # scores about the same.
        entries = [
            {
                "datetime": datetime(2026, 8, 15, h, 0, 0),
                "speaker": "P1",
                "text": "x",
            }
            for h in range(0, 24)
        ]
        assert find_combat_offset(entries, [dump]) is None

    def test_resolves_a_quarter_hour_zone(self, tmp_path):
        """Nepal is UTC+5:45. Whole-hour candidates would miss it."""
        from sources.game_log.fvtt_chat import find_combat_offset

        stamps = [f"2026-08-15T12:{m:02d}:00Z" for m in range(0, 40, 2)]
        dump = tmp_path / "Бой.txt"
        dump.write_text(
            json.dumps({
                "rounds": [{
                    "turns": [
                        {"chat_messages": [{"timestamp": s} for s in stamps]}
                    ]
                }]
            }),
            encoding="utf-8",
        )
        # Same instants written in UTC+5:45 local time: 12:00Z → 17:45.
        entries = [
            {
                "datetime": datetime(2026, 8, 15, 17, 45 + m)
                if 45 + m < 60
                else datetime(2026, 8, 15, 18, 45 + m - 60),
                "speaker": "P1",
                "text": "x",
            }
            for m in range(0, 40, 2)
        ]
        assert find_combat_offset(entries, [dump]) == 5.75

    def test_none_when_coverage_is_too_thin(self, tmp_path):
        """A single clear peak is not enough — it has to cover the fight.

        Here the winner is unambiguous (nothing else scores at all) so
        the margin check passes, but it accounts for a fifth of the
        encounter. Combat and chat that barely overlap mean the two
        files are not describing the same evening.
        """
        from sources.game_log.fvtt_chat import find_combat_offset

        # Irregular spacing on purpose: an evenly spaced fight lines up
        # with itself under several shifts, and then the margin check
        # fires first and this test proves nothing about the ratio.
        offsets_min = [0, 1, 2, 3, 5, 8, 13, 21, 22, 23, 25, 30, 31, 33, 34, 40]
        dump = tmp_path / "Бой.txt"
        dump.write_text(
            json.dumps({
                "rounds": [{
                    "turns": [{
                        "chat_messages": [
                            {"timestamp": f"2026-08-15T12:{m:02d}:00Z"}
                            for m in offsets_min
                        ]
                    }]
                }]
            }),
            encoding="utf-8",
        )
        # Chat covers only the first five of sixteen events, at +2h.
        entries = [
            {
                "datetime": datetime(2026, 8, 15, 14, m),
                "speaker": "P1",
                "text": "x",
            }
            for m in offsets_min[:5]
        ]
        assert find_combat_offset(entries, [dump]) is None

    @pytest.mark.parametrize(
        "payload",
        [
            {"rounds": {"1": {"turns": []}}},           # array became an object
            {"rounds": "abc"},
            {"rounds": 5},
            {"rounds": [{"turns": ["x"]}]},
            {"rounds": [{"turns": [{"chat_messages": [["a"]]}]}]},
            {"rounds": [{"turns": [{"chat_messages": {"a": 1}}]}]},
            {"rounds": [None]},
            [],                                          # not an object at all
        ],
        ids=[
            "rounds-as-object", "rounds-as-string", "rounds-as-int",
            "turns-of-strings", "messages-of-lists", "messages-as-object",
            "null-round", "top-level-array",
        ],
    )
    def test_structurally_broken_dump_is_skipped(self, tmp_path, payload):
        """Wrong types anywhere must not escape as an exception.

        MergerWorker._parse_chat catches only FileNotFoundError, so
        anything thrown here takes the whole chat merge down with it —
        a malformed combat file must cost the anchor, not the session.
        """
        from sources.game_log.fvtt_chat import find_combat_offset

        dump = tmp_path / "Бой.txt"
        dump.write_text(json.dumps(payload), encoding="utf-8")
        assert find_combat_offset(self._entries(), [dump]) is None

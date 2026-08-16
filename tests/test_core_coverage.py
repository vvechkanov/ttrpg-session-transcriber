"""Tier 1 — core.coverage: what the recording failed to capture.

The merger has always dropped chat and combat events that predate the
recording; it just did it silently. These tests pin the numbers it
should be announcing instead.

Ground truth comes from tests/fixtures/tz_late_start — a real session
where Record was pressed 1h47m late. See its README.

Nothing here may depend on the machine's timezone. Combat times are
rendered with the offset the resolver picked for the chat log, and that
step is pinned via ``pin_system_tz``; an assertion that only holds in
Prague is a broken assertion, not a passing test.
"""

import shutil
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"


def _copy_fixture(session: Path) -> Path:
    session.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "info.txt", session / "info.txt")
    shutil.copy(
        FIXTURE_DIR / "fvtt-log-fixture.txt", session / "fvtt-log-fixture.txt"
    )
    shutil.copy(FIXTURE_DIR / "combat.json", session / "Бой.txt")
    return session


@pytest.fixture()
def late_session(tmp_path, pin_system_tz):
    """The late-start fixture laid out as a session folder."""
    pin_system_tz(2.0)
    return _copy_fixture(tmp_path / "Сессия-17")


class TestAnalyseCoverage:
    def test_counts_match_the_merger(self, late_session):
        from core.coverage import analyse_coverage

        report = analyse_coverage(late_session)
        assert report is not None
        assert report.chat_total == 353
        assert report.chat_dropped == 260
        # 18:55:09 local first entry vs 20:42:09 local recording start.
        assert round(report.late_start_seconds) == 6420

    def test_flags_the_encounter_with_no_audio(self, late_session):
        from core.coverage import analyse_coverage

        report = analyse_coverage(late_session)
        assert report is not None
        assert len(report.combats_missed) == 1
        label, start, end = report.combats_missed[0]
        assert label == "Бой"
        assert (start, end) == ("19:11", "20:18")

    def test_combat_clock_follows_the_resolved_offset(
        self, tmp_path, pin_system_tz
    ):
        """Combat times must not be printed in the machine's zone.

        The session was played at +2. Open the folder on a laptop set to
        UTC and the chat log still reads 7:11 PM — so the banner has to
        as well, or the two disagree on screen. Pinning the ladder to a
        different offset here is exactly that scenario.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(5.0)
        report = analyse_coverage(_copy_fixture(tmp_path / "elsewhere"))
        assert report is not None
        # 17:11:48Z rendered at +5, not at whatever the OS thinks.
        assert report.combats_missed[0][1] == "22:11"

    def test_message_names_the_loss(self, late_session):
        from core.coverage import analyse_coverage

        message = analyse_coverage(late_session).message
        assert "1 ч 47 мин" in message
        assert "260 из 353 сообщений" in message
        assert "Бой 19:11–20:18" in message

    def test_silent_when_recording_covers_everything(
        self, tmp_path, pin_system_tz
    ):
        """A recording started before the chat has nothing to report."""
        from core.coverage import analyse_coverage

        pin_system_tz(0.0)
        session = tmp_path / "ok"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T17:00:00Z\n", encoding="utf-8"
        )
        (session / "fvtt-log-ok.txt").write_text(
            "[8/15/2026, 6:00:00 PM] GM\n"
            "hi\n"
            "---------------------------\n",
            encoding="utf-8",
        )
        report = analyse_coverage(session)
        assert report is not None
        assert report.is_empty
        assert report.message == ""

    def test_pre_game_banter_is_not_a_warning(self, tmp_path, pin_system_tz):
        """One "привет" ten seconds before Record is normal, not a loss.

        chat_dropped is non-zero for any late start at all, however
        small, so the threshold has to be the thing that decides whether
        to speak up.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(0.0)
        session = tmp_path / "banter"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T18:00:10Z\n", encoding="utf-8"
        )
        (session / "fvtt-log-b.txt").write_text(
            "[8/15/2026, 6:00:00 PM] GM\n"          # 10s before Record
            "привет\n"
            "---------------------------\n"
            "[8/15/2026, 6:30:00 PM] GM\n"
            "поехали\n"
            "---------------------------\n",
            encoding="utf-8",
        )
        report = analyse_coverage(session)
        assert report is not None
        assert report.chat_dropped == 1
        assert report.is_empty
        assert report.message == ""

    def test_returns_none_without_info_txt(self, tmp_path):
        from core.coverage import analyse_coverage

        session = tmp_path / "no-info"
        session.mkdir()
        (session / "fvtt-log-x.txt").write_text(
            "[8/15/2026, 6:00:00 PM] GM\nhi\n---------------------------\n",
            encoding="utf-8",
        )
        assert analyse_coverage(session) is None

    def test_returns_none_for_empty_folder(self, tmp_path):
        from core.coverage import analyse_coverage

        session = tmp_path / "empty"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T17:00:00Z\n", encoding="utf-8"
        )
        assert analyse_coverage(session) is None

    def test_unreadable_combat_is_not_reported_as_healthy(self, tmp_path):
        """A broken Бой.txt must not read as "everything is fine".

        There is a combat here and we could not parse it, so we know
        nothing — which is the None case, not the is_empty case.
        """
        from core.coverage import analyse_coverage

        session = tmp_path / "broken-combat"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T17:00:00Z\n", encoding="utf-8"
        )
        (session / "Бой 1.txt").write_text("{not json at all", encoding="utf-8")
        assert analyse_coverage(session) is None

    def test_ongoing_encounter_is_not_reported_as_missed(
        self, tmp_path, pin_system_tz
    ):
        """A fight straddling the start has audio for part of it.

        Calling that "без аудио" would be a lie, so only encounters that
        ended before Record was pressed count.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(0.0)
        session = tmp_path / "straddle"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T18:00:00Z\n", encoding="utf-8"
        )
        (session / "Бой 1.txt").write_text(
            '{"started_at": "2026-08-15T17:30:00Z",'
            ' "ended_at": "2026-08-15T18:30:00Z"}',
            encoding="utf-8",
        )
        report = analyse_coverage(session)
        assert report is not None
        assert report.combats_missed == ()

    def test_finds_info_txt_inside_a_craig_segment(self, tmp_path, pin_system_tz):
        """Restarted recordings keep info.txt in craig-1/, not the root.

        That layout exists *because* the recording was interrupted, so
        it is the last place a late-start warning should go missing.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(2.0)
        session = tmp_path / "multi"
        segment = session / "craig-1"
        segment.mkdir(parents=True)
        shutil.copy(FIXTURE_DIR / "info.txt", segment / "info.txt")
        shutil.copy(
            FIXTURE_DIR / "fvtt-log-fixture.txt", session / "fvtt-log-fixture.txt"
        )
        report = analyse_coverage(session)
        assert report is not None
        assert report.chat_dropped == 260

    def test_uses_the_same_chat_discovery_as_the_merger(
        self, tmp_path, pin_system_tz
    ):
        """A file the merger will not open must not be counted here.

        core.discovery matches ``fvtt-log-*.txt`` (hyphen required);
        core.file_matchers also accepts a bare ``fvtt-log.txt``. Counting
        by the looser rule would promise messages that never reach
        merged.txt.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(2.0)
        session = tmp_path / "bare-name"
        session.mkdir()
        shutil.copy(FIXTURE_DIR / "info.txt", session / "info.txt")
        shutil.copy(
            FIXTURE_DIR / "fvtt-log-fixture.txt", session / "fvtt-log.txt"
        )
        assert analyse_coverage(session) is None


class TestRuDuration:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (6420.0, "1 ч 47 мин"),
            (3600.0, "1 ч"),
            (300.0, "5 мин"),
            (0.0, "0 мин"),
        ],
    )
    def test_formats(self, seconds, expected):
        from core.coverage import _ru_duration

        assert _ru_duration(seconds) == expected

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
        """Combat times must be printed in the offset the chat resolved to.

        Open a session recorded at +2 on a laptop set to UTC and the chat
        log still reads 7:11 PM — so the banner has to as well, or the
        two disagree on screen next to each other.

        The dump here carries too few chat_messages for the combat anchor
        to fire, which is what leaves the ladder on the system rung and
        lets the test pin the resolved offset to something the OS zone
        certainly is not.
        """
        import json

        from core.coverage import analyse_coverage

        pin_system_tz(5.0)
        session = tmp_path / "elsewhere"
        session.mkdir()
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T18:00:00Z\n", encoding="utf-8"
        )
        (session / "fvtt-log-e.txt").write_text(
            "[8/15/2026, 11:30:00 PM] GM\nhi\n---------------------------\n",
            encoding="utf-8",
        )
        (session / "Бой 1.txt").write_text(
            json.dumps({
                "started_at": "2026-08-15T17:11:00Z",
                "ended_at": "2026-08-15T17:40:00Z",
            }),
            encoding="utf-8",
        )

        report = analyse_coverage(session)
        assert report is not None
        # 17:11Z at the resolved +5 → 22:11, whatever the OS zone says.
        assert report.combats_missed[0][1] == "22:11"

    def test_combat_anchor_decides_the_clock_when_available(
        self, late_session, pin_system_tz
    ):
        """The dump, not the machine, must set the offset here.

        The pin is moved to +9 on purpose: with it left at the true +2
        the assertion passes whether or not coverage hands the combat
        paths to the resolver, and the wiring goes untested. At +9 only
        the anchor rung can produce these times.
        """
        from core.coverage import analyse_coverage

        pin_system_tz(9.0)
        report = analyse_coverage(late_session)
        assert report.combats_missed[0][1:] == ("19:11", "20:18")
        assert report.chat_dropped == 260

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
        """Баннер считает ровно тот файл, который откроет мерджер.

        Требование то же, что и раньше, а ожидание — противоположное.
        Прежде обе стороны звали ``find_fvtt_chat_log`` с шаблоном
        ``fvtt-log-*.txt``, и голый ``fvtt-log.txt`` не попадал ни в
        мердж, ни в баннер: совпадение достигалось тем, что молчали
        оба. Теперь искатель один (``detect_fvtt_chat_logs``), файл
        доезжает до ``merged.txt`` — и баннер обязан его посчитать,
        иначе он недосчитает реально слитые сообщения.

        Карточка https://trello.com/c/eyFOj25c .
        """
        from core.coverage import analyse_coverage
        from core.file_matchers import detect_fvtt_chat_logs

        pin_system_tz(2.0)
        session = tmp_path / "bare-name"
        session.mkdir()
        shutil.copy(FIXTURE_DIR / "info.txt", session / "info.txt")
        shutil.copy(
            FIXTURE_DIR / "fvtt-log-fixture.txt", session / "fvtt-log.txt"
        )

        # Мерджер откроет именно этот файл — предпосылка теста, а не
        # его вывод: без неё «баннер посчитал» ничего не значит.
        assert [p.name for p in detect_fvtt_chat_logs(session)] == [
            "fvtt-log.txt"
        ]

        report = analyse_coverage(session)
        assert report is not None
        assert report.chat_total > 0

    def test_counts_the_same_log_the_merger_will_open(
        self, tmp_path, pin_system_tz
    ):
        """С двумя чат-логами баннер обязан считать ПЕРВЫЙ.

        Мерджер берёт ``detect_fvtt_chat_logs(...)[0]``. Если баннер
        возьмёт другой элемент того же набора, он снова разойдётся с
        мерджем — по индексу, а не по шаблону. Прежде этот выбор не
        держал ни один тест: ``[-1]`` проходил насквозь.

        Второй лог сделан заведомо длиннее первого, чтобы ``chat_total``
        у двух файлов различался — иначе тест зеленеет на любом выборе.
        """
        from core.coverage import analyse_coverage
        from core.file_matchers import detect_fvtt_chat_logs

        pin_system_tz(2.0)
        session = tmp_path / "two-logs"
        session.mkdir()
        shutil.copy(FIXTURE_DIR / "info.txt", session / "info.txt")

        first = session / "fvtt-log-a.txt"
        second = session / "fvtt-log-b.txt"
        fixture = (FIXTURE_DIR / "fvtt-log-fixture.txt").read_text(
            encoding="utf-8"
        )
        first.write_text(fixture, encoding="utf-8")
        second.write_text(fixture + fixture, encoding="utf-8")

        found = detect_fvtt_chat_logs(session)
        assert [p.name for p in found] == [first.name, second.name]

        only_first = analyse_coverage(session)
        assert only_first is not None

        # Отдельная сессия с одним лишь первым файлом даёт эталон.
        solo = tmp_path / "one-log"
        solo.mkdir()
        shutil.copy(FIXTURE_DIR / "info.txt", solo / "info.txt")
        (solo / "fvtt-log-a.txt").write_text(fixture, encoding="utf-8")
        solo_report = analyse_coverage(solo)
        assert solo_report is not None

        assert only_first.chat_total == solo_report.chat_total


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

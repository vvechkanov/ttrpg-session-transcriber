"""Tier 1 — CombatAwareRenderer.

The transcript is raw material for an LLM, and a flat list of "line,
line, roll" loses the two facts that make a fight a fight: whose turn
it is and which round we are in. The model then reconstructs those by
guessing, which is to say it invents them.

Outside a fight this renderer must be byte-identical to plain-text —
that is what makes it safe to switch on.
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.events import ChatEvent, GameEvent, SpeechEvent
from renderers import RENDERERS
from renderers.combat_aware import CombatAwareRenderer
from renderers.plain_text import PlainTextRenderer

TZ = timezone(timedelta(hours=2))
START = datetime(2026, 8, 15, 20, 15, 0, tzinfo=TZ)


def _game(at, action, actor="", detail="", minutes=None):
    return GameEvent(
        at=at,
        actor=actor,
        action=action,
        detail=detail,
        wall_clock=START + timedelta(minutes=minutes if minutes is not None else 0),
    )


def _render(events) -> str:
    return CombatAwareRenderer().render(events).decode("utf-8")


def _fight(*, scene="Мост Гоблинов", end=True, summary="rounds=3 | xp=1200"):
    events = [
        _game(0, "encounter_start", detail=scene, minutes=0),
        _game(1, "initiative", "Бель", "init=19, lvl=4, pc", minutes=0),
        _game(1, "initiative", "Киран", "init=28, lvl=4, pc", minutes=0),
        _game(2, "round_start", detail="1", minutes=0),
        _game(3, "turn_start", "Киран", "HP 40/42", minutes=0),
        SpeechEvent(
            start=4.0,
            end=6.0,
            speaker="Лиля (Киран)",
            text="каст Fireball",
            wall_clock=START,
        ),
    ]
    if end:
        events.append(_game(9, "encounter_end", minutes=83))
        events.append(
            _game(9, "encounter_summary_global", detail=summary, minutes=83)
        )
    return events


class TestBlockShape:
    def test_header_carries_the_name_and_the_clock(self):
        out = _render(_fight())
        assert "━━━ БОЙ 1: Мост Гоблинов ━━━  [20:15 – 21:38]" in out

    def test_unnamed_scene_is_not_printed(self):
        """Foundry fills in "Unknown Scene" itself — it means nothing."""
        out = _render(_fight(scene="Unknown Scene"))
        assert "━━━ БОЙ 1 ━━━" in out
        assert "Unknown" not in out

    def test_no_clock_no_span(self):
        """Without a session zone the block still renders, just untimed."""
        events = [
            GameEvent(at=0, actor="", action="encounter_start", detail="Мост"),
            GameEvent(at=9, actor="", action="encounter_end", detail=""),
        ]
        out = _render(events)
        assert "━━━ БОЙ 1: Мост ━━━" in out
        assert "[" not in out.splitlines()[0]

    def test_unfinished_fight_still_closes(self):
        """A dump can end mid-fight: recording stopped, file truncated."""
        out = _render(_fight(end=False))
        assert "БОЙ 1" in out
        assert "Конец боя" in out
        assert "…" in out, "an open-ended span should say so"

    def test_fights_are_numbered(self):
        out = _render(_fight() + _fight(scene="Причал"))
        assert "БОЙ 1: Мост Гоблинов" in out
        assert "БОЙ 2: Причал" in out


class TestOrderInsideTheBlock:
    def test_initiative_is_sorted_high_to_low(self):
        out = _render(_fight())
        assert "Инициатива: Киран (28) → Бель (19)" in out

    def test_turn_heading_names_the_round(self):
        out = _render(_fight())
        assert "Раунд 1 · ход Киран (HP 40/42)" in out

    def test_speech_is_indented_and_timed(self):
        out = _render(_fight())
        assert "  [20:15] Лиля (Киран): каст Fireball" in out

    def test_chat_inside_a_fight_keeps_its_marker(self):
        events = _fight()
        events.insert(
            -2,
            ChatEvent(
                at=5.0,
                channel="ic",
                author="Бель",
                text="27",
                wall_clock=START + timedelta(minutes=1),
            ),
        )
        assert "  [20:16] [ЧАТ] Бель: 27" in _render(events)

    def test_initiative_does_not_repeat_in_the_body(self):
        out = _render(_fight())
        assert out.count("init=28") == 0, "raw initiative detail leaked"


class TestFooter:
    def test_summary_lands_in_the_footer(self):
        """Summaries arrive after encounter_end and must not escape.

        They carry the same timestamp as the end event, so a block that
        closed on the end would spill rounds and XP into plain text.
        """
        out = _render(_fight())
        assert "━━━ Конец боя · 3 раунда · XP +1200 ━━━" in out
        assert "rounds=3" not in out

    def test_per_actor_stats_are_grouped(self):
        events = _fight()
        events.append(
            _game(9, "encounter_summary_actor", "Киран", "pc lvl=4 | DMG=78", minutes=83)
        )
        out = _render(events)
        assert "Итоги по участникам:" in out
        assert "  · Киран: pc lvl=4 | DMG=78" in out

    def test_footer_without_a_summary_is_still_closed(self):
        out = _render(_fight(summary=""))
        assert "━━━ Конец боя ━━━" in out

    @pytest.mark.parametrize(
        "rounds,expected",
        [(1, "1 раунд"), (3, "3 раунда"), (5, "5 раундов"), (11, "11 раундов")],
    )
    def test_round_count_agrees_with_itself(self, rounds, expected):
        out = _render(_fight(summary=f"rounds={rounds}"))
        assert expected in out


class TestOutsideCombat:
    def test_matches_plain_text_exactly(self):
        """Switching renderers must not disturb non-combat transcript."""
        events = [
            SpeechEvent(start=0.0, end=1.0, speaker="Вова", text="привет"),
            ChatEvent(at=2.0, channel="ic", author="Бель", text="27"),
            SpeechEvent(start=3.0, end=4.0, speaker="Настя", text="идём"),
        ]
        assert _render(events) == PlainTextRenderer().render(events).decode("utf-8")

    def test_speech_around_a_fight_stays_outside_it(self):
        before = SpeechEvent(start=0.0, end=1.0, speaker="Вова", text="начинаем")
        after = SpeechEvent(start=99.0, end=100.0, speaker="Вова", text="дальше")
        out = _render([before, *_fight(), after])

        assert out.index("Вова: начинаем") < out.index("БОЙ 1")
        assert out.index("Вова: дальше") > out.index("Конец боя")
        # ...and unindented, because they are not part of the fight.
        assert "\nВова: дальше" in out


def test_registered_under_its_name():
    assert RENDERERS["combat-aware"] is CombatAwareRenderer


class TestNothingIsLost:
    """Completeness beats tidiness — the project's own quality criterion.

    CombatDumpSource builds action names out of the dump
    (``f"effect_{event_type}"``), so any whitelist of known actions is
    guaranteed to fall behind the data. An unknown kind must print,
    not vanish.
    """

    def test_unknown_action_inside_a_fight_still_prints(self):
        events = _fight()
        events.insert(-2, _game(5, "effect_suppressed", "Киран", "Bless"))
        events.insert(-2, _game(6, "death_save", "Бель", "провал"))

        out = _render(events)
        assert "Киран: Bless" in out
        assert "Бель: провал" in out

    def test_every_game_event_survives_the_block(self):
        kinds = [
            "action", "hp_change", "movement", "effect_applied",
            "effect_removed", "effect_changed", "brand_new_kind",
        ]
        events = _fight()
        for i, kind in enumerate(kinds):
            events.insert(-2, _game(5 + i, kind, "Актёр", f"деталь-{i}"))

        out = _render(events)
        for i in range(len(kinds)):
            assert f"деталь-{i}" in out, f"{kinds[i]} disappeared"


class TestMalformedStreams:
    """A dump is someone else's export; it will arrive in odd shapes."""

    def test_empty_stream(self):
        assert _render([]) == ""

    def test_end_without_a_start_is_not_swallowed(self):
        """No block was open, so it falls through to plain-text."""
        out = _render([_game(0, "encounter_end")])
        assert "БОЙ ОКОНЧЕН" in out

    def test_summaries_without_a_fight_still_print(self):
        out = _render([_game(0, "encounter_summary_global", detail="rounds=2")])
        assert out.strip(), "the summary vanished"

    def test_nested_starts_close_the_previous_block(self):
        """Two encounter_starts in a row must yield two blocks."""
        events = [
            _game(0, "encounter_start", detail="Первый"),
            _game(1, "turn_start", "Киран"),
            _game(2, "encounter_start", detail="Второй"),
            _game(3, "turn_start", "Бель"),
            _game(4, "encounter_end"),
        ]
        out = _render(events)
        assert "БОЙ 1: Первый" in out
        assert "БОЙ 2: Второй" in out
        assert "ход Киран" in out
        assert "ход Бель" in out


class TestInitiativeOrder:
    def test_fractional_tiebreaks_are_respected(self):
        """Foundry breaks ties with fractions: 18.14 acts before 18.02.

        Rounding both to 18 sent the order to the alphabet, and the
        printed queue then disagreed with the actual turn order.
        """
        events = [
            _game(0, "encounter_start", detail="Мост"),
            _game(1, "initiative", "Яна", "init=18.14, lvl=4, pc"),
            _game(1, "initiative", "Абрам", "init=18.02, lvl=4, pc"),
            _game(9, "encounter_end"),
        ]
        out = _render(events)
        assert "Инициатива: Яна (18.14) → Абрам (18.02)" in out

    def test_whole_numbers_stay_whole(self):
        out = _render(_fight())
        assert "Киран (28)" in out
        assert "28.0" not in out

"""Tier 1 — the merger, the UI helper and the timeline strip must agree.

Three call sites need the chat log's UTC offset: ``FvttChatSource``
(which actually places the messages), ``core.fvtt_helpers`` (what the
UI shows) and ``core.timeline_window.chat_span`` (where the strip is
drawn). They used to compute it three different ways, so on a session
with a late recording start the screen disagreed with the output file
by two whole hours.

Fixture: ``tests/fixtures/tz_late_start`` — a real session where Craig
started recording 1h47m after the Foundry chat log begins. See its
README for the ground truth.
"""

from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"
CHAT_LOG = FIXTURE_DIR / "fvtt-log-fixture.txt"
INFO = FIXTURE_DIR / "info.txt"
COMBAT = FIXTURE_DIR / "combat.json"

#: The session was played in CEST. Every consumer must land on this.
TRUE_OFFSET = 2.0

#: First chat entry, in the browser's local time: 8/15/2026 6:55:09 PM.
FIRST_ENTRY_LOCAL = datetime(2026, 8, 15, 18, 55, 9)


def test_fixture_present():
    assert CHAT_LOG.exists() and INFO.exists()


def test_heuristic_alone_is_wrong_here():
    """Documents the bug the resolver exists to route around.

    ``guess_tz_offset`` assumes Record was pressed near the start of the
    chat. Here it was pressed 1h47m later, so the heuristic answers 0
    instead of the true +2 — and every consumer that called it directly
    inherited that error.
    """
    from sources.game_log.fvtt_chat import (
        guess_tz_offset,
        parse_fvtt_log,
        parse_info_start_time,
    )

    entries = parse_fvtt_log(CHAT_LOG)
    rec_start = parse_info_start_time(INFO)
    assert guess_tz_offset(entries, rec_start) == 0.0


def test_merger_and_ui_helper_agree(tmp_path, pin_system_tz):
    """Both must land on +2 without help from the machine's own zone.

    The pin is a deliberately wrong +9. Leaving it at the true +2 would
    let the system rung supply the right answer to both sides and the
    test would pass even if the combat dump never reached either one.
    """
    from core.fvtt_helpers import detect_fvtt_tz_offset
    from sources.game_log.fvtt_chat import FvttChatSource

    pin_system_tz(9.0)

    src = FvttChatSource(
        chat_log_path=CHAT_LOG,
        info_file_path=INFO,
        combat_paths=[COMBAT],
    )
    src.extract(tmp_path)

    assert src.last_resolution is not None
    assert src.last_resolution.offset_hours == TRUE_OFFSET
    assert src.last_resolution.source == "combat"
    assert detect_fvtt_tz_offset(CHAT_LOG, INFO) == src.last_resolution.offset_hours


def test_timeline_strip_agrees(pin_system_tz):
    """``chat_span`` must place the strip where the merger put the chat."""
    from core.timeline_window import chat_span, parse_info_start

    pin_system_tz(TRUE_OFFSET)

    info_start = parse_info_start(INFO)
    span = chat_span(CHAT_LOG, info_start)
    assert span is not None

    first_utc, _last_utc = span
    expected = FIRST_ENTRY_LOCAL.replace(tzinfo=timezone.utc)
    actual_offset = (expected - first_utc).total_seconds() / 3600
    assert actual_offset == TRUE_OFFSET


def test_late_start_drops_pre_recording_chat(tmp_path, pin_system_tz):
    """With the correct offset most of this log predates the recording.

    260 of 353 entries land before Craig's start time. That is not a
    parsing failure — it is what actually happened, and commit B makes
    the pipeline say so out loud instead of dropping them in silence.
    """
    from sources.game_log.fvtt_chat import FvttChatSource, parse_fvtt_log

    pin_system_tz(TRUE_OFFSET)

    total = len(parse_fvtt_log(CHAT_LOG))
    kept = len(
        FvttChatSource(
            chat_log_path=CHAT_LOG, info_file_path=INFO, combat_paths=[COMBAT]
        ).extract(tmp_path)
    )
    assert total == 353
    assert kept == 93

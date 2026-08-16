"""Tier 1 — ScriptMerger unit tests: 8 cases from architect spec.

No audio, no models, no subprocess. Must run in <5s.
"""

import pytest
from domain.annotations import ChatMessage, SpeechSegment
from domain.events import ChatEvent, SpeechEvent
from datetime import datetime, timedelta, timezone

from domain.timeline import Timeline
from mergers.script_merger import ScriptMerger


def _tl(speech=None, chat=None) -> Timeline:
    """Helper to build a Timeline with empty defaults."""
    return Timeline(
        speech=speech or [],
        emotions=[],
        chat=chat or [],
        game_log=[],
    )


def _seg(start, end, speaker, text, confidence=None) -> SpeechSegment:
    return SpeechSegment(start=start, end=end, speaker=speaker, text=text, confidence=confidence)


def _msg(at, author, text, channel="ic") -> ChatMessage:
    return ChatMessage(at=at, channel=channel, author=author, text=text)


class TestScriptMergerEmptyInput:
    """Case 1 — empty timeline returns empty list."""

    def test_empty_timeline(self):
        merger = ScriptMerger()
        result = merger.merge(_tl())
        assert result == []

    def test_empty_speech_only(self):
        merger = ScriptMerger()
        result = merger.merge(_tl(speech=[]))
        assert result == []


class TestScriptMergerSingleSegment:
    """Case 2 — single speech segment becomes one SpeechEvent unchanged."""

    def test_single_segment(self):
        merger = ScriptMerger()
        tl = _tl(speech=[_seg(0.0, 2.0, "GM", "Hello world")])
        result = merger.merge(tl)
        assert len(result) == 1
        ev = result[0]
        assert isinstance(ev, SpeechEvent)
        assert ev.speaker == "GM"
        assert ev.text == "Hello world"
        assert ev.start == pytest.approx(0.0)
        assert ev.end == pytest.approx(2.0)


class TestScriptMergerSameSpeakerGlue:
    """Case 3 — same speaker within gap_sec gets glued into one event."""

    def test_glue_two_segments_within_gap(self):
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, "GM", "First part"),
            _seg(1.5, 3.0, "GM", "second part"),  # gap = 0.5s <= 1.0
        ])
        result = merger.merge(tl)
        assert len(result) == 1
        ev = result[0]
        assert ev.speaker == "GM"
        assert "First part" in ev.text
        assert "second part" in ev.text
        assert ev.start == pytest.approx(0.0)
        assert ev.end == pytest.approx(3.0)

    def test_glue_three_consecutive(self):
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, "GM", "A"),
            _seg(1.2, 2.0, "GM", "B"),
            _seg(2.5, 3.5, "GM", "C"),
        ])
        result = merger.merge(tl)
        assert len(result) == 1
        assert result[0].text == "A B C"


class TestScriptMergerDifferentSpeakerNoGlue:
    """Case 4 — different speakers are NOT glued even with small gap."""

    def test_different_speakers_not_glued(self):
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, "GM", "My line"),
            _seg(1.2, 2.5, "Player", "Their line"),  # gap 0.2s but different speaker
        ])
        result = merger.merge(tl)
        assert len(result) == 2
        speakers = [ev.speaker for ev in result]
        assert "GM" in speakers
        assert "Player" in speakers

    def test_large_gap_same_speaker_not_glued(self):
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, "GM", "First"),
            _seg(3.0, 4.0, "GM", "Second"),  # gap = 2.0s > 1.0
        ])
        result = merger.merge(tl)
        assert len(result) == 2


class TestScriptMergerSpeechChatInterleave:
    """Case 5 — speech and chat events are interleaved by time."""

    def test_chat_interleaved_between_speech(self):
        merger = ScriptMerger()
        tl = _tl(
            speech=[
                _seg(0.0, 1.0, "GM", "Welcome"),
                _seg(5.0, 6.0, "Player", "Thanks"),
            ],
            chat=[_msg(3.0, "Player", "Excited!")],
        )
        result = merger.merge(tl)
        assert len(result) == 3
        # Order: speech@0, chat@3, speech@5
        assert isinstance(result[0], SpeechEvent)
        assert isinstance(result[1], ChatEvent)
        assert isinstance(result[2], SpeechEvent)

    def test_chat_before_speech_comes_first(self):
        merger = ScriptMerger()
        tl = _tl(
            speech=[_seg(10.0, 11.0, "GM", "Late speech")],
            chat=[_msg(1.0, "Player", "Early chat")],
        )
        result = merger.merge(tl)
        assert isinstance(result[0], ChatEvent)
        assert isinstance(result[1], SpeechEvent)


class TestScriptMergerTiebreaker:
    """Case 6 — same timestamp: speech (sort key 0) before chat (sort key 1)."""

    def test_speech_before_chat_at_same_time(self):
        merger = ScriptMerger()
        tl = _tl(
            speech=[_seg(5.0, 6.0, "GM", "Simultaneous speech")],
            chat=[_msg(5.0, "Player", "Simultaneous chat")],
        )
        result = merger.merge(tl)
        assert len(result) == 2
        assert isinstance(result[0], SpeechEvent)
        assert isinstance(result[1], ChatEvent)


class TestScriptMergerUnknownChatChannel:
    """Case 7 — unknown chat channel is coerced to 'ic'."""

    def test_unknown_channel_becomes_ic(self):
        merger = ScriptMerger()
        tl = _tl(chat=[_msg(1.0, "Player", "text", channel="unknown-channel")])
        result = merger.merge(tl)
        assert len(result) == 1
        ev = result[0]
        assert isinstance(ev, ChatEvent)
        assert ev.channel == "ic"

    def test_ooc_channel_preserved(self):
        merger = ScriptMerger()
        tl = _tl(chat=[_msg(1.0, "Player", "brb", channel="ooc")])
        result = merger.merge(tl)
        assert result[0].channel == "ooc"


class TestScriptMergerNoneSpeaker:
    """Case 8 — segment with speaker=None becomes SpeechEvent with speaker=''."""

    def test_none_speaker_becomes_empty_string(self):
        merger = ScriptMerger()
        tl = _tl(speech=[_seg(0.0, 1.0, None, "Unknown voice")])
        result = merger.merge(tl)
        assert len(result) == 1
        ev = result[0]
        assert isinstance(ev, SpeechEvent)
        assert ev.speaker == ""

    def test_none_speaker_no_glue_with_named_speaker(self):
        """None-speaker segments are NOT glued to any other speaker."""
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, None, "unknown"),
            _seg(1.2, 2.0, "GM", "named"),   # gap 0.2s but None != "GM"
        ])
        result = merger.merge(tl)
        assert len(result) == 2

    def test_two_none_speaker_segments_not_glued(self):
        """None speaker segments are NOT glued together (speaker is None)."""
        merger = ScriptMerger(gap_sec=1.0)
        tl = _tl(speech=[
            _seg(0.0, 1.0, None, "first"),
            _seg(1.2, 2.0, None, "second"),  # both None, gap small
        ])
        result = merger.merge(tl)
        # Both have speaker=None, gluing condition requires speaker is not None
        assert len(result) == 2


class TestMergeGapSuitsVadBackends:
    """The default gap must glue VAD-sliced monologues back together.

    Whisper does not trim silence, so its consecutive same-speaker
    segments sit back to back (median gap 0.06 s on a real session) and
    almost anything glues them. A VAD-sliced backend cuts the silence
    out, so the gap between segments is the real pause in speech
    (median 1.41 s). At the old 1.0 s threshold a long monologue stayed
    shattered into separate turns and the transcript read as though one
    speaker had been given the floor repeatedly.
    """

    def test_default_glues_a_typical_vad_pause(self):
        from mergers.script_merger import DEFAULT_MERGE_GAP_SEC

        # Median same-speaker pause measured on session 15.
        assert DEFAULT_MERGE_GAP_SEC > 1.41

    def test_default_does_not_glue_across_a_real_turn_boundary(self):
        from mergers.script_merger import DEFAULT_MERGE_GAP_SEC

        # Beyond ~3 s the numbers keep improving only because genuine
        # turn boundaries get swallowed, which hides interleaving.
        assert DEFAULT_MERGE_GAP_SEC <= 2.5

    def test_monologue_fragments_become_one_turn(self):
        """Four fragments of one monologue, pauses just over a second."""

        merger = ScriptMerger()
        result = merger.merge(_tl(speech=[
            _seg(0.0, 4.0, "GM", "и вот вы выходите на площадь"),
            _seg(5.4, 9.0, "GM", "посреди неё стоит фонтан"),
            _seg(10.5, 14.0, "GM", "вода в нём почему-то чёрная"),
            _seg(15.4, 18.0, "GM", "что делаете"),
        ]))

        assert len(result) == 1, [e.text for e in result]
        assert result[0].text.startswith("и вот вы выходите")
        assert result[0].text.endswith("что делаете")

    def test_a_real_exchange_still_interleaves(self):
        """Gluing must not swallow the other speaker's reply."""

        merger = ScriptMerger()
        result = merger.merge(_tl(speech=[
            _seg(0.0, 2.0, "GM", "что делаете"),
            _seg(2.5, 4.0, "Alice", "иду к фонтану"),
            _seg(4.5, 6.0, "GM", "ты подходишь"),
        ]))

        assert [e.speaker for e in result] == ["GM", "Alice", "GM"]


class TestWallClockStamping:
    """Absolute time reaches events without touching the render contract.

    A renderer that wants to print "20:15" needs the recording start and
    the session's timezone, and `render(events) -> bytes` carries
    neither. Rather than widen that signature for every renderer, the
    merger — the one place where relative offsets and the recording
    start meet — stamps each event.
    """

    #: Session 17: Record pressed at 20:42:09 local, which is +02:00.
    REC_START = datetime(
        2026, 8, 15, 20, 42, 9, tzinfo=timezone(timedelta(hours=2))
    )

    def _timeline(self, recording_start):
        from domain.annotations import ChatMessage, GameLogEntry, SpeechSegment

        return Timeline(
            speech=[SpeechSegment(start=60.0, end=62.0, speaker="Вова", text="да")],
            emotions=[],
            chat=[ChatMessage(at=120.0, channel="ic", author="Бель", text="27")],
            game_log=[
                GameLogEntry(at=180.0, actor="Киран", action="turn_start", detail="")
            ],
            recording_start=recording_start,
        )

    def test_every_event_kind_gets_stamped(self):
        events = ScriptMerger().merge(self._timeline(self.REC_START))
        assert events, "nothing to check"
        assert all(e.wall_clock is not None for e in events)

    def test_stamp_reads_as_the_session_clock(self):
        """The point of the exercise: strftime gives the players' hours."""
        events = ScriptMerger().merge(self._timeline(self.REC_START))
        stamps = {e.wall_clock.strftime("%H:%M") for e in events}
        # +60 s, +120 s, +180 s past 20:42:09.
        assert stamps == {"20:43", "20:44", "20:45"}

    def test_speech_is_stamped_from_its_start(self):
        from domain.events import SpeechEvent

        events = ScriptMerger().merge(self._timeline(self.REC_START))
        speech = next(e for e in events if isinstance(e, SpeechEvent))
        assert speech.wall_clock == self.REC_START + timedelta(seconds=speech.start)

    def test_no_recording_start_leaves_events_unstamped(self):
        """Unknown zone must produce no time, not a UTC time mislabelled."""
        events = ScriptMerger().merge(self._timeline(None))
        assert events
        assert all(e.wall_clock is None for e in events)

    def test_stamp_keeps_the_instant_not_just_the_digits(self):
        """It stays an aware datetime — a real moment, comparable."""
        events = ScriptMerger().merge(self._timeline(self.REC_START))
        first = min(e.wall_clock for e in events)
        assert first.tzinfo is not None
        assert first.utcoffset() == timedelta(hours=2)

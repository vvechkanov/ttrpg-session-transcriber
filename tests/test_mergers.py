"""Tier 1 — ScriptMerger unit tests: 8 cases from architect spec.

No audio, no models, no subprocess. Must run in <5s.
"""

import pytest
from domain.annotations import ChatMessage, SpeechSegment
from domain.events import ChatEvent, SpeechEvent
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

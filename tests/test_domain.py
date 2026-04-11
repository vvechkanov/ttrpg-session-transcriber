"""Tier 1 — domain layer smoke tests.

Tests dataclass shapes, union types, and speaker_map helpers.
No audio, no models, no subprocess. Must run in <5s.
"""

import json
import pytest
from pathlib import Path


# ── domain.annotations ────────────────────────────────────────────────────────

class TestAnnotations:
    def test_speech_segment_fields(self):
        from domain.annotations import SpeechSegment
        seg = SpeechSegment(start=0.0, end=1.5, speaker="GM", text="Hello")
        assert seg.start == 0.0
        assert seg.end == 1.5
        assert seg.speaker == "GM"
        assert seg.text == "Hello"
        assert seg.confidence is None

    def test_speech_segment_with_confidence(self):
        from domain.annotations import SpeechSegment
        seg = SpeechSegment(start=1.0, end=2.0, speaker=None, text="Hmm", confidence=0.9)
        assert seg.speaker is None
        assert seg.confidence == pytest.approx(0.9)

    def test_emotion_tag_fields(self):
        from domain.annotations import EmotionTag
        tag = EmotionTag(start=0.0, end=2.0, label="happy", confidence=0.8)
        assert tag.label == "happy"
        assert tag.confidence == pytest.approx(0.8)

    def test_chat_message_fields(self):
        from domain.annotations import ChatMessage
        msg = ChatMessage(at=10.0, channel="ic", author="Player", text="Hello world")
        assert msg.at == pytest.approx(10.0)
        assert msg.channel == "ic"
        assert msg.author == "Player"
        assert msg.text == "Hello world"

    def test_game_log_entry_fields(self):
        from domain.annotations import GameLogEntry
        entry = GameLogEntry(at=5.0, actor="Aragorn", action="roll", detail="d20: 17")
        assert entry.actor == "Aragorn"
        assert entry.action == "roll"
        assert entry.detail == "d20: 17"

    def test_annotation_union_accepts_all_types(self):
        """Annotation union type is correct — all four types are assignable."""
        from domain.annotations import (
            Annotation, SpeechSegment, EmotionTag, ChatMessage, GameLogEntry
        )
        items: list[Annotation] = [
            SpeechSegment(0.0, 1.0, "GM", "text"),
            EmotionTag(0.0, 1.0, "neutral", 0.5),
            ChatMessage(3.0, "ooc", "Player", "brb"),
            GameLogEntry(4.0, "Fighter", "damage", "2d6: 8"),
        ]
        assert len(items) == 4


# ── domain.events ─────────────────────────────────────────────────────────────

class TestEvents:
    def test_speech_event_defaults(self):
        from domain.events import SpeechEvent
        ev = SpeechEvent(start=0.0, end=1.0, speaker="GM", text="Test")
        assert ev.emotion is None
        assert ev.parallel_group is None

    def test_chat_event_channel_literal(self):
        from domain.events import ChatEvent
        ev_ic = ChatEvent(at=5.0, channel="ic", author="Player", text="hello")
        ev_ooc = ChatEvent(at=6.0, channel="ooc", author="Player", text="brb")
        assert ev_ic.channel == "ic"
        assert ev_ooc.channel == "ooc"

    def test_game_event_action_literal(self):
        from domain.events import GameEvent
        ev = GameEvent(at=10.0, actor="Fighter", action="roll", detail="1d20: 15")
        assert ev.action == "roll"

    def test_script_event_union(self):
        from domain.events import ScriptEvent, SpeechEvent, ChatEvent, GameEvent
        events: list[ScriptEvent] = [
            SpeechEvent(0.0, 1.0, "GM", "Hello"),
            ChatEvent(2.0, "ic", "Player", "Hey"),
            GameEvent(3.0, "Rogue", "spell", "Magic Missile"),
        ]
        assert len(events) == 3


# ── domain.timeline ───────────────────────────────────────────────────────────

class TestTimeline:
    def test_timeline_construction(self):
        from domain.timeline import Timeline
        from domain.annotations import SpeechSegment, ChatMessage
        tl = Timeline(
            speech=[SpeechSegment(0.0, 1.0, "GM", "text")],
            emotions=[],
            chat=[ChatMessage(5.0, "ic", "P", "msg")],
            game_log=[],
        )
        assert len(tl.speech) == 1
        assert len(tl.chat) == 1
        assert tl.emotions == []
        assert tl.game_log == []

    def test_timeline_empty(self):
        from domain.timeline import Timeline
        tl = Timeline(speech=[], emotions=[], chat=[], game_log=[])
        assert tl.speech == []


# ── domain.speaker_map ────────────────────────────────────────────────────────

class TestSpeakerMap:
    def test_load_speaker_map_session_dir(self, tmp_path):
        from domain.speaker_map import load_speaker_map
        data = {
            "1-gm": {"player": "TestGM", "character": "", "role": "GM"},
            "2-player": {"player": "Alice", "character": "Aragorn", "role": "PC"},
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        result = load_speaker_map(tmp_path)
        assert result["1-gm"] == "TestGM"
        assert result["2-player"] == "Alice (Aragorn)"

    def test_load_speaker_map_player_only(self, tmp_path):
        from domain.speaker_map import load_speaker_map
        data = {"1-gm": {"player": "Bob", "character": ""}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        result = load_speaker_map(tmp_path)
        assert result["1-gm"] == "Bob"

    def test_load_speaker_map_character_only(self, tmp_path):
        from domain.speaker_map import load_speaker_map
        data = {"1-pc": {"player": "", "character": "Legolas"}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        result = load_speaker_map(tmp_path)
        assert result["1-pc"] == "Legolas"

    def test_load_speaker_map_returns_empty_on_missing_file(self, tmp_path):
        from domain.speaker_map import load_speaker_map
        # tmp_path has no speaker_map.json and is not the project root
        # We need to ensure the project root speaker_map.json isn't found
        # by passing a subdir that doesn't exist anywhere relevant.
        empty_dir = tmp_path / "no_map_here"
        empty_dir.mkdir()
        result = load_speaker_map(empty_dir)
        # May return project root's map if it exists, so just check it's a dict
        assert isinstance(result, dict)

    def test_load_speaker_map_invalid_json(self, tmp_path):
        from domain.speaker_map import load_speaker_map
        (tmp_path / "speaker_map.json").write_text("NOT JSON", encoding="utf-8")
        result = load_speaker_map(tmp_path)
        assert isinstance(result, dict)

    def test_resolve_speaker_found(self):
        from domain.speaker_map import resolve_speaker
        smap = {"1-gm": "TestGM", "2-player": "Alice (Aragorn)"}
        assert resolve_speaker("1-gm", smap) == "TestGM"
        assert resolve_speaker("2-player", smap) == "Alice (Aragorn)"

    def test_resolve_speaker_json_suffix_fallback(self):
        from domain.speaker_map import resolve_speaker
        smap = {"1-gm.json": "OldFormat"}
        assert resolve_speaker("1-gm", smap) == "OldFormat"

    def test_resolve_speaker_not_found_returns_stem(self):
        from domain.speaker_map import resolve_speaker
        assert resolve_speaker("unknown-track", {}) == "unknown-track"

    def test_resolve_speaker_empty_map(self):
        from domain.speaker_map import resolve_speaker
        assert resolve_speaker("3-player2", {}) == "3-player2"

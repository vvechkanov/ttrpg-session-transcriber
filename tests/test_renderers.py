"""Tier 1 — PlainTextRenderer byte-for-byte output tests.

No audio, no models. Must run in <5s.
"""

import pytest
from domain.events import ChatEvent, GameEvent, SpeechEvent
from renderers.plain_text import PlainTextRenderer


def _speech(speaker, text, start=0.0, end=1.0) -> SpeechEvent:
    return SpeechEvent(start=start, end=end, speaker=speaker, text=text)


def _chat(author, text, channel="ic", at=0.0) -> ChatEvent:
    return ChatEvent(at=at, channel=channel, author=author, text=text)


class TestPlainTextRendererSpeechLine:
    """Speech line format: '<Speaker>: <text>\n\n'"""

    def test_single_speech_event(self):
        r = PlainTextRenderer()
        result = r.render([_speech("GM", "Hello world")])
        assert result == b"GM: Hello world\n\n"

    def test_speech_event_unicode(self):
        r = PlainTextRenderer()
        result = r.render([_speech("TestGM", "\u0425\u043e\u0440\u043e\u0448\u043e")])
        assert result == "TestGM: \u0425\u043e\u0440\u043e\u0448\u043e\n\n".encode("utf-8")

    def test_speaker_with_parentheses(self):
        r = PlainTextRenderer()
        result = r.render([_speech("Alice (Aragorn)", "text")])
        assert result == b"Alice (Aragorn): text\n\n"

    def test_empty_speaker(self):
        r = PlainTextRenderer()
        result = r.render([_speech("", "some text")])
        assert result == b": some text\n\n"


class TestPlainTextRendererChatLine:
    """Chat line format: '[ЧАТ] <author>: <text>\n\n'"""

    def test_single_chat_event(self):
        r = PlainTextRenderer()
        result = r.render([_chat("Player1", "Hello!")])
        assert result == "[ЧАТ] Player1: Hello!\n\n".encode("utf-8")

    def test_chat_ooc_channel(self):
        r = PlainTextRenderer()
        result = r.render([_chat("Player1", "brb", channel="ooc")])
        # Channel does not affect format — both ic and ooc use [ЧАТ] prefix
        assert result == "[ЧАТ] Player1: brb\n\n".encode("utf-8")


class TestPlainTextRendererEmptyList:
    """Empty events list returns empty bytes."""

    def test_empty_events(self):
        r = PlainTextRenderer()
        result = r.render([])
        assert result == b""

    def test_result_is_bytes(self):
        r = PlainTextRenderer()
        result = r.render([])
        assert isinstance(result, bytes)


class TestPlainTextRendererMixed:
    """Mixed speech + chat events — double newline separates each."""

    def test_speech_then_chat(self):
        r = PlainTextRenderer()
        events = [
            _speech("GM", "Opening", start=0.0, end=1.0),
            _chat("Player", "Excited!", at=3.0),
        ]
        result = r.render(events).decode("utf-8")
        lines = result.split("\n\n")
        # After split on \n\n we get: ['GM: Opening', '[ЧАТ] Player: Excited!', '']
        assert lines[0] == "GM: Opening"
        assert lines[1] == "[ЧАТ] Player: Excited!"
        assert lines[2] == ""

    def test_multiple_speech_events(self):
        r = PlainTextRenderer()
        events = [
            _speech("GM", "First", start=0.0),
            _speech("Player", "Second", start=2.0),
            _speech("GM", "Third", start=4.0),
        ]
        result = r.render(events).decode("utf-8")
        assert result == "GM: First\n\nPlayer: Second\n\nGM: Third\n\n"

    def test_game_event_rendered_via_generic_fallback(self):
        """Unknown GameEvent.action falls through to ``[ИГРА] ...`` line."""
        r = PlainTextRenderer()
        events = [
            _speech("GM", "text"),
            GameEvent(at=1.0, actor="Fighter", action="roll", detail="d20: 15"),
            _chat("Player", "nice roll"),
        ]
        result = r.render(events).decode("utf-8")
        assert "GM: text" in result
        assert "[ЧАТ] Player: nice roll" in result
        # Generic fallback line for unknown action vocabulary.
        assert "[ИГРА] roll — Fighter — d20: 15" in result

    def test_output_is_utf8_bytes(self):
        r = PlainTextRenderer()
        events = [_speech("Тест", "\u0422\u0435\u043a\u0441\u0442")]
        result = r.render(events)
        assert isinstance(result, bytes)
        decoded = result.decode("utf-8")
        assert "\u0422\u0435\u043a\u0441\u0442" in decoded

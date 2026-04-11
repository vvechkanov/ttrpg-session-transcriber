"""Таймлайн одной сессии: четыре параллельных потока аннотаций."""

from dataclasses import dataclass

from domain.annotations import ChatMessage, EmotionTag, GameLogEntry, SpeechSegment


@dataclass
class Timeline:
    """Контейнер сырых аннотаций сессии по четырём типам потоков."""

    speech: list[SpeechSegment]
    emotions: list[EmotionTag]
    chat: list[ChatMessage]
    game_log: list[GameLogEntry]

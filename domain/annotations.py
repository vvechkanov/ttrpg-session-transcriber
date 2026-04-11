"""Сырые аннотации от источников: речь, эмоции, чат, game log."""

from dataclasses import dataclass


@dataclass
class SpeechSegment:
    """Сегмент речи одного говорящего."""

    start: float
    end: float
    speaker: str | None
    text: str
    confidence: float | None = None


@dataclass
class EmotionTag:
    """Эмоциональная метка на временном интервале."""

    start: float
    end: float
    label: str
    confidence: float


@dataclass
class ChatMessage:
    """Сообщение из чата (Discord/FVTT)."""

    at: float
    channel: str  # "ic" | "ooc" и возможные расширения — open set
    author: str
    text: str


@dataclass
class GameLogEntry:
    """Запись из игрового лога (броски, урон, заклинания)."""

    at: float
    actor: str
    action: str  # "roll" | "damage" | "spell" и расширения — open set
    detail: str


Annotation = SpeechSegment | EmotionTag | ChatMessage | GameLogEntry

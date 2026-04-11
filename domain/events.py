"""Нормализованные события после merger-а, готовые для renderer-а."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class SpeechEvent:
    """Речь говорящего, возможно с эмоцией и маркером параллельной группы."""

    start: float
    end: float
    speaker: str
    text: str
    emotion: str | None = None
    parallel_group: int | None = None


@dataclass
class ChatEvent:
    """Сообщение чата с закрытым набором каналов."""

    at: float
    channel: Literal["ic", "ooc"]
    author: str
    text: str


@dataclass
class GameEvent:
    """Игровое событие с закрытым набором действий."""

    at: float
    actor: str
    action: Literal["roll", "damage", "spell"]
    detail: str


ScriptEvent = SpeechEvent | ChatEvent | GameEvent

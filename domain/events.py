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
    """Игровое событие.

    ``action`` — открытое множество (mirror ``GameLogEntry.action``):
    конкретные источники определяют свой вокабуляр. Сейчас в ходу:

    * ``"encounter_start"`` / ``"encounter_end"`` — начало/конец боя
      (от ``CombatDumpSource``).
    * ``"round_start"`` — начало раунда инициативы.
    * ``"turn_start"`` — ход персонажа.
    * ``"roll"`` / ``"damage"`` / ``"spell"`` — индивидуальные действия
      (зарезервированы под будущие парсеры).
    """

    at: float
    actor: str
    action: str
    detail: str


ScriptEvent = SpeechEvent | ChatEvent | GameEvent

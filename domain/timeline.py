"""Таймлайн одной сессии: четыре параллельных потока аннотаций."""

from dataclasses import dataclass
from datetime import datetime

from domain.annotations import ChatMessage, EmotionTag, GameLogEntry, SpeechSegment


@dataclass
class Timeline:
    """Контейнер сырых аннотаций сессии по четырём типам потоков."""

    speech: list[SpeechSegment]
    emotions: list[EmotionTag]
    chat: list[ChatMessage]
    game_log: list[GameLogEntry]

    #: Момент старта записи — единственная точка, связывающая
    #: относительные ``at`` аннотаций с настоящим временем.
    #:
    #: Aware-datetime, но в **зоне самой сессии**, а не в UTC: это
    #: по-прежнему точный момент, и при этом ``.strftime("%H:%M")``
    #: сразу даёт те часы, которые игрок видит в фаундривском логе.
    #: Хранить UTC значило бы обязать каждого рендерера отдельно
    #: узнавать зону — а узнать её неоткуда, кроме как разобрав чат.
    #:
    #: ``None`` — зона неизвестна или лишь угадана. Тогда абсолютного
    #: времени просто нет, и рендерер обязан обойтись без него, а не
    #: подставить UTC под видом местного.
    recording_start: datetime | None = None

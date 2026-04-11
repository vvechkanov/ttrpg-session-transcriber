"""Абстрактный Source — извлечение аннотаций из session_dir."""

from abc import ABC, abstractmethod
from pathlib import Path

from domain.annotations import Annotation


class Source(ABC):
    """Абстрактный источник аннотаций.

    Каждый наследник реализует ``extract(session_dir)`` и возвращает плоский
    список ``Annotation`` (``SpeechSegment``/``EmotionTag``/``ChatMessage``/
    ``GameLogEntry``) — тип зависит от конкретного источника.
    """

    name: str

    @abstractmethod
    def extract(self, session_dir: Path) -> list[Annotation]:
        """Извлечь аннотации из ``session_dir``."""
        ...

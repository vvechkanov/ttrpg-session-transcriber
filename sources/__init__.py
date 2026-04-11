"""Sources layer: извлечение Annotation из session_dir.

Импортирует только ``domain``, stdlib и third-party ASR библиотеки
(faster-whisper, whisperx CLI). Никаких зависимостей на ``core``,
``mergers``, ``renderers``, ``ui``.

Registry — hardcoded dict-ы, без pip entry_points и без самописного
plugin discovery (ADR-11). Тяжёлые зависимости (faster-whisper, whisperx)
импортируются лениво внутри ``Source.extract()``, поэтому импорт
``sources`` не падает на машинах без CUDA/моделей.
"""

from sources.base import Source
from sources.game_log.fvtt_chat import FvttChatSource
from sources.speech.faster_whisper import FasterWhisperSource
from sources.speech.gigaam import GigaAMSource
from sources.speech.whisperx import WhisperXSource

SPEECH_SOURCES: dict[str, type[Source]] = {
    "faster-whisper": FasterWhisperSource,
    "whisperx": WhisperXSource,
    "gigaam": GigaAMSource,
}

GAME_LOG_SOURCES: dict[str, type[Source]] = {
    "fvtt-chat": FvttChatSource,
}


def get_speech_source(name: str) -> type[Source]:
    """Вернуть класс speech source по имени из ``SPEECH_SOURCES``."""
    if name not in SPEECH_SOURCES:
        raise ValueError(
            f"Unknown speech source: {name!r}. Available: {list(SPEECH_SOURCES)}"
        )
    return SPEECH_SOURCES[name]


def list_speech_sources() -> list[str]:
    """Вернуть список зарегистрированных speech source names."""
    return list(SPEECH_SOURCES)


def get_game_log_source(name: str) -> type[Source]:
    """Вернуть класс game log source по имени из ``GAME_LOG_SOURCES``."""
    if name not in GAME_LOG_SOURCES:
        raise ValueError(
            f"Unknown game log source: {name!r}. Available: {list(GAME_LOG_SOURCES)}"
        )
    return GAME_LOG_SOURCES[name]

"""FVTT chat helper functions for the UI layer.

Тонкий shim поверх ``sources.game_log.fvtt_chat`` для случаев, когда
UI хочет узнать таймзону чат-лога ДО запуска pipeline — например чтобы
показать её на экране сессии.

Всё тяжёлое (fvtt lexer, лесенка резолвера) делегируется в ``sources``;
здесь только обвязка с публичным API.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sources.game_log.fvtt_chat import TzResolution


def detect_fvtt_tz_offset(chat_log_path: Path, info_path: Path) -> float:
    """Автодетект UTC offset чат-лога — то же число, что возьмёт мерджер.

    Возвращает offset в часах (может быть отрицательным). Бросает
    ``ValueError`` если ``info.txt`` не содержит ``Start time:`` строку.
    Если chat log пуст — возвращает ``0.0``.

    Идёт через ``resolve_tz_offset``, а не через ``guess_tz_offset``
    напрямую: раньше UI показывал результат голой эвристики, мерджер
    брал системную таймзону, и на сессии с поздним стартом записи они
    расходились на два часа. Нужны подробности (какая ступень лесенки
    сработала) — зовите :func:`describe_fvtt_tz`.
    """
    return describe_fvtt_tz(chat_log_path, info_path).offset_hours


def describe_fvtt_tz(chat_log_path: Path, info_path: Path) -> TzResolution:
    """То же, что :func:`detect_fvtt_tz_offset`, но с происхождением офсета.

    Импорт ``sources`` — локальный, внутри функции. Не из-за слоёв
    (``core`` → ``sources`` разрешён, см. ARCHITECTURE.md, и
    ``core.pipeline`` импортирует их на уровне модуля), а чтобы UI не
    тянул парсеры на старте ради экрана, который может и не открыться.
    """
    from sources.game_log.fvtt_chat import (
        EMPTY_LOG_RESOLUTION,
        parse_fvtt_log,
        parse_info_start_time,
        resolve_tz_offset,
    )

    entries = parse_fvtt_log(chat_log_path)
    if not entries:
        # ``info.txt`` намеренно не читаем: для пустого лога офсет ни на
        # что не влияет, а эта ветка исторически не падала на битом
        # ``info.txt`` — Timeline-экран на такой сессии должен рисоваться.
        return EMPTY_LOG_RESOLUTION

    rec_start = parse_info_start_time(info_path)
    return resolve_tz_offset(entries, rec_start)

"""FVTT chat helper functions for the UI layer.

Тонкий shim поверх ``sources.game_log.fvtt_chat`` для случаев, когда
UI хочет автодетектить timezone ДО запуска pipeline (и, соответственно,
не может импортировать ``sources`` напрямую — см. layer rules в
``ARCHITECTURE.md``).

Всё тяжёлое (fvtt lexer, tz search) делегируется в ``sources``; здесь
только простая обвязка с публичным API.
"""

from __future__ import annotations

from pathlib import Path


def detect_fvtt_tz_offset(chat_log_path: Path, info_path: Path) -> float:
    """Автодетект UTC offset по первому chat entry и Craig info.txt.

    Возвращает offset в часах (может быть отрицательным). Бросает
    ``ValueError`` если ``info.txt`` не содержит ``Start time:`` строку.
    Если chat log пуст — возвращает ``0.0``.
    """
    from sources.game_log.fvtt_chat import (
        guess_tz_offset,
        parse_fvtt_log,
        parse_info_start_time,
    )

    entries = parse_fvtt_log(chat_log_path)
    if not entries:
        return 0.0
    rec_start = parse_info_start_time(info_path)
    return guess_tz_offset(entries, rec_start)
